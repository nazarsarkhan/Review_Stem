import asyncio
import os
from pathlib import Path
from typing import Any, List, Optional, Type, TypeVar

import openai
from dotenv import load_dotenv
from pydantic import BaseModel

from .config import ReviewStemConfig
from .logger import logger

load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.home() / ".reviewstem" / ".env")

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, config: ReviewStemConfig | None = None):
        self.config = config or ReviewStemConfig.from_env()
        self.api_key = openai.api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Create a .env file or export it before running ReviewStem.")

        self.client = openai.AsyncOpenAI(api_key=self.api_key)
        self.model = self.config.model
        self.temperature = self.config.temperature
        self.call_count = 0
        self.call_log: list[dict[str, Any]] = []

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

        kwargs = {
            "model": self.model,
            "messages": messages,
            "response_format": schema,
            "temperature": self.temperature,
        }

        if tools:
            kwargs["tools"] = tools

        for attempt in range(max_retries):
            try:
                response = await self.client.beta.chat.completions.parse(**kwargs)
                self._record_call(stage, response)
                parsed = response.choices[0].message.parsed
                if parsed:
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
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
        )
        self._record_call(stage, response)
        return response.choices[0].message.content or ""

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
