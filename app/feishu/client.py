from __future__ import annotations

import json
from typing import Any

import httpx

from app.scheduler.reminder_engine import NotificationSendError

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuAPIError(Exception):
    """Raised when the Feishu API returns an error response."""


class FeishuClient:
    """Minimal Feishu Open Platform client for sending text messages."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        base_url: str = FEISHU_API_BASE,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport
        self._tenant_access_token: str | None = None

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout, transport=self._transport)

    def get_tenant_access_token(self, *, force_refresh: bool = False) -> str:
        if self._tenant_access_token and not force_refresh:
            return self._tenant_access_token
        with self._client() as client:
            response = client.post(
                "/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") != 0:
            raise FeishuAPIError(payload.get("msg", "failed to fetch tenant access token"))
        token = payload.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuAPIError("missing tenant access token in response")
        self._tenant_access_token = token
        return token

    def send_text(
        self,
        receive_id: str,
        text: str,
        *,
        receive_id_type: str = "chat_id",
    ) -> dict[str, Any]:
        token = self.get_tenant_access_token()
        with self._client() as client:
            response = client.post(
                "/im/v1/messages",
                params={"receive_id_type": receive_id_type},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": receive_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") != 0:
            raise FeishuAPIError(payload.get("msg", "failed to send message"))
        return payload

    def send_text_message(self, receive_id: str, text: str) -> dict[str, Any]:
        return self.send_text(receive_id, text)


class FeishuNotificationSender:
    """Adapter so the scheduler can deliver reminders through Feishu."""

    def __init__(self, client: FeishuClient, chat_id: str) -> None:
        self.client = client
        self.chat_id = chat_id

    def send(self, content: str) -> None:
        try:
            self.client.send_text(self.chat_id, content)
        except (FeishuAPIError, httpx.HTTPError) as exc:
            raise NotificationSendError(str(exc)) from exc
