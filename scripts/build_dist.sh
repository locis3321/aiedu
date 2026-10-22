#!/usr/bin/env bash
# 构建两个包的 sdist+wheel 并用 twine 校验（元数据完整性检查）。
# CI 的 build-dist job 与本地发版前都跑这个。
set -euo pipefail

cd "$(dirname "$0")/.."

python -m pip install -q --upgrade build twine

for pkg in aiedu-core aiedu-mcp; do
  echo "=== build $pkg ==="
  rm -rf "packages/$pkg/dist"
  (cd "packages/$pkg" && python -m build)
done

echo "=== twine check ==="
python -m twine check packages/aiedu-core/dist/* packages/aiedu-mcp/dist/*

echo "=== 产物 ==="
ls -l packages/aiedu-core/dist packages/aiedu-mcp/dist
