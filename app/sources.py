import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from app.errors import RunConfigurationError
from app.models import Message


class FixtureSource:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self, limit: int) -> list[Message]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Message.model_validate(item) for item in raw[:limit]]


class DiscordSource:
    """Minimal read-only Discord REST adapter; never writes or mutates messages."""

    def __init__(
        self,
        channel_id: str,
        token: str | None = None,
        *,
        request: Callable[..., httpx.Response] = httpx.get,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
        backoff_seconds: float = 0.25,
        max_backoff_seconds: float = 1.0,
        observe: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.token = token or os.getenv("DISCORD_BOT_TOKEN")
        if not self.token:
            raise RunConfigurationError("DISCORD_BOT_TOKEN is required for the discord source")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.request = request
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.observe = observe or (lambda _event: None)

    def _emit_attempt(
        self,
        *,
        attempt: int,
        status: str,
        will_retry: bool,
        http_status: int | None = None,
    ) -> None:
        event: dict[str, object] = {
            "action": "discord_read_attempt",
            "attempt": attempt,
            "max_attempts": self.max_attempts,
            "status": status,
            "will_retry": will_retry,
        }
        if http_status is not None:
            event["http_status"] = http_status
        self.observe(event)

    def _emit_final(self, *, attempt: int, status: str) -> None:
        self.observe(
            {
                "action": "discord_read_final",
                "attempt": attempt,
                "max_attempts": self.max_attempts,
                "status": status,
                "will_retry": False,
            }
        )

    def read(self, limit: int) -> list[Message]:
        for attempt_index in range(self.max_attempts):
            attempt = attempt_index + 1
            try:
                response = self.request(
                    f"https://discord.com/api/v10/channels/{self.channel_id}/messages",
                    params={"limit": limit},
                    headers={"Authorization": f"Bot {self.token}"},
                    timeout=10,
                )
            except Exception:
                self._emit_attempt(attempt=attempt, status="request_error", will_retry=False)
                self._emit_final(attempt=attempt, status="request_error")
                raise

            retryable = response.status_code == 429 or response.status_code >= 500
            will_retry = retryable and attempt < self.max_attempts
            status = "ok" if response.is_success else "http_error"
            self._emit_attempt(
                attempt=attempt,
                status=status,
                will_retry=will_retry,
                http_status=response.status_code,
            )
            if not will_retry:
                break
            delay = min(self.backoff_seconds * (2**attempt_index), self.max_backoff_seconds)
            self.sleep(delay)

        if not response.is_success:
            self._emit_final(attempt=attempt, status="http_error")
            response.raise_for_status()

        try:
            messages = [
                Message(
                    id=item["id"],
                    author=item["author"].get("global_name") or item["author"]["username"],
                    content=item.get("content", ""),
                    timestamp=item["timestamp"],
                )
                for item in response.json()
            ]
        except Exception:
            self._emit_final(attempt=attempt, status="invalid_response")
            raise

        self._emit_final(attempt=attempt, status="ok")
        return messages
