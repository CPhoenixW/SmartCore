from __future__ import annotations

import pytest

from app.server.agent.legacy_time_routes import createLegacyTimeRouter
from app.server.agent.v2_routes import _normalize_query_body, _resolved_iso, createAgentV2Router


def test_agent_normalizes_utc_and_naive_times_to_shanghai() -> None:
    context = {
        "timezone": "Asia/Shanghai",
        "request": {
            "timezone": "Asia/Shanghai",
            "now": "2026-07-08T10:00:00+08:00",
        },
    }

    assert _resolved_iso(
        "2026-07-08T20:00:00Z",
        context,
        "stTime",
    ) == "2026-07-09T04:00:00+08:00"
    assert _resolved_iso(
        "2026-07-08T20:00:00",
        context,
        "stTime",
    ) == "2026-07-08T20:00:00+08:00"


def test_agent_anchors_time_only_values_to_request_date() -> None:
    context = {
        "request": {
            "timezone": "Asia/Shanghai",
            "now": "2026-07-08T10:00:00+08:00",
        }
    }

    assert _resolved_iso("20:30", context, "stTime") == "2026-07-08T20:30:00+08:00"


def test_agent_rejects_unresolved_relative_text() -> None:
    with pytest.raises(ValueError, match="relative text"):
        _resolved_iso(
            "明天晚上八点",
            {
                "request": {
                    "timezone": "Asia/Shanghai",
                    "now": "2026-07-08T10:00:00+08:00",
                }
            },
            "stTime",
        )


def test_query_normalization_rejects_undocumented_range_fields() -> None:
    with pytest.raises(ValueError, match=r"end_time, start_time.*timeRange"):
        _normalize_query_body(
            {
                "start_time": "2026-07-20T00:00:00+08:00",
                "end_time": "2026-07-20T23:59:59+08:00",
            }
        )

    with pytest.raises(ValueError, match=r"filter.*timeRange"):
        _normalize_query_body(
            {
                "filter": {
                    "time_range": {
                        "start": "2026-07-20T00:00:00+08:00",
                        "end": "2026-07-20T23:59:59+08:00",
                    }
                }
            }
        )


def test_query_normalization_accepts_only_start_and_end_inside_time_range() -> None:
    normalized = _normalize_query_body(
        {
            "timeRange": {
                "start": "2026-07-20T00:00:00+08:00",
                "end": "2026-07-20T23:59:59+08:00",
            },
            "includeLinkedPlans": True,
        }
    )
    assert normalized["timeRange"] == {
        "start": "2026-07-20T00:00:00+08:00",
        "end": "2026-07-20T23:59:59+08:00",
    }

    with pytest.raises(ValueError, match="unsupported timeRange field"):
        _normalize_query_body({"timeRange": {"start_time": "2026-07-20"}})


def test_modern_and_legacy_agent_paths_use_safe_routers() -> None:
    modern_paths = {route.path for route in createAgentV2Router().routes}
    legacy_paths = {route.path for route in createLegacyTimeRouter().routes}

    assert "/agent/context" in modern_paths
    assert "/agent/tools" in modern_paths
    assert "/agent/db/query_events" in modern_paths
    assert "/agent/db/create_event" in modern_paths
    assert "/agent/db/update_event" in modern_paths
    assert "/agent/evtQuery" in legacy_paths
    assert "/agent/evtCreate" in legacy_paths
    assert "/agent/evtUpdate" in legacy_paths
