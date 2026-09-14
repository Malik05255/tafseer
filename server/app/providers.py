import asyncio
import json
import logging
import re
from typing import Any, Awaitable, Callable

import httpx

from .config import settings


logger = logging.getLogger("tafseer.providers")


class ProviderUnavailable(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Provider returned JSON that is not an object")
    return parsed


def _error_label(exc: Exception) -> str:
    # Never include request URLs here: the Gemini key is a query parameter.
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    return type(exc).__name__


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}
    return isinstance(exc, (json.JSONDecodeError, ValueError, KeyError, TypeError))


class ModelRouter:
    def __init__(self) -> None:
        self.timeout = httpx.Timeout(55.0, connect=12.0)

    @staticmethod
    def _gemini_models() -> list[str]:
        # Keep quality first, but do not let a transient outage on one Gemini model
        # take down the whole tafseer session. These are stable production models.
        ordered = [
            settings.primary_model,
            "gemini-3.6-flash",
            "gemini-2.5-flash",
        ]
        unique: list[str] = []
        for model in ordered:
            model = str(model or "").strip()
            if model and model not in unique:
                unique.append(model)
        return unique

    async def generate_json(self, system: str, user: str) -> dict[str, Any]:
        errors: list[str] = []

        if settings.gemini_api_key:
            for model in self._gemini_models():
                try:
                    return await self._with_retry(
                        f"gemini:{model}",
                        lambda model=model: self._gemini(system, user, model),
                    )
                except Exception as exc:
                    label = _error_label(exc)
                    logger.warning(
                        "provider_failed provider=gemini model=%s error=%s",
                        model,
                        label,
                    )
                    errors.append(f"gemini:{model}:{label}")

        if settings.openrouter_api_key:
            try:
                return await self._with_retry(
                    "openrouter",
                    lambda: self._openrouter(system, user),
                )
            except Exception as exc:
                label = _error_label(exc)
                logger.warning("provider_failed provider=openrouter error=%s", label)
                errors.append(f"openrouter:{label}")

        if not errors:
            raise ProviderUnavailable("No AI provider key configured")
        raise ProviderUnavailable("All configured AI providers failed: " + " | ".join(errors))

    async def _with_retry(
        self,
        provider: str,
        call: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        # One short retry per model absorbs transient capacity/JSON issues. If that
        # still fails, move to the next model instead of burning the whole timeout.
        for attempt in range(2):
            try:
                return await call()
            except Exception as exc:
                last_error = exc
                if attempt == 1 or not _retryable(exc):
                    raise
                logger.info(
                    "provider_retry provider=%s attempt=%s error=%s",
                    provider,
                    attempt + 1,
                    _error_label(exc),
                )
                await asyncio.sleep(0.6)
        assert last_error is not None
        raise last_error

    async def _gemini(self, system: str, user: str, model: str) -> dict[str, Any]:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
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
        if not text.strip():
            raise ValueError("Gemini returned empty text")
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
        choices = data.get("choices") or []
        if not choices:
            raise ProviderUnavailable("OpenRouter returned no choice")
        content = choices[0].get("message", {}).get("content", "")
        if not content.strip():
            raise ValueError("OpenRouter returned empty content")
        return _extract_json(content)
