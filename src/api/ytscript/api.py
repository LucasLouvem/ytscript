import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from infra.errors import InvalidApiKeyError, InvalidUrlError, YTScriptError
from ytscript.controllers.transcript_controller import get_transcript_details
from ytscript.api_keys import api_keys_from_env
from ytscript.rate_limiter import key_limiter_from_env, limiter_from_env
from ytscript.views.transcript_view import build_details_payload

WEB_DIR = Path(__file__).resolve().parents[3] / "public"

app = FastAPI(title="YTScript")
rate_limiter = limiter_from_env()
key_rate_limiter = key_limiter_from_env()
api_keys = api_keys_from_env()


class TranscriptRequest(BaseModel):
    url: str
    language: str | None = None
    translate_to: str | None = None


def client_key(request: Request) -> str:
    if os.environ.get("VERCEL"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.exception_handler(YTScriptError)
async def handle_ytscript_error(request: Request, error: YTScriptError) -> JSONResponse:
    headers = {}
    retry_after = getattr(error, "retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(status_code=error.status_code, content=error.to_dict(), headers=headers)


@app.exception_handler(RequestValidationError)
async def handle_invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    invalid_url = InvalidUrlError()
    return JSONResponse(status_code=invalid_url.status_code, content=invalid_url.to_dict())


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/transcripts")
def create_transcript(
    body: TranscriptRequest,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict:
    try:
        key_id = api_keys.authenticate(x_api_key)
    except InvalidApiKeyError:
        rate_limiter.check(client_key(request))
        raise
    if key_id:
        key_rate_limiter.check(key_id)
    else:
        rate_limiter.check(client_key(request))
    details = get_transcript_details(
        body.url, language=body.language, translate_to=body.translate_to
    )
    return build_details_payload(details)


if not os.environ.get("VERCEL"):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
