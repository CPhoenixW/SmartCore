from __future__ import annotations

from typing import TYPE_CHECKING

from app.feishu.client import FeishuClient

if TYPE_CHECKING:
    from app.feishu.event_handler import FeishuEventHandler, create_feishu_router

__all__ = ["FeishuClient", "FeishuEventHandler", "create_feishu_router"]


def __getattr__(name: str):
    if name == "FeishuEventHandler":
        from app.feishu.event_handler import FeishuEventHandler

        return FeishuEventHandler
    if name == "create_feishu_router":
        from app.feishu.event_handler import create_feishu_router

        return create_feishu_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
