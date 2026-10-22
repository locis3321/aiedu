#!/usr/bin/env bash
# 演示服务部署脚本（架构增量 v1 · C11/D7）。
# 流程：打 tag → 构建 player dist → 同步到 VPS → pip 安装同 tag wheel → 重启 systemd →
#       SQLite WAL checkpoint + .backup() 到备份目录（保留 7 份）。
# 用法：bash deploy/deploy-demo.sh --dry-run   （自检：只打印将执行的命令）
#       bash deploy/deploy-demo.sh <vps> <tag>  （真实部署）
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi
VPS="${1:-}"
TAG="${2:-v0.1.0}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] $*"
  else
    echo "[run] $*"
    "$@"
  fi
}

echo "== 0) 校验 tag（与 wheel 版本一致）=="
run grep -q "version = \"${TAG#v}\"" "$REPO_ROOT/packages/aiedu-mcp/pyproject.toml"

echo "== 1) 构建 player dist（唯一真源 = 同 tag）=="
run bash -c "cd '$REPO_ROOT/packages/aiedu-player' && npm ci && npm run build"

echo "== 2) 构建 aiedu-mcp wheel =="
run bash -c "cd '$REPO_ROOT' && bash scripts/build_dist.sh >/dev/null"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "== dry-run 自检完成 =="
  exit 0
fi

: "${VPS:?请提供 VPS 地址与 tag：bash deploy/deploy-demo.sh user@host v0.1.0}"

echo "== 3) 同步 player dist 与 wheel 到 VPS =="
run rsync -az "$REPO_ROOT/packages/aiedu-player/dist/" "$VPS:/opt/aiedu/player_dist/"
run rsync -az "$REPO_ROOT/packages/aiedu-mcp/dist/" "$VPS:/tmp/aiedu-dist/"

echo "== 4) 在 VPS 安装同 tag 包并重启服务 =="
run ssh "$VPS" "/opt/aiedu/venv/bin/pip install --upgrade /tmp/aiedu-dist/aiedu_mcp-*.whl && \
  systemctl restart aiedu-demo"

echo "== 5) 数据库备份（D7：SQLite .backup() 保留 7 份）=="
run ssh "$VPS" "mkdir -p /var/lib/aiedu/backups && \
  sqlite3 /var/lib/aiedu/aiedu_auth.db 'PRAGMA wal_checkpoint(TRUNCATE);' 2>/dev/null || true; \
  sqlite3 /var/lib/aiedu/aiedu_auth.db '.backup /var/lib/aiedu/backups/aiedu_auth-\$(date +%F-%H%M%S).db' && \
  ls -t /var/lib/aiedu/backups/*.db | tail -n +8 | xargs -r rm -f"

echo "== 完成。验证：curl -s https://<域名>/health =="
