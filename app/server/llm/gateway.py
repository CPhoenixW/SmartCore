from __future__ import annotations

import base64
from functools import lru_cache
from typing import Any

import httpx
import openai
from openai import OpenAI

from app.server.config import Settings, get_settings


class LLMConfigurationError(RuntimeError):
    """Raised when the natural-language gateway is not configured."""


class LLMGatewayError(RuntimeError):
    """Raised when the natural-language gateway request fails."""


@lru_cache(maxsize=8)
def _build_client(
    api_key: str,
    base_url: str,
    max_retries: int,
    timeout_seconds: int,
) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(float(timeout_seconds)),
        max_retries=max_retries,
    )


def _effective_api_key(settings: Settings) -> str:
    # DEEPSEEK_API_KEY is accepted as a compatibility fallback for existing deployments.
    return (settings.llm_api_key or settings.deepseek_api_key).strip()


def complete_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0,
    settings: Settings | None = None,
    extra_body: dict[str, Any] | None = None,
) -> str:
    """Run one natural-language request through the configured TokenDance gateway."""
    active_settings = settings or get_settings()
    api_key = _effective_api_key(active_settings)
    if not api_key:
        raise LLMConfigurationError(
            "LLM_API_KEY 未配置；请在 deploy/.env 中填写中转站 API Key"
        )

    client = _build_client(
        api_key,
        active_settings.llm_base_url,
        active_settings.llm_max_retries,
        active_settings.llm_timeout_seconds,
    )
    request: dict[str, Any] = {
        "model": active_settings.llm_model,
        "messages": messages,
        "temperature": temperature,
    }
    if extra_body is not None:
        request["extra_body"] = extra_body

    try:
        response = client.chat.completions.create(**request)
    except openai.APIStatusError as exc:
        request_id = f"，request_id={exc.request_id}" if exc.request_id else ""
        raise LLMGatewayError(
            f"中转站返回 HTTP {exc.status_code}{request_id}"
        ) from exc
    except openai.APIConnectionError as exc:
        raise LLMGatewayError(f"无法连接中转站：{exc}") from exc
    except openai.APIError as exc:
        raise LLMGatewayError(f"中转站请求失败：{exc}") from exc

    if not response.choices:
        raise LLMGatewayError("中转站没有返回候选结果")
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise LLMGatewayError("中转站返回了空内容")
    return content.strip()


def analyze_image(
    image: bytes,
    *,
    mime_type: str,
    prompt: str,
    settings: Settings | None = None,
) -> str:
    """Describe an inbound image through the configured vision model."""
    active_settings = settings or get_settings()
    api_key = _effective_api_key(active_settings)
    if not api_key:
        raise LLMConfigurationError("LLM_API_KEY 未配置；无法解析图片")
    if not image:
        raise LLMGatewayError("图片内容为空")

    encoded = base64.b64encode(image).decode("ascii")
    client = _build_client(
        api_key,
        active_settings.llm_base_url,
        active_settings.vision_max_retries,
        active_settings.vision_timeout_seconds,
    )
    try:
        response = client.chat.completions.create(
            model=active_settings.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                        },
                    ],
                }
            ],
            temperature=0,
            max_tokens=active_settings.vision_max_output_tokens,
        )
    except openai.APIStatusError as exc:
        request_id = f"，request_id={exc.request_id}" if exc.request_id else ""
        raise LLMGatewayError(f"视觉模型返回 HTTP {exc.status_code}{request_id}") from exc
    except openai.APIConnectionError as exc:
        raise LLMGatewayError(f"无法连接视觉模型：{exc}") from exc
    except openai.APIError as exc:
        raise LLMGatewayError(f"视觉模型请求失败：{exc}") from exc
    if not response.choices:
        raise LLMGatewayError("视觉模型没有返回候选结果")
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise LLMGatewayError("视觉模型返回了空内容")
    return content.strip()
