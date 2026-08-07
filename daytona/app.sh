#!/usr/bin/env bash
# 在沙箱内管理应用生命周期。
# 用法: bash daytona/app.sh start|stop|status
set -euo pipefail

# daytona CLI 依赖 HOME；本机可能未设置
export HOME="${HOME:-/root}"

SANDBOX_NAME="${SANDBOX_NAME:-outlookmailplus}"
ACTION="${1:-start}"
PORT="${PORT:-5000}"

wait_started() {
  for _ in $(seq 1 30); do
    ST=$(daytona sandbox info "$SANDBOX_NAME" -f json 2>/dev/null \
      | python3 -c "import json,sys;print(json.load(sys.stdin).get('state','?'))" 2>/dev/null || echo '?')
    case "$ST" in
      started|running) return 0 ;;
    esac
    echo "等待沙箱 $SANDBOX_NAME 启动（当前: $ST）..."
    sleep 10
  done
  echo "错误：沙箱 $SANDBOX_NAME 未在 5 分钟内启动"
  exit 1
}

case "$ACTION" in
  start)
    wait_started
    # 镜像内没有 pgrep，用 /healthz 探测是否已在运行
    daytona exec "$SANDBOX_NAME" -- bash -lc 'cd /app && mkdir -p data && if ! python3 -c "import urllib.request as u; u.urlopen(\"http://127.0.0.1:'"$PORT"'/healthz\", timeout=2)" >/dev/null 2>&1; then nohup scripts/start-gunicorn.sh > /tmp/oemp-app.log 2>&1 & fi; sleep 6; python3 -c "import urllib.request as u; print(\"healthz\", u.urlopen(\"http://127.0.0.1:'"$PORT"'/healthz\", timeout=5).status)"'
    echo "预览地址（24 小时有效）:"
    daytona preview-url "$SANDBOX_NAME" -p "$PORT" --expires 86400
    ;;
  stop)
    daytona exec "$SANDBOX_NAME" -- bash -lc 'pkill -f start-gunicorn.sh 2>/dev/null || true; pkill -f "gunicorn" 2>/dev/null || true; echo "应用已停止"'
    ;;
  status)
    daytona sandbox info "$SANDBOX_NAME" -f json | head -25
    ;;
  *)
    echo "用法: bash daytona/app.sh start|stop|status"
    exit 1
    ;;
esac
