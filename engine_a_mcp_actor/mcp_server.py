#!/usr/bin/env python3
"""
Engine A — Self-Contained Paid MCP Server (stdio JSON-RPC 2.0 + HTTP REST + x402).

Uses Python 3.14 standard library ONLY (zero pip dependencies).
Modes:
  1. MCP stdio server (default):
       python3 mcp_server.py
  2. Lightweight HTTP REST + Streamable MCP server (for Coze Plugin / Web / Agents):
       python3 mcp_server.py --http 8787
  3. HTTP 402 (x402 Base USDC header-gate demo mode; does not perform on-chain tx verification):
       python3 mcp_server.py --http 8787 --enable-x402
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ENGINE_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = ENGINE_DIR.parent
CONFIG_PATH: Path = PROJECT_ROOT / "config.json"
MODELS_LIVE_PATH: Path = PROJECT_ROOT / "shared_data" / "models_live.json"
OPENAPI_SPEC_PATH: Path = ENGINE_DIR / "openapi_coze.json"

SERVER_NAME: str = "ai-llm-price-router-mcp"
SERVER_VERSION: str = "1.0.0"
MCP_PROTOCOL_VERSION: str = "2024-11-05"
BASE_USDC_CONTRACT: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
X402_PRICE_USDC: str = "0.005"
X402_PRICE_ATOMIC: str = "5000"  # 0.005 USDC (6 decimals)

# Import helper functions from sibling fetch_and_enrich.py
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import fetch_and_enrich  # noqa: E402
import pricing_core  # noqa: E402


# ---------------------------------------------------------------------------
# Data & Config Helpers
# ---------------------------------------------------------------------------


def get_runtime_config() -> dict[str, Any]:
    return fetch_and_enrich.load_config(CONFIG_PATH)


def get_usdc_wallet(config: dict[str, Any] | None = None) -> str:
    cfg = config if config is not None else get_runtime_config()
    payout = cfg.get("payout_readiness") or {}
    return str(
        payout.get("usdc_base_wallet_address")
        or cfg.get("usdc_base_wallet_address")
        or "0xYOUR_BASE_USDC_WALLET_ADDRESS"
    )


def load_models_catalog() -> dict[str, Any]:
    """Load shared_data/models_live.json (auto-generating if missing) & overlay live config URLs."""
    if not MODELS_LIVE_PATH.exists():
        payload = fetch_and_enrich.refresh_models_live(MODELS_LIVE_PATH)
    else:
        try:
            payload = json.loads(MODELS_LIVE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = fetch_and_enrich.refresh_models_live(MODELS_LIVE_PATH)

    affiliate_map = fetch_and_enrich.resolve_affiliate_map(get_runtime_config())
    for model in payload.get("models", []):
        key = model.get("provider_config_key")
        if key and key in affiliate_map:
            url = affiliate_map[key]
            model["signup_url"] = url
            model["affiliate_url"] = url
            if model.get("region") == "cn_direct":
                model["model_page_url"] = url
    return payload


def _normalize_region(region: str | None) -> str:
    val = str(region or "any").strip().lower()
    if val in ("cn", "cn_direct", "china", "domestic", "mainland", "rmb"):
        return "cn_direct"
    if val in ("global", "usd", "intl", "international", "openrouter", "overseas"):
        return "global"
    return "any"


def _normalize_task_type(task_type: str | None) -> str:
    val = str(task_type or "general").strip().lower()
    if val in ("code", "coding", "programming", "dev", "swe", "agent"):
        return "coding"
    if val in ("reason", "reasoning", "math", "logic", "think", "thinking", "r1"):
        return "reasoning"
    if val in ("free", "zero"):
        return "free"
    if val in ("cheap", "budget", "low_cost", "economy"):
        return "cheap"
    if val in ("vision", "image", "multimodal"):
        return "multimodal"
    return "general"


def _compact_model_view(model: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": model["id"],
        "name": model["name"],
        "provider": model["provider"],
        "region": model["region"],
        "input_usd_per_1m": model["input_usd_per_1m"],
        "output_usd_per_1m": model["output_usd_per_1m"],
        "input_rmb_per_1m": model["input_rmb_per_1m"],
        "output_rmb_per_1m": model["output_rmb_per_1m"],
        "context_length": model["context_length"],
        "supports_tools": model["supports_tools"],
        "modality": model["modality"],
        "value_score": model["value_score"],
        "tags": model["tags"],
        "signup_url": model["signup_url"],
    }
    if extra:
        view.update(extra)
    return view


# ---------------------------------------------------------------------------
# 3 High-Utility Agent Tools
# ---------------------------------------------------------------------------


def recommend_cheapest_model(
    task_type: str = "coding",
    min_context: int = 32000,
    region_preference: str = "any",
    monthly_input_m: float = 10.0,
    monthly_output_m: float = 2.0,
) -> dict[str, Any]:
    """
    Recommend the cheapest & highest-value AI models for a workload in USD and RMB.
    """
    catalog = load_models_catalog()
    models: list[dict[str, Any]] = catalog.get("models", [])

    norm_task = _normalize_task_type(task_type)
    norm_region = _normalize_region(region_preference)
    min_ctx = max(0, int(float(min_context or 0)))
    in_m = max(0.0, float(monthly_input_m if monthly_input_m is not None else 10.0))
    out_m = max(0.0, float(monthly_output_m if monthly_output_m is not None else 2.0))

    # Flagship reference baseline ($3.00/1M input, $15.00/1M output — e.g. Claude Sonnet 4)
    baseline_usd = in_m * 3.0 + out_m * 15.0

    filtered: list[dict[str, Any]] = []
    for m in models:
        if m["context_length"] < min_ctx:
            continue
        if norm_region != "any" and m["region"] != norm_region:
            continue
        tags = m.get("tags", [])
        if norm_task == "coding" and "coding" not in tags:
            continue
        if norm_task == "reasoning" and "reasoning" not in tags:
            continue
        if norm_task == "free" and not m.get("is_free"):
            continue
        if norm_task == "cheap" and "cheap" not in tags:
            continue
        if norm_task == "multimodal" and "image" not in str(m.get("modality", "")):
            continue
        filtered.append(m)

    # Relax task filter if strict combination yielded nothing
    relaxed_note = None
    if not filtered:
        for m in models:
            if m["context_length"] >= min_ctx and (norm_region == "any" or m["region"] == norm_region):
                filtered.append(m)
        relaxed_note = f"No exact tag match for task_type='{norm_task}' at min_context={min_ctx}; showing best general matches."

    scored_items: list[dict[str, Any]] = []
    for m in filtered:
        est_usd = round(in_m * m["input_usd_per_1m"] + out_m * m["output_usd_per_1m"], 4)
        est_rmb = round(in_m * m["input_rmb_per_1m"] + out_m * m["output_rmb_per_1m"], 4)
        savings_pct = (
            round(max(0.0, (1.0 - (est_usd / baseline_usd)) * 100.0), 1)
            if baseline_usd > 0
            else 0.0
        )
        scored_items.append(
            _compact_model_view(
                m,
                {
                    "estimated_monthly_usd": est_usd,
                    "estimated_monthly_rmb": est_rmb,
                    "savings_vs_flagship_pct": savings_pct,
                },
            )
        )

    paid_sorted = sorted(
        [x for x in scored_items if x["estimated_monthly_usd"] > 0 or ("free" not in x["tags"])],
        key=lambda x: (x["estimated_monthly_usd"], -x["value_score"]),
    )
    free_sorted = sorted(
        [x for x in scored_items if "free" in x["tags"]],
        key=lambda x: (-x["value_score"], -x["context_length"]),
    )
    value_sorted = sorted(
        scored_items,
        key=lambda x: (-x["value_score"], x["estimated_monthly_usd"]),
    )

    cheapest_paid = paid_sorted[0] if paid_sorted else None
    best_value = value_sorted[0] if value_sorted else None
    best_free = free_sorted[0] if free_sorted else None

    # Assemble deduplicated top recommendations (cheapest paid + top value + free)
    top_recs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for candidate in (
        ([cheapest_paid] if cheapest_paid else [])
        + ([best_value] if best_value else [])
        + paid_sorted[:4]
        + free_sorted[:2]
    ):
        if candidate and candidate["id"] not in seen_ids:
            seen_ids.add(candidate["id"])
            top_recs.append(candidate)
        if len(top_recs) >= 6:
            break

    result: dict[str, Any] = {
        "query": {
            "task_type": norm_task,
            "min_context": min_ctx,
            "region_preference": norm_region,
            "monthly_input_m": in_m,
            "monthly_output_m": out_m,
        },
        "updated_at": catalog.get("updated_at"),
        "fx_rate_usd_to_rmb": catalog.get("fx_rate_usd_to_rmb", 7.20),
        "total_candidates_matched": len(scored_items),
        "cheapest_paid_pick": cheapest_paid,
        "best_value_pick": best_value,
        "best_free_pick": best_free,
        "recommendations": top_recs,
    }
    if relaxed_note:
        result["note"] = relaxed_note
    return result


def _check_snapshot_staleness(catalog: dict[str, Any]) -> str | None:
    raw_ts = str(catalog.get("last_live_verified_at") or catalog.get("updated_at") or "")
    if not raw_ts:
        return "价格快照缺少核验时间戳，请运行 fetch_and_enrich.py 刷新。"
    try:
        parsed = dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        age_days = (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds() / 86400.0
        if age_days > 7.0:
            return f"本地快照距上次在线核验已超过 {int(age_days)} 天（{raw_ts[:10]}），建议重新核对厂商实时价格。"
    except ValueError:
        pass
    return None


def calculate_api_budget(
    model_query: str = "deepseek-v3",
    daily_requests: int = 1000,
    avg_input_tokens: int = 1500,
    avg_output_tokens: int = 500,
    cache_hit_rate: float = 0.0,
    reasoning_multiplier: float = 1.0,
    output_includes_reasoning: bool = False,
    usage_mode: str = "interactive_ide",
    peak_5h_calls: int | None = None,
    team_size: int = 1,
    monthly_requests: int | None = None,
    monthly_input_m: float | None = None,
    monthly_output_m: float | None = None,
    cached_input_m: float | None = None,
    usage_snippet: str | None = None,
    days_observed: float = 30.0,
) -> dict[str, Any]:
    """
    Calculate daily/monthly/annual USD & RMB API budget for a given model, evaluate Coding Plan quotas
    & renewal breakeven, and suggest cheaper alternatives.
    Supports direct monthly bill totals (`monthly_requests`, `monthly_input_m`, `monthly_output_m`, `cached_input_m`)
    and deterministic log/JSON parsing (`usage_snippet`, `days_observed`).
    """
    catalog = load_models_catalog()
    models: list[dict[str, Any]] = catalog.get("models", [])

    reqs = max(0.0, float(daily_requests if daily_requests is not None else 1000))
    in_tok = max(0.0, float(avg_input_tokens if avg_input_tokens is not None else 1500))
    out_tok = max(0.0, float(avg_output_tokens if avg_output_tokens is not None else 500))
    hit_rate = min(1.0, max(0.0, float(cache_hit_rate or 0.0)))
    r_mult = max(1.0, float(reasoning_multiplier or 1.0))
    inc_cot = bool(output_includes_reasoning)
    parsed_usage_summary: dict[str, Any] | None = None
    bill_audit: dict[str, Any] | None = None
    exact_monthly_in_m: float | None = None
    exact_monthly_out_m: float | None = None

    if usage_snippet is not None and str(usage_snippet).strip() != "":
        obs_days = float(days_observed if days_observed is not None else 30.0)
        parsed_usage_summary = pricing_core.parse_usage_log_snippet(
            str(usage_snippet),
            days_observed=obs_days,
        )
        reqs = float(parsed_usage_summary["daily_requests"])
        in_tok = float(parsed_usage_summary["avg_input_tokens"])
        out_tok = float(parsed_usage_summary["avg_output_tokens"])
        hit_rate = float(parsed_usage_summary["cache_hit_rate"])
        exact_monthly_in_m = float(parsed_usage_summary["monthly_input_m"])
        exact_monthly_out_m = float(parsed_usage_summary["monthly_output_m"])
        if parsed_usage_summary.get("output_includes_reasoning"):
            inc_cot = True
        if parsed_usage_summary.get("detected_format") == "csv_multimodel_bill":
            if not str(model_query or "").strip() or str(model_query).strip().lower() == "auto":
                bd = parsed_usage_summary.get("model_breakdown") or []
                if bd:
                    model_query = str(bd[0].get("model") or "deepseek-v3")
            bill_audit = pricing_core.audit_csv_bill(
                models=models,
                raw_text=parsed_usage_summary,
                days_observed=obs_days,
                usage_mode=usage_mode,
                team_size=team_size,
                offers=catalog.get("coding_plans") if isinstance(catalog.get("coding_plans"), list) else None,
                fx_rate=float(catalog.get("fx_rate_usd_to_rmb", 7.20)),
            )
    elif any(v is not None for v in (monthly_requests, monthly_input_m, monthly_output_m, cached_input_m)):
        if monthly_requests is not None:
            m_reqs = int(round(float(monthly_requests)))
            if m_reqs <= 0 or m_reqs > 30_000_000:
                raise ValueError("Invalid monthly_requests (must be between 1 and 30,000,000)")
        elif monthly_input_m is not None and float(monthly_input_m) > 0:
            m_reqs = max(1, int(round((float(monthly_input_m) * 1_000_000.0) / max(1.0, in_tok))))
        else:
            m_reqs = max(1, int(round(reqs * 30.0)))

        m_in = float(monthly_input_m) if monthly_input_m is not None else (m_reqs * in_tok) / 1_000_000.0
        m_out = float(monthly_output_m) if monthly_output_m is not None else (m_reqs * out_tok) / 1_000_000.0
        if m_in < 0 or m_out < 0:
            raise ValueError("Monthly token totals must be non-negative")

        if cached_input_m is not None:
            c_in = float(cached_input_m)
            if c_in < 0 or (m_in > 0 and c_in > m_in) or (m_in == 0 and c_in > 0):
                raise ValueError("Invalid cached_input_m")
            hit_rate = round(c_in / m_in, 4) if m_in > 0 else 0.0

        exact_monthly_in_m = m_in
        exact_monthly_out_m = m_out
        reqs = float(max(1, math.ceil(m_reqs / 30.0) if m_reqs % 30 != 0 else (m_reqs // 30)))
        in_tok = float(max(0, int(round((m_in * 1_000_000.0) / m_reqs))))
        out_tok = float(max(0, int(round((m_out * 1_000_000.0) / m_reqs))))
        parsed_usage_summary = {
            "detected_format": "monthly_bill_totals",
            "monthly_requests": m_reqs,
            "monthly_input_m": round(m_in, 6),
            "monthly_output_m": round(m_out, 6),
            "cached_input_m": round(float(cached_input_m), 6) if cached_input_m is not None else round(m_in * hit_rate, 6),
            "daily_requests": int(reqs),
            "avg_input_tokens": int(in_tok),
            "avg_output_tokens": int(out_tok),
            "cache_hit_rate": hit_rate,
        }

    best_match, match_note = pricing_core.resolve_model_query(models, model_query)
    if best_match is None:
        raise ValueError("Model catalog is empty")

    if exact_monthly_in_m is not None and exact_monthly_out_m is not None:
        monthly_in_m = exact_monthly_in_m
        monthly_out_m = exact_monthly_out_m
        daily_in_m = monthly_in_m / 30.0
        daily_out_m = monthly_out_m / 30.0
    else:
        daily_in_m = (reqs * in_tok) / 1_000_000.0
        daily_out_m = (reqs * out_tok) / 1_000_000.0
        monthly_in_m = daily_in_m * 30.0
        monthly_out_m = daily_out_m * 30.0

    model_hit_factor = float(
        best_match.get("cache_hit_factor")
        if best_match.get("cache_hit_factor") is not None
        else (0.2 if best_match.get("region") == "cn_direct" else 0.5)
    )
    is_reasoning = "reasoning" in (best_match.get("tags") or [])
    effective_r_mult = 1.0 if (inc_cot or not is_reasoning) else r_mult

    bill_usd = pricing_core.calculate_token_bill(
        monthly_input_m=monthly_in_m,
        monthly_output_m=monthly_out_m,
        input_price_per_1m=best_match["input_usd_per_1m"],
        output_price_per_1m=best_match["output_usd_per_1m"],
        cache_hit_rate=hit_rate,
        cache_hit_factor=model_hit_factor,
        reasoning_multiplier=effective_r_mult,
        output_includes_reasoning=inc_cot,
    )
    bill_rmb = pricing_core.calculate_token_bill(
        monthly_input_m=monthly_in_m,
        monthly_output_m=monthly_out_m,
        input_price_per_1m=best_match["input_rmb_per_1m"],
        output_price_per_1m=best_match["output_rmb_per_1m"],
        cache_hit_rate=hit_rate,
        cache_hit_factor=model_hit_factor,
        reasoning_multiplier=effective_r_mult,
        output_includes_reasoning=inc_cot,
    )

    monthly_usd = bill_usd["total_cost"]
    daily_usd = monthly_usd / 30.0
    yearly_usd = daily_usd * 365.0

    monthly_rmb = bill_rmb["total_cost"]
    daily_rmb = monthly_rmb / 30.0
    yearly_rmb = daily_rmb * 365.0

    # Find cheaper alternatives using identical cache & reasoning assumptions
    target_tags = {t for t in best_match.get("tags", []) if t in ("coding", "reasoning")}
    cheaper_cn: list[dict[str, Any]] = []
    cheaper_gl: list[dict[str, Any]] = []

    for cand in models:
        if cand["id"] == best_match["id"] or cand.get("is_free"):
            continue
        if target_tags and not (target_tags & set(cand.get("tags", []))):
            continue
        cand_hit_factor = float(
            cand.get("cache_hit_factor")
            if cand.get("cache_hit_factor") is not None
            else (0.2 if cand.get("region") == "cn_direct" else 0.5)
        )
        cand_usd = pricing_core.calculate_token_bill(
            monthly_input_m=monthly_in_m,
            monthly_output_m=monthly_out_m,
            input_price_per_1m=cand["input_usd_per_1m"],
            output_price_per_1m=cand["output_usd_per_1m"],
            cache_hit_rate=hit_rate,
            cache_hit_factor=cand_hit_factor,
            reasoning_multiplier=r_mult if "reasoning" in (cand.get("tags") or []) else 1.0,
            output_includes_reasoning=inc_cot,
        )["total_cost"]
        cand_rmb = pricing_core.calculate_token_bill(
            monthly_input_m=monthly_in_m,
            monthly_output_m=monthly_out_m,
            input_price_per_1m=cand["input_rmb_per_1m"],
            output_price_per_1m=cand["output_rmb_per_1m"],
            cache_hit_rate=hit_rate,
            cache_hit_factor=cand_hit_factor,
            reasoning_multiplier=r_mult if "reasoning" in (cand.get("tags") or []) else 1.0,
            output_includes_reasoning=inc_cot,
        )["total_cost"]
        if monthly_usd > 0 and cand_usd < monthly_usd * 0.90:
            sav_usd = round(monthly_usd - cand_usd, 4)
            sav_rmb = round(monthly_rmb - cand_rmb, 4)
            sav_pct = round(((monthly_usd - cand_usd) / monthly_usd) * 100.0, 1)
            entry = _compact_model_view(
                cand,
                {
                    "monthly_cost_usd": round(cand_usd, 4),
                    "monthly_cost_rmb": round(cand_rmb, 4),
                    "monthly_savings_usd": sav_usd,
                    "monthly_savings_rmb": sav_rmb,
                    "savings_pct": sav_pct,
                },
            )
            if cand["region"] == "cn_direct":
                cheaper_cn.append(entry)
            else:
                cheaper_gl.append(entry)

    cheaper_cn.sort(key=lambda x: (x["monthly_cost_usd"], -x["value_score"]))
    cheaper_gl.sort(key=lambda x: (x["monthly_cost_usd"], -x["value_score"]))
    alternatives = (cheaper_cn[:2] + cheaper_gl[:2])[:4]

    coding_eval = pricing_core.evaluate_coding_plans(
        daily_calls=reqs,
        payg_monthly_rmb=monthly_rmb,
        usage_mode=usage_mode,
        peak_5h_calls=peak_5h_calls,
        model_id=best_match,
        team_size=team_size,
    )
    self_host_eval = pricing_core.evaluate_self_host_vs_payg(current_payg_rmb=monthly_rmb)
    api_model_id = str(best_match.get("api_model_id") or best_match["id"])
    vendor_key = str(best_match.get("provider_config_key") or best_match["id"])

    response: dict[str, Any] = {
        "query": {
            "model_query": model_query,
            "daily_requests": int(reqs),
            "avg_input_tokens": int(in_tok),
            "avg_output_tokens": int(out_tok),
            "cache_hit_rate": hit_rate,
            "reasoning_multiplier": effective_r_mult,
            "output_includes_reasoning": inc_cot,
            "usage_mode": coding_eval["usage_mode"],
            "peak_5h_calls": int(peak_5h_calls) if peak_5h_calls is not None else None,
            "team_size": coding_eval["team_size"],
        },
        "quote_verified_date": catalog.get("quote_verified_date", pricing_core.QUOTE_VERIFIED_DATE),
        "last_live_verified_at": catalog.get("last_live_verified_at") or catalog.get("updated_at"),
        "matched_model": _compact_model_view(
            best_match,
            {
                "api_base_url": best_match.get("api_base_url"),
                "api_model_id": api_model_id,
                "cache_hit_factor": model_hit_factor,
            },
        ),
        "token_volume": {
            "daily_input_tokens": int(round(reqs * in_tok)),
            "daily_output_tokens": int(round(reqs * out_tok)),
            "monthly_input_millions": round(monthly_in_m, 4),
            "monthly_output_millions": round(monthly_out_m, 4),
            "effective_input_factor": bill_rmb["effective_input_factor"],
            "effective_output_factor": bill_rmb["effective_output_factor"],
        },
        "budget_estimate": {
            "daily_usd": round(daily_usd, 4),
            "monthly_usd": round(monthly_usd, 2),
            "yearly_usd": round(yearly_usd, 2),
            "daily_rmb": round(daily_rmb, 4),
            "monthly_rmb": round(monthly_rmb, 2),
            "yearly_rmb": round(yearly_rmb, 2),
            "input_monthly_rmb": round(bill_rmb["input_cost"], 2),
            "output_monthly_rmb": round(bill_rmb["output_cost"], 2),
            "fx_rate_usd_to_rmb": catalog.get("fx_rate_usd_to_rmb", 7.20),
        },
        "coding_plan_evaluation": coding_eval,
        "self_host_evaluation": self_host_eval,
        "client_endpoints": {
            "payg_openai": pricing_core.get_client_endpoint_config(
                vendor_or_plan=vendor_key,
                client_type="openai_compat",
                billing_mode="payg",
                model_id=api_model_id,
                fallback_base_url=best_match.get("api_base_url"),
            ),
            "coding_plan_claude_code": pricing_core.get_client_endpoint_config(
                vendor_or_plan=vendor_key,
                client_type="claude_code",
                billing_mode="coding_plan",
                model_id=api_model_id,
                fallback_base_url=best_match.get("api_base_url"),
            ),
        },
        "cheaper_alternatives": alternatives,
    }
    if parsed_usage_summary is not None:
        response["parsed_usage_summary"] = parsed_usage_summary
    if bill_audit is not None:
        response["bill_audit"] = bill_audit
    stale_warn = _check_snapshot_staleness(catalog)
    if stale_warn:
        response["snapshot_stale_warning"] = stale_warn
    if match_note:
        response["match_note"] = match_note
    return response


def list_free_and_ultra_cheap_models(region: str = "any") -> dict[str, Any]:
    """
    List $0/¥0 free API models and ultra-cheap paid models (blended <= $0.50 / ¥3.60 per 1M tokens).
    """
    catalog = load_models_catalog()
    models: list[dict[str, Any]] = catalog.get("models", [])
    norm_region = _normalize_region(region)

    free_models: list[dict[str, Any]] = []
    ultra_cheap_models: list[dict[str, Any]] = []

    for m in models:
        if norm_region != "any" and m["region"] != norm_region:
            continue
        if m.get("is_free") or ("free" in m.get("tags", [])):
            free_models.append(_compact_model_view(m))
        elif m.get("blended_usd_per_1m", 999.0) <= 0.50:
            ultra_cheap_models.append(
                _compact_model_view(
                    m,
                    {
                        "blended_usd_per_1m": m["blended_usd_per_1m"],
                        "blended_rmb_per_1m": m["blended_rmb_per_1m"],
                    },
                )
            )

    free_models.sort(key=lambda x: (-x["value_score"], -x["context_length"]))
    ultra_cheap_models.sort(key=lambda x: (x["blended_usd_per_1m"], -x["value_score"]))

    return {
        "region_filter": norm_region,
        "updated_at": catalog.get("updated_at"),
        "fx_rate_usd_to_rmb": catalog.get("fx_rate_usd_to_rmb", 7.20),
        "total_free_models": len(free_models),
        "total_ultra_cheap_paid_models": len(ultra_cheap_models),
        "free_models": free_models[:20],
        "ultra_cheap_paid_models": ultra_cheap_models[:20],
    }


# ---------------------------------------------------------------------------
# MCP Tool Registry & JSON-RPC 2.0 Dispatcher
# ---------------------------------------------------------------------------

MCP_TOOLS_SPEC: list[dict[str, Any]] = [
    {
        "name": "recommend_cheapest_model",
        "description": (
            "Recommend the cheapest and best-value LLM APIs across 80+ Global (OpenRouter USD) "
            "and Mainland China (Aliyun Bailian, Tencent Cloud, SiliconFlow, Volcengine RMB) "
            "channels for coding, reasoning, multimodal, or general tasks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "description": "Workload type: 'coding', 'reasoning', 'general', 'multimodal', 'cheap', or 'free'.",
                    "default": "coding",
                },
                "min_context": {
                    "type": "integer",
                    "description": "Minimum context window in tokens (e.g. 32000, 128000, 1000000).",
                    "default": 32000,
                },
                "region_preference": {
                    "type": "string",
                    "description": "Channel region filter: 'cn_direct' (Mainland China RMB), 'global' (USD), or 'any'.",
                    "default": "any",
                },
                "monthly_input_m": {
                    "type": "number",
                    "description": "Estimated monthly prompt/input tokens in millions.",
                    "default": 10.0,
                },
                "monthly_output_m": {
                    "type": "number",
                    "description": "Estimated monthly completion/output tokens in millions.",
                    "default": 2.0,
                },
            },
            "required": [],
        },
    },
    {
        "name": "calculate_api_budget",
        "description": (
            "Calculate exact daily, monthly, and yearly LLM API costs in both USD and RMB "
            "for a given model (e.g. 'gpt-4.1', 'claude-sonnet-4', 'deepseek-v3', 'qwen3', 'doubao') "
            "and automatically discover cheaper drop-in alternatives."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_query": {
                    "type": "string",
                    "description": "Model ID or fuzzy name query (e.g. 'deepseek-v3', 'claude-sonnet-4', 'qwen3', or 'auto' when passing a multi-model CSV bill in `usage_snippet`).",
                    "default": "deepseek-v3",
                },
                "daily_requests": {
                    "type": "integer",
                    "description": "Expected number of API requests per day.",
                    "default": 1000,
                },
                "avg_input_tokens": {
                    "type": "integer",
                    "description": "Average input/prompt tokens per request.",
                    "default": 1500,
                },
                "avg_output_tokens": {
                    "type": "integer",
                    "description": "Average output/completion tokens per request.",
                    "default": 500,
                },
                "cache_hit_rate": {
                    "type": "number",
                    "description": "Prompt cache hit ratio between 0.0 and 0.9 (e.g. 0.5 for 50% hit rate).",
                    "default": 0.0,
                },
                "peak_5h_calls": {"type": "integer", "minimum": 0, "description": "Optional peak calls in a rolling five-hour window"},
                "reasoning_multiplier": {
                    "type": "number",
                    "description": "Reasoning CoT output multiplier (e.g. 2.5 when hidden thinking tokens are not included in avg_output_tokens).",
                    "default": 1.0,
                },
                "output_includes_reasoning": {
                    "type": "boolean",
                    "description": "Set true if avg_output_tokens already includes reasoning tokens (disables extra multiplier).",
                    "default": False,
                },
                "usage_mode": {
                    "type": "string",
                    "description": "'interactive_ide' (Claude Code/Cursor/Cline) or 'automated_backend' (excludes personal Coding Plans).",
                    "default": "interactive_ide",
                },
                "team_size": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "Number of interactive IDE developer seats (1..50, default 1). Compares N compliant personal Coding Plan seats against a shared team Pay-As-You-Go API pool.",
                    "default": 1,
                },
                "monthly_requests": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional monthly API call total from a billing statement (overrides daily_requests when provided).",
                },
                "monthly_input_m": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Optional monthly input tokens in millions from a billing statement.",
                },
                "monthly_output_m": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Optional monthly output tokens in millions from a billing statement.",
                },
                "cached_input_m": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Optional cached input tokens in millions (computes exact cache_hit_rate = cached_input_m / monthly_input_m).",
                },
                "usage_snippet": {
                    "type": "string",
                    "description": "Optional multi-model OpenRouter/cloud CSV or TSV bill, Claude Code `/cost` output, OpenAI/Bailian/DeepSeek `usage` JSON, or cloud console summary to parse and audit automatically.",
                },
                "days_observed": {
                    "type": "number",
                    "description": "Observation window in days for `usage_snippet` (default 30; e.g. 7 for a 7-day log).",
                    "default": 30.0,
                },
            },
            "required": ["model_query"],
        },
    },
    {
        "name": "list_free_and_ultra_cheap_models",
        "description": (
            "List all currently active $0/¥0 free LLM API endpoints and ultra-cheap paid models "
            "(<= $0.50 / ¥3.60 per 1M tokens) filtered by 'cn_direct', 'global', or 'any'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Region filter: 'cn_direct' (China RMB), 'global' (Global USD), or 'any'.",
                    "default": "any",
                }
            },
            "required": [],
        },
    },
]


def dispatch_tool_call(tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Execute one of the 3 registered tools by name."""
    args = arguments or {}
    if tool_name == "recommend_cheapest_model":
        return recommend_cheapest_model(
            task_type=args.get("task_type", "coding"),
            min_context=args.get("min_context", 32000),
            region_preference=args.get("region_preference", "any"),
            monthly_input_m=args.get("monthly_input_m", 10.0),
            monthly_output_m=args.get("monthly_output_m", 2.0),
        )
    if tool_name == "calculate_api_budget":
        return calculate_api_budget(
            model_query=args.get("model_query", "deepseek-v3"),
            daily_requests=args.get("daily_requests", 1000),
            avg_input_tokens=args.get("avg_input_tokens", 1500),
            avg_output_tokens=args.get("avg_output_tokens", 500),
            cache_hit_rate=args.get("cache_hit_rate", 0.0),
            reasoning_multiplier=args.get("reasoning_multiplier", 1.0),
            output_includes_reasoning=args.get("output_includes_reasoning", False),
            usage_mode=args.get("usage_mode", "interactive_ide"),
            peak_5h_calls=args.get("peak_5h_calls"),
            team_size=args.get("team_size", 1),
            monthly_requests=args.get("monthly_requests"),
            monthly_input_m=args.get("monthly_input_m"),
            monthly_output_m=args.get("monthly_output_m"),
            cached_input_m=args.get("cached_input_m"),
            usage_snippet=args.get("usage_snippet"),
            days_observed=args.get("days_observed", 30.0),
        )
    if tool_name == "list_free_and_ultra_cheap_models":
        return list_free_and_ultra_cheap_models(
            region=args.get("region", "any"),
        )
    raise KeyError(f"Unknown tool: {tool_name}")


def handle_jsonrpc_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 request or notification."""
    method = msg.get("method")
    has_id = "id" in msg
    req_id = msg.get("id")
    params = msg.get("params") or {}

    # JSON-RPC notifications (no 'id') receive no response
    if not has_id:
        return None

    if method == "initialize":
        client_proto = params.get("protocolVersion") or MCP_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS_SPEC},
        }

    if method == "tools/call":
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        try:
            data = dispatch_tool_call(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(data, ensure_ascii=False, indent=2),
                        }
                    ],
                    "structuredContent": data,
                    "isError": False,
                },
            }
        except KeyError as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": str(exc)},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Tool execution error: {exc}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_stdio_server() -> None:
    """Run MCP stdio JSON-RPC 2.0 server (supports newline-delimited JSON & Content-Length framing)."""
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        first_line = stdin.readline()
        if not first_line:
            break

        stripped = first_line.strip()
        if not stripped:
            continue

        use_content_length = False
        if stripped.lower().startswith(b"content-length:"):
            use_content_length = True
            length = int(stripped.split(b":", 1)[1].strip())
            # Consume remaining headers up to blank line
            while True:
                hdr_line = stdin.readline()
                if not hdr_line or hdr_line in (b"\r\n", b"\n"):
                    break
            raw_body = stdin.read(length)
        else:
            raw_body = stripped

        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            out_bytes = json.dumps(err_resp, ensure_ascii=False).encode("utf-8") + b"\n"
            stdout.write(out_bytes)
            stdout.flush()
            continue

        if isinstance(parsed, list):
            responses = [r for item in parsed if (r := handle_jsonrpc_message(item)) is not None]
            resp_obj: Any = responses if responses else None
        else:
            resp_obj = handle_jsonrpc_message(parsed)

        if resp_obj is not None:
            payload_bytes = json.dumps(resp_obj, ensure_ascii=False).encode("utf-8")
            if use_content_length:
                header = f"Content-Length: {len(payload_bytes)}\r\n\r\n".encode("ascii")
                stdout.write(header + payload_bytes)
            else:
                stdout.write(payload_bytes + b"\n")
            stdout.flush()


# ---------------------------------------------------------------------------
# Lightweight HTTP API + Coze Plugin Backend + Optional x402 USDC Gate
# ---------------------------------------------------------------------------


class ModelRouterHTTPHandler(BaseHTTPRequestHandler):
    enable_x402: bool = False

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[HTTP] {self.address_string()} - {fmt % args}\n")

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any] | list[Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-PAYMENT, Payment-Signature",
        )
        self.send_header(
            "Access-Control-Expose-Headers",
            "X-Payment-Required, X-Payment-Protocol, X-Payment-Network, "
            "X-Payment-Asset, X-Payment-Amount, X-Payment-PayTo, WWW-Authenticate",
        )
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _check_x402_gate(self, resource_path: str) -> bool:
        """Return True if authorized; send 402 Payment Required and return False if unpaid."""
        if not self.enable_x402:
            return True

        payment_proof = (
            self.headers.get("X-PAYMENT")
            or self.headers.get("Payment-Signature")
            or self.headers.get("X-402-Payment")
        )
        if payment_proof:
            return True

        wallet = get_usdc_wallet()
        headers_402 = {
            "X-Payment-Required": "true",
            "X-Payment-Protocol": "x402",
            "X-Payment-Network": "base",
            "X-Payment-Chain-Id": "eip155:8453",
            "X-Payment-Asset": f"USDC ({BASE_USDC_CONTRACT})",
            "X-Payment-Amount": X402_PRICE_USDC,
            "X-Payment-PayTo": wallet,
            "WWW-Authenticate": (
                f'x402 network="base", asset="USDC", amount="{X402_PRICE_USDC}", payTo="{wallet}"'
            ),
        }
        body_402 = {
            "x402Version": 1,
            "error": "Payment Required: Pass signed Base USDC x402 payment header in 'X-PAYMENT'.",
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "base",
                    "chainId": "eip155:8453",
                    "maxAmountRequired": X402_PRICE_ATOMIC,
                    "amountUsdc": X402_PRICE_USDC,
                    "resource": resource_path,
                    "description": "AI LLM Price Router & Token Budget API call ($0.005 USDC)",
                    "mimeType": "application/json",
                    "payTo": wallet,
                    "maxTimeoutSeconds": 60,
                    "asset": BASE_USDC_CONTRACT,
                }
            ],
        }
        self._send_json(402, body_402, extra_headers=headers_402)
        return False

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

        if path in ("/", "/health"):
            catalog = load_models_catalog()
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "total_models": catalog.get("total_models", 0),
                    "updated_at": catalog.get("updated_at"),
                    "x402_enabled": self.enable_x402,
                    "x402_pay_to": get_usdc_wallet() if self.enable_x402 else None,
                    "endpoints": [
                        "GET/POST /api/recommend",
                        "GET/POST /api/budget",
                        "GET/POST /api/free-cheap",
                        "POST /mcp",
                        "GET /openapi.json",
                    ],
                },
            )
            return

        if path == "/openapi.json":
            if OPENAPI_SPEC_PATH.exists():
                spec = json.loads(OPENAPI_SPEC_PATH.read_text(encoding="utf-8"))
                self._send_json(200, spec)
            else:
                self._send_json(404, {"error": "openapi_coze.json not found"})
            return

        if path == "/api/recommend":
            if not self._check_x402_gate(path):
                return
            res = recommend_cheapest_model(
                task_type=qs.get("task_type", "coding"),
                min_context=int(float(qs.get("min_context", 32000))),
                region_preference=qs.get("region_preference", "any"),
                monthly_input_m=float(qs.get("monthly_input_m", 10.0)),
                monthly_output_m=float(qs.get("monthly_output_m", 2.0)),
            )
            self._send_json(200, res)
            return

        if path == "/api/budget":
            if not self._check_x402_gate(path):
                return
            try:
                inc_raw = str(qs.get("output_includes_reasoning", "false")).strip().lower()
                inc_reasoning = inc_raw in ("1", "true", "yes")
                peak_val = int(float(qs["peak_5h_calls"])) if "peak_5h_calls" in qs and qs["peak_5h_calls"] != "" else None
                m_reqs_val = (
                    int(float(qs["monthly_requests"]))
                    if "monthly_requests" in qs and qs["monthly_requests"] != ""
                    else None
                )
                m_in_val = (
                    float(qs["monthly_input_m"])
                    if "monthly_input_m" in qs and qs["monthly_input_m"] != ""
                    else None
                )
                m_out_val = (
                    float(qs["monthly_output_m"])
                    if "monthly_output_m" in qs and qs["monthly_output_m"] != ""
                    else None
                )
                c_in_val = (
                    float(qs["cached_input_m"])
                    if "cached_input_m" in qs and qs["cached_input_m"] != ""
                    else None
                )
                res = calculate_api_budget(
                    model_query=qs.get("model_query") or qs.get("model_id") or "deepseek-v3",
                    daily_requests=int(float(qs.get("daily_requests", 1000))),
                    avg_input_tokens=int(float(qs.get("avg_input_tokens", 1500))),
                    avg_output_tokens=int(float(qs.get("avg_output_tokens", 500))),
                    cache_hit_rate=float(qs.get("cache_hit_rate", 0.0)),
                    reasoning_multiplier=float(qs.get("reasoning_multiplier", 1.0)),
                    output_includes_reasoning=inc_reasoning,
                    usage_mode=qs.get("usage_mode", "interactive_ide"),
                    peak_5h_calls=peak_val,
                    team_size=int(float(qs.get("team_size", 1))),
                    monthly_requests=m_reqs_val,
                    monthly_input_m=m_in_val,
                    monthly_output_m=m_out_val,
                    cached_input_m=c_in_val,
                    usage_snippet=qs.get("usage_snippet"),
                    days_observed=float(qs.get("days_observed", 30.0)),
                )
                self._send_json(200, res)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            return

        if path == "/api/free-cheap":
            if not self._check_x402_gate(path):
                return
            res = list_free_and_ultra_cheap_models(region=qs.get("region", "any"))
            self._send_json(200, res)
            return

        self._send_json(404, {"error": f"Unknown endpoint: {path}"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        body = self._read_json_body()

        if path == "/mcp":
            # Allow discovery (initialize, ping, tools/list) free; gate tools/call under x402
            if body.get("method") == "tools/call" and not self._check_x402_gate(path):
                return
            resp = handle_jsonrpc_message(body)
            self._send_json(200, resp if resp is not None else {"ok": True})
            return

        if path == "/api/recommend":
            if not self._check_x402_gate(path):
                return
            res = dispatch_tool_call("recommend_cheapest_model", body)
            self._send_json(200, res)
            return

        if path == "/api/budget":
            if not self._check_x402_gate(path):
                return
            res = dispatch_tool_call("calculate_api_budget", body)
            self._send_json(200, res)
            return

        if path == "/api/free-cheap":
            if not self._check_x402_gate(path):
                return
            res = dispatch_tool_call("list_free_and_ultra_cheap_models", body)
            self._send_json(200, res)
            return

        self._send_json(404, {"error": f"Unknown endpoint: {path}"})


def run_http_server(port: int, host: str = "0.0.0.0", enable_x402: bool = False) -> None:
    ModelRouterHTTPHandler.enable_x402 = enable_x402
    server = ThreadingHTTPServer((host, port), ModelRouterHTTPHandler)
    wallet_info = f" | x402 Base USDC -> {get_usdc_wallet()}" if enable_x402 else ""
    print(
        f"[{SERVER_NAME}] HTTP server listening on http://{host}:{port}{wallet_info}",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[HTTP] Shutting down server.", file=sys.stderr)
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI LLM Price Router — MCP stdio JSON-RPC 2.0 & HTTP/Coze/x402 Server"
    )
    parser.add_argument(
        "--http",
        type=int,
        default=None,
        metavar="PORT",
        help="Run lightweight HTTP REST + Streamable MCP server on PORT (e.g. 8787).",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Bind host for --http mode (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--enable-x402",
        action="store_true",
        help="Enable HTTP 402 Payment Required (x402 Base USDC) micropayment gate on HTTP endpoints.",
    )
    args = parser.parse_args()

    if args.http is not None:
        run_http_server(port=args.http, host=args.host, enable_x402=args.enable_x402)
    else:
        run_stdio_server()


if __name__ == "__main__":
    main()
