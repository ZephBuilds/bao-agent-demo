import re
from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "test.yml"
DEV_REQUIREMENTS = Path(__file__).parents[1] / "requirements-dev.txt"


def test_actions_are_pinned_to_immutable_commits() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    action_references = re.findall(r"uses:\s+([^\s#]+)", workflow)

    assert action_references
    for reference in action_references:
        _, separator, revision = reference.rpartition("@")
        assert separator == "@"
        assert re.fullmatch(r"[0-9a-f]{40}", revision)


def test_pytest_requirement_stays_on_the_patched_major_version() -> None:
    requirements = DEV_REQUIREMENTS.read_text(encoding="utf-8").splitlines()

    pytest_requirements = [line for line in requirements if line.startswith("pytest")]

    assert pytest_requirements == ["pytest>=9.0.3,<10"]


def test_dependency_audit_is_a_blocking_gate_before_container_build() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    requirements = DEV_REQUIREMENTS.read_text(encoding="utf-8")
    steps = [line.strip() for line in workflow.splitlines()]

    ruff_step = "- run: ruff check ."
    security_step = "- run: python3 scripts/security_check.py"
    audit_name = "- name: Audit runtime dependencies"
    audit_command = "run: pip-audit --requirement requirements.txt --strict"
    docker_build_step = "- run: docker build -t bao-agent-demo ."

    assert "pip-audit>=2.9,<3" in requirements.splitlines()
    assert steps.count(ruff_step) == 1
    assert steps.count(security_step) == 1
    assert "- run: python3 scripts/preflight.py" not in steps
    assert steps.count(audit_name) == 1
    assert steps.count(audit_command) == 1
    assert steps.count(docker_build_step) == 1
    assert (
        steps.index(ruff_step)
        < steps.index(security_step)
        < steps.index(audit_name)
        < steps.index(audit_command)
        < steps.index(docker_build_step)
    )

    audit_block = workflow[
        workflow.index("      - name: Audit runtime dependencies") : workflow.index(
            "      - run: docker build -t bao-agent-demo ."
        )
    ]
    assert "continue-on-error" not in audit_block
    assert "ignore-vuln" not in audit_block
    assert "secrets." not in audit_block


def test_container_smoke_gate_runs_once_between_build_and_pytest() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    steps = [line.strip() for line in workflow.splitlines()]

    security_step = "- run: python3 scripts/security_check.py"
    docker_build_step = "- run: docker build -t bao-agent-demo ."
    smoke_step = "- name: Smoke test container"
    pytest_step = "- run: python3 -m pytest"

    assert steps.count(security_step) == 1
    assert steps.count(docker_build_step) == 1
    assert steps.count(smoke_step) == 1
    assert steps.count(pytest_step) == 1
    assert (
        steps.index(security_step)
        < steps.index(docker_build_step)
        < steps.index(smoke_step)
        < steps.index(pytest_step)
    )

    smoke_block = workflow[
        workflow.index("      - name: Smoke test container") : workflow.index(
            "      - run: python3 -m pytest"
        )
    ]
    container_name = 'container_name="bao-agent-demo-ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"'
    cleanup = "trap 'docker rm -f \"$container_name\" >/dev/null 2>&1 || true' EXIT"
    docker_run = 'docker run -d --network none --name "$container_name" bao-agent-demo'
    health_request = 'urlopen("http://127.0.0.1:8000/health")'
    exact_response = """if [ "$response" = '{"status":"ok"}' ]; then"""

    assert smoke_block.count(container_name) == 1
    assert smoke_block.count(cleanup) == 1
    assert smoke_block.count(docker_run) == 1
    assert " -p " not in smoke_block
    assert "--publish" not in smoke_block
    assert smoke_block.count(health_request) == 1
    assert smoke_block.count(exact_response) == 1
    assert smoke_block.index(container_name) < smoke_block.index(cleanup)
    assert smoke_block.index(cleanup) < smoke_block.index(docker_run)
    assert smoke_block.index(docker_run) < smoke_block.index(health_request)
