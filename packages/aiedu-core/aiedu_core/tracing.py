"""轻量 tracing：默认 no-op，无外部依赖（开源内核不引入 OpenTelemetry）。

需要可观测性的宿主可自行插桩；本模块只保证 pipeline 的 span 调用点可运行。
"""

from contextlib import contextmanager


class NoopSpan:
    def set_attribute(self, *args, **kwargs):
        return None

    def set_status(self, *args, **kwargs):
        return None

    def record_exception(self, *args, **kwargs):
        return None


@contextmanager
def _span(name: str):
    yield NoopSpan()


class NoopTracer:
    def start_as_current_span(self, name=None, **kwargs):
        return _span(name or "")


def get_tracer():
    """获取 tracer；开源内核恒为 no-op，不发起任何网络导出。"""
    return NoopTracer()
