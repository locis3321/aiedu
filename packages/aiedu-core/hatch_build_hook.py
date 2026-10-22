"""hatch 构建钩子：把仓库根的 teaching-skills 拷进包内。

为什么必须有：teaching-skills 是"零 LLM 覆盖 3 类题型"的资产，
不随包发布的话，装完 aiedu-core 的用户连 16+8/16-9 都只能拿到 capability_gap。

- 仓库根 `teaching-skills/` 是唯一真源（开发时直接用）；
- 构建时拷进 `aiedu_core/teaching_skills/`（包数据，随 wheel/sdist 一起走）；
- 拷贝目录不入 git（.gitignore），避免出现第二份"真源"。
"""

import shutil
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):  # noqa: D102 - hatch 接口
        package_root = Path(self.root)
        repo_root = package_root.parents[1]  # packages/aiedu-core → packages → 仓库根
        source = repo_root / "teaching-skills"
        target = package_root / "aiedu_core" / "teaching_skills"
        if not source.is_dir():
            # 从 sdist 重建时源码已随包携带，跳过拷贝（不报错）
            return
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        print(f"[build] teaching-skills → {target}")
