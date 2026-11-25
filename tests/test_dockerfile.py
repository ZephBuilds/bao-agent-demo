from pathlib import Path

DOCKERFILE = Path(__file__).parents[1] / "Dockerfile"
APP_ID = "10001"


def test_runtime_uses_fixed_non_root_user_with_owned_app_files() -> None:
    lines = [
        line.strip()
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert APP_ID != "0"
    assert f"groupadd --gid {APP_ID} app" in " ".join(lines)
    assert f"useradd --uid {APP_ID} --gid {APP_ID}" in " ".join(lines)

    runtime_copies = {
        f"COPY --chown={APP_ID}:{APP_ID} app ./app",
        f"COPY --chown={APP_ID}:{APP_ID} fixtures ./fixtures",
        f"COPY --chown={APP_ID}:{APP_ID} cli.py .",
    }
    assert runtime_copies <= set(lines)

    user_line = f"USER {APP_ID}:{APP_ID}"
    assert lines.count(user_line) == 1
    assert lines.index(user_line) < next(
        index for index, line in enumerate(lines) if line.startswith("CMD ")
    )
