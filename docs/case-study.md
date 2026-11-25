# Case study: turning untrusted messages into auditable tasks

## Problem

Operational commitments are often buried in chat. Copying them manually into a
tracker is slow, inconsistent, and difficult to audit. Directly connecting an
LLM to a real channel would also create avoidable privacy and prompt-injection
risks.

## Approach

Bao Agent Demo treats every message as untrusted input and keeps the source
read-only. A shared domain service accepts either fictional fixtures or a
minimal Discord adapter, selects a deterministic or model-backed extractor,
validates the result with Pydantic, and emits a structured task report plus a
sanitized JSONL trace.

The offline rules path is the reproducible baseline: reviewers can run the CLI,
API, and tests without credentials, network access, or paid services. The
optional Anthropic adapter demonstrates typed model output without becoming a
requirement for evaluation.

## Trust boundaries

- Discord access is read-only and limited to one explicit channel.
- Message content is data, never an instruction to the agent runtime.
- Tokens, channel IDs, URLs, payloads, and exception text are excluded from
  traces.
- Provider and transport errors are mapped to a small public error contract.
- Generated runtime output and `.env` files are excluded from publication.
- The release preflight scans all public files for credential-like material.

## Reproducible evidence

```bash
PYTHONPATH=.deps:. python3 -m pytest -q
PYTHONPATH=.deps:. python3 cli.py
python3 scripts/preflight.py
```

Current verified result: 33 tests pass, the public-release preflight passes,
and the offline fixture produces three tasks from five fictional messages.

## Engineering signals

- Python, FastAPI, Pydantic, HTTPX, CLI and REST interfaces.
- Deterministic baseline plus an optional LLM adapter.
- Retry policy for 429 and transient 5xx responses with bounded backoff.
- Structured latency, token, cost, retry, and error telemetry.
- CI, Docker, dependency auditing, and executable security contracts.

## Limitations

This is a portfolio slice, not a production task platform. It deliberately
omits durable storage, end-user authentication, queues, write-back to Discord,
and aggregate monitoring. Those features should be added only after defining
tenant isolation and operational ownership.
