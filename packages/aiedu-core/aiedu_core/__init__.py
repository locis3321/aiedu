"""aiedu-core：数学可信教学引擎内核。

输入一道题 → 输出经过独立数学核验（SymPy）、答案门控（先想后看）、
可交互渲染的课程规格（LessonSpec v2）。LLM 为可选路径。
"""

from aiedu_core.pipeline.pipeline import PipelineError, run_pipeline

__all__ = ["PipelineError", "run_pipeline"]
