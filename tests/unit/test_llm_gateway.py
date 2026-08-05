from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.server.api.ai_routes import _extract_json_object, _normalize_course
from app.server.config import Settings
from app.server.llm import gateway

pytestmark = pytest.mark.unit


def test_default_natural_language_gateway_config() -> None:
    settings = Settings()
    assert settings.llm_provider == "tokendance"
    assert settings.llm_base_url == "https://tokendance.space/gateway/v1"
    assert settings.llm_model == "deepseek-v4-flash"
    assert settings.vision_model == "deepseek-ocr-2"
    assert settings.vision_max_output_tokens == 128
    assert settings.vision_max_retries == 0
    assert settings.vision_timeout_seconds == 60
    assert settings.computer_analysis_direct_llm_enabled is True
    assert settings.computer_analysis_model == "deepseek-v4-flash"
    assert settings.computer_analysis_openclaw_fallback_enabled is False
    assert settings.computer_daily_preview_enabled is False
    assert settings.computer_daily_preview_min_interval_minutes == 240


def test_gateway_client_has_bounded_http_timeout(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(
                    prompt_tokens=120,
                    completion_tokens=30,
                    total_tokens=150,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=80),
                ),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(gateway, "OpenAI", FakeOpenAI)
    gateway._build_client.cache_clear()
    settings = Settings(
        llm_api_key="test-key",
        llm_base_url="https://tokendance.space/gateway/v1",
        llm_model="deepseek-v4-flash",
    )

    with caplog.at_level("INFO"):
        result = gateway.complete_chat(
            [{"role": "user", "content": "hello"}],
            settings=settings,
            model="deepseek-v4-flash",
            max_tokens=512,
            response_format={"type": "json_object"},
            usage_label="test_usage",
        )

    assert result == '{"ok": true}'
    client_options = captured["client"]
    assert isinstance(client_options, dict)
    assert client_options["base_url"] == "https://tokendance.space/gateway/v1"
    timeout = client_options["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 120
    assert timeout.read == 120
    assert timeout.write == 120
    assert timeout.pool == 120
    request = captured["request"]
    assert isinstance(request, dict)
    assert request["model"] == "deepseek-v4-flash"
    assert request["max_tokens"] == 512
    assert request["response_format"] == {"type": "json_object"}
    assert (
        "llm_usage label=test_usage model=deepseek-v4-flash input_tokens=120 "
        "output_tokens=30 total_tokens=150 cached_tokens=80"
    ) in caplog.text


def test_image_gateway_bounds_ocr_output_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="识别结果"))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(gateway, "OpenAI", FakeOpenAI)
    gateway._build_client.cache_clear()
    settings = Settings(
        llm_api_key="test-key",
        vision_model="deepseek-ocr-2",
        vision_max_output_tokens=64,
        vision_max_retries=0,
        vision_timeout_seconds=30,
    )

    assert (
        gateway.analyze_image(
            b"image",
            mime_type="image/png",
            prompt="Free OCR.",
            settings=settings,
        )
        == "识别结果"
    )
    client_options = captured["client"]
    assert isinstance(client_options, dict)
    timeout = client_options["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 30
    assert client_options["max_retries"] == 0
    request = captured["request"]
    assert isinstance(request, dict)
    assert request["model"] == "deepseek-ocr-2"
    assert request["max_tokens"] == 64


def test_existing_deepseek_key_is_only_an_api_key_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="done"))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(gateway, "OpenAI", FakeOpenAI)
    gateway._build_client.cache_clear()
    settings = Settings(
        llm_api_key="",
        deepseek_api_key="legacy-key",
        deepseek_base_url="https://api.deepseek.com",
    )

    assert (
        gateway.complete_chat(
            [{"role": "user", "content": "hello"}],
            settings=settings,
        )
        == "done"
    )
    assert captured["api_key"] == "legacy-key"
    assert captured["base_url"] == "https://tokendance.space/gateway/v1"


def test_json_extraction_accepts_fenced_or_explained_output() -> None:
    assert _extract_json_object('```json\n{"courseName":"Math"}\n```') == {"courseName": "Math"}
    assert _extract_json_object('解析结果如下：\n{"courseName":"Math"}\n请确认') == {
        "courseName": "Math"
    }


def test_course_normalization_accepts_human_week_numbers() -> None:
    parsed = _normalize_course(
        {
            "courseName": "Robotics",
            "weekDay": "星期二",
            "startWeek": "第1周",
            "endWeek": "第16周",
        }
    )
    assert parsed["weekDay"] == 2
    assert parsed["startWeek"] == 1
    assert parsed["endWeek"] == 16
