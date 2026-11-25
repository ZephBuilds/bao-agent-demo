from pathlib import Path

from scripts.preflight import README_REQUIREMENTS, check


def make_public_demo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("\n".join(README_REQUIREMENTS), encoding="utf-8")
    (root / ".gitignore").write_text("logs/*.jsonl\noutput/*.json\n", encoding="utf-8")
    (root / "app.py").write_text("CHANNEL_ID = 'ID_DE_CANAL'\n", encoding="utf-8")


def messages(root: Path) -> list[str]:
    return [finding.render(root) for finding in check(root)]


def test_clean_sanitized_demo_passes_with_ignored_runtime_outputs(tmp_path: Path) -> None:
    make_public_demo(tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "trace.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "report.json").write_text("{}\n", encoding="utf-8")

    assert check(tmp_path) == []


def test_detects_sensitive_files_secrets_discord_ids_and_unignored_output(tmp_path: Path) -> None:
    make_public_demo(tmp_path)
    (tmp_path / ".env").write_text("SAFE_TO_DISPLAY=no\n", encoding="utf-8")
    (tmp_path / "config.py").write_text(
        "API_KEY = 'live-secret-value-12345'\n"  # preflight: allow-test-data
        "CHANNEL_ID = '123456789012345678'\n",  # preflight: allow-test-data
        encoding="utf-8",
    )
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "debug.txt").write_text("generated\n", encoding="utf-8")

    result = messages(tmp_path)

    assert any(".env: sensitive environment file" in item for item in result)
    assert any("config.py:1: plausible hard-coded secret" in item for item in result)
    assert any("config.py:2: plausible real Discord ID" in item for item in result)
    assert any("output/debug.txt: generated runtime output" in item for item in result)


def test_requires_explicit_allow_marker_for_fictitious_test_and_fixture_values(
    tmp_path: Path,
) -> None:
    make_public_demo(tmp_path)
    for directory in ("tests", "fixtures"):
        target = tmp_path / directory
        target.mkdir()
        (target / "fake_data.py").write_text(
            "TOKEN='live-looking-secret-value'  # preflight: allow-test-data\n"
            "ID='123456789012345678'  # preflight: allow-test-data\n",
            encoding="utf-8",
        )

    assert check(tmp_path) == []


def test_scans_unmarked_test_and_fixture_values(tmp_path: Path) -> None:
    make_public_demo(tmp_path)
    target = tmp_path / "tests"
    target.mkdir()
    (target / "accidental.py").write_text(
        "TOKEN='live-looking-secret-value'\n"  # preflight: allow-test-data
        "ID='123456789012345678'\n",  # preflight: allow-test-data
        encoding="utf-8",
    )

    result = messages(tmp_path)

    assert any("tests/accidental.py:1: plausible hard-coded secret" in item for item in result)
    assert any("tests/accidental.py:2: plausible real Discord ID" in item for item in result)


def test_readme_must_keep_every_sanitized_placeholder(tmp_path: Path) -> None:
    make_public_demo(tmp_path)
    (tmp_path / "README.md").write_text("cp .env.example .env\n", encoding="utf-8")

    result = messages(tmp_path)

    assert any(
        "missing sanitized example or placeholder: --channel-id ID_DE_CANAL" in item
        for item in result
    )
    assert any(
        "missing sanitized example or placeholder: DISCORD_BOT_TOKEN" in item for item in result
    )
