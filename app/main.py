import httpx
from fastapi import FastAPI, HTTPException

from app.errors import RunConfigurationError
from app.models import RunRequest, TaskReport
from app.service import run_agent

app = FastAPI(
    title="Bao Agent Demo",
    version="0.1.0",
    description="Privacy-safe task extraction agent with structured tracing.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", response_model=TaskReport)
def create_run(request: RunRequest) -> TaskReport:
    try:
        return run_agent(request)
    except (RunConfigurationError, OSError):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_run_configuration"},
        ) from None
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_provider_unavailable"},
        ) from None
