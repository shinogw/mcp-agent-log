# mcp-agent-log

複数のAIエージェント間で会話ログを共有するMCPサーバー。

Claude Codeなど複数のエージェントが同じプロジェクトで協業するとき、各エージェントの会話履歴・決定事項をチーム全体で参照できるようにします。

## アーキテクチャ

```
[Agent A1] ──write──> [MCP Log Server] <──read── [Agent B1]
[Agent B1] ──write──> [MCP Log Server] <──read── [Agent A1]
                              │
                         [SQLite DB]
                              │
                     Human が閲覧・検索
```

## インストール

```bash
git clone https://github.com/shinogw/mcp-agent-log.git
cd mcp-agent-log
pip install -e .
```

## Claude Code への登録

`.claude/mcp.json` または `~/.claude/claude_desktop_config.json` に追加:

```json
{
  "mcpServers": {
    "agent-log": {
      "command": "python3",
      "args": ["/path/to/mcp-agent-log/server.py"]
    }
  }
}
```

または Claude Code CLI から:

```bash
claude mcp add agent-log -- python3 /path/to/mcp-agent-log/server.py
```

## 利用できるツール

### `log_message`
会話の要点・決定事項をログに記録する。

| 引数 | 型 | 説明 |
|---|---|---|
| `agent` | string | エージェント名 (例: "A1") |
| `human` | string | ヒューマン名 (例: "HumanA") |
| `content` | string | 記録する内容 |
| `tags` | list[string] | タグのリスト (省略可) |

### `get_recent_logs`
最近のログを取得する。

| 引数 | 型 | 説明 |
|---|---|---|
| `n` | int | 取得件数（デフォルト20） |
| `agent` | string | エージェントで絞り込み（省略可） |

### `get_logs_by_tag`
タグでログを検索する。

| 引数 | 型 | 説明 |
|---|---|---|
| `tag` | string | 検索するタグ |

### `search_logs`
キーワードでログ本文を全文検索する。

| 引数 | 型 | 説明 |
|---|---|---|
| `keyword` | string | 検索キーワード |

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

`agent_logs.db`（SQLite）がサーバーと同じディレクトリに作成されます。
複数マシンで共有する場合は、このファイルをNFS・S3・共有ストレージに置くか、サーバーを1台のマシンで稼働させてネットワーク越しにアクセスしてください。
