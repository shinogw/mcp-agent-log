"""
Discord Bot
- DBに登録された全チャンネルのメッセージを自動でDBに記録
- ANTHROPIC_API_KEY が設定されている場合、Claude が返信
- Bot自身のメッセージは記録しない（無限ループ防止）
- ✅ リアクションで記録完了を通知
"""

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import discord
import httpx

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

_data_dir = Path(__file__).parent / "data"
DB_PATH = _data_dir / "agent_logs.db"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def get_registered_channels() -> dict[int, str]:
    """DBに登録済みの {channel_id: webhook_url} を返す"""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT channel_id, webhook_url FROM channels").fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}
    except Exception:
        return {}


def get_recent_channel_logs(channel_id: int, n: int = 10) -> list[dict]:
    """チャンネルの直近ログを取得（会話コンテキスト用）"""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT agent, human, content FROM logs WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
            (channel_id, n),
        ).fetchall()
        conn.close()
        return [{"agent": r[0], "human": r[1], "content": r[2]} for r in reversed(rows)]
    except Exception:
        return []


def save_to_db(human: str, content: str, channel_id: int, agent: str = "discord"):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO logs (agent, human, content, tags, channel_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (agent, human, content, json.dumps([agent]), channel_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


async def call_claude(human: str, message: str, history: list[dict]) -> str:
    """Claude API を呼んで返答を生成する"""
    # 会話履歴をメッセージリストに変換
    messages = []
    for log in history[:-1]:  # 最新のメッセージは別途追加するので除く
        if log["agent"] == "discord":
            messages.append({"role": "user", "content": f"[{log['human']}]: {log['content']}"})
        elif log["agent"] == "claude-bot":
            messages.append({"role": "assistant", "content": log["content"]})

    # 今回のメッセージを追加
    messages.append({"role": "user", "content": f"[{human}]: {message}"})

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 1024,
                "system": "あなたはDiscordチャンネルで会話をサポートするAIアシスタントです。簡潔に日本語で返答してください。",
                "messages": messages,
            },
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


async def post_to_webhook(webhook_url: str, content: str):
    """Discord Webhook に投稿する"""
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            await http.post(webhook_url, json={"content": content, "username": "Claude"})
    except Exception as e:
        print(f"Webhook投稿エラー: {e}")


@client.event
async def on_ready():
    print(f"Discord Bot ready: {client.user}")
    channels = get_registered_channels()
    print(f"監視中のチャンネル: {list(channels.keys()) if channels else '(未登録)'}")
    print(f"Claude API: {'有効' if ANTHROPIC_API_KEY else '無効（記録のみ）'}")


@client.event
async def on_message(message: discord.Message):
    # Bot自身のメッセージは無視
    if message.author.bot:
        return

    registered = get_registered_channels()
    if message.channel.id not in registered:
        return

    channel_id = message.channel.id
    human = message.author.display_name
    content = message.content

    # DBに記録
    save_to_db(human, content, channel_id)
    await message.add_reaction("✅")

    # Claude API が有効なら返信
    if ANTHROPIC_API_KEY:
        try:
            history = get_recent_channel_logs(channel_id, n=10)
            reply = await call_claude(human, content, history)

            # 返信をDBに記録
            save_to_db("Claude", reply, channel_id, agent="claude-bot")

            # Webhook で返信
            webhook_url = registered[channel_id]
            await post_to_webhook(webhook_url, reply)
        except Exception as e:
            print(f"Claude返信エラー: {e}")


if __name__ == "__main__":
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN が設定されていません")
    client.run(token)
