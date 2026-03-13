"""
Discord Bot
- 特定チャンネル（例: #cc-agent）のメッセージを自動でDBに記録
- エージェントからの通知も同じチャンネルに投稿される（Webhook経由）
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

# メンバーの書き込み・エージェントの通知を1つのチャンネルで行う
LOG_CHANNEL_ID = int(os.environ["DISCORD_LOG_CHANNEL_ID"])


def save_to_db(human: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO logs (agent, human, content, tags, created_at) VALUES (?, ?, ?, ?, ?)",
        ("discord", human, content, json.dumps(["discord"]), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


@client.event
async def on_ready():
    print(f"Discord Bot ready: {client.user}")


@client.event
async def on_message(message: discord.Message):
    # Bot自身のメッセージは無視
    if message.author.bot:
        return

    # 記録対象チャンネルのみ処理
    if message.channel.id != LOG_CHANNEL_ID:
        return

    save_to_db(message.author.display_name, message.content)

    # ✅ リアクションで記録完了を通知
    await message.add_reaction("✅")


if __name__ == "__main__":
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN が設定されていません")
    client.run(token)
