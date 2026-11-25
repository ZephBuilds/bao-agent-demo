import json
from collections.abc import Iterator

import httpx
import pytest

from app.sources import DiscordSource


def response(status_code: int, payload: list[dict[str, object]] | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload or {"message": "error"},
        request=httpx.Request("GET", "https://discord.test/messages"),
    )


def requester(responses: Iterator[httpx.Response], calls: list[int]):
    def request(*args: object, **kwargs: object) -> httpx.Response:
        calls.append(1)
        return next(responses)

    return request


def test_discord_retries_429_and_5xx_with_capped_backoff() -> None:
    payload = [
        {
            "id": "message-1",
            "author": {"username": "Bao", "global_name": None},
            "content": "Oferta relevante",
            "timestamp": "2026-11-09T06:00:00Z",
        }
    ]
    calls: list[int] = []
    sleeps: list[float] = []
    responses = iter([response(429), response(503), response(200, payload)])
    source = DiscordSource(
        "channel-1",
        token="test-token",
        request=requester(responses, calls),
        sleep=sleeps.append,
        backoff_seconds=0.75,
        max_backoff_seconds=1.0,
    )

    messages = source.read(limit=10)

    assert len(calls) == 3
    assert sleeps == [0.75, 1.0]
    assert messages[0].id == "message-1"


def test_discord_does_not_retry_permanent_4xx() -> None:
    calls: list[int] = []
    sleeps: list[float] = []
    source = DiscordSource(
        "channel-1",
        token="test-token",
        request=requester(iter([response(403)]), calls),
        sleep=sleeps.append,
    )

    with pytest.raises(httpx.HTTPStatusError):
        source.read(limit=10)

    assert len(calls) == 1
    assert sleeps == []


def test_discord_stops_after_max_attempts() -> None:
    calls: list[int] = []
    sleeps: list[float] = []
    source = DiscordSource(
        "channel-1",
        token="test-token",
        request=requester(iter([response(500), response(502)]), calls),
        sleep=sleeps.append,
        max_attempts=2,
    )

    with pytest.raises(httpx.HTTPStatusError):
        source.read(limit=10)

    assert len(calls) == 2
    assert sleeps == [0.25]


def test_discord_observability_records_recovery_without_private_data() -> None:
    private_sentinels = {
        "channel": "private-channel-8675309",
        "token": "private-token-do-not-log",
        "payload": "private-message-do-not-log",
    }
    payload = [
        {
            "id": "message-1",
            "author": {"username": "Bao", "global_name": None},
            "content": private_sentinels["payload"],
            "timestamp": "2026-11-09T06:00:00Z",
        }
    ]
    events: list[dict[str, object]] = []
    source = DiscordSource(
        private_sentinels["channel"],
        token=private_sentinels["token"],
        request=requester(iter([response(503), response(200, payload)]), []),
        sleep=lambda _delay: None,
        observe=events.append,
    )

    source.read(limit=10)

    assert events == [
        {
            "action": "discord_read_attempt",
            "attempt": 1,
            "max_attempts": 3,
            "status": "http_error",
            "will_retry": True,
            "http_status": 503,
        },
        {
            "action": "discord_read_attempt",
            "attempt": 2,
            "max_attempts": 3,
            "status": "ok",
            "will_retry": False,
            "http_status": 200,
        },
        {
            "action": "discord_read_final",
            "attempt": 2,
            "max_attempts": 3,
            "status": "ok",
            "will_retry": False,
        },
    ]
    serialized_events = json.dumps(events)
    assert all(sentinel not in serialized_events for sentinel in private_sentinels.values())


def test_discord_observability_records_final_failure_without_private_data() -> None:
    private_sentinels = {
        "channel": "private-channel-final-failure",
        "token": "private-token-final-failure",
        "exception": "private-upstream-exception-message",
    }
    events: list[dict[str, object]] = []
    failed_responses = iter(
        [
            response(500, {"message": private_sentinels["exception"]}),
            response(502, {"message": private_sentinels["exception"]}),
        ]
    )
    source = DiscordSource(
        private_sentinels["channel"],
        token=private_sentinels["token"],
        request=requester(failed_responses, []),
        sleep=lambda _delay: None,
        max_attempts=2,
        observe=events.append,
    )

    with pytest.raises(httpx.HTTPStatusError):
        source.read(limit=10)

    assert events == [
        {
            "action": "discord_read_attempt",
            "attempt": 1,
            "max_attempts": 2,
            "status": "http_error",
            "will_retry": True,
            "http_status": 500,
        },
        {
            "action": "discord_read_attempt",
            "attempt": 2,
            "max_attempts": 2,
            "status": "http_error",
            "will_retry": False,
            "http_status": 502,
        },
        {
            "action": "discord_read_final",
            "attempt": 2,
            "max_attempts": 2,
            "status": "http_error",
            "will_retry": False,
        },
    ]
    serialized_events = json.dumps(events)
    assert all(sentinel not in serialized_events for sentinel in private_sentinels.values())
