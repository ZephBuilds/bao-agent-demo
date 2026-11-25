import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from scripts import security_check

ROOT = Path(__file__).parents[1]
README = ROOT / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
COMMAND = "python3 scripts/security_check.py"
CI_CLAIM = f"CI ejecuta exactamente el mismo comando canónico local: `{COMMAND}`."


def test_security_check_stops_after_failed_preflight() -> None:
    failure_code = 23
    preflight_command = (sys.executable, "scripts/preflight.py")

    with patch(
        "scripts.security_check.subprocess.run",
        side_effect=subprocess.CalledProcessError(failure_code, preflight_command),
    ) as run:
        result = security_check.main()

    assert result == failure_code
    run.assert_called_once_with(preflight_command, cwd=security_check.ROOT, check=True)


def test_security_check_is_documented_once_matches_ci_and_is_fail_fast_and_offline() -> None:
    readme = README.read_text(encoding="utf-8")
    workflow_steps = [
        line.strip() for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
    ]
    source = (ROOT / "scripts" / "security_check.py").read_text(encoding="utf-8")
    commands = [command for _, command in security_check.GATES]

    assert readme.count(COMMAND) == 2
    assert readme.count(CI_CLAIM) == 1
    assert workflow_steps.count(f"- run: {COMMAND}") == 1
    assert "[matriz de amenazas y controles](SECURITY.md)" in readme
    assert commands[0] == (sys.executable, "scripts/preflight.py")
    assert all(command[0] == sys.executable for command in commands)
    assert commands[1][1:4] == ("-m", "pytest", "-q")

    contract_targets = set(commands[1][4:])
    assert len(contract_targets) == len(commands[1][4:])
    assert len({label for label, _ in security_check.GATES}) == len(security_check.GATES)
    assert "tests/test_security_contract.py" in contract_targets
    assert any(target.startswith("tests/test_dockerfile.py::") for target in contract_targets)
    assert sum(target.startswith("tests/test_ci_workflow.py::") for target in contract_targets) == 2
    assert "check=True" in source
    assert "shell=True" not in source
    assert not any(
        forbidden in " ".join(command).lower()
        for command in commands
        for forbidden in ("http://", "https://", "curl ", "wget ", "pip install")
    )
