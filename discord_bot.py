"""
Discord Bot
- DBに登録された全チャンネルのメッセージを自動でDBに記録
- Bot自身のメッセージは記録しない（無限ループ防止）
- ✅ リアクションで記録完了を通知
"""

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path

import discord

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

_data_dir = Path(__file__).parent / "data"
DB_PATH = _data_dir / "agent_logs.db"


def get_registered_channel_ids() -> set[int]:
    """DBに登録済みのチャンネルIDセットを返す"""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT channel_id FROM channels").fetchall()
        conn.close()
        return {row[0] for row in rows}
    except Exception:
        return set()


def save_to_db(human: str, content: str, channel_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO logs (agent, human, content, tags, channel_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("discord", human, content, json.dumps(["discord"]), channel_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


@client.event
async def on_ready():
    print(f"Discord Bot ready: {client.user}")
    channel_ids = get_registered_channel_ids()
    print(f"監視中のチャンネル: {channel_ids if channel_ids else '(未登録)'}")


@client.event
async def on_message(message: discord.Message):
    # Bot自身のメッセージは無視
    if message.author.bot:
        return

    # DBに登録済みのチャンネルのみ処理
    registered = get_registered_channel_ids()
    if message.channel.id not in registered:
        return

    save_to_db(message.author.display_name, message.content, message.channel.id)

    # ✅ リアクションで記録完了を通知
    await message.add_reaction("✅")


if __name__ == "__main__":
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN が設定されていません")
    client.run(token)
