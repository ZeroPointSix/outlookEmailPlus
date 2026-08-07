#!/usr/bin/env bash
# 重建 Daytona 快照 outlookmailplus。
# 用法: bash daytona/snapshot.sh
# 前置: 已安装 daytona CLI 并登录；或提供 DAYTONA_API_KEY。
set -euo pipefail

# daytona CLI 依赖 HOME；本机可能未设置
export HOME="${HOME:-/root}"

SNAPSHOT_NAME="${SNAPSHOT_NAME:-outlookmailplus}"
REGION="${DAYTONA_REGION:-us}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"

if ! command -v daytona >/dev/null 2>&1; then
  echo "缺少 daytona CLI，请先安装：https://www.daytona.io/docs/en/tools/cli"
  exit 1
fi

# 未配置凭据时自动登录（CI 使用）
if [ -n "${DAYTONA_API_KEY:-}" ]; then
  daytona login --api-key "$DAYTONA_API_KEY" >/dev/null 2>&1
fi

# 快照已存在则先删除，保证同名重建
daytona snapshot delete "$SNAPSHOT_NAME" >/dev/null 2>&1 || true

# 从仓库根目录的 Dockerfile 构建快照。
# --cpu/--memory/--disk 会作为从该快照创建沙箱时的默认资源。
daytona snapshot create "$SNAPSHOT_NAME" \
  -f "$DOCKERFILE" \
  --cpu 2 \
  --memory 4 \
  --disk 10 \
  --region "$REGION"

echo "快照 $SNAPSHOT_NAME 已重建（region: $REGION）"
