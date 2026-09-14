from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import InterpretRequest, InterpretResponse
from .service import TafseerService

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type", "Authorization"],
)
service = TafseerService()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "Tafseer HAI"}


@app.post("/v1/interpret", response_model=InterpretResponse)
async def interpret(request: InterpretRequest) -> InterpretResponse:
    return await service.interpret_step(request)
