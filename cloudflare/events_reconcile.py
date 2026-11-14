#!/usr/bin/env python3
"""
First-Party Attribution Validator & Daily Reconciliation Aggregator (`events_reconcile.py`).

Matches the exact whitelist and deduplicated CTR formulas used by `functions/events.js`
and `functions/admin/stats.js`:
  - Whitelisted events: `page_view`, `result_view`, `offer_impression`, `affiliate_click`, `share_open`
  - External metric label: `估算日 UV` (daily rotating ephemeral browser token; no cross-day ID)
  - Card CTR = `unique_clickers / unique_viewers` (viewport-entered impressions only)
  - Separate ledger columns for `厂商有效订单` & `已结算人民币` (sourced from affiliate consoles)
"""

from __future__ import annotations

import re
from typing import Any

ALLOWED_EVENTS: frozenset[str] = frozenset(
    {
        "page_view",
        "result_view",
        "offer_impression",
        "affiliate_click",
        "share_copy",
        "share_summary",
        "share_open",
    }
)

ALLOWED_ROUTES: frozenset[str] = frozenset(
    {
        "/",
        "/coding-plan-2026/",
        "/deepseek-vs-qwen/",
        "/claude-code-domestic/",
        "/dify-openclaw-cloud-server/",
    }
)

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_./:\-]{1,96}$")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_event_payload(payload: dict[str, Any]) -> tuple[bool, str, dict[str, str]]:
    if not isinstance(payload, dict):
        return False, "payload_not_dict", {}

    event_name = str(payload.get("event_name") or "").strip()
    if event_name not in ALLOWED_EVENTS:
        return False, f"disallowed_event:{event_name}", {}

    day_bucket = str(payload.get("day_bucket") or "").strip()
    if not _DAY_RE.match(day_bucket):
        return False, "invalid_day_bucket", {}

    browser_day_id = str(payload.get("browser_day_id") or "").strip()
    if not browser_day_id or len(browser_day_id) > 48 or not _SAFE_TOKEN_RE.match(browser_day_id):
        return False, "invalid_browser_day_id", {}

    raw_route = str(payload.get("route") or "/").strip()
    route = raw_route if raw_route in ALLOWED_ROUTES else "/"

    raw_source = str(payload.get("source_channel") or "unknown").strip()[:64]
    source_channel = raw_source if _SAFE_TOKEN_RE.match(raw_source) else "unknown"

    offer_id = str(payload.get("offer_id") or "").strip()[:80]
    if offer_id and not _SAFE_TOKEN_RE.match(offer_id):
        offer_id = ""

    slot_id = str(payload.get("slot_id") or "").strip()[:48]
    if slot_id and not _SAFE_TOKEN_RE.match(slot_id):
        slot_id = ""

    usage_mode = str(payload.get("usage_mode") or "").strip()
    if usage_mode not in ("", "interactive_ide", "automated_backend"):
        usage_mode = ""

    matched_model_id = str(payload.get("matched_model_id") or "").strip()[:80]
    if matched_model_id and not _SAFE_TOKEN_RE.match(matched_model_id):
        matched_model_id = ""

    return (
        True,
        "ok",
        {
            "event_name": event_name,
            "day_bucket": day_bucket,
            "browser_day_id": browser_day_id,
            "route": route,
            "source_channel": source_channel,
            "offer_id": offer_id,
            "slot_id": slot_id,
            "usage_mode": usage_mode,
            "matched_model_id": matched_model_id,
        },
    )


def summarize_daily_reconciliation(
    events: list[dict[str, Any]],
    *,
    day: str,
    vendor_ledger_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    uv_all: set[str] = set()
    uv_calc_done: set[str] = set()
    uv_shares_copied: set[str] = set()
    uv_share_open: set[str] = set()
    offer_viewers: dict[str, set[str]] = {}
    offer_clickers: dict[str, set[str]] = {}
    route_uv: dict[str, set[str]] = {}
    source_uv: dict[str, set[str]] = {}

    for raw in events:
        ok, _, clean = validate_event_payload(raw)
        if not ok or clean["day_bucket"] != day:
            continue

        bid = clean["browser_day_id"]
        ev = clean["event_name"]
        rt = clean["route"]
        src = clean["source_channel"]
        oid = clean["offer_id"]

        uv_all.add(bid)
        route_uv.setdefault(rt, set()).add(bid)
        source_uv.setdefault(src, set()).add(bid)

        if ev == "result_view":
            uv_calc_done.add(bid)
        elif ev in ("share_copy", "share_summary"):
            uv_shares_copied.add(bid)
        elif ev == "share_open":
            uv_share_open.add(bid)
        elif ev == "offer_impression" and oid:
            offer_viewers.setdefault(oid, set()).add(bid)
        elif ev == "affiliate_click" and oid:
            offer_clickers.setdefault(oid, set()).add(bid)

    all_offer_ids = sorted(set(offer_viewers.keys()) | set(offer_clickers.keys()))
    offers_summary: dict[str, dict[str, Any]] = {}
    for oid in all_offer_ids:
        v_cnt = len(offer_viewers.get(oid, set()))
        c_cnt = len(offer_clickers.get(oid, set()))
        ctr_pct = round((c_cnt / v_cnt) * 100.0, 2) if v_cnt > 0 else 0.0
        offers_summary[oid] = {
            "unique_viewers": v_cnt,
            "unique_clickers": c_cnt,
            "ctr_pct": ctr_pct,
        }

    ledger = vendor_ledger_rows or []
    valid_orders = sum(int(r.get("valid_orders") or 0) for r in ledger if r.get("day_bucket") == day)
    pending_rmb = round(sum(float(r.get("pending_rmb") or 0.0) for r in ledger if r.get("day_bucket") == day), 2)
    settled_rmb = round(sum(float(r.get("settled_rmb") or 0.0) for r in ledger if r.get("day_bucket") == day), 2)

    calc_uv_count = len(uv_calc_done)
    settled_per_100_calc_users = (
        round((settled_rmb / calc_uv_count) * 100.0, 2) if calc_uv_count > 0 else 0.0
    )

    return {
        "day": day,
        "metric_label_zh": "估算日 UV（按日轮换随机浏览器标识，跨设备/清理存储/拦截存在偏差）",
        "estimated_daily_uv": len(uv_all),
        "calculations_completed_uv": calc_uv_count,
        "shares_copied_uv": len(uv_shares_copied),
        "share_opens_uv": len(uv_share_open),
        "routes_uv": {k: len(v) for k, v in sorted(route_uv.items())},
        "sources_uv": {k: len(v) for k, v in sorted(source_uv.items())},
        "offers": offers_summary,
        "vendor_valid_orders": valid_orders,
        "pending_commission_rmb": pending_rmb,
        "settled_commission_rmb": settled_rmb,
        "settled_rmb_per_100_calc_users": settled_per_100_calc_users,
        "attribution_note_zh": "厂商有效订单与已结算人民币以阿里云云大使 / 腾讯云 CPS 联盟后台记录为准；未配置官方子推广位时仅做厂商与日期级汇总。",
    }
