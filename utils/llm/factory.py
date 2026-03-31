from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

from .config import (
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT,
    MINI_LLM_CONFIG,
)


def get_llm(
    model: str = "gpt-4o-mini",
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT,
    **kwargs,
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        **kwargs,
    )


def get_mini_llm(**kwargs) -> ChatOpenAI:
    return get_llm(
        model=MINI_LLM_CONFIG["model"],
        temperature=MINI_LLM_CONFIG["temperature"],
        max_tokens=MINI_LLM_CONFIG["max_tokens"],
        timeout=MINI_LLM_CONFIG["timeout"],
        **kwargs,
    )


def get_structured_llm(
    output_schema: Type[T],
    model: str = "gpt-4o-mini",
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT,
    **kwargs,
) -> Runnable[Any, T]:
    base_llm = get_llm(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        **kwargs,
    )
    return base_llm.with_structured_output(output_schema, include_raw=False)


def get_structured_mini_llm(output_schema: Type[T], **kwargs) -> Runnable[Any, T]:
    return get_structured_llm(
        output_schema=output_schema,
        model=MINI_LLM_CONFIG["model"],
        temperature=MINI_LLM_CONFIG["temperature"],
        max_tokens=MINI_LLM_CONFIG["max_tokens"],
        timeout=MINI_LLM_CONFIG["timeout"],
        **kwargs,
    )
