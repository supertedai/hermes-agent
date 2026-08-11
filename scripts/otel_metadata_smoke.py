"""Metadata-only OpenTelemetry smoke for the isolated MWP runtime."""
from __future__ import annotations

import json
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult


class MemoryExporter(SpanExporter):
    def __init__(self) -> None:
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        return None


exporter = MemoryExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("mwp.standard-stack", "1")

with tracer.start_as_current_span("mwp.otel.smoke") as span:
    span.set_attribute("mwp.axis", "system")
    span.set_attribute("mwp.provenance", "metadata_only")
    span.set_attribute("mwp.verified", False)
    span.set_attribute("mwp.side_effects", False)

assert len(exporter.spans) == 1
record = exporter.spans[0]
assert record.name == "mwp.otel.smoke"
assert record.attributes["mwp.provenance"] == "metadata_only"
assert record.attributes["mwp.verified"] is False
assert record.attributes["mwp.side_effects"] is False
print(json.dumps({
    "status": "PASS",
    "span_name": record.name,
    "trace_id": format(record.context.trace_id, "032x"),
    "span_id": format(record.context.span_id, "016x"),
    "provenance": record.attributes["mwp.provenance"],
    "verified": record.attributes["mwp.verified"],
    "side_effects": record.attributes["mwp.side_effects"],
}, sort_keys=True))
