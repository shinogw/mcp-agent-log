#!/bin/bash
# メンバーの認証情報を設定するスクリプト
# 使い方: ./setup-auth.sh <username> <password>

set -e

USERNAME=${1:-member}
PASSWORD=${2}

if [ -z "$PASSWORD" ]; then
    echo "Usage: $0 <username> <password>"
    echo "Example: $0 alice secret123"
    exit 1
fi

HTPASSWD_FILE="./nginx/.htpasswd"

# openssl で htpasswd エントリを生成（apache2-utils 不要）
HASH=$(openssl passwd -apr1 "$PASSWORD")

if [ -f "$HTPASSWD_FILE" ]; then
    # 既存ユーザーを更新 or 追加
    if grep -q "^${USERNAME}:" "$HTPASSWD_FILE"; then
        sed -i "s|^${USERNAME}:.*|${USERNAME}:${HASH}|" "$HTPASSWD_FILE"
        echo "Updated user: $USERNAME"
    else
        echo "${USERNAME}:${HASH}" >> "$HTPASSWD_FILE"
        echo "Added user: $USERNAME"
    fi
else
    echo "${USERNAME}:${HASH}" > "$HTPASSWD_FILE"
    echo "Created $HTPASSWD_FILE with user: $USERNAME"
fi
