import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any, List, Optional, Type, TypeVar

import openai
from pydantic import BaseModel

from .config import ReviewStemConfig
from .logger import logger

T = TypeVar("T", bound=BaseModel)


def _normalize_message(m: Any) -> Any:
    """Coerce a message into a JSON-serializable dict for cache hashing.

    OpenAI's tool-call loop echoes the assistant turn back as a
    ``ChatCompletionMessage`` pydantic object (see motor_cortex draft review);
    a raw ``json.dumps`` over the messages list would crash on it.
    """
    if isinstance(m, dict):
        return m
    if hasattr(m, "model_dump"):
        return m.model_dump(mode="json", exclude_none=True)
    if hasattr(m, "to_dict"):
        return m.to_dict()
    return str(m)


def _cache_key(model: str, messages: list, schema_name: str, temperature: float, seed: int | None) -> str:
    normalized = [_normalize_message(m) for m in messages]
    payload = json.dumps(
        {
            "model": model,
            "messages": normalized,
            "schema": schema_name,
            "temperature": temperature,
            "seed": seed,
        },
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class LLMClient:
    def __init__(
        self,
        config: ReviewStemConfig | None = None,
        seed: int | None = None,
        temperature: float | None = None,
        cache_dir: Path | str | None = None,
    ):
        self.config = config or ReviewStemConfig.from_env()
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Create a .env file or export it before running ReviewStem.")

        self.client = openai.AsyncOpenAI(api_key=self.api_key)
        self.model = self.config.model
        self.temperature = self.config.temperature if temperature is None else temperature
        self.seed = seed
        self.call_count = 0
        self.cache_hits = 0
        self.call_log: list[dict[str, Any]] = []
        self.cache_dir: Path | None = Path(cache_dir) if cache_dir else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{key}.json"

    def _cache_get_parsed(self, key: str, schema: Type[T]) -> T | None:
        path = self._cache_path(key)
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("kind") != "parse":
                return None
            return schema.model_validate(payload["data"])
        except Exception as e:
            logger.warning("LLM cache miss for %s: %s", key[:8], e)
            return None

    def _cache_put_parsed(self, key: str, obj: BaseModel) -> None:
        path = self._cache_path(key)
        if path is None:
            return
        path.write_text(
            json.dumps({"kind": "parse", "data": obj.model_dump()}, indent=2),
            encoding="utf-8",
        )

    def _cache_get_text(self, key: str) -> str | None:
        path = self._cache_path(key)
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("kind") != "generate":
                return None
            return payload["data"]
        except Exception:
            return None

    def _cache_put_text(self, key: str, text: str) -> None:
        path = self._cache_path(key)
        if path is None:
            return
        path.write_text(
            json.dumps({"kind": "generate", "data": text}, indent=2),
            encoding="utf-8",
        )

    async def parse(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: str = "You are a precise, professional code review assistant.",
        tools: Optional[List[dict]] = None,
        messages: Optional[List[dict]] = None,
        stage: str = "parse",
    ) -> T:
        """Invoke the OpenAI structured-output parser with retries."""
        max_retries = 3

        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

        cache_key = _cache_key(self.model, messages, schema.__name__, self.temperature, self.seed)
        cached = self._cache_get_parsed(cache_key, schema)
        if cached is not None:
            self.cache_hits += 1
            self.call_count += 1
            self.call_log.append({"stage": stage, "cached": True})
            return cached

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "response_format": schema,
            "temperature": self.temperature,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed
        if tools:
            kwargs["tools"] = tools

        for attempt in range(max_retries):
            try:
                response = await self.client.beta.chat.completions.parse(**kwargs)
                self._record_call(stage, response)
                parsed = response.choices[0].message.parsed
                if parsed:
                    self._cache_put_parsed(cache_key, parsed)
                    return parsed
                logger.error("LLM returned None instead of parsed schema.")
            except openai.RateLimitError:
                logger.warning("Rate limit hit. Retrying in %s seconds.", 2**attempt)
                await asyncio.sleep(2**attempt)
            except Exception as e:
                logger.error("LLM parsing error: %s", e)
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1)

        raise RuntimeError("Failed to generate structured output after retries.")

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "You are a precise, professional code review assistant.",
        stage: str = "generate",
    ) -> str:
        """Generate plain text from the configured model."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        cache_key = _cache_key(self.model, messages, "_text_", self.temperature, self.seed)
        cached = self._cache_get_text(cache_key)
        if cached is not None:
            self.cache_hits += 1
            self.call_count += 1
            self.call_log.append({"stage": stage, "cached": True})
            return cached

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed

        response = await self.client.chat.completions.create(**kwargs)
        self._record_call(stage, response)
        text = response.choices[0].message.content or ""
        self._cache_put_text(cache_key, text)
        return text

    def _record_call(self, stage: str, response: Any) -> None:
        self.call_count += 1
        usage = getattr(response, "usage", None)
        self.call_log.append(
            {
                "stage": stage,
                "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
            }
        )
