"""Run the offline security gates with one fail-fast command."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GATES = (
    (
        "public-release preflight",
        (sys.executable, "scripts/preflight.py"),
    ),
    (
        "security contracts",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_security_contract.py",
            "tests/test_dockerfile.py::test_runtime_uses_fixed_non_root_user_with_owned_app_files",
            "tests/test_ci_workflow.py::test_dependency_audit_is_a_blocking_gate_before_container_build",
            "tests/test_ci_workflow.py::test_container_smoke_gate_runs_once_between_build_and_pytest",
        ),
    ),
)


def main() -> int:
    try:
        for label, command in GATES:
            print(f"[security] {label}", flush=True)
            subprocess.run(command, cwd=ROOT, check=True)
    except subprocess.CalledProcessError as error:
        return error.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
