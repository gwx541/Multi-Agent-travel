"""OpenTelemetry 初始化 + 一组方便业务代码用的 trace helper。

设计目标：
- 配了 OTEL_EXPORTER_OTLP_ENDPOINT 就把 trace 发到 Jaeger / Aspire Dashboard
- 没配就降级到 console exporter（stdout 打印），保证开发时也能看到 span 结构
- 所有 helper 都是『失败静默』——OTel 自身异常绝不能影响业务流

最小用法：
    setup_otel()  # 一次性初始化
    with span("agent.planning_agent", subtask=...):
        ...
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_initialized = False
_tracer = None


def setup_otel(service_name: str = "travelagent") -> None:
    """初始化 OTel。多次调用幂等。"""
    global _initialized, _tracer
    if _initialized:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        resource = Resource.create({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )
                # endpoint 一般给到 http://jaeger:4318；OTLP HTTP 自动补 /v1/traces
                exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info(f"[otel] OTLP HTTP exporter → {endpoint}")
            except Exception as e:
                logger.warning(f"[otel] OTLP exporter init failed, fallback console: {e}")
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            # 没配 endpoint：开发模式，打印到 stdout，至少能看 span 结构
            if os.getenv("OTEL_CONSOLE", "").strip().lower() in ("1", "true", "yes"):
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                logger.info("[otel] ConsoleSpanExporter enabled (OTEL_CONSOLE=true)")
            else:
                logger.info("[otel] no OTLP endpoint configured; spans not exported")

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        _initialized = True
        logger.info("[otel] tracer ready")
    except Exception as e:
        logger.warning(f"[otel] setup failed: {e}; continuing without tracing")
        _tracer = None


def instrument_fastapi(app: Any) -> None:
    """给 FastAPI app 自动加 HTTP request span。失败静默。"""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("[otel] FastAPI instrumented")
    except Exception as e:
        logger.warning(f"[otel] FastAPI instrument failed: {e}")


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    """通用 span 上下文管理器。OTel 没初始化就成 no-op。

    用法：
        with span("agent.planning_agent", subtask="..."):
            ...
        # 失败时 span 会被标记 ERROR
    """
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as sp:
        try:
            for k, v in attrs.items():
                if v is None:
                    continue
                if isinstance(v, (str, bool, int, float)):
                    sp.set_attribute(k, v)
                else:
                    sp.set_attribute(k, str(v))
        except Exception:
            pass
        try:
            yield sp
        except BaseException as e:
            try:
                from opentelemetry.trace import Status, StatusCode
                sp.set_status(Status(StatusCode.ERROR, f"{type(e).__name__}: {e}"))
                sp.record_exception(e)
            except Exception:
                pass
            raise


def set_attr(sp: Any, key: str, value: Any) -> None:
    """给已存在的 span 加属性。sp 为 None 时 no-op。"""
    if sp is None or value is None:
        return
    try:
        if isinstance(value, (str, bool, int, float)):
            sp.set_attribute(key, value)
        else:
            sp.set_attribute(key, str(value))
    except Exception:
        pass
