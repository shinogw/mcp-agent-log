# mcp-agent-log

複数のAIエージェント間で会話ログを共有するMCPサーバー。

チームで複数のAIエージェント（Claude Codeなど）が協業するとき、各エージェントの会話履歴・決定事項を全員が参照・検索できます。

## アーキテクチャ

```
[Agent A1] ──HTTP/SSE──> [mcp-agent-log] <──HTTP/SSE── [Agent B1]
                                │
                           agent_logs.db
                                │
                      Human が閲覧・検索
```

## クイックスタート

```bash
git clone https://github.com/shinogw/mcp-agent-log.git
cd mcp-agent-log

# 1. メンバーの認証情報を設定
chmod +x setup-auth.sh
./setup-auth.sh alice password123
./setup-auth.sh bob  password456   # メンバーを追加する場合

# 2. 起動
docker compose up -d
```

これで `http://localhost/sse`（Basic認証あり）でサーバーが起動します。

## Claude Code への登録

```bash
claude mcp add agent-log \
  --transport sse \
  --url http://YOUR_HOST/sse \
  --header "Authorization: Basic $(echo -n 'USERNAME:PASSWORD' | base64)"
```

## メンバーの追加・削除

```bash
# 追加
./setup-auth.sh carol newpassword

# 削除（.htpasswd を直接編集）
sed -i '/^carol:/d' nginx/.htpasswd

# 再起動不要（nginx が自動で読み直す）
```

## 利用できるツール

| ツール | 説明 |
|---|---|
| `log_message` | 会話の要点・決定事項を記録する |
| `get_recent_logs` | 最近のログを取得する（エージェント絞り込み可） |
| `get_logs_by_tag` | タグでログを検索する |
| `search_logs` | キーワードで全文検索する |

### `log_message` の引数

| 引数 | 型 | 説明 |
|---|---|---|
| `agent` | string | エージェント名 (例: "A1") |
| `human` | string | ヒューマン名 (例: "HumanA") |
| `content` | string | 記録する内容 |
| `tags` | list[string] | タグのリスト（省略可） |

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

## ログの保存場所

`data/agent_logs.db`（SQLite）に保存されます。`docker compose` を使う場合は `./data/` ディレクトリにマウントされます。

## Docker なしで動かす場合

```bash
pip install -e .
python server.py --host 0.0.0.0 --port 8600
```
