"""
MCP Agent Log Server
複数のAIエージェント間で会話ログを共有するMCPサーバー（HTTP/SSE対応）
チャンネル単位でマルチテナント対応
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import httpx
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

app = Server("agent-log")

_data_dir = Path(__file__).parent / "data"
_data_dir.mkdir(exist_ok=True)
DB_PATH = _data_dir / "agent_logs.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            channel_id INTEGER PRIMARY KEY,
            webhook_url TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            human TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            channel_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    # 既存DBへのマイグレーション（channel_idカラムがなければ追加）
    try:
        conn.execute("ALTER TABLE logs ADD COLUMN channel_id INTEGER")
    except sqlite3.OperationalError:
        pass

    # .env に DISCORD_LOG_CHANNEL_ID / DISCORD_NOTIFY_WEBHOOK_URL があれば自動登録
    channel_id_env  = os.environ.get("DISCORD_LOG_CHANNEL_ID")
    webhook_url_env = os.environ.get("DISCORD_NOTIFY_WEBHOOK_URL")
    if channel_id_env and webhook_url_env:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO channels (channel_id, webhook_url, name, created_at) VALUES (?, ?, ?, ?)",
                (int(channel_id_env), webhook_url_env, "default", datetime.now().isoformat()),
            )
        except Exception:
            pass

    conn.commit()
    conn.close()


def _row_to_dict(r) -> dict:
    d = {
        "id": r["id"],
        "agent": r["agent"],
        "human": r["human"],
        "content": r["content"],
        "tags": json.loads(r["tags"]),
        "created_at": r["created_at"],
    }
    if r["channel_id"]:
        d["channel_id"] = r["channel_id"]
    return d


def _get_webhook_url(channel_id: int) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT webhook_url FROM channels WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    conn.close()
    return row["webhook_url"] if row else None


async def _post_to_discord(webhook_url: str, content: str):
    """Discord の Webhook に通知を送る（失敗しても無視）"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(webhook_url, json={"content": content})
    except Exception:
        pass


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="log_message",
            description="会話の要点・決定事項をログに記録する。notify=True でDiscordにも通知。channel_id を指定すると対象チャンネルに返信。",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent":      {"type": "string",  "description": "エージェント名 (例: A1)"},
                    "human":      {"type": "string",  "description": "ヒューマン名 (例: HumanA)"},
                    "content":    {"type": "string",  "description": "記録する内容"},
                    "tags":       {"type": "array",   "items": {"type": "string"}, "description": "タグのリスト"},
                    "notify":     {"type": "boolean", "description": "True にすると Discord にも投稿される"},
                    "channel_id": {"type": "integer", "description": "通知先DiscordチャンネルのスノーフレークID"},
                },
                "required": ["agent", "human", "content"],
            },
        ),
        Tool(
            name="get_recent_logs",
            description="最近のログを取得する",
            inputSchema={
                "type": "object",
                "properties": {
                    "n":          {"type": "integer", "description": "取得件数（デフォルト20）"},
                    "agent":      {"type": "string",  "description": "エージェントで絞り込み（省略で全件）"},
                    "channel_id": {"type": "integer", "description": "チャンネルで絞り込み（省略で全件）"},
                },
            },
        ),
        Tool(
            name="get_logs_by_tag",
            description="タグでログを検索する",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag":        {"type": "string",  "description": "検索するタグ"},
                    "channel_id": {"type": "integer", "description": "チャンネルで絞り込み（省略で全件）"},
                },
                "required": ["tag"],
            },
        ),
        Tool(
            name="search_logs",
            description="キーワードでログ本文を全文検索する",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword":    {"type": "string",  "description": "検索キーワード"},
                    "channel_id": {"type": "integer", "description": "チャンネルで絞り込み（省略で全件）"},
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="register_channel",
            description="Discordチャンネルを登録する（管理者用）",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id":  {"type": "integer", "description": "DiscordチャンネルのスノーフレークID"},
                    "webhook_url": {"type": "string",  "description": "チャンネルのWebhook URL"},
                    "name":        {"type": "string",  "description": "チャンネルの識別名 (例: project-a)"},
                },
                "required": ["channel_id", "webhook_url", "name"],
            },
        ),
        Tool(
            name="list_channels",
            description="登録済みチャンネル一覧を取得する",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "log_message":
        agent      = arguments["agent"]
        human      = arguments["human"]
        content    = arguments["content"]
        tags       = arguments.get("tags", [])
        notify     = arguments.get("notify", False)
        channel_id = arguments.get("channel_id")

        conn = get_conn()
        conn.execute(
            "INSERT INTO logs (agent, human, content, tags, channel_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (agent, human, content, json.dumps(tags, ensure_ascii=False), channel_id, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        if notify and channel_id:
            webhook_url = _get_webhook_url(channel_id)
            if webhook_url:
                tag_str = " ".join(f"`{t}`" for t in tags) if tags else ""
                discord_msg = f"@here **[{agent} → {human}]**\n{content}"
                if tag_str:
                    discord_msg += f"\nタグ: {tag_str}"
                await _post_to_discord(webhook_url, discord_msg)

        result = {"status": "logged", "agent": agent, "human": human, "channel_id": channel_id, "notified": notify}

    elif name == "get_recent_logs":
        conn = get_conn()
        n          = arguments.get("n", 20)
        agent      = arguments.get("agent")
        channel_id = arguments.get("channel_id")

        conditions, params = [], []
        if agent:
            conditions.append("agent = ?")
            params.append(agent)
        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(n)
        rows = conn.execute(
            f"SELECT * FROM logs {where} ORDER BY id DESC LIMIT ?", params
        ).fetchall()
        conn.close()
        result = [_row_to_dict(r) for r in rows]

    elif name == "get_logs_by_tag":
        conn = get_conn()
        channel_id = arguments.get("channel_id")
        if channel_id:
            rows = conn.execute(
                "SELECT * FROM logs WHERE tags LIKE ? AND channel_id = ? ORDER BY id DESC",
                (f'%"{arguments["tag"]}"%', channel_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM logs WHERE tags LIKE ? ORDER BY id DESC",
                (f'%"{arguments["tag"]}"%',),
            ).fetchall()
        conn.close()
        result = [_row_to_dict(r) for r in rows]

    elif name == "search_logs":
        conn = get_conn()
        channel_id = arguments.get("channel_id")
        if channel_id:
            rows = conn.execute(
                "SELECT * FROM logs WHERE content LIKE ? AND channel_id = ? ORDER BY id DESC",
                (f'%{arguments["keyword"]}%', channel_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM logs WHERE content LIKE ? ORDER BY id DESC",
                (f'%{arguments["keyword"]}%',),
            ).fetchall()
        conn.close()
        result = [_row_to_dict(r) for r in rows]

    elif name == "register_channel":
        channel_id  = arguments["channel_id"]
        webhook_url = arguments["webhook_url"]
        ch_name     = arguments["name"]
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO channels (channel_id, webhook_url, name, created_at) VALUES (?, ?, ?, ?)",
            (channel_id, webhook_url, ch_name, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        result = {"status": "registered", "channel_id": channel_id, "name": ch_name}

    elif name == "list_channels":
        conn = get_conn()
        rows = conn.execute("SELECT channel_id, name, created_at FROM channels ORDER BY created_at DESC").fetchall()
        conn.close()
        result = [{"channel_id": r["channel_id"], "name": r["name"], "created_at": r["created_at"]} for r in rows]

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


def create_starlette_app(mcp_server: Server) -> Starlette:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8600)
    args = parser.parse_args()

    init_db()
    starlette_app = create_starlette_app(app)
    uvicorn.run(starlette_app, host=args.host, port=args.port)
