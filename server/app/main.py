from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import InterpretRequest, InterpretResponse
from .service import TafseerService

app = FastAPI(title=settings.app_name, version="1.0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type", "Authorization"],
)
service = TafseerService()


def _configured_providers() -> list[str]:
    providers: list[str] = []
    if settings.gemini_api_key:
        providers.append("gemini")
    if settings.openrouter_api_key:
        providers.append("openrouter")
    return providers


@app.get("/health")
async def health() -> dict:
    providers = _configured_providers()
    return {
        "status": "ok",
        "service": "Tafseer HAI",
        "ai_ready": bool(providers),
        "providers": providers,
    }


@app.post("/v1/interpret", response_model=InterpretResponse)
async def interpret(request: InterpretRequest) -> InterpretResponse:
    if not _configured_providers():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ai_provider_not_configured",
                "message": "No AI provider is configured for Tafseer HAI.",
            },
        )
    return await service.interpret_step(request)
