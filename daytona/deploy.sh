#!/usr/bin/env bash
# 全量刷新部署：快照 -> 沙箱 -> 启动应用 -> 输出预览地址。
# 用法: bash daytona/deploy.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$DIR/snapshot.sh"
bash "$DIR/sandbox.sh"
bash "$DIR/app.sh" start

echo "部署完成"
