import ast
from pathlib import Path

SECURITY = Path(__file__).parents[1] / "SECURITY.md"
ROOT = SECURITY.parent
EXPECTED_THREATS = {
    "prompt-injection",
    "sensitive-data",
    "least-privilege",
    "vulnerable-dependencies",
    "container-isolation",
}


def _matrix_rows() -> dict[str, tuple[str, str, str]]:
    rows: dict[str, tuple[str, str, str]] = {}
    for line in SECURITY.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) == 4, f"invalid security matrix row: {line}"
        threat_id = cells[0].strip("`")
        assert threat_id not in rows, f"duplicate threat: {threat_id}"
        rows[threat_id] = (cells[1], cells[2], cells[3].strip("`"))
    return rows


def test_security_matrix_covers_required_threats_with_offline_executable_evidence() -> None:
    rows = _matrix_rows()

    assert set(rows) == EXPECTED_THREATS
    for threat, control, evidence in rows.values():
        assert threat
        assert control
        assert evidence.startswith("python3 -m pytest -q tests/")
        assert "::test_" in evidence or evidence == "python3 -m pytest -q tests/test_preflight.py"
        assert not any(
            forbidden in evidence.lower()
            for forbidden in ("http://", "https://", "curl ", "wget ", "token", "secret", "key=")
        )

        target = evidence.removeprefix("python3 -m pytest -q ")
        test_path, separator, test_name = target.partition("::")
        source_path = ROOT / test_path
        assert source_path.is_file(), f"missing evidence file: {test_path}"
        test_functions = {
            node.name
            for node in ast.parse(source_path.read_text(encoding="utf-8")).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        }
        if separator:
            assert test_name in test_functions, f"missing evidence test: {target}"
        else:
            assert test_functions, f"evidence file has no tests: {test_path}"
