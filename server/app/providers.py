import json
import re
from typing import Any

import httpx

from .config import settings


class ProviderUnavailable(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


class ModelRouter:
    def __init__(self) -> None:
        self.timeout = httpx.Timeout(70.0, connect=15.0)

    suspend_placeholder = None

    async def generate_json(self, system: str, user: str) -> dict[str, Any]:
        errors: list[str] = []

        if settings.gemini_api_key:
            try:
                return await self._gemini(system, user)
            except Exception as exc:  # fallback must survive provider outages/quotas
                errors.append(f"gemini: {exc}")

        if settings.openrouter_api_key:
            try:
                return await self._openrouter(system, user)
            except Exception as exc:
                errors.append(f"openrouter: {exc}")

        if not errors:
            raise ProviderUnavailable("No AI provider key configured")
        raise ProviderUnavailable("All configured AI providers failed: " + " | ".join(errors))

    async def _gemini(self, system: str, user: str) -> dict[str, Any]:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.primary_model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                params={"key": settings.gemini_api_key},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderUnavailable("Gemini returned no candidate")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        return _extract_json(text)

    async def _openrouter(self, system: str, user: str) -> dict[str, Any]:
        payload = {
            "model": settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "X-Title": "Tafseer HAI",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return _extract_json(content)
