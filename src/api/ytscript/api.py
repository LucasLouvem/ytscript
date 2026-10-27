from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from infra.errors import InvalidUrlError, YTScriptError
from ytscript.controllers.transcript_controller import get_transcript_details
from ytscript.views.transcript_view import build_details_payload

WEB_DIR = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="YTScript")


class TranscriptRequest(BaseModel):
    url: str
    language: str | None = None
    translate_to: str | None = None


@app.exception_handler(YTScriptError)
async def handle_ytscript_error(request: Request, error: YTScriptError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error.to_dict())


@app.exception_handler(RequestValidationError)
async def handle_invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    invalid_url = InvalidUrlError()
    return JSONResponse(status_code=invalid_url.status_code, content=invalid_url.to_dict())


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/transcripts")
def create_transcript(body: TranscriptRequest) -> dict:
    details = get_transcript_details(
        body.url, language=body.language, translate_to=body.translate_to
    )
    return build_details_payload(details)


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
