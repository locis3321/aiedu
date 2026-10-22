#!/usr/bin/env bash
# 发版：先 testpypi 走通 → 再 PyPI → 打 tag。
#
# 凭据只从环境变量来（不进代码、不进 git）：
#   export TWINE_USERNAME="__token__"
#   export TWINE_PASSWORD="<pypi-token>"      # PyPI
#   export TEST_PYPI_USERNAME="__token__"
#   export TEST_PYPI_PASSWORD="<testpypi-token>"
#
# 用法：
#   bash scripts/release.sh testpypi     # 先在 testpypi 验证
#   bash scripts/release.sh pypi         # 正式发布
set -euo pipefail

cd "$(dirname "$0")/.."

REPO="testpypi"       # 默认先 testpypi
if [ "${1:-}" = "pypi" ]; then
  REPO="pypi"
fi

bash scripts/build_dist.sh

if [ "$REPO" = "testpypi" ]; then
  : "${TEST_PYPI_USERNAME:?请先导出 TEST_PYPI_USERNAME/TEST_PYPI_PASSWORD}"
  python -m twine upload --repository testpypi \
    packages/aiedu-core/dist/* packages/aiedu-mcp/dist/*
  echo "testpypi 上传完成。验证："
  echo "  pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple aiedu-core aiedu-mcp"
else
  : "${TWINE_USERNAME:?请先导出 TWINE_USERNAME/TWINE_PASSWORD}"
  python -m twine upload packages/aiedu-core/dist/* packages/aiedu-mcp/dist/*
  echo "PyPI 上传完成。验证（真实安装 + 真实调用）："
  echo "  uvx aiedu-mcp --transport stdio   # 然后让宿主调用 verify_math('7x8', 56)"
fi

echo "=== 打 tag（推送前确认 remote 与权限）==="
git tag -a "v0.1.0" -m "aiedu 0.1.0：核心内核 + MCP server + 课堂渲染器"
echo "已打本地 tag v0.1.0；推送：git push <remote> v0.1.0"
