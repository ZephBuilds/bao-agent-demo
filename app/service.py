from pathlib import Path

from app.errors import RunConfigurationError
from app.extractors import AnthropicExtractor, Extractor, RuleExtractor
from app.models import RunRequest, TaskReport
from app.sources import DiscordSource, FixtureSource
from app.tracing import JsonlTracer

ROOT = Path(__file__).resolve().parents[1]


def run_agent(request: RunRequest, trace_path: Path | None = None) -> TaskReport:
    tracer = JsonlTracer(trace_path or ROOT / "logs" / "trace.jsonl")

    if request.source == "fixture":
        source = FixtureSource(ROOT / "fixtures" / "messages.json")
    else:
        if not request.channel_id:
            raise RunConfigurationError("channel_id is required for the discord source")
        source = DiscordSource(request.channel_id, observe=tracer.emit)

    extractor: Extractor = RuleExtractor() if request.extractor == "rules" else AnthropicExtractor()

    with tracer.span("read_messages", source=request.source, limit=request.limit) as span:
        messages = source.read(request.limit)
        span.update({"messages": len(messages), "chars": sum(len(m.content) for m in messages)})

    with tracer.span("extract_tasks", extractor=extractor.name) as span:
        report = extractor.extract(messages)
        span.update({"tasks": len(report.tasks), "schema_valid": True, **extractor.usage})

    return report
