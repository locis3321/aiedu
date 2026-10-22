"""OpenTelemetry 初始化与轻量助手。

- 标准 OTLP 导出（HTTP/protobuf，默认 http://localhost:4318）；
- 未配置或后端不可达时静默降级为 Noop，绝不阻断生成主链路；
- 环境变量：OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_SERVICE_NAME / AIEDU_TRACE（设为 0 关闭）。

查看：Grafana Tempo（infra/compose.yaml）→ Grafana UI 搜索 service=aiedu。
"""

import os

_TRACER = None
_ENABLED = False


def is_enabled() -> bool:
    return _ENABLED


def init_tracing() -> None:
    """幂等初始化 TracerProvider + OTLP exporter；失败降级 Noop。"""
    global _TRACER, _ENABLED
    if _TRACER is not None:
        return
    if os.environ.get("AIEDU_TRACE", "1") == "0":
        # 关闭导出，但仍设置全局 TracerProvider（无处理器）：直接使用
        # opentelemetry.trace.get_tracer() 的代码拿到可用 span，不发起网络。
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        trace.set_tracer_provider(TracerProvider())
        _TRACER = trace.get_tracer("aiedu.generation")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        service = os.environ.get("OTEL_SERVICE_NAME", "aiedu")
        provider = TracerProvider(resource=Resource.create({"service.name": service}))
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(
            BatchSpanProcessor(exporter, schedule_delay_millis=1000)
        )
        trace.set_tracer_provider(provider)

        import atexit

        atexit.register(lambda: exporter.shutdown())
        _TRACER = trace.get_tracer("aiedu.generation")
        _ENABLED = True
    except Exception:  # noqa: BLE001 —— 可观测缺省不影响主链路
        _TRACER = _noop_tracer()


def _noop_tracer():
    class _Noop:
        def start_as_current_span(self, *a, **k):
            from contextlib import nullcontext

            return nullcontext()

        def start_span(self, *a, **k):
            from contextlib import nullcontext

            return nullcontext()

    return _Noop()


def get_tracer():
    """获取 tracer；未初始化时自动初始化（懒）。"""
    global _TRACER
    if _TRACER is None:
        init_tracing()
    return _TRACER
