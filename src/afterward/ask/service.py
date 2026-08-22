"""HTTP in front of :class:`afterward.ask.api.Assistant`.

Three routes. ``POST /ask`` is the conversation. ``GET /health`` says whether a model is
configured, which dataset is loaded, and what the limits are, and carries no counters a
visitor could use to learn about other visitors. ``GET /`` is a one-line description.

CORS is locked to the site origin(s) in ``AFTERWARD_AI_ALLOWED_ORIGINS``; with none set only
same-origin and non-browser callers can reach it, which is what local development is. The
service never sets a cookie and never reads one.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from afterward.ask import PROMPT_VERSION
from afterward.ask.api import AskRequest, AskResponse, Assistant
from afterward.ask.dataset import DEFAULT_DATASET_DIR, Dataset
from afterward.ask.limits import LimitExceeded, Limits, Meter
from afterward.ask.provider import provider_from_env

ALLOWED_ORIGINS_ENV = "AFTERWARD_AI_ALLOWED_ORIGINS"
SITE_ROOT_ENV = "AFTERWARD_AI_SITE_ROOT"


def create_app(assistant: Assistant, *, allowed_origins: Sequence[str] = ()) -> FastAPI:
    app = FastAPI(title="afterward.ask", docs_url=None, redoc_url=None, openapi_url=None)
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["POST", "GET"],
            allow_headers=["content-type"],
            allow_credentials=False,
            max_age=600,
        )

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "afterward.ask",
            "about": "AI at the edges; the published dataset is the only evidence.",
            "adr": "docs/adr/0003-runtime-ai-at-the-edges.md",
        }

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "ai": "configured" if assistant.available else "off",
            "provider": assistant.provider.name if assistant.provider else None,
            "model": assistant.provider.model if assistant.provider else None,
            "prompt_version": PROMPT_VERSION,
            "snapshot_date": assistant.dataset.snapshot_date,
            "is_fixture": assistant.dataset.is_fixture,
            "programs": len(assistant.dataset.programs),
            "occupations": len(assistant.dataset.occupations),
            "limits": assistant.meter.limits.as_dict(),
        }

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest, request: Request) -> AskResponse:
        return assistant.ask(body, client_key=client_key(request))

    @app.exception_handler(LimitExceeded)
    def limited(_: Request, exc: LimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"status": "limited", "scope": exc.scope, "retry_after": exc.retry_after},
            headers={"Retry-After": str(exc.retry_after)},
        )

    return app


def client_key(request: Request) -> str:
    """Who to rate-limit. The connecting address, or the first forwarded one behind a proxy.

    Not logged, not stored beyond the in-memory window, never returned to anyone.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def app_from_env(dataset_dir: Path | None = None) -> FastAPI:
    """What ``make ask-serve`` and the Lambda handler build: everything from the environment."""
    dataset = Dataset.load(
        dataset_dir or Path(os.environ.get("AFTERWARD_DATASET_DIR", DEFAULT_DATASET_DIR))
    )
    assistant = Assistant(
        dataset,
        provider_from_env(),
        meter=Meter(limits=Limits.from_env()),
        site_root=os.environ.get(SITE_ROOT_ENV, ""),
    )
    origins = [o.strip() for o in os.environ.get(ALLOWED_ORIGINS_ENV, "").split(",") if o.strip()]
    return create_app(assistant, allowed_origins=origins)
