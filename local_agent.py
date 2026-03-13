"""
Local Agent — Mac常駐スクリプト
Discordメッセージを受信 → claude -p でローカル実行 → Webhook で返信

使い方:
  1. .env.local に設定を書く
  2. python local_agent.py
  3. Discord の対象チャンネルにメッセージを送る → claude が応答

要件:
  - claude CLI が認証済み（claude auth login済み）
  - discord.py, python-dotenv インストール済み
"""

import asyncio
import os
import subprocess
import textwrap
from pathlib import Path

import discord
import httpx
from dotenv import load_dotenv

# .env.local を優先して読み込む
_here = Path(__file__).parent
load_dotenv(_here / ".env.local", override=True)
load_dotenv(_here / ".env")

# ── 設定 ──────────────────────────────────────────────
DISCORD_BOT_TOKEN  = os.environ["DISCORD_BOT_TOKEN"]
AGENT_CHANNEL_ID   = int(os.environ["AGENT_CHANNEL_ID"])   # 自分専用チャンネルID
AGENT_WEBHOOK_URL  = os.environ["AGENT_WEBHOOK_URL"]       # 同チャンネルのWebhook URL
WORK_DIR           = os.environ.get("AGENT_WORK_DIR", str(Path.home()))
CLAUDE_TOOLS       = os.environ.get(
    "AGENT_CLAUDE_TOOLS",
    "Read,Write,Edit,Bash,Glob,Grep,LS"
)
CLAUDE_MAX_TOKENS  = int(os.environ.get("AGENT_MAX_TURNS", "10"))
BOT_NAME           = os.environ.get("AGENT_BOT_NAME", "Claude Agent")
DISCORD_MSG_LIMIT  = 1900  # Discord の2000文字制限より余裕を持たせる
# ──────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# メッセージキュー（逐次処理用）
_queue: asyncio.Queue = asyncio.Queue()


async def run_claude(prompt: str) -> str:
    """claude -p をサブプロセスで非同期実行して結果を返す"""
    cmd = [
        "claude",
        "-p", prompt,
        "--allowedTools", CLAUDE_TOOLS,
        "--max-turns", str(CLAUDE_MAX_TOKENS),
        "--output-format", "text",
    ]
    loop = asyncio.get_event_loop()
    proc = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=WORK_DIR,
        ),
    )
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if proc.returncode != 0 and not stdout:
        return f"エラー (exit {proc.returncode}):\n```\n{stderr[:800]}\n```"

    result = stdout or "(出力なし)"
    if stderr:
        result += f"\n\n---\n*stderr:* `{stderr[:300]}`"
    return result


async def post_to_webhook(content: str):
    """長いメッセージを分割してWebhookに投稿"""
    chunks = textwrap.wrap(content, DISCORD_MSG_LIMIT, replace_whitespace=False)
    if not chunks:
        chunks = ["(空の応答)"]

    async with httpx.AsyncClient(timeout=10) as http:
        for chunk in chunks:
            await http.post(AGENT_WEBHOOK_URL, json={
                "content": chunk,
                "username": BOT_NAME,
            })


async def worker():
    """キューからメッセージを1件ずつ取り出して逐次処理する"""
    while True:
        message, user, content = await _queue.get()
        try:
            print(f"[local_agent] 処理開始 [{user}]: {content[:100]}")
            queue_size = _queue.qsize()
            if queue_size > 0:
                await post_to_webhook(f"*（{queue_size}件待機中）*")

            prompt = f"[{user}からの指示]:\n{content}"
            reply  = await run_claude(prompt)

            await message.add_reaction("✅")
            await message.remove_reaction("⚙️", client.user)
            await post_to_webhook(f"**[{user}への返答]**\n{reply}")
        except Exception as e:
            print(f"[local_agent] エラー: {e}")
            await post_to_webhook(f"エラーが発生しました: {e}")
        finally:
            _queue.task_done()


@client.event
async def on_ready():
    print(f"[local_agent] Bot ready: {client.user}")
    print(f"  監視チャンネル: {AGENT_CHANNEL_ID}")
    print(f"  作業ディレクトリ: {WORK_DIR}")
    print(f"  許可ツール: {CLAUDE_TOOLS}")
    # バックグラウンドワーカー起動
    asyncio.create_task(worker())


@client.event
async def on_message(message: discord.Message):
    # Bot 自身・他チャンネルは無視
    if message.author.bot:
        return
    if message.channel.id != AGENT_CHANNEL_ID:
        return

    user    = message.author.display_name
    content = message.content.strip()
    if not content:
        return

    # キューに積む（受信確認リアクション）
    await message.add_reaction("⚙️")
    queue_pos = _queue.qsize() + 1
    if queue_pos > 1:
        await post_to_webhook(f"*{user}さんのメッセージを受信（{queue_pos}番目に待機中）*")
    print(f"[local_agent] キュー追加 [{user}] (待機:{queue_pos}件)")
    await _queue.put((message, user, content))


if __name__ == "__main__":
    client.run(DISCORD_BOT_TOKEN)
