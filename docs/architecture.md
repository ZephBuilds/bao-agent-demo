# Architecture and trust boundaries

```text
Fictional fixture ─┐
                   ├── MessageSource ── AgentService ── TaskExtractor
Discord REST GET ──┘                         │                 │
                                             ├── TaskReport ───┘
                                             └── sanitized JSONL trace
```

## Components

- `app/sources.py`: fictional fixture input and the read-only Discord adapter.
- `app/extractors.py`: deterministic rules and optional Anthropic extraction.
- `app/service.py`: orchestration, validation, retries, and error mapping.
- `app/tracing.py`: allowlisted operational events without private payloads.
- `app/main.py`: FastAPI boundary.
- `cli.py`: offline reviewer path over the same domain service.

## Security posture

The system is intentionally asymmetric: it can observe an authorized source
but cannot publish, reply, delete, or modify Discord content. The public demo
uses fictional data. Live credentials belong only in a local `.env`, which is
ignored and rejected by the release preflight if accidentally included.

## Failure behavior

- Invalid local configuration: stable HTTP 400 public code.
- Upstream provider or transport failure: stable HTTP 502 public code.
- Permanent Discord 4xx: fail once without retry.
- Discord 429 or transient 5xx: bounded retries and sanitized attempt events.
- Invalid 2xx response: fail closed without retrying malformed data.
