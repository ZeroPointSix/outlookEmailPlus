#!/usr/bin/env bash
# 重建 Daytona 沙箱 outlookmailplus（基于快照）。
# 用法: bash daytona/sandbox.sh
# 前置: 快照已存在（先运行 snapshot.sh）；密钥见 daytona/.env.local 或环境变量。
set -euo pipefail

# daytona CLI 依赖 HOME；本机可能未设置
export HOME="${HOME:-/root}"

SNAPSHOT_NAME="${SNAPSHOT_NAME:-outlookmailplus}"
SANDBOX_NAME="${SANDBOX_NAME:-outlookmailplus}"
REGION="${DAYTONA_REGION:-us}"
AUTO_STOP="${AUTO_STOP:-0}"   # 0 = 不自动停止（UAT 常驻）

# 从 daytona/.env.local 加载密钥（该文件不入库）
ENV_FILE="$(dirname "${BASH_SOURCE[0]}")/.env.local"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

if [ -z "${OEMP_SECRET_KEY:-}" ]; then
  echo "缺少 OEMP_SECRET_KEY（环境变量或 daytona/.env.local）"
  exit 1
fi
if [ -z "${OEMP_LOGIN_PASSWORD:-}" ]; then
  echo "缺少 OEMP_LOGIN_PASSWORD（环境变量或 daytona/.env.local）"
  exit 1
fi

daytona sandbox delete "$SANDBOX_NAME" >/dev/null 2>&1 || true

daytona sandbox create \
  --name "$SANDBOX_NAME" \
  --snapshot "$SNAPSHOT_NAME" \
  --public \
  --target "$REGION" \
  --auto-stop "$AUTO_STOP" \
  -e SECRET_KEY="$OEMP_SECRET_KEY" \
  -e LOGIN_PASSWORD="$OEMP_LOGIN_PASSWORD" \
  -e HOST=0.0.0.0 \
  -e PORT=5000 \
  -e SCHEDULER_AUTOSTART=true \
  -e ALLOW_LOGIN_PASSWORD_CHANGE=false

echo "沙箱 $SANDBOX_NAME 已创建（snapshot: $SNAPSHOT_NAME）"
