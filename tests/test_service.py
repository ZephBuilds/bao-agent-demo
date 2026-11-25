import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.errors import RunConfigurationError
from app.main import app
from app.models import RunRequest, TaskReport
from app.service import run_agent
from app.sources import DiscordSource


def test_fixture_run_extracts_only_explicit_tasks(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    report = run_agent(RunRequest(), trace_path=trace)

    assert report.messages_analyzed == 5
    assert len(report.tasks) == 3
    assert report.tasks[0].priority == "high"
    assert report.tasks[0].due_date == "2026-11-02"
    assert report.tasks[1].due_date == "2026-11-06"
    assert {task.source_message_id for task in report.tasks} == {
        "demo-001",
        "demo-003",
        "demo-005",
    }

    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [event["action"] for event in events] == ["read_messages", "extract_tasks"]
    assert all(event["status"] == "ok" for event in events)
    assert events[1]["schema_valid"] is True


def test_discord_requires_channel_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="channel_id"):
        run_agent(RunRequest(source="discord"), trace_path=tmp_path / "trace.jsonl")


def test_discord_run_persists_sanitized_events_in_operation_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "discord-trace.jsonl"
    private = {
        "channel": "private-channel-service-integration",
        "token": "private-token-service-integration",
        "message_id": "private-message-id-service-integration",
        "author": "private-author-service-integration",
        "content": "Tarea: private-payload-service-integration para mañana",
    }
    payload = [
        {
            "id": private["message_id"],
            "author": {"username": private["author"], "global_name": None},
            "content": private["content"],
            "timestamp": "2026-11-09T06:00:00Z",
        }
    ]
    requests: list[tuple[str, dict[str, object]]] = []

    def simulated_get(url: str, **kwargs: object) -> httpx.Response:
        requests.append((url, kwargs))
        return httpx.Response(
            200,
            json=payload,
            request=httpx.Request("GET", url),
        )

    def source_factory(
        channel_id: str,
        *,
        observe: Callable[[dict[str, object]], None],
    ) -> DiscordSource:
        return DiscordSource(
            channel_id,
            token=private["token"],
            request=simulated_get,
            sleep=lambda _delay: pytest.fail("a successful read must not sleep"),
            observe=observe,
        )

    monkeypatch.setattr("app.service.DiscordSource", source_factory)

    report = run_agent(
        RunRequest(source="discord", channel_id=private["channel"], limit=1),
        trace_path=trace,
    )

    assert report.messages_analyzed == 1
    assert len(requests) == 1
    requested_url, request_options = requests[0]
    assert requested_url.endswith(f"/channels/{private['channel']}/messages")
    assert request_options["params"] == {"limit": 1}

    raw_trace = trace.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_trace.splitlines()]
    assert [event["action"] for event in events] == [
        "discord_read_attempt",
        "discord_read_final",
        "read_messages",
        "extract_tasks",
    ]
    assert events[0] == {
        "timestamp": events[0]["timestamp"],
        "action": "discord_read_attempt",
        "attempt": 1,
        "max_attempts": 3,
        "status": "ok",
        "will_retry": False,
        "http_status": 200,
    }
    assert events[1] == {
        "timestamp": events[1]["timestamp"],
        "action": "discord_read_final",
        "attempt": 1,
        "max_attempts": 3,
        "status": "ok",
        "will_retry": False,
    }
    assert events[2]["status"] == "ok"
    assert events[2]["source"] == "discord"
    assert events[2]["messages"] == 1
    assert events[3]["status"] == "ok"
    assert events[3]["schema_valid"] is True

    private_values = [*private.values(), requested_url, json.dumps(payload)]
    assert all(value not in raw_trace for value in private_values)


def test_discord_run_recovers_from_transient_5xx_with_sanitized_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "discord-transient-5xx-trace.jsonl"
    private = {
        "channel": "private-channel-transient-5xx-service-integration",
        "token": "private-token-transient-5xx-service-integration",
        "provider_body": "private-provider-body-transient-5xx-service-integration",
        "message_id": "private-message-id-transient-5xx-service-integration",
        "author": "private-author-transient-5xx-service-integration",
        "content": "Tarea: private-content-transient-5xx-service-integration para manana",
    }
    failure_body = {"message": private["provider_body"]}
    payload = [
        {
            "id": private["message_id"],
            "author": {"username": private["author"], "global_name": None},
            "content": private["content"],
            "timestamp": "2026-11-09T19:00:00Z",
        }
    ]
    responses = iter([(502, failure_body), (200, payload)])
    requests: list[tuple[str, dict[str, object]]] = []
    sleeps: list[float] = []

    def simulated_get(url: str, **kwargs: object) -> httpx.Response:
        requests.append((url, kwargs))
        status_code, body = next(responses)
        return httpx.Response(
            status_code,
            json=body,
            request=httpx.Request("GET", url),
        )

    def source_factory(
        channel_id: str,
        *,
        observe: Callable[[dict[str, object]], None],
    ) -> DiscordSource:
        return DiscordSource(
            channel_id,
            token=private["token"],
            request=simulated_get,
            sleep=sleeps.append,
            backoff_seconds=0.4,
            observe=observe,
        )

    monkeypatch.setattr("app.service.DiscordSource", source_factory)

    report = run_agent(
        RunRequest(source="discord", channel_id=private["channel"], limit=1),
        trace_path=trace,
    )

    assert report.messages_analyzed == 1
    assert len(report.tasks) == 1
    assert len(requests) == 2
    assert sleeps == [0.4]

    raw_trace = trace.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_trace.splitlines()]
    assert [event["action"] for event in events] == [
        "discord_read_attempt",
        "discord_read_attempt",
        "discord_read_final",
        "read_messages",
        "extract_tasks",
    ]
    assert [event["status"] for event in events] == [
        "http_error",
        "ok",
        "ok",
        "ok",
        "ok",
    ]
    assert [event["attempt"] for event in events[:3]] == [1, 2, 2]
    assert [event["will_retry"] for event in events[:3]] == [True, False, False]
    assert [event.get("http_status") for event in events[:2]] == [502, 200]
    assert events[3]["source"] == "discord"
    assert events[3]["messages"] == 1
    assert events[4]["schema_valid"] is True
    assert events[4]["tasks"] == 1

    requested_urls = [url for url, _options in requests]
    private_values = [
        *private.values(),
        json.dumps(failure_body),
        json.dumps(payload),
        *requested_urls,
    ]
    assert all(value not in raw_trace for value in private_values)


def test_discord_run_retries_429_with_capped_backoff_and_sanitized_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "discord-rate-limit-trace.jsonl"
    private = {
        "channel": "private-channel-rate-limit-service-integration",
        "token": "private-token-rate-limit-service-integration",
        "provider_message": "private-provider-body-rate-limit-service-integration",
        "provider_code": "private-provider-code-rate-limit-service-integration",
        "message_id": "private-message-id-rate-limit-service-integration",
        "author": "private-author-rate-limit-service-integration",
        "content": "Tarea: private-content-rate-limit-service-integration para manana",
    }
    rate_limit_body = {
        "message": private["provider_message"],
        "code": private["provider_code"],
    }
    payload = [
        {
            "id": private["message_id"],
            "author": {"username": private["author"], "global_name": None},
            "content": private["content"],
            "timestamp": "2026-11-09T17:00:00Z",
        }
    ]
    responses = iter([(429, rate_limit_body), (429, rate_limit_body), (200, payload)])
    requests: list[tuple[str, dict[str, object]]] = []
    sleeps: list[float] = []

    def simulated_get(url: str, **kwargs: object) -> httpx.Response:
        requests.append((url, kwargs))
        status_code, body = next(responses)
        return httpx.Response(
            status_code,
            json=body,
            request=httpx.Request("GET", url),
        )

    def source_factory(
        channel_id: str,
        *,
        observe: Callable[[dict[str, object]], None],
    ) -> DiscordSource:
        return DiscordSource(
            channel_id,
            token=private["token"],
            request=simulated_get,
            sleep=sleeps.append,
            backoff_seconds=0.75,
            max_backoff_seconds=1.0,
            observe=observe,
        )

    monkeypatch.setattr("app.service.DiscordSource", source_factory)

    report = run_agent(
        RunRequest(source="discord", channel_id=private["channel"], limit=1),
        trace_path=trace,
    )

    assert report.messages_analyzed == 1
    assert len(requests) == 3
    assert sleeps == [0.75, 1.0]

    raw_trace = trace.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_trace.splitlines()]
    assert [event["action"] for event in events] == [
        "discord_read_attempt",
        "discord_read_attempt",
        "discord_read_attempt",
        "discord_read_final",
        "read_messages",
        "extract_tasks",
    ]
    assert [event["status"] for event in events] == [
        "http_error",
        "http_error",
        "ok",
        "ok",
        "ok",
        "ok",
    ]
    assert [event["attempt"] for event in events[:4]] == [1, 2, 3, 3]
    assert [event["will_retry"] for event in events[:4]] == [True, True, False, False]
    assert [event.get("http_status") for event in events[:3]] == [429, 429, 200]

    requested_urls = [url for url, _options in requests]
    private_values = [
        *private.values(),
        json.dumps(rate_limit_body),
        json.dumps(payload),
        *requested_urls,
    ]
    assert all(value not in raw_trace for value in private_values)


def test_discord_run_traces_exhausted_5xx_without_private_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "discord-failure-trace.jsonl"
    private = {
        "channel": "private-channel-exhausted-service-integration",
        "token": "private-token-exhausted-service-integration",
        "provider_message": "private-provider-message-service-integration",
        "payload": "private-payload-service-integration",
        "message_id": "private-message-id-exhausted-service-integration",
        "author_id": "private-author-id-exhausted-service-integration",
        "author": "private-author-exhausted-service-integration",
        "content": "private-content-exhausted-service-integration",
    }
    provider_body = {
        "message": private["provider_message"],
        "payload": private["payload"],
        "id": private["message_id"],
        "author": {"id": private["author_id"], "username": private["author"]},
        "content": private["content"],
    }
    status_codes = iter([500, 502, 503])
    requested_urls: list[str] = []
    sleeps: list[float] = []

    def simulated_get(url: str, **_kwargs: object) -> httpx.Response:
        requested_urls.append(url)
        return httpx.Response(
            next(status_codes),
            json=provider_body,
            request=httpx.Request("GET", url),
        )

    def source_factory(
        channel_id: str,
        *,
        observe: Callable[[dict[str, object]], None],
    ) -> DiscordSource:
        return DiscordSource(
            channel_id,
            token=private["token"],
            request=simulated_get,
            sleep=sleeps.append,
            observe=observe,
        )

    monkeypatch.setattr("app.service.DiscordSource", source_factory)

    with pytest.raises(httpx.HTTPStatusError):
        run_agent(
            RunRequest(source="discord", channel_id=private["channel"], limit=1),
            trace_path=trace,
        )

    assert len(requested_urls) == 3
    assert sleeps == [0.25, 0.5]

    raw_trace = trace.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_trace.splitlines()]
    assert [event["action"] for event in events] == [
        "discord_read_attempt",
        "discord_read_attempt",
        "discord_read_attempt",
        "discord_read_final",
        "read_messages",
    ]
    assert [event["status"] for event in events] == [
        "http_error",
        "http_error",
        "http_error",
        "http_error",
        "error",
    ]
    assert [event["attempt"] for event in events[:4]] == [1, 2, 3, 3]
    assert [event["will_retry"] for event in events[:4]] == [True, True, False, False]
    assert [event.get("http_status") for event in events[:3]] == [500, 502, 503]
    assert events[4]["source"] == "discord"
    assert events[4]["error_type"] == "HTTPStatusError"

    private_values = [*private.values(), json.dumps(provider_body), *requested_urls]
    assert all(value not in raw_trace for value in private_values)


def test_discord_run_traces_permanent_4xx_once_without_private_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "discord-permanent-4xx-trace.jsonl"
    private = {
        "channel": "private-channel-permanent-4xx-service-integration",
        "token": "private-token-permanent-4xx-service-integration",
        "provider_message": "private-provider-message-permanent-4xx-service-integration",
        "provider_code": "private-provider-code-permanent-4xx-service-integration",
    }
    provider_body = {
        "message": private["provider_message"],
        "code": private["provider_code"],
    }
    requested_urls: list[str] = []
    sleeps: list[float] = []

    def simulated_get(url: str, **_kwargs: object) -> httpx.Response:
        requested_urls.append(url)
        return httpx.Response(
            403,
            json=provider_body,
            request=httpx.Request("GET", url),
        )

    def source_factory(
        channel_id: str,
        *,
        observe: Callable[[dict[str, object]], None],
    ) -> DiscordSource:
        return DiscordSource(
            channel_id,
            token=private["token"],
            request=simulated_get,
            sleep=sleeps.append,
            observe=observe,
        )

    monkeypatch.setattr("app.service.DiscordSource", source_factory)

    with pytest.raises(httpx.HTTPStatusError):
        run_agent(
            RunRequest(source="discord", channel_id=private["channel"], limit=1),
            trace_path=trace,
        )

    assert len(requested_urls) == 1
    assert sleeps == []

    raw_trace = trace.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_trace.splitlines()]
    assert [event["action"] for event in events] == [
        "discord_read_attempt",
        "discord_read_final",
        "read_messages",
    ]
    assert [event["status"] for event in events] == ["http_error", "http_error", "error"]
    assert [event["attempt"] for event in events[:2]] == [1, 1]
    assert [event["will_retry"] for event in events[:2]] == [False, False]
    assert events[0]["http_status"] == 403
    assert events[2]["source"] == "discord"
    assert events[2]["error_type"] == "HTTPStatusError"

    private_values = [*private.values(), json.dumps(provider_body), *requested_urls]
    assert all(value not in raw_trace for value in private_values)


def test_discord_run_traces_transport_error_once_without_private_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "discord-transport-error-trace.jsonl"
    private = {
        "channel": "private-channel-transport-service-integration",
        "token": "private-token-transport-service-integration",
        "exception_message": "private-transport-message-service-integration",
    }
    requested_urls: list[str] = []
    sleeps: list[float] = []

    def simulated_get(url: str, **_kwargs: object) -> httpx.Response:
        requested_urls.append(url)
        raise httpx.ConnectError(
            private["exception_message"],
            request=httpx.Request("GET", url),
        )

    def source_factory(
        channel_id: str,
        *,
        observe: Callable[[dict[str, object]], None],
    ) -> DiscordSource:
        return DiscordSource(
            channel_id,
            token=private["token"],
            request=simulated_get,
            sleep=sleeps.append,
            observe=observe,
        )

    monkeypatch.setattr("app.service.DiscordSource", source_factory)

    with pytest.raises(httpx.ConnectError, match=private["exception_message"]):
        run_agent(
            RunRequest(source="discord", channel_id=private["channel"], limit=1),
            trace_path=trace,
        )

    assert len(requested_urls) == 1
    assert sleeps == []

    raw_trace = trace.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_trace.splitlines()]
    assert [event["action"] for event in events] == [
        "discord_read_attempt",
        "discord_read_final",
        "read_messages",
    ]
    assert [event["status"] for event in events] == [
        "request_error",
        "request_error",
        "error",
    ]
    assert [event["attempt"] for event in events[:2]] == [1, 1]
    assert [event["max_attempts"] for event in events[:2]] == [3, 3]
    assert [event["will_retry"] for event in events[:2]] == [False, False]
    assert events[2]["source"] == "discord"
    assert events[2]["error_type"] == "ConnectError"

    private_values = [*private.values(), *requested_urls]
    assert all(value not in raw_trace for value in private_values)


@pytest.mark.parametrize(
    "provider_body",
    [
        '{"private-provider-body-malformed-service-integration":',
        '{"private-provider-body-not-list-service-integration": true}',
    ],
    ids=["malformed-json", "non-list-json"],
)
def test_discord_run_traces_invalid_200_response_once_without_private_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_body: str,
) -> None:
    trace = tmp_path / "discord-invalid-response-trace.jsonl"
    private = {
        "channel": "private-channel-invalid-response-service-integration",
        "token": "private-token-invalid-response-service-integration",
        "author": "private-author-invalid-response-service-integration",
        "content": "private-content-invalid-response-service-integration",
    }
    requested_urls: list[str] = []
    sleeps: list[float] = []

    def simulated_get(url: str, **_kwargs: object) -> httpx.Response:
        requested_urls.append(url)
        return httpx.Response(
            200,
            content=provider_body,
            request=httpx.Request("GET", url),
        )

    def source_factory(
        channel_id: str,
        *,
        observe: Callable[[dict[str, object]], None],
    ) -> DiscordSource:
        return DiscordSource(
            channel_id,
            token=private["token"],
            request=simulated_get,
            sleep=sleeps.append,
            observe=observe,
        )

    monkeypatch.setattr("app.service.DiscordSource", source_factory)

    with pytest.raises((json.JSONDecodeError, TypeError)):
        run_agent(
            RunRequest(source="discord", channel_id=private["channel"], limit=1),
            trace_path=trace,
        )

    assert len(requested_urls) == 1
    assert sleeps == []

    raw_trace = trace.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_trace.splitlines()]
    assert [event["action"] for event in events] == [
        "discord_read_attempt",
        "discord_read_final",
        "read_messages",
    ]
    assert [event["status"] for event in events] == ["ok", "invalid_response", "error"]
    assert events[0]["attempt"] == events[1]["attempt"] == 1
    assert events[0]["will_retry"] is False
    assert events[1]["will_retry"] is False
    assert events[2]["source"] == "discord"

    private_values = [*private.values(), provider_body, *requested_urls]
    assert all(value not in raw_trace for value in private_values)


def test_limit_is_validated() -> None:
    with pytest.raises(ValueError):
        RunRequest(limit=0)


def test_prompt_injection_message_is_not_executed_or_extracted(tmp_path: Path) -> None:
    report = run_agent(RunRequest(), trace_path=tmp_path / "trace.jsonl")

    assert "demo-004" not in {task.source_message_id for task in report.tasks}
    assert all("secretos" not in task.title for task in report.tasks)


def test_api_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    response = client.post("/runs", json={"source": "fixture", "extractor": "rules", "limit": 5})

    assert response.status_code == 200
    assert len(response.json()["tasks"]) == 3


@pytest.mark.parametrize(
    ("failure", "status_code", "code"),
    [
        (
            RunConfigurationError(
                "token=secret-sentinel channel=123456 path=/private/sentinel traceback-sentinel"
            ),
            400,
            "invalid_run_configuration",
        ),
        (
            httpx.ConnectError(
                "network-secret-sentinel traceback-sentinel",
                request=httpx.Request(
                    "GET", "https://private-provider.invalid/channels/123456/messages"
                ),
            ),
            502,
            "upstream_provider_unavailable",
        ),
    ],
)
def test_api_errors_are_machine_readable_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status_code: int,
    code: str,
) -> None:
    def fail_run(_request: RunRequest) -> TaskReport:
        raise failure

    monkeypatch.setattr("app.main.run_agent", fail_run)
    response = TestClient(app).post("/runs", json={})

    assert response.status_code == status_code
    assert response.json() == {"detail": {"code": code}}
    serialized = response.text.casefold()
    for sentinel in (
        "secret-sentinel",
        "network-secret-sentinel",
        "123456",
        "/private/sentinel",
        "private-provider.invalid",
        "traceback-sentinel",
    ):
        assert sentinel not in serialized
