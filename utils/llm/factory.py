from typing import Any, TypeVar

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from .config import (
    DEFAULT_LLM_CONFIG,
    DEFAULT_TEMPERATURE,
)

T = TypeVar("T", bound=BaseModel)


def get_llm(
    model: str = DEFAULT_LLM_CONFIG["model"],
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_LLM_CONFIG["max_tokens"],
    timeout: int = DEFAULT_LLM_CONFIG["timeout"],
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
        model=DEFAULT_LLM_CONFIG["model"],
        temperature=DEFAULT_LLM_CONFIG["temperature"],
        max_tokens=DEFAULT_LLM_CONFIG["max_tokens"],
        timeout=DEFAULT_LLM_CONFIG["timeout"],
        **kwargs,
    )


def get_structured_llm(
    output_schema: type[T],
    model: str = DEFAULT_LLM_CONFIG["model"],
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_LLM_CONFIG["max_tokens"],
    timeout: int = DEFAULT_LLM_CONFIG["timeout"],
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


def get_structured_mini_llm(output_schema: type[T], **kwargs) -> Runnable[Any, T]:
    return get_structured_llm(
        output_schema=output_schema,
        model=DEFAULT_LLM_CONFIG["model"],
        temperature=DEFAULT_LLM_CONFIG["temperature"],
        max_tokens=DEFAULT_LLM_CONFIG["max_tokens"],
        timeout=DEFAULT_LLM_CONFIG["timeout"],
        **kwargs,
    )
