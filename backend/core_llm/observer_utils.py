"""
observer_utils.py

Centralized observability utilities using OpenTelemetry.
Keeps tracing concerns isolated from business logic.
"""

import os
from contextlib import nullcontext
from typing import Dict, Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from openinference.instrumentation.langchain import LangChainInstrumentor
from openinference.instrumentation import using_attributes
from config import Settings


def setup_observability() -> None:
    """
    Initialize OpenTelemetry tracing + LangChain instrumentation.

    Safe to call once at app startup.
    """
    endpoint = Settings().PHOENIX_COLLECTOR_ENDPOINT or ""
    
    if len(endpoint) == 0:
        print("⚠️ PHOENIX_COLLECTOR_ENDPOINT not set, skipping observability setup")
        return
    

    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    )

    trace.set_tracer_provider(tracer_provider)

    # Instrument LangChain pipelines
    LangChainInstrumentor().instrument()


def safe_attributes(attrs: Dict[str, Any]):
    """
    Wrap tracing attributes safely.

    If OpenTelemetry fails, fallback to no-op context
    instead of crashing the pipeline.
    """
    try:
        return using_attributes(attributes=attrs)
    except Exception:
        return nullcontext()
    
