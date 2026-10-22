"""全链路可观测：OpenTelemetry 埋点（后端：Grafana Tempo / 任意 OTLP）。

不用自建 trace 表与 UI：Otel 标准协议 + 开源查看服务，避免重复造轮子。
"""

from app.observability.tracing import get_tracer, init_tracing, is_enabled

__all__ = ["get_tracer", "init_tracing", "is_enabled"]
