# mcp-agent-log

複数のAIエージェント間で会話ログを共有するMCPサーバー。

Claude Codeなど複数のエージェントが同じプロジェクトで協業するとき、各エージェントの会話履歴・決定事項をチーム全体で参照できるようにします。

## アーキテクチャ

```
[Agent A1] ──HTTP/SSE──> [MCP Log Server on VPS] <──HTTP/SSE── [Agent B1]
                                    │
                               agent_logs.db
                              （VPS上に1つだけ）
                                    │
                          Human が閲覧・検索（全員）
```

- **コード**: GitHub（パブリック）で管理
- **ログDB**: VPS上でプライベート管理（コラボレーターのみアクセス可）

## 利用できるツール

| ツール | 説明 |
|---|---|
| `log_message` | 会話の要点・決定事項を記録する |
| `get_recent_logs` | 最近のログを取得する（エージェント絞り込み可） |
| `get_logs_by_tag` | タグでログを検索する |
| `search_logs` | キーワードで全文検索する |

## VPSへのデプロイ（サーバー管理者向け）

```bash
# 1. clone & セットアップ
git clone https://github.com/shinogw/mcp-agent-log.git /opt/mcp-agent-log
cd /opt/mcp-agent-log
python3 -m venv .venv
.venv/bin/pip install -e .

# 2. systemd サービス登録
cp mcp-agent-log.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mcp-agent-log

# 3. nginx Basic認証ユーザー追加
htpasswd -c /etc/nginx/.htpasswd-mcp <username>
```

### nginx 設定（抜粋）

```nginx
location /mcp/ {
    auth_basic "MCP Agent Log";
    auth_basic_user_file /etc/nginx/.htpasswd-mcp;

    proxy_pass http://127.0.0.1:8600/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_buffering off;        # SSE に必須
    proxy_cache off;
    proxy_read_timeout 3600s;   # SSE の長時間接続を維持
}
```

## Claude Code への登録（メンバー向け）

```bash
claude mcp add agent-log \
  --transport sse \
  --url https://<your-domain>/mcp/sse \
  --header "Authorization: Basic $(echo -n '<user>:<password>' | base64)"
```

または `.claude/mcp.json` に直接記述:

```json
{
  "mcpServers": {
    "agent-log": {
      "transport": "sse",
      "url": "https://<your-domain>/mcp/sse",
      "headers": {
        "Authorization": "Basic <base64(user:password)>"
      }
    }
  }
}
```

## エージェントへの指示例

```
# 作業開始時
"get_recent_logs で昨日の状況を確認してから作業を始めてください"

# 重要な決定をしたとき
"この設計決定を log_message で記録してください。
 agent: A1, human: HumanA,
 content: 認証方式をJWTからセッションCookieに変更。理由: モバイル対応のため
 tags: [設計決定, 認証]"

# 他のエージェントの状況確認
"get_recent_logs で agent=B1 の最新状況を確認してください"

# 過去の決定を検索
"search_logs で '認証' に関する過去の決定を確認してください"
```

## ローカル動作確認

```bash
pip install -e .
python server.py --host 127.0.0.1 --port 8600
```
