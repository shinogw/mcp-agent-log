#!/bin/bash
# local_agent.py をMacのlaunchdに登録して常駐化するセットアップスクリプト
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USERNAME="$(whoami)"
PLIST_NAME="com.local-agent"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$SCRIPT_DIR/logs"

echo "=== local_agent セットアップ ==="
echo "ユーザー: $USERNAME"
echo "スクリプト: $SCRIPT_DIR/local_agent.py"

# .env.local の確認
if [ ! -f "$SCRIPT_DIR/.env.local" ]; then
    echo ""
    echo "⚠️  .env.local が見つかりません。"
    echo "   cp $SCRIPT_DIR/.env.local.example $SCRIPT_DIR/.env.local"
    echo "   を実行して設定を記入してください。"
    exit 1
fi

# python3 / claude のパス確認
PYTHON_PATH="$(which python3)"
CLAUDE_PATH="$(which claude 2>/dev/null || echo '')"

echo "Python: $PYTHON_PATH"
echo "Claude: ${CLAUDE_PATH:-（未検出）}"

if [ -z "$CLAUDE_PATH" ]; then
    echo "⚠️  claude CLI が PATH にありません。インストールを確認してください。"
fi

# ログディレクトリ作成
mkdir -p "$LOG_DIR"

# plist 生成
cat > "$PLIST_DST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_NAME}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_PATH}</string>
    <string>${SCRIPT_DIR}/local_agent.py</string>
  </array>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/local_agent.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/local_agent_err.log</string>

  <key>KeepAlive</key>
  <true/>
  <key>RunAtLoad</key>
  <true/>

  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:$(dirname "$PYTHON_PATH")</string>
  </dict>
</dict>
</plist>
EOF

echo "✅ plist 生成: $PLIST_DST"

# 既存のエージェントをアンロード（エラーは無視）
launchctl unload "$PLIST_DST" 2>/dev/null || true

# ロード
launchctl load "$PLIST_DST"
echo "✅ launchd に登録完了"

echo ""
echo "確認コマンド:"
echo "  launchctl list | grep local-agent   # 稼働確認"
echo "  tail -f $LOG_DIR/local_agent.log    # ログ確認"
echo ""
echo "停止: launchctl unload $PLIST_DST"
echo "再起動: launchctl unload $PLIST_DST && launchctl load $PLIST_DST"
