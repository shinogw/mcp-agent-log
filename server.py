"""
MCP Agent Log Server
複数のAIエージェント間で会話ログを共有するMCPサーバー
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
import sqlite3
import json
from datetime import datetime
from pathlib import Path

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


@app.tool()
async def log_message(agent: str, human: str, content: str, tags: list[str] = []) -> dict:
    """
    会話の要点をログに記録する

    Args:
        agent: エージェント名 (例: "A1", "B1")
        human: ヒューマン名 (例: "HumanA", "HumanB")
        content: 記録する内容（決定事項・進捗・メモなど）
        tags: タグのリスト (例: ["設計決定", "認証"])
    """
    conn = get_conn()
    conn.execute(
        "INSERT INTO logs (agent, human, content, tags, created_at) VALUES (?, ?, ?, ?, ?)",
        (agent, human, content, json.dumps(tags, ensure_ascii=False), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return {"status": "logged", "agent": agent, "human": human}


@app.tool()
async def get_recent_logs(n: int = 20, agent: str = None) -> list[dict]:
    """
    最近のログを取得する

    Args:
        n: 取得件数（デフォルト20件）
        agent: 特定のエージェントで絞り込む（省略で全エージェント）
    """
    conn = get_conn()
    if agent:
        rows = conn.execute(
            "SELECT * FROM logs WHERE agent = ? ORDER BY id DESC LIMIT ?",
            (agent, n)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?",
            (n,)
        ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "agent": r["agent"],
            "human": r["human"],
            "content": r["content"],
            "tags": json.loads(r["tags"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@app.tool()
async def get_logs_by_tag(tag: str) -> list[dict]:
    """
    タグでログを検索する

    Args:
        tag: 検索するタグ (例: "設計決定")
    """
    conn = get_conn()
    rows = conn.execute(
        'SELECT * FROM logs WHERE tags LIKE ? ORDER BY id DESC',
        (f'%"{tag}"%',)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "agent": r["agent"],
            "human": r["human"],
            "content": r["content"],
            "tags": json.loads(r["tags"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@app.tool()
async def search_logs(keyword: str) -> list[dict]:
    """
    キーワードでログ本文を全文検索する

    Args:
        keyword: 検索キーワード
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM logs WHERE content LIKE ? ORDER BY id DESC",
        (f"%{keyword}%",)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "agent": r["agent"],
            "human": r["human"],
            "content": r["content"],
            "tags": json.loads(r["tags"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


if __name__ == "__main__":
    import asyncio
    init_db()
    asyncio.run(stdio_server(app))
