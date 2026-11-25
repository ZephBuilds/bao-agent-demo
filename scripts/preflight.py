"""Fail fast when the repository is not safe to publish.

This checker intentionally uses only the Python standard library. It scans all
files that form the public demo, including tests and fixtures, while respecting
explicit ignores for generated output and line-level test-data exceptions.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRECTORIES = {
    ".deps",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
}
SENSITIVE_FILENAMES = {".env", ".env.local", ".env.production", ".env.development"}
GENERATED_PREFIXES = {"logs", "output"}
README_REQUIREMENTS = (
    "cp .env.example .env",
    "--channel-id ID_DE_CANAL",
    "ANTHROPIC_API_KEY",
    "DISCORD_BOT_TOKEN",
    "DISCORD_CHANNEL_ID",
)
PLACEHOLDER_MARKERS = (
    "example",
    "fake",
    "ficticio",
    "id_de_",
    "placeholder",
    "sample",
    "sentinel",
    "test",
    "do-not-persist",
    "your_",
)

SECRET_PATTERNS = (
    (
        "Anthropic API key",
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b"),
    ),
    (
        "Discord bot token",
        re.compile(
            r"\b(?:mfa\.[A-Za-z0-9_-]{20,}|"
            r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,})\b"
        ),
    ),
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|authorization|bot[_-]?token|password|secret|token)\b"
    r"\s*[:=]\s*[\"']?([^\s\"'#,}]{12,})"
)
DISCORD_SNOWFLAKE = re.compile(r"(?<!\d)\d{17,20}(?!\d)")
ALLOW_TEST_DATA_MARKER = "preflight: allow-test-data"


@dataclass(frozen=True)
class Finding:
    path: Path
    message: str
    line: int | None = None

    def render(self, root: Path) -> str:
        location = self.path.relative_to(root).as_posix()
        if self.line is not None:
            location = f"{location}:{self.line}"
        return f"{location}: {self.message}"


def _ignore_patterns(root: Path) -> tuple[str, ...]:
    ignore_file = root / ".gitignore"
    if not ignore_file.is_file():
        return ()
    return tuple(
        line.strip()
        for line in ignore_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and not line.startswith("!")
    )


def _is_ignored(relative: Path, patterns: tuple[str, ...]) -> bool:
    value = relative.as_posix()
    return any(
        fnmatch.fnmatch(value, pattern.rstrip("/"))
        or fnmatch.fnmatch(value, f"{pattern.rstrip('/')}/*")
        for pattern in patterns
    )


def _candidate_files(root: Path) -> list[Path]:
    patterns = _ignore_patterns(root)
    candidates: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRECTORIES for part in relative.parts):
            continue
        if path.is_file() and not _is_ignored(relative, patterns):
            candidates.append(path)
    return sorted(candidates)


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _scan_text(path: Path) -> list[Finding]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []

    findings: list[Finding] = []
    for number, line in enumerate(lines, start=1):
        if ALLOW_TEST_DATA_MARKER in line:
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                if not _looks_like_placeholder(match.group(0)):
                    findings.append(Finding(path, f"plausible {label} found", number))
        assignment = SECRET_ASSIGNMENT.search(line)
        if assignment and not _looks_like_placeholder(assignment.group(1)):
            findings.append(Finding(path, "plausible hard-coded secret found", number))
        if DISCORD_SNOWFLAKE.search(line):
            findings.append(Finding(path, "plausible real Discord ID found", number))
    return findings


def check(root: Path) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []

    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and path.name in SENSITIVE_FILENAMES
            and not any(part in SKIP_DIRECTORIES for part in relative.parts[:-1])
        ):
            findings.append(Finding(path, "sensitive environment file must not be published"))

    patterns = _ignore_patterns(root)
    for prefix in GENERATED_PREFIXES:
        generated = root / prefix
        if not generated.is_dir():
            continue
        for path in generated.rglob("*"):
            if path.is_file() and not _is_ignored(path.relative_to(root), patterns):
                findings.append(Finding(path, "generated runtime output is not ignored"))

    for path in _candidate_files(root):
        findings.extend(_scan_text(path))

    readme = root / "README.md"
    if not readme.is_file():
        findings.append(Finding(readme, "README is required"))
    else:
        content = readme.read_text(encoding="utf-8")
        for required in README_REQUIREMENTS:
            if required not in content:
                findings.append(
                    Finding(readme, f"missing sanitized example or placeholder: {required}")
                )

    return sorted(findings, key=lambda item: (str(item.path), item.line or 0, item.message))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that the demo is safe to publish.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    findings = check(root)
    if findings:
        print("Public-release preflight failed:")
        for finding in findings:
            print(f"- {finding.render(root)}")
        return 1
    print("Public-release preflight passed: no private or generated data detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
