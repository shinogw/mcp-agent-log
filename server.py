"""
MCP Agent Log Server
複数のAIエージェント間で会話ログを共有するMCPサーバー（HTTP/SSE対応）
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

app = Server("agent-log")

DB_PATH = Path(__file__).parent / "agent_logs.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            human TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _row_to_dict(r) -> dict:
    return {
        "id": r["id"],
        "agent": r["agent"],
        "human": r["human"],
        "content": r["content"],
        "tags": json.loads(r["tags"]),
        "created_at": r["created_at"],
    }


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="log_message",
            description="会話の要点・決定事項をログに記録する",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent":   {"type": "string", "description": "エージェント名 (例: A1)"},
                    "human":   {"type": "string", "description": "ヒューマン名 (例: HumanA)"},
                    "content": {"type": "string", "description": "記録する内容"},
                    "tags":    {"type": "array", "items": {"type": "string"}, "description": "タグのリスト"},
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
                    "n":     {"type": "integer", "description": "取得件数（デフォルト20）"},
                    "agent": {"type": "string",  "description": "エージェントで絞り込み（省略で全件）"},
                },
            },
        ),
        Tool(
            name="get_logs_by_tag",
            description="タグでログを検索する",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "検索するタグ"},
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
                    "keyword": {"type": "string", "description": "検索キーワード"},
                },
                "required": ["keyword"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "log_message":
        conn = get_conn()
        conn.execute(
            "INSERT INTO logs (agent, human, content, tags, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                arguments["agent"],
                arguments["human"],
                arguments["content"],
                json.dumps(arguments.get("tags", []), ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        result = {"status": "logged", "agent": arguments["agent"], "human": arguments["human"]}

    elif name == "get_recent_logs":
        conn = get_conn()
        n = arguments.get("n", 20)
        agent = arguments.get("agent")
        if agent:
            rows = conn.execute(
                "SELECT * FROM logs WHERE agent = ? ORDER BY id DESC LIMIT ?", (agent, n)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        conn.close()
        result = [_row_to_dict(r) for r in rows]

    elif name == "get_logs_by_tag":
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM logs WHERE tags LIKE ? ORDER BY id DESC",
            (f'%"{arguments["tag"]}"%',),
        ).fetchall()
        conn.close()
        result = [_row_to_dict(r) for r in rows]

    elif name == "search_logs":
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM logs WHERE content LIKE ? ORDER BY id DESC",
            (f'%{arguments["keyword"]}%',),
        ).fetchall()
        conn.close()
        result = [_row_to_dict(r) for r in rows]

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
