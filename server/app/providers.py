import asyncio
import copy
import hashlib
import json
import logging
import re
import time
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
        # A 429 is normally quota/rate-limit related. Retrying the same model a
        # fraction of a second later only burns latency. The router switches model.
        return exc.response.status_code in {408, 409, 425, 500, 502, 503, 504}
    return isinstance(exc, (json.JSONDecodeError, ValueError, KeyError, TypeError))


class ModelRouter:
    CACHE_TTL_SECONDS = 15 * 60
    CACHE_MAX_ITEMS = 128
    RATE_LIMIT_COOLDOWN_SECONDS = 120
    CAPACITY_COOLDOWN_SECONDS = 20

    def __init__(self) -> None:
        self.timeout = httpx.Timeout(55.0, connect=12.0)
        self._cooldown_until: dict[str, float] = {}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _gemini_models() -> list[str]:
        # Quality first. Lite models are deliberate production fallbacks for
        # high-throughput stages and free-tier pressure, not random legacy models.
        ordered = [
            settings.primary_model,
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
        ]
        unique: list[str] = []
        for model in ordered:
            model = str(model or "").strip()
            if model and model not in unique:
                unique.append(model)
        return unique

    def _cache_key(self, system: str, user: str) -> str:
        return hashlib.sha256((system + "\n\u241f\n" + user).encode("utf-8")).hexdigest()

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        item = self._cache.get(key)
        if item is None:
            return None
        created_at, payload = item
        if time.monotonic() - created_at > self.CACHE_TTL_SECONDS:
            self._cache.pop(key, None)
            return None
        return copy.deepcopy(payload)

    def _put_cached(self, key: str, payload: dict[str, Any]) -> None:
        now = time.monotonic()
        self._cache[key] = (now, copy.deepcopy(payload))
        if len(self._cache) <= self.CACHE_MAX_ITEMS:
            return
        # Drop oldest entries. The cache is intentionally tiny and per-instance.
        oldest = sorted(self._cache.items(), key=lambda item: item[1][0])[
            : len(self._cache) - self.CACHE_MAX_ITEMS
        ]
        for old_key, _ in oldest:
            self._cache.pop(old_key, None)

    def _available(self, provider_key: str) -> bool:
        return time.monotonic() >= self._cooldown_until.get(provider_key, 0.0)

    def _cooldown(self, provider_key: str, seconds: int) -> None:
        self._cooldown_until[provider_key] = max(
            self._cooldown_until.get(provider_key, 0.0),
            time.monotonic() + seconds,
        )

    async def generate_json(self, system: str, user: str) -> dict[str, Any]:
        cache_key = self._cache_key(system, user)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.info("provider_cache_hit")
            return cached

        errors: list[str] = []

        if settings.gemini_api_key:
            for model in self._gemini_models():
                provider_key = f"gemini:{model}"
                if not self._available(provider_key):
                    logger.info("provider_skipped_cooldown provider=gemini model=%s", model)
                    continue
                try:
                    result = await self._with_retry(
                        provider_key,
                        lambda model=model: self._gemini(system, user, model),
                    )
                    self._put_cached(cache_key, result)
                    return result
                except Exception as exc:
                    label = _error_label(exc)
                    if isinstance(exc, httpx.HTTPStatusError):
                        status = exc.response.status_code
                        if status == 429:
                            self._cooldown(provider_key, self.RATE_LIMIT_COOLDOWN_SECONDS)
                        elif status in {500, 502, 503, 504}:
                            self._cooldown(provider_key, self.CAPACITY_COOLDOWN_SECONDS)
                    logger.warning(
                        "provider_failed provider=gemini model=%s error=%s",
                        model,
                        label,
                    )
                    errors.append(f"gemini:{model}:{label}")

        if settings.openrouter_api_key:
            provider_key = "openrouter"
            if self._available(provider_key):
                try:
                    result = await self._with_retry(
                        provider_key,
                        lambda: self._openrouter(system, user),
                    )
                    self._put_cached(cache_key, result)
                    return result
                except Exception as exc:
                    label = _error_label(exc)
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                        self._cooldown(provider_key, self.RATE_LIMIT_COOLDOWN_SECONDS)
                    logger.warning("provider_failed provider=openrouter error=%s", label)
                    errors.append(f"openrouter:{label}")

        if not errors:
            raise ProviderUnavailable("No AI provider is currently available")
        raise ProviderUnavailable("All configured AI providers failed: " + " | ".join(errors))

    async def _with_retry(
        self,
        provider: str,
        call: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return await call()
            except Exception as exc:
                last_error = exc
                # Never retry the same model immediately on quota exhaustion.
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    raise
                if attempt == 1 or not _retryable(exc):
                    raise
                logger.info(
                    "provider_retry provider=%s attempt=%s error=%s",
                    provider,
                    attempt + 1,
                    _error_label(exc),
                )
                await asyncio.sleep(1.0 + attempt * 1.5)
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
                "temperature": 0.15,
                "maxOutputTokens": 4096,
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
            "temperature": 0.15,
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
