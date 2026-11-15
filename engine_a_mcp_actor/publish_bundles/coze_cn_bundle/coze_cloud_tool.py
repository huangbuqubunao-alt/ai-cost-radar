#!/usr/bin/env python3
"""
扣子 (Coze.cn) 云端 IDE 插件 v0.0.2 — AI 大模型实时比价路由与 Coding Plan 额度核验器
================================================================================
✅ 零第三方依赖（纯 Python 标准库 urllib/json/pathlib，无需安装任何 pip 包）
✅ 与 Web 端（/coding-plan-2026/）及 MCP Server 共用同一套缓存/思考倍率与官方额度核验公式
✅ 标准入口签名 `def handler(args: Args) -> Output:`，可直接全选粘贴至 Coze.cn 云端 IDE 发布 v0.0.2

官方核验依据 (2026-11-13):
  - 阿里云百炼 Coding Plan: https://help.aliyun.com/zh/model-studio/coding-plan
    (Lite 已停新购；Pro 首月新客 ¥39.90 / 续费 ¥200，5h 限 6,000 次 / 周限 45,000 次 / 月限 90,000 次)
  - 腾讯云 Coding Plan: https://cloud.tencent.com/document/product/1823/130092
    (Lite 原价 ¥40/月 限 1,200/9,000/18,000 次；Pro 原价 ¥200/月 限 6,000/45,000/90,000 次)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

try:
    from runtime import Args  # Coze.cn 云端 IDE 运行时自动注入
except ImportError:
    Args = Any  # 本地命令行 / 单元测试自测兼容

Output = Dict[str, Any]

LIVE_FEED_URL = "https://ai-cost-radar-nlu.pages.dev/api/models_live.json"
WEB_BASE_URL = "https://ai-cost-radar-nlu.pages.dev/"
QUOTE_VERIFIED_DATE = "2026-11-13"
PRO_MONTHLY_CAP = 90_000
PRO_WEEKLY_CAP = 45_000
PRO_5H_CAP = 6_000
LITE_MONTHLY_CAP = 18_000
LITE_WEEKLY_CAP = 9_000
LITE_5H_CAP = 1_200
DEFAULT_FX_USD_TO_RMB = 7.20

SUBSCRIPTION_OFFERS_2026: list[dict[str, Any]] = [
    {
        "id": "aliyun-coding-plan",
        "offer_type": "subscription",
        "name": "阿里云百炼 Coding Plan 编程套餐",
        "vendor": "阿里云百炼 (Aliyun Bailian)",
        "official_source_url": "https://help.aliyun.com/zh/model-studio/coding-plan",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": True,
        "featured_partner": True,
        "models_covered": ["qwen3.5-plus", "qwen3-coder-next", "kimi-k2.5", "glm-5", "MiniMax-M2.5"],
        "tiers": [
            {
                "tier_id": "lite",
                "name": "Lite 基础版（已停新购）",
                "purchasable": False,
                "first_month_rmb": None,
                "renewal_rmb": 40.0,
                "quota_5h": LITE_5H_CAP,
                "quota_weekly": LITE_WEEKLY_CAP,
                "quota_monthly": LITE_MONTHLY_CAP,
            },
            {
                "tier_id": "pro",
                "name": "Pro 高级版",
                "purchasable": True,
                "first_month_rmb": 39.90,
                "renewal_rmb": 200.0,
                "quota_5h": PRO_5H_CAP,
                "quota_weekly": PRO_WEEKLY_CAP,
                "quota_monthly": PRO_MONTHLY_CAP,
            },
        ],
    },
    {
        "id": "tencent-coding-plan",
        "offer_type": "subscription",
        "name": "腾讯云 LKEAP Coding Plan 编程套餐",
        "vendor": "腾讯云 (Tencent Cloud)",
        "official_source_url": "https://cloud.tencent.com/document/product/1823/130092",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": True,
        "featured_partner": True,
        "models_covered": ["tc-code-latest", "hunyuan-t1", "kimi-k2.5", "glm-5", "MiniMax-M2.5"],
        "tiers": [
            {
                "tier_id": "lite",
                "name": "Lite 轻量版",
                "purchasable": True,
                "first_month_rmb": None,
                "renewal_rmb": 40.0,
                "quota_5h": LITE_5H_CAP,
                "quota_weekly": LITE_WEEKLY_CAP,
                "quota_monthly": LITE_MONTHLY_CAP,
            },
            {
                "tier_id": "pro",
                "name": "Pro 专业版",
                "purchasable": True,
                "first_month_rmb": None,
                "renewal_rmb": 200.0,
                "quota_5h": PRO_5H_CAP,
                "quota_weekly": PRO_WEEKLY_CAP,
                "quota_monthly": PRO_MONTHLY_CAP,
            },
        ],
    },
    {
        "id": "volcengine-coding-plan",
        "offer_type": "subscription",
        "name": "火山方舟 Coding Plan 编程套餐",
        "vendor": "字节跳动 · 火山引擎",
        "official_source_url": "https://www.volcengine.com/docs/82379",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": True,
        "featured_partner": False,
        "models_covered": ["doubao-seed-2.0-pro", "deepseek-v3", "kimi-k2.5", "glm-5"],
        "tiers": [
            {
                "tier_id": "lite",
                "name": "Lite 轻量版",
                "purchasable": True,
                "first_month_rmb": None,
                "renewal_rmb": 40.0,
                "quota_5h": LITE_5H_CAP,
                "quota_weekly": LITE_WEEKLY_CAP,
                "quota_monthly": LITE_MONTHLY_CAP,
            },
            {
                "tier_id": "pro",
                "name": "Pro 专业版",
                "purchasable": True,
                "first_month_rmb": None,
                "renewal_rmb": 200.0,
                "quota_5h": PRO_5H_CAP,
                "quota_weekly": PRO_WEEKLY_CAP,
                "quota_monthly": PRO_MONTHLY_CAP,
            },
        ],
    },
]

FALLBACK_CATALOG: dict[str, Any] = {
    "updated_at": "2026-11-13T00:00:00Z",
    "quote_verified_date": QUOTE_VERIFIED_DATE,
    "source": "builtin_coze_fallback_2026_v3",
    "fx_rate_usd_to_rmb": 7.20,
    "models": [
        {
            "id": "aliyun-bailian/qwen3-coder-next",
            "name": "阿里云百炼: Qwen3-Coder-Next (256K 代码重构主力)",
            "provider": "阿里云百炼 (Aliyun Bailian)",
            "provider_config_key": "aliyun_bailian_url",
            "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_model_id": "qwen3-coder-next",
            "cache_hit_factor": 0.2,
            "region": "cn_direct",
            "input_usd_per_1m": 0.1667,
            "output_usd_per_1m": 0.6667,
            "input_rmb_per_1m": 1.2,
            "output_rmb_per_1m": 4.8,
            "blended_usd_per_1m": 0.2917,
            "blended_rmb_per_1m": 2.1,
            "context_length": 262144,
            "supports_tools": True,
            "modality": "text->text",
            "is_free": False,
            "value_score": 98.2,
            "tags": ["coding", "cheap", "cn_direct"],
            "signup_url": "https://bailian.console.aliyun.com/?userCode=vlxk7knp",
        },
        {
            "id": "aliyun-bailian/qwen3.5-plus",
            "name": "阿里云百炼: Qwen3.5-Plus (百万长文本全能旗舰)",
            "provider": "阿里云百炼 (Aliyun Bailian)",
            "provider_config_key": "aliyun_bailian_url",
            "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_model_id": "qwen3.5-plus",
            "cache_hit_factor": 0.2,
            "region": "cn_direct",
            "input_usd_per_1m": 0.1111,
            "output_usd_per_1m": 0.2778,
            "input_rmb_per_1m": 0.8,
            "output_rmb_per_1m": 2.0,
            "blended_usd_per_1m": 0.1528,
            "blended_rmb_per_1m": 1.1,
            "context_length": 1000000,
            "supports_tools": True,
            "modality": "text+image->text",
            "is_free": False,
            "value_score": 98.5,
            "tags": ["coding", "reasoning", "cheap", "cn_direct"],
            "signup_url": "https://bailian.console.aliyun.com/?userCode=vlxk7knp",
        },
        {
            "id": "tencent-cloud/hunyuan-t1",
            "name": "腾讯云: 混元 Hunyuan-T1 (256K 深度推理)",
            "provider": "腾讯云 (Tencent Cloud)",
            "provider_config_key": "tencent_cps_url",
            "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
            "api_model_id": "hunyuan-t1-latest",
            "cache_hit_factor": 0.2,
            "region": "cn_direct",
            "input_usd_per_1m": 0.1389,
            "output_usd_per_1m": 0.5556,
            "input_rmb_per_1m": 1.0,
            "output_rmb_per_1m": 4.0,
            "blended_usd_per_1m": 0.2431,
            "blended_rmb_per_1m": 1.75,
            "context_length": 256000,
            "supports_tools": True,
            "modality": "text->text",
            "is_free": False,
            "value_score": 97.6,
            "tags": ["coding", "reasoning", "cheap", "cn_direct"],
            "signup_url": "https://curl.qcloud.com/EGH3k1cs",
        },
        {
            "id": "tencent-cloud/deepseek-v3",
            "name": "腾讯云: DeepSeek-V3.2 满血专线版",
            "provider": "腾讯云 (Tencent Cloud)",
            "provider_config_key": "tencent_cps_url",
            "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
            "api_model_id": "deepseek-v3",
            "cache_hit_factor": 0.2,
            "region": "cn_direct",
            "input_usd_per_1m": 0.2778,
            "output_usd_per_1m": 1.1111,
            "input_rmb_per_1m": 2.0,
            "output_rmb_per_1m": 8.0,
            "blended_usd_per_1m": 0.4861,
            "blended_rmb_per_1m": 3.5,
            "context_length": 131072,
            "supports_tools": True,
            "modality": "text->text",
            "is_free": False,
            "value_score": 96.0,
            "tags": ["coding", "cheap", "cn_direct"],
            "signup_url": "https://curl.qcloud.com/EGH3k1cs",
        },
        {
            "id": "siliconflow/Qwen/Qwen2.5-7B-Instruct",
            "name": "硅基流动 SiliconFlow: Qwen2.5-7B-Instruct (免费API)",
            "provider": "硅基流动 (SiliconFlow)",
            "provider_config_key": "siliconflow_invite_url",
            "api_base_url": "https://api.siliconflow.cn/v1",
            "api_model_id": "Qwen/Qwen2.5-7B-Instruct",
            "cache_hit_factor": 1.0,
            "region": "cn_direct",
            "input_usd_per_1m": 0.0,
            "output_usd_per_1m": 0.0,
            "input_rmb_per_1m": 0.0,
            "output_rmb_per_1m": 0.0,
            "blended_usd_per_1m": 0.0,
            "blended_rmb_per_1m": 0.0,
            "context_length": 32768,
            "supports_tools": True,
            "modality": "text->text",
            "is_free": True,
            "value_score": 96.5,
            "tags": ["free", "cheap", "coding", "cn_direct"],
            "signup_url": "https://cloud.siliconflow.cn/i/VjtrbFsv",
        },
        {
            "id": "volcengine/doubao-seed-2.0-pro",
            "name": "火山引擎方舟: 豆包 Doubao-Seed-2.0-Pro (旗舰高并发)",
            "provider": "火山引擎 (Volcengine Ark)",
            "provider_config_key": "volcengine_ark_url",
            "api_base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_model_id": "doubao-seed-2-0-pro-250415",
            "cache_hit_factor": 0.2,
            "region": "cn_direct",
            "input_usd_per_1m": 0.1111,
            "output_usd_per_1m": 0.2778,
            "input_rmb_per_1m": 0.8,
            "output_rmb_per_1m": 2.0,
            "blended_usd_per_1m": 0.1528,
            "blended_rmb_per_1m": 1.1,
            "context_length": 256000,
            "supports_tools": True,
            "modality": "text+image->text",
            "is_free": False,
            "value_score": 98.1,
            "tags": ["coding", "cheap", "cn_direct"],
            "signup_url": "https://console.volcengine.com/ark",
        },
        {
            "id": "aliyun-bailian/qwen-turbo",
            "name": "阿里云百炼: Qwen-Turbo (极速低成本百万窗口)",
            "provider": "阿里云百炼 (Aliyun Bailian)",
            "provider_config_key": "aliyun_bailian_url",
            "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_model_id": "qwen-turbo",
            "cache_hit_factor": 0.2,
            "region": "cn_direct",
            "input_usd_per_1m": 0.0417,
            "output_usd_per_1m": 0.0833,
            "input_rmb_per_1m": 0.3,
            "output_rmb_per_1m": 0.6,
            "blended_usd_per_1m": 0.0521,
            "blended_rmb_per_1m": 0.375,
            "context_length": 1000000,
            "supports_tools": True,
            "modality": "text->text",
            "is_free": False,
            "value_score": 97.4,
            "tags": ["cheap", "coding", "cn_direct"],
            "signup_url": "https://bailian.console.aliyun.com/?userCode=vlxk7knp",
        },
        {
            "id": "anthropic/claude-sonnet-4",
            "name": "Anthropic: Claude Sonnet 4",
            "provider": "OpenRouter (Global)",
            "api_base_url": "https://openrouter.ai/api/v1",
            "api_model_id": "anthropic/claude-sonnet-4",
            "cache_hit_factor": 0.5,
            "region": "global",
            "input_usd_per_1m": 3.0,
            "output_usd_per_1m": 15.0,
            "input_rmb_per_1m": 21.6,
            "output_rmb_per_1m": 108.0,
            "blended_usd_per_1m": 6.0,
            "blended_rmb_per_1m": 43.2,
            "context_length": 200000,
            "supports_tools": True,
            "modality": "text+image->text",
            "is_free": False,
            "value_score": 92.5,
            "tags": ["coding", "reasoning", "global"],
            "signup_url": "https://openrouter.ai",
        },
    ],
}


def _get_param(inp: Any, key: str, default: Any = None) -> Any:
    if inp is None:
        return default
    if isinstance(inp, dict):
        val = inp.get(key)
    else:
        val = getattr(inp, key, None)
    return default if val is None or val == "" else val


def _fetch_live_catalog(logger: Any = None) -> dict[str, Any]:
    """本地仓库环境优先读最新 shared_data/models_live.json；Coze 云端沙箱走 HTTPS 实时源，失败自动降级内置快照。"""
    try:
        local_candidate = Path(__file__).resolve().parents[3] / "shared_data" / "models_live.json"
        if local_candidate.exists():
            local_payload = json.loads(local_candidate.read_text(encoding="utf-8"))
            if isinstance(local_payload.get("models"), list) and local_payload["models"]:
                return local_payload
    except Exception:  # noqa: BLE001
        pass

    req = urllib.request.Request(
        LIVE_FEED_URL,
        headers={
            "User-Agent": "Coze-AI-Cost-Radar-Plugin/2.0",
            "Accept": "application/json",
        },
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload.get("models"), list) and len(payload["models"]) > 0:
                return payload
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        if logger and hasattr(logger, "warning"):
            logger.warning(f"Live feed fallback triggered: {exc}")
    return FALLBACK_CATALOG


def _calc_token_bill(
    monthly_in_m: float,
    monthly_out_m: float,
    in_price: float,
    out_price: float,
    cache_hit_rate: float,
    cache_hit_factor: float,
    reasoning_mult: float,
    output_includes_reasoning: bool,
) -> dict[str, float]:
    hit_rate = min(1.0, max(0.0, float(cache_hit_rate or 0.0)))
    hit_factor = min(1.0, max(0.0, float(cache_hit_factor if cache_hit_factor is not None else 1.0)))
    in_factor = (1.0 - hit_rate) + (hit_rate * hit_factor)
    out_factor = 1.0 if output_includes_reasoning else max(1.0, float(reasoning_mult or 1.0))
    in_cost = monthly_in_m * in_factor * in_price
    out_cost = monthly_out_m * out_factor * out_price
    return {
        "input_cost": round(in_cost, 4),
        "output_cost": round(out_cost, 4),
        "total_cost": round(in_cost + out_cost, 4),
    }


def _fmt_wan(calls: int) -> str:
    return f"{calls // 10_000} 万次" if calls % 10_000 == 0 else f"{calls / 10_000:.1f} 万次"


def _plan_covers_model(plan: dict[str, Any], model: dict[str, Any] | str | None) -> bool:
    if not plan or plan.get("offer_type") != "subscription" or model is None:
        return False
    if isinstance(model, dict):
        model_text = f"{model.get('id', '')} {model.get('api_model_id', '')} {model.get('name', '')}".lower()
    else:
        model_text = str(model).strip().lower()
    if not model_text:
        return False
    cov = " ".join(str(x).lower() for x in (plan.get("models_covered") or []))
    if "qwen" in model_text and "qwen" in cov:
        return True
    if ("hunyuan" in model_text or "tc-code" in model_text) and ("hunyuan" in cov or "tc-code" in cov):
        return True
    if "doubao" in model_text and "doubao" in cov:
        return True
    if "kimi" in model_text and "kimi" in cov:
        return True
    if "glm" in model_text and "glm" in cov:
        return True
    if "minimax" in model_text and "minimax" in cov:
        return True
    if ("deepseek-v3" in model_text or "deepseek-chat" in model_text) and "deepseek-v3" in cov:
        return True
    return False


def _evaluate_coding_plan_verdict(
    daily_calls: int,
    payg_rmb: float,
    usage_mode: str,
    peak: int | None = None,
    model: dict[str, Any] | str | None = None,
    offers: list[dict[str, Any]] | None = None,
    team_size: int = 1,
) -> dict[str, Any]:
    seats = max(1, min(50, int(round(float(team_size or 1)))))
    d_calls = max(0, int(daily_calls))
    monthly_calls = d_calls * 30
    per_seat_monthly_calls = math.ceil(monthly_calls / seats) if monthly_calls > 0 else 0
    total_pro_monthly = PRO_MONTHLY_CAP * seats
    total_pro_weekly = PRO_WEEKLY_CAP * seats
    total_pro_5h = PRO_5H_CAP * seats
    total_lite_monthly = LITE_MONTHLY_CAP * seats
    total_lite_5h = LITE_5H_CAP * seats
    is_backend = str(usage_mode or "").strip().lower() in (
        "automated_backend",
        "backend",
        "api_service",
        "batch",
        "non_interactive",
    )
    norm_mode = "automated_backend" if is_backend else "interactive_ide"
    source_offers = [
        o for o in (offers or SUBSCRIPTION_OFFERS_2026) if isinstance(o, dict) and o.get("offer_type") == "subscription"
    ] or SUBSCRIPTION_OFFERS_2026

    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for offer in source_offers:
        if norm_mode == "automated_backend" and offer.get("interactive_only", True):
            excluded.append(
                {
                    "plan_id": offer["id"],
                    "name": offer["name"],
                    "reason_zh": "官方条款仅限交互式 AI 编程工具（Claude Code / Cursor / Cline 等），禁止用于非交互式后端、批处理或 API 服务。",
                    "official_source_url": offer.get("official_source_url", ""),
                }
            )
            continue

        purchasable_tiers = [t for t in offer.get("tiers", []) if t.get("purchasable")]
        chosen_tier: dict[str, Any] | None = None
        for tier in purchasable_tiers:
            if (
                monthly_calls <= int(tier["quota_monthly"]) * seats
                and (d_calls * 7) <= int(tier["quota_weekly"]) * seats
            ):
                if peak is None or peak <= int(tier["quota_5h"]) * seats:
                    chosen_tier = tier
                    break

        pro_tier = next(
            (t for t in purchasable_tiers if t["tier_id"] == "pro"),
            purchasable_tiers[-1] if purchasable_tiers else None,
        )
        ref_tier = chosen_tier or pro_tier
        if ref_tier is None:
            continue

        covers_model = _plan_covers_model(offer, model) if model is not None else True
        first_rmb = ref_tier.get("first_month_rmb")
        unit_renewal = float(ref_tier["renewal_rmb"])
        unit_first = float(first_rmb) if first_rmb is not None else unit_renewal
        renewal_rmb = round(unit_renewal * seats, 2)
        effective_first_rmb = round(unit_first * seats, 2)

        overflow_hybrid: dict[str, Any] | None = None
        if (
            norm_mode == "interactive_ide"
            and pro_tier is not None
            and monthly_calls > int(pro_tier["quota_monthly"]) * seats
            and (peak is None or peak <= int(pro_tier["quota_5h"]) * seats)
        ):
            covered_calls = int(pro_tier["quota_monthly"]) * seats
            overflow_calls = monthly_calls - covered_calls
            overflow_payg_rmb = round(payg_rmb * (overflow_calls / float(monthly_calls)), 2)
            pro_raw_first = pro_tier.get("first_month_rmb")
            pro_unit_renewal = float(pro_tier["renewal_rmb"])
            pro_unit_first = float(pro_raw_first) if pro_raw_first is not None else pro_unit_renewal
            first_plan = round(pro_unit_first * seats, 2)
            renew_plan = round(pro_unit_renewal * seats, 2)
            first_tot = round(first_plan + overflow_payg_rmb, 2)
            renew_tot = round(renew_plan + overflow_payg_rmb, 2)
            first_sav = round(payg_rmb - first_tot, 2)
            renew_sav = round(payg_rmb - renew_tot, 2)
            overflow_hybrid = {
                "seats_count": seats,
                "covered_calls": covered_calls,
                "overflow_calls": overflow_calls,
                "overflow_payg_rmb": overflow_payg_rmb,
                "first_month_plan_rmb": first_plan,
                "renewal_plan_rmb": renew_plan,
                "first_month_total_rmb": first_tot,
                "renewal_total_rmb": renew_tot,
                "first_month_saving_rmb": first_sav,
                "renewal_saving_rmb": renew_sav,
                "saves_on_renewal": bool(renew_sav > 0),
            }

        if chosen_tier is None and monthly_calls <= int(ref_tier["quota_monthly"]) * seats:
            status = "exceeds_5h_cap"
            first_month_saving = None
            renewal_saving = None
        elif chosen_tier is None:
            status = "exceeds_monthly_cap"
            first_month_saving = None
            renewal_saving = None
        else:
            first_month_saving = round(payg_rmb - effective_first_rmb, 2)
            renewal_saving = round(payg_rmb - renewal_rmb, 2)
            if renewal_saving > 0:
                status = "recommended_even_on_renewal"
            elif first_rmb is not None and first_month_saving > 0:
                status = "first_month_only"
            else:
                status = "payg_cheaper"

        eligible.append(
            {
                "plan_id": offer["id"],
                "name": offer["name"],
                "vendor": offer.get("vendor", ""),
                "featured_partner": bool(offer.get("featured_partner")),
                "covers_selected_model": covers_model,
                "official_source_url": offer.get("official_source_url", ""),
                "verified_date": offer.get("verified_date", QUOTE_VERIFIED_DATE),
                "status": status,
                "seats_count": seats,
                "matched_tier": chosen_tier["tier_id"] if chosen_tier else "exceeds_pro",
                "first_month_rmb": effective_first_rmb,
                "has_first_month_promo": first_rmb is not None,
                "renewal_rmb": renewal_rmb,
                "quota_5h": int(ref_tier["quota_5h"]) * seats,
                "quota_weekly": int(ref_tier["quota_weekly"]) * seats,
                "quota_monthly": int(ref_tier["quota_monthly"]) * seats,
                "first_month_savings_rmb": first_month_saving,
                "renewal_savings_rmb": renewal_saving,
                "overflow_hybrid": overflow_hybrid,
            }
        )

    same_family = [
        item for item in eligible if item["covers_selected_model"] and item["status"] == "recommended_even_on_renewal"
    ]
    same_family.sort(
        key=lambda x: (float(x["renewal_savings_rmb"] or 0.0), 1 if x.get("featured_partner") else 0),
        reverse=True,
    )
    rec_same_family = same_family[0]["plan_id"] if same_family else None

    hybrid_candidates = [
        item
        for item in eligible
        if item["covers_selected_model"]
        and isinstance(item.get("overflow_hybrid"), dict)
        and item["overflow_hybrid"]["saves_on_renewal"]
    ]
    hybrid_candidates.sort(
        key=lambda x: (
            float(x["overflow_hybrid"]["renewal_saving_rmb"]),
            float(x["overflow_hybrid"]["first_month_saving_rmb"]),
            1 if x.get("featured_partner") else 0,
        ),
        reverse=True,
    )
    best_hybrid = hybrid_candidates[0] if hybrid_candidates else None
    rec_overflow_hybrid = best_hybrid["plan_id"] if best_hybrid else None

    if is_backend:
        return {
            "usage_mode": "automated_backend",
            "team_size": seats,
            "per_seat_monthly_calls": per_seat_monthly_calls,
            "monthly_calls_30d": monthly_calls,
            "recommended_same_family_plan_id": None,
            "recommended_overflow_hybrid_plan_id": None,
            "eligible_subscriptions": [],
            "excluded_subscriptions": excluded,
            "headline_zh": (
                "当前为非交互式后端/API服务场景：已排除阿里云百炼、腾讯云与火山方舟个人 Coding Plan"
                "（官方规则仅限 Claude Code / Cursor / Cline 等交互式编程工具），请直接使用按量 API。"
            ),
            "window_note_zh": "非交互式后端不可使用个人编程套餐。",
        }

    if monthly_calls > total_pro_monthly:
        over = monthly_calls - total_pro_monthly
        if seats == 1:
            base_headline = (
                f"按 30 天预计 {_fmt_wan(monthly_calls)}（{monthly_calls:,} 次模型调用），"
                f"超出 Pro 月额度 {_fmt_wan(over)}（百炼/腾讯/火山 Pro 月上限均为 {PRO_MONTHLY_CAP:,} 次）——"
                "¥200 包月套餐不够用，超出部分需走按量 API 或多账号/企业方案！"
            )
            pro_phrase = f"1 份 {best_hybrid['name']} Pro 打底前 9 万次" if best_hybrid else ""
        else:
            base_headline = (
                f"按 {seats} 人团队 30 天合计 {_fmt_wan(monthly_calls)}（人均约 {per_seat_monthly_calls:,} 次/月），"
                f"超出 {seats} 席 Pro 合计月额度 {_fmt_wan(over)}（合计上限 {total_pro_monthly:,} 次）——"
            )
            pro_phrase = (
                f"{seats} 份 {best_hybrid['name']} Pro 打底前 {_fmt_wan(best_hybrid['overflow_hybrid']['covered_calls'])}"
                if best_hybrid
                else ""
            )
        if best_hybrid is not None:
            bh = best_hybrid["overflow_hybrid"]
            headline = (
                base_headline
                + f"可采用「{pro_phrase} + 超额 {_fmt_wan(bh['overflow_calls'])}走按量 API」："
                f"首月约 ¥{bh['first_month_total_rmb']:.2f} / 续费月约 ¥{bh['renewal_total_rmb']:.2f}，"
                f"净省 ¥{bh['renewal_saving_rmb']:.2f}/月。"
            )
        else:
            headline = base_headline + f"当前模型全程纯按量仅约 ¥{payg_rmb:.2f}/月，无需叠加包月。"
        window_note = f"{'合计 ' if seats > 1 else ''}Pro 另有每 5 小时 {total_pro_5h:,} 次、每周 {total_pro_weekly:,} 次硬上限。"
    else:
        window_note = (
            f"月额度足够，5 小时窗口待确认（{'合计 ' if seats > 1 else ''}Pro 每 5h 限 {total_pro_5h:,} 次 / 腾讯与火山 Lite 每 5h 限 {total_lite_5h:,} 次；"
            "注意单位为模型调用次数，一次提问可能触发 5～30 次调用）。"
        )
        if seats == 1:
            if monthly_calls > LITE_MONTHLY_CAP:
                over_lite = monthly_calls - LITE_MONTHLY_CAP
                headline = (
                    f"按 30 天预计 {monthly_calls:,} 次调用：超出腾讯/火山 Lite 月上限 {over_lite:,} 次（Lite 限 18,000 次/月，百炼 Lite 已停新购），"
                    f"需对标 Pro 档（90,000 次/月，百炼新客首月 ¥39.90、各家续费原价 ¥200/月；当前同模型按量约 ¥{payg_rmb:.2f}/月）。"
                )
            else:
                headline = (
                    f"按 30 天预计 {monthly_calls:,} 次调用：在腾讯/火山 Lite（¥40/月，18,000 次/月）与各家 Pro（90,000 次/月）额度内；"
                    f"当前同模型按量约 ¥{payg_rmb:.2f}/月，请同时对比首月特惠与次月 ¥200 续费原价。"
                )
        else:
            headline = (
                f"按 {seats} 人团队 30 天合计 {monthly_calls:,} 次调用（人均约 {per_seat_monthly_calls:,} 次/月）："
                f"在 {seats} 席独立套餐上限内（合计上限 {total_pro_monthly:,} 次/月，续费合计 ¥{200 * seats:,}/月；共享按量池约 ¥{payg_rmb:.2f}/月）。"
            )
    if peak is not None and monthly_calls <= total_pro_monthly:
        if peak > total_pro_5h:
            window_note = f"5 小时峰值 {peak:,} 次，超过 {'合计 ' if seats > 1 else ''}Pro 窗口上限 {total_pro_5h:,} 次。"
        elif peak > total_lite_5h:
            window_note = "5 小时峰值超过 Lite 上限，处于 Pro 窗口额度内。"
        else:
            window_note = "5 小时峰值处于 Lite 和 Pro 窗口额度内。"
    return {
        "usage_mode": "interactive_ide",
        "team_size": seats,
        "per_seat_monthly_calls": per_seat_monthly_calls,
        "monthly_calls_30d": monthly_calls,
        "recommended_same_family_plan_id": rec_same_family,
        "recommended_overflow_hybrid_plan_id": rec_overflow_hybrid,
        "eligible_subscriptions": eligible,
        "excluded_subscriptions": excluded,
        "headline_zh": headline,
        "window_note_zh": window_note,
    }


def _normalize_region(region: str) -> str:
    val = str(region or "any").strip().lower()
    if val in ("cn", "cn_direct", "china", "domestic", "rmb", "国内"):
        return "cn_direct"
    if val in ("global", "usd", "intl", "openrouter", "海外"):
        return "global"
    return "any"


def _normalize_task(task_type: str) -> str:
    val = str(task_type or "coding").strip().lower()
    if val in ("code", "coding", "programming", "dev", "代码", "编程"):
        return "coding"
    if val in ("reason", "reasoning", "math", "logic", "r1", "推理"):
        return "reasoning"
    if val in ("free", "zero", "免费"):
        return "free"
    if val in ("cheap", "budget", "低价"):
        return "cheap"
    if val in ("vision", "image", "multimodal", "多模态"):
        return "multimodal"
    return "general"


def _compact_view(m: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    item = {
        "id": m["id"],
        "name": m["name"],
        "provider": m["provider"],
        "region": m["region"],
        "input_rmb_per_1m": m["input_rmb_per_1m"],
        "output_rmb_per_1m": m["output_rmb_per_1m"],
        "input_usd_per_1m": m["input_usd_per_1m"],
        "output_usd_per_1m": m["output_usd_per_1m"],
        "context_length": m["context_length"],
        "value_score": m["value_score"],
        "api_base_url": m.get("api_base_url", ""),
        "api_model_id": m.get("api_model_id", m["id"]),
        "signup_url": m.get("signup_url") or m.get("affiliate_url") or "",
    }
    if extra:
        item.update(extra)
    return item


def _run_recommend(catalog: dict[str, Any], inp: Any) -> tuple[str, dict[str, Any], str]:
    models = catalog.get("models", [])
    task = _normalize_task(str(_get_param(inp, "task_type", "coding")))
    region = _normalize_region(str(_get_param(inp, "region_preference", "any")))
    min_ctx = max(0, int(float(_get_param(inp, "min_context", 32000))))
    in_m = max(0.0, float(_get_param(inp, "monthly_input_m", 10.0)))
    out_m = max(0.0, float(_get_param(inp, "monthly_output_m", 2.0)))

    baseline_usd = in_m * 3.0 + out_m * 15.0
    filtered = []
    for m in models:
        if m.get("context_length", 0) < min_ctx:
            continue
        if region != "any" and m.get("region") != region:
            continue
        tags = m.get("tags", [])
        if task == "coding" and "coding" not in tags:
            continue
        if task == "reasoning" and "reasoning" not in tags:
            continue
        if task == "free" and not m.get("is_free"):
            continue
        if task == "cheap" and "cheap" not in tags:
            continue
        if task == "multimodal" and "image" not in str(m.get("modality", "")):
            continue
        filtered.append(m)

    if not filtered:
        filtered = [m for m in models if region == "any" or m.get("region") == region] or models

    scored = []
    for m in filtered:
        est_usd = round(in_m * m["input_usd_per_1m"] + out_m * m["output_usd_per_1m"], 4)
        est_rmb = round(in_m * m["input_rmb_per_1m"] + out_m * m["output_rmb_per_1m"], 2)
        sav_pct = round(max(0.0, (1.0 - est_usd / baseline_usd) * 100.0), 1) if baseline_usd > 0 else 0.0
        scored.append(
            _compact_view(
                m,
                {
                    "estimated_monthly_rmb": est_rmb,
                    "estimated_monthly_usd": est_usd,
                    "savings_vs_flagship_pct": sav_pct,
                    "is_free": bool(m.get("is_free")),
                },
            )
        )

    paid = sorted([x for x in scored if not x["is_free"]], key=lambda x: (x["estimated_monthly_usd"], -x["value_score"]))
    free = sorted([x for x in scored if x["is_free"]], key=lambda x: (-x["value_score"], -x["context_length"]))
    best_val = sorted(scored, key=lambda x: (-x["value_score"], x["estimated_monthly_usd"]))

    cheapest_paid = paid[0] if paid else None
    top_value = best_val[0] if best_val else None
    top_free = free[0] if free else None

    summary = (
        f"已对比 {len(scored)} 款候选大模型（任务={task}，地区={region}，报价核验日={QUOTE_VERIFIED_DATE}）："
        + (
            f"最低成本付费首选【{cheapest_paid['name']}】预计按量 ¥{cheapest_paid['estimated_monthly_rmb']}/月 (${cheapest_paid['estimated_monthly_usd']}/月)；"
            if cheapest_paid
            else ""
        )
        + (f"免费首选【{top_free['name']}】(¥0/月)。" if top_free else "")
    )
    deep_url = f"{WEB_BASE_URL}?region={'cn' if region == 'cn_direct' else ('global' if region == 'global' else 'all')}&qv={QUOTE_VERIFIED_DATE}"
    return (
        summary,
        {
            "cheapest_paid_pick": cheapest_paid,
            "best_value_pick": top_value,
            "best_free_pick": top_free,
            "top_recommendations": (paid[:4] + free[:2])[:5],
        },
        deep_url,
    )


def _parse_scaled_num(raw_val: Any) -> float:
    if isinstance(raw_val, (int, float)):
        return max(0.0, float(raw_val))
    import re

    s = str(raw_val or "").strip().replace(",", "").replace("_", "")
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(百万|亿|万|千|[kKmMbBwW])?$", s)
    if not m:
        raise ValueError(f"invalid_number:{raw_val}")
    base = float(m.group(1))
    unit = (m.group(2) or "").lower()
    mult_map = {
        "b": 1_000_000_000.0,
        "亿": 100_000_000.0,
        "m": 1_000_000.0,
        "百万": 1_000_000.0,
        "w": 10_000.0,
        "万": 10_000.0,
        "k": 1_000.0,
        "千": 1_000.0,
        "": 1.0,
    }
    return max(0.0, base * mult_map.get(unit, 1.0))


def _parse_currency_rmb(raw_val: Any, header_compact: str, fx_rate: float = DEFAULT_FX_USD_TO_RMB) -> float:
    import re

    s = str(raw_val or "").strip()
    if not s or s.lower() in ("-", "n/a", "na", "null", "none"):
        return 0.0
    s_low = s.lower()
    if any(sym in s_low for sym in ("¥", "￥", "rmb", "cny", "元")):
        is_rmb = True
    elif any(sym in s_low for sym in ("$", "usd")):
        is_rmb = False
    elif any(k in header_compact for k in ("rmb", "cny", "应付金额", "账单金额", "消费金额", "费用", "金额", "花费", "总费用", "元")):
        is_rmb = True
    else:
        is_rmb = False
    cleaned = re.sub(r"^(?:usd|rmb|cny|us\$|[$¥￥])\s*", "", s, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*(?:usd|rmb|cny|元)$", "", cleaned, flags=re.IGNORECASE).strip()
    if not cleaned:
        return 0.0
    val = _parse_scaled_num(cleaned)
    return val if is_rmb else val * fx_rate


def _try_parse_csv_bill(text: str, days: float, fx_rate: float = DEFAULT_FX_USD_TO_RMB) -> dict[str, Any] | None:
    import csv
    import io
    import re

    raw_lines = []
    for ln in text.splitlines():
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^\|?[\s:\-]+(?:\|[\s:\-]+)+\|?$", stripped):
            continue
        raw_lines.append(stripped)
    if len(raw_lines) < 2:
        return None

    header_line = raw_lines[0]
    is_pipe = header_line.count("|") >= 2
    delim: str | None = None
    if is_pipe:
        delim = "|"
    else:
        counts = [(d, header_line.count(d)) for d in ("\t", ",", ";")]
        counts.sort(key=lambda x: x[1], reverse=True)
        if counts[0][1] >= 1:
            delim = counts[0][0]
    if delim is None:
        return None

    rows = (
        [[cell.strip().strip('"').strip("'") for cell in ln.strip("|").split("|")] for ln in raw_lines]
        if is_pipe
        else list(csv.reader(io.StringIO("\n".join(raw_lines)), delimiter=delim))
    )
    if len(rows) < 2:
        return None
    raw_headers = [str(c or "").strip().lstrip("\ufeff").strip('"').strip("'") for c in rows[0]]
    if len(raw_headers) < 2 or any(re.match(r"^[0-9.]+$", h) for h in raw_headers if h):
        return None
    compact_headers = [re.sub(r"[\s_\-()/（）]+", "", h.lower()) for h in raw_headers]

    def _find_col(alias_set: set[str]) -> int | None:
        for idx, ch in enumerate(compact_headers):
            if ch in alias_set:
                return idx
        return None

    col_model = _find_col({"model", "modelid", "modelname", "modelpermaslug", "modelslug", "permaslug", "endpoint", "模型", "模型名称", "模型id", "调用模型"})
    col_req = _find_col({"requests", "requestcount", "numrequests", "calls", "apicalls", "totalrequests", "totalcalls", "count", "调用次数", "请求次数", "请求数", "调用量"})
    col_in = _find_col({"tokensprompt", "nativetokensprompt", "prompttokens", "inputtokens", "totalinputtokens", "input", "prompt", "输入token", "输入tokens", "输入token数", "提问token", "入参token"})
    col_out = _find_col({"tokenscompletion", "nativetokenscompletion", "completiontokens", "outputtokens", "totaloutputtokens", "output", "completion", "输出token", "输出tokens", "输出token数", "回答token", "出参token"})
    col_cached = _find_col({"nativetokenscached", "cachedtokens", "cachedinputtokens", "prompttokenscached", "cachehit", "缓存命中token", "缓存命中tokens", "命中缓存token", "缓存token", "缓存输入token", "命中缓存"})
    col_cread = _find_col({"cachereadinputtokens", "cachereadtokens", "cacheread"})
    col_cwrite = _find_col({"cachecreationinputtokens", "cachewritetokens", "cachewrite", "缓存写入token"})
    col_reason = _find_col({"nativetokensreasoning", "reasoningtokens", "thinkingtokens", "思考token", "思考tokens", "推理token"})
    col_cost = _find_col({"usage", "cost", "totalcost", "spend", "amount", "bill", "costusd", "spendusd", "costrmb", "costcny", "应付金额", "账单金额", "消费金额", "费用", "金额", "花费", "总费用"})

    if col_in is None and col_out is None:
        return None

    summary_labels = {"total", "totals", "sum", "summary", "合计", "总计", "汇总", "小计"}
    groups: dict[str, dict[str, Any]] = {}
    cost_header_compact = compact_headers[col_cost] if col_cost is not None else ""

    def _cell_num(r: list[str], idx: int | None) -> float:
        if idx is None or idx >= len(r):
            return 0.0
        v = str(r[idx] or "").strip()
        if not v or v.lower() in ("-", "n/a", "na", "null", "none"):
            return 0.0
        return _parse_scaled_num(v)

    for r in rows[1:]:
        if not r or all(not str(c or "").strip() for c in r):
            continue
        first_clean = str(r[0] or "").strip().lower()
        model_raw = str(r[col_model] if (col_model is not None and col_model < len(r)) else "").strip()
        if first_clean in summary_labels or model_raw.lower() in summary_labels:
            continue
        in_val = _cell_num(r, col_in)
        out_val = _cell_num(r, col_out)
        cached_sub_val = _cell_num(r, col_cached)
        cread_val = _cell_num(r, col_cread)
        cwrite_val = _cell_num(r, col_cwrite)
        reason_val = _cell_num(r, col_reason)
        if col_cread is not None or col_cwrite is not None:
            row_in = in_val + cread_val + cwrite_val
            row_cached = cread_val
        else:
            row_in = max(in_val, cached_sub_val)
            row_cached = min(row_in, cached_sub_val)
        if row_in <= 0 and out_val <= 0:
            continue
        row_reqs = (_cell_num(r, col_req) or 1.0) if col_req is not None else 1.0
        row_cost_rmb = _parse_currency_rmb(r[col_cost], cost_header_compact, fx_rate=fx_rate) if (col_cost is not None and col_cost < len(r)) else 0.0
        model_label = model_raw or "unknown"
        g_key = model_label.lower()
        if g_key not in groups:
            groups[g_key] = {
                "model": model_label,
                "requests": 0.0,
                "input_tokens": 0.0,
                "cached_input_tokens": 0.0,
                "output_tokens": 0.0,
                "reasoning_tokens": 0.0,
                "reported_cost_rmb": 0.0,
            }
        grp = groups[g_key]
        grp["requests"] += row_reqs
        grp["input_tokens"] += row_in
        grp["cached_input_tokens"] += row_cached
        grp["output_tokens"] += out_val
        grp["reasoning_tokens"] += reason_val
        grp["reported_cost_rmb"] += row_cost_rmb

    if not groups:
        raise ValueError("CSV bill contains zero positive token rows")

    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (g["reported_cost_rmb"], g["input_tokens"] + g["output_tokens"]),
        reverse=True,
    )
    model_breakdown: list[dict[str, Any]] = []
    total_reqs = total_in = total_cached = total_out = total_reason = total_cost_rmb = 0.0
    for g in sorted_groups:
        g_in = g["input_tokens"]
        g_cached = min(g_in, max(0.0, g["cached_input_tokens"]))
        total_reqs += g["requests"]
        total_in += g_in
        total_cached += g_cached
        total_out += g["output_tokens"]
        total_reason += g["reasoning_tokens"]
        total_cost_rmb += g["reported_cost_rmb"]
        model_breakdown.append(
            {
                "model": g["model"],
                "requests": int(round(g["requests"])),
                "input_tokens": int(round(g_in)),
                "cached_input_tokens": int(round(g_cached)),
                "output_tokens": int(round(g["output_tokens"])),
                "reasoning_tokens": int(round(g["reasoning_tokens"])),
                "cache_hit_rate": round(g_cached / g_in, 4) if g_in > 0 else 0.0,
                "output_includes_reasoning": bool(g["reasoning_tokens"] > 0),
                "reported_cost_rmb": round(g["reported_cost_rmb"], 4),
            }
        )

    daily_requests = max(1, int(round(total_reqs / days)))
    monthly_requests = max(1, int(round((total_reqs / days) * 30.0)))
    return {
        "detected_format": "csv_multimodel_bill",
        "source_format": "csv_multimodel",
        "deduplicated_chunks": 0,
        "days_observed": days,
        "distinct_models_count": len(model_breakdown),
        "total_requests": int(round(total_reqs)),
        "monthly_requests": monthly_requests,
        "total_input_tokens": int(round(total_in)),
        "cached_input_tokens": int(round(total_cached)),
        "total_output_tokens": int(round(total_out)),
        "monthly_input_m": round(((total_in / days) * 30.0) / 1_000_000.0, 6),
        "monthly_output_m": round(((total_out / days) * 30.0) / 1_000_000.0, 6),
        "daily_requests": daily_requests,
        "avg_input_tokens": max(1, int(round(total_in / max(1.0, total_reqs)))) if total_in > 0 else 1500,
        "avg_output_tokens": max(1, int(round(total_out / max(1.0, total_reqs)))) if total_out > 0 else 500,
        "cache_hit_rate": round(total_cached / total_in, 4) if total_in > 0 else 0.0,
        "output_includes_reasoning": bool(total_reason > 0),
        "calls_estimated": False,
        "reported_cost_rmb": round(total_cost_rmb, 2),
        "monthly_reported_cost_rmb": round((total_cost_rmb / days) * 30.0, 2),
        "model_breakdown": model_breakdown,
    }


def _try_parse_json_records_bill(text: str, days: float, fx_rate: float = DEFAULT_FX_USD_TO_RMB) -> dict[str, Any] | None:
    raw_records: list[dict[str, Any]] | None = None
    source_format: str | None = None

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                raw_records = [x for x in parsed if isinstance(x, dict)]
                source_format = "json_array_multimodel"
        except json.JSONDecodeError:
            raw_records = None
    elif text.startswith("{") and text.endswith("}"):
        try:
            single = json.loads(text)
            if isinstance(single, dict):
                for lk in ("data", "records", "logs", "items", "generations"):
                    cand = single.get(lk)
                    if isinstance(cand, list) and any(isinstance(x, dict) for x in cand):
                        raw_records = [x for x in cand if isinstance(x, dict)]
                        source_format = "json_array_multimodel"
                        break
                if raw_records is None:
                    msg_obj = single.get("message")
                    resp_obj = single.get("response")
                    if (isinstance(msg_obj, dict) and (isinstance(msg_obj.get("usage"), dict) or single.get("type") in ("user", "assistant", "summary", "system"))) or (
                        isinstance(resp_obj, dict) and isinstance(resp_obj.get("body"), dict)
                    ):
                        raw_records = [single]
                        source_format = "jsonl_multimodel"
        except json.JSONDecodeError:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            if len(lines) >= 2:
                parsed_lines: list[dict[str, Any]] = []
                all_json = True
                for ln in lines:
                    if ln.startswith("{") and ln.endswith("}"):
                        try:
                            obj = json.loads(ln)
                            if isinstance(obj, dict):
                                parsed_lines.append(obj)
                            else:
                                all_json = False
                        except json.JSONDecodeError:
                            all_json = False
                    else:
                        all_json = False
                if len(parsed_lines) >= 2 or (all_json and len(parsed_lines) >= 1):
                    raw_records = parsed_lines
                    source_format = "jsonl_multimodel"

    if raw_records is None or source_format is None:
        return None

    def _snum(v: Any) -> float:
        if v is None or isinstance(v, (dict, list, bool)):
            return 0.0
        try:
            return _parse_scaled_num(v)
        except ValueError:
            return 0.0

    def _fval(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for k in keys:
            if d.get(k) is not None and not isinstance(d.get(k), (dict, list, bool)):
                return d.get(k)
        return None

    skip_types = {"user", "summary", "system", "file-history-snapshot", "queue-operation"}
    summary_labels = {"total", "totals", "sum", "summary", "合计", "总计", "汇总", "小计"}
    deduped: dict[str, dict[str, Any]] = {}
    anon: list[dict[str, Any]] = []
    dedup_cnt = 0

    for rec in raw_records:
        if str(rec.get("type") or "").strip().lower() in skip_types:
            continue
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        resp = rec.get("response") if isinstance(rec.get("response"), dict) else {}
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        u = (
            (msg.get("usage") if isinstance(msg.get("usage"), dict) else None)
            or (body.get("usage") if isinstance(body.get("usage"), dict) else None)
            or (rec.get("usage") if isinstance(rec.get("usage"), dict) else None)
            or {}
        )
        m_raw = (
            _fval(rec, ("model_permaslug", "model", "model_id", "model_name", "api_model_id"))
            or _fval(msg, ("model", "model_id"))
            or _fval(body, ("model", "model_id"))
            or "unknown"
        )
        m_label = str(m_raw).strip() or "unknown"
        if m_label.lower() in summary_labels:
            continue

        merged = {**rec, **body, **msg, **u}
        if "cache_read_input_tokens" in merged or "cache_creation_input_tokens" in merged:
            row_in = _snum(merged.get("input_tokens")) + _snum(merged.get("cache_read_input_tokens")) + _snum(merged.get("cache_creation_input_tokens"))
            row_cached = _snum(merged.get("cache_read_input_tokens"))
        else:
            p_det = merged.get("prompt_tokens_details") if isinstance(merged.get("prompt_tokens_details"), dict) else {}
            in_det = merged.get("input_tokens_details") if isinstance(merged.get("input_tokens_details"), dict) else {}
            in_val = _snum(_fval(merged, ("prompt_tokens", "native_tokens_prompt", "tokens_prompt", "input_tokens", "total_input_tokens")))
            c_raw = (
                p_det.get("cached_tokens")
                if p_det.get("cached_tokens") is not None
                else (
                    in_det.get("cached_tokens")
                    if in_det.get("cached_tokens") is not None
                    else _fval(merged, ("native_tokens_cached", "cached_tokens", "cached_input_tokens", "cache_hit_tokens"))
                )
            )
            c_val = _snum(c_raw)
            row_in = max(in_val, c_val)
            row_cached = min(row_in, c_val)

        out_val = _snum(_fval(merged, ("completion_tokens", "native_tokens_completion", "tokens_completion", "output_tokens", "total_output_tokens")))
        c_det = merged.get("completion_tokens_details") if isinstance(merged.get("completion_tokens_details"), dict) else {}
        o_det = merged.get("output_tokens_details") if isinstance(merged.get("output_tokens_details"), dict) else {}
        r_raw = (
            c_det.get("reasoning_tokens")
            if c_det.get("reasoning_tokens") is not None
            else (o_det.get("reasoning_tokens") if o_det.get("reasoning_tokens") is not None else _fval(merged, ("native_tokens_reasoning", "reasoning_tokens", "thinking_tokens")))
        )
        reason_val = _snum(r_raw)
        if row_in <= 0 and out_val <= 0:
            continue

        req_raw = _fval(rec, ("requests", "total_requests", "calls", "api_calls", "num_requests", "request_count"))
        row_reqs = max(1.0, _snum(req_raw)) if req_raw is not None else 1.0

        rmb_raw = _fval(rec, ("cost_rmb", "spend_rmb", "cost_cny", "应付金额", "账单金额"))
        usd_raw = _fval(rec, ("spend", "response_cost", "cost_usd", "costUSD", "total_cost", "cost"))
        if usd_raw is None and rec.get("usage") is not None and not isinstance(rec.get("usage"), (dict, list, bool)):
            usd_raw = rec.get("usage")
        if rmb_raw is not None:
            row_cost_rmb = _parse_currency_rmb(rmb_raw, "costrmb", fx_rate=fx_rate)
        elif usd_raw is not None:
            row_cost_rmb = _parse_currency_rmb(usd_raw, "costusd", fx_rate=fx_rate)
        else:
            row_cost_rmb = 0.0

        dedupe_id = None
        if req_raw is None:
            if msg.get("id"):
                dedupe_id = f"msg:{msg['id']}"
            elif body.get("id"):
                dedupe_id = f"body:{body['id']}"
            elif rec.get("generation_id"):
                dedupe_id = f"gen:{rec['generation_id']}"
            elif rec.get("request_id"):
                dedupe_id = f"req:{rec['request_id']}"
            elif rec.get("id"):
                dedupe_id = f"id:{rec['id']}"

        ent = {
            "model": m_label,
            "requests": row_reqs,
            "input_tokens": row_in,
            "cached_input_tokens": row_cached,
            "output_tokens": out_val,
            "reasoning_tokens": reason_val,
            "reported_cost_rmb": row_cost_rmb,
        }
        if dedupe_id:
            if dedupe_id in deduped:
                dedup_cnt += 1
                prev = deduped[dedupe_id]
                for nk in ("requests", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "reported_cost_rmb"):
                    prev[nk] = max(prev[nk], ent[nk])
                if prev["model"] == "unknown" and ent["model"] != "unknown":
                    prev["model"] = ent["model"]
            else:
                deduped[dedupe_id] = ent
        else:
            anon.append(ent)

    all_ent = list(deduped.values()) + anon
    if not all_ent:
        raise ValueError("JSON/JSONL bill contains zero positive token records")

    groups: dict[str, dict[str, Any]] = {}
    for ent in all_ent:
        gk = ent["model"].lower()
        if gk not in groups:
            groups[gk] = {
                "model": ent["model"],
                "requests": 0.0,
                "input_tokens": 0.0,
                "cached_input_tokens": 0.0,
                "output_tokens": 0.0,
                "reasoning_tokens": 0.0,
                "reported_cost_rmb": 0.0,
            }
        g = groups[gk]
        g["requests"] += ent["requests"]
        g["input_tokens"] += ent["input_tokens"]
        g["cached_input_tokens"] += ent["cached_input_tokens"]
        g["output_tokens"] += ent["output_tokens"]
        g["reasoning_tokens"] += ent["reasoning_tokens"]
        g["reported_cost_rmb"] += ent["reported_cost_rmb"]

    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (g["reported_cost_rmb"], g["input_tokens"] + g["output_tokens"]),
        reverse=True,
    )
    model_breakdown: list[dict[str, Any]] = []
    total_reqs = total_in = total_cached = total_out = total_reason = total_cost_rmb = 0.0
    for g in sorted_groups:
        g_in = g["input_tokens"]
        g_cached = min(g_in, max(0.0, g["cached_input_tokens"]))
        total_reqs += g["requests"]
        total_in += g_in
        total_cached += g_cached
        total_out += g["output_tokens"]
        total_reason += g["reasoning_tokens"]
        total_cost_rmb += g["reported_cost_rmb"]
        model_breakdown.append(
            {
                "model": g["model"],
                "requests": int(round(g["requests"])),
                "input_tokens": int(round(g_in)),
                "cached_input_tokens": int(round(g_cached)),
                "output_tokens": int(round(g["output_tokens"])),
                "reasoning_tokens": int(round(g["reasoning_tokens"])),
                "cache_hit_rate": round(g_cached / g_in, 4) if g_in > 0 else 0.0,
                "output_includes_reasoning": bool(g["reasoning_tokens"] > 0),
                "reported_cost_rmb": round(g["reported_cost_rmb"], 4),
            }
        )

    daily_requests = max(1, int(round(total_reqs / days)))
    monthly_requests = max(1, int(round((total_reqs / days) * 30.0)))
    return {
        "detected_format": "csv_multimodel_bill",
        "source_format": source_format,
        "deduplicated_chunks": dedup_cnt,
        "days_observed": days,
        "distinct_models_count": len(model_breakdown),
        "total_requests": int(round(total_reqs)),
        "monthly_requests": monthly_requests,
        "total_input_tokens": int(round(total_in)),
        "cached_input_tokens": int(round(total_cached)),
        "total_output_tokens": int(round(total_out)),
        "monthly_input_m": round(((total_in / days) * 30.0) / 1_000_000.0, 6),
        "monthly_output_m": round(((total_out / days) * 30.0) / 1_000_000.0, 6),
        "daily_requests": daily_requests,
        "avg_input_tokens": max(1, int(round(total_in / max(1.0, total_reqs)))) if total_in > 0 else 1500,
        "avg_output_tokens": max(1, int(round(total_out / max(1.0, total_reqs)))) if total_out > 0 else 500,
        "cache_hit_rate": round(total_cached / total_in, 4) if total_in > 0 else 0.0,
        "output_includes_reasoning": bool(total_reason > 0),
        "calls_estimated": False,
        "reported_cost_rmb": round(total_cost_rmb, 2),
        "monthly_reported_cost_rmb": round((total_cost_rmb / days) * 30.0, 2),
        "model_breakdown": model_breakdown,
    }


def _match_model_in_catalog(models: list[dict[str, Any]], raw_q: str) -> dict[str, Any]:
    import re as _re

    raw = str(raw_q or "deepseek-v3").strip() or "deepseek-v3"
    q = raw.lower()
    norm_q = q
    if norm_q.startswith("aliyun/"):
        norm_q = "aliyun-bailian/" + norm_q.removeprefix("aliyun/")
    elif norm_q.startswith("tencent/"):
        norm_q = "tencent-cloud/" + norm_q.removeprefix("tencent/")
    for m in models:
        if m["id"] == raw or m["id"].lower() == norm_q:
            return m
    suffix_matches = [
        m for m in models
        if str(m.get("api_model_id") or "").lower() == q or m["id"].lower().endswith("/" + q)
    ]
    if suffix_matches:
        suffix_matches.sort(
            key=lambda item: (
                1 if item.get("region") == "cn_direct" else 0,
                0 if item.get("is_free") else 1,
                float(item.get("value_score") or 0.0),
            ),
            reverse=True,
        )
        return suffix_matches[0]

    stripped_q = _re.sub(r"-(?:20\d{2}-\d{2}-\d{2}|20\d{6}|\d{4})$", "", q)
    slug_base = stripped_q.split("/")[-1]
    alias_cands: list[str] = []
    if stripped_q != q:
        alias_cands.extend([stripped_q, slug_base])
    if slug_base in ("deepseek-reasoner", "r1"):
        alias_cands.append("deepseek-r1")
    elif slug_base in ("deepseek-chat", "v3"):
        alias_cands.append("deepseek-v3")
    elif slug_base in ("gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano", "o1-mini", "o3-mini", "o4-mini"):
        alias_cands.extend(["openai/gpt-5.4-mini", "openai/gpt-5-mini"])
    elif slug_base.startswith(("gpt-4", "chatgpt-4o")) or slug_base in ("o1", "o3", "o3-pro"):
        alias_cands.extend(["openai/gpt-5.4", "openai/gpt-5.5"])
    elif "claude" in slug_base and "sonnet" in slug_base:
        alias_cands.extend(["anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5", "anthropic/claude-sonnet-4"])
    elif "claude" in slug_base and "opus" in slug_base:
        alias_cands.extend(["anthropic/claude-opus-5.5", "anthropic/claude-opus-5"])
    elif "claude" in slug_base and "haiku" in slug_base:
        alias_cands.append("anthropic/claude-haiku-5.5")
    for ca in alias_cands:
        ca_low = ca.lower()
        ca_hits = [
            m for m in models
            if m["id"].lower() == ca_low
            or str(m.get("api_model_id") or "").lower() == ca_low
            or m["id"].lower().endswith("/" + ca_low)
        ]
        if ca_hits:
            ca_hits.sort(
                key=lambda item: (
                    1 if item.get("region") == "cn_direct" else 0,
                    0 if item.get("is_free") else 1,
                    float(item.get("value_score") or 0.0),
                ),
                reverse=True,
            )
            return ca_hits[0]

    wants_free = "free" in q
    best_match = models[0]
    best_rank = -1.0
    q_tokens = [tok for tok in norm_q.replace("/", " ").replace("-", " ").split() if tok]
    for m in models:
        mid = m["id"].lower()
        api_id = str(m.get("api_model_id") or "").lower()
        mname = m["name"].lower()
        hay = f"{mid} {api_id} {mname} {m['provider'].lower()}"
        score = 0.0
        if norm_q in mid or (api_id and q in api_id):
            score = 700.0
        elif q in mname:
            score = 600.0
        elif q_tokens and all(tok in hay for tok in q_tokens):
            score = 500.0
        elif q_tokens:
            overlap = sum(1 for tok in q_tokens if tok in hay)
            if overlap > 0:
                score = overlap * 120.0
        if score > 0:
            if not wants_free and m.get("is_free"):
                score -= 50.0
            score += float(m.get("value_score", 0.0)) * 0.1
            if score > best_rank:
                best_rank = score
                best_match = m
    return best_match


def _resolve_coze_env_key_var(model: dict[str, Any]) -> str:
    pkey = str(model.get("provider_config_key") or "").lower()
    base = str(model.get("api_base_url") or "").lower()
    if pkey == "aliyun_bailian_url" or "dashscope.aliyuncs.com" in base:
        return "DASHSCOPE_API_KEY"
    if pkey == "tencent_cps_url" or "lkeap.cloud.tencent.com" in base:
        return "TENCENT_LKEAP_API_KEY"
    if pkey == "volcengine_ark_url" or "volces.com" in base:
        return "VOLCENGINE_ARK_API_KEY"
    if pkey == "siliconflow_invite_url" or "siliconflow.cn" in base:
        return "SILICONFLOW_API_KEY"
    return "OPENROUTER_API_KEY"


def _resolve_coze_api_base(model: dict[str, Any]) -> str:
    base = str(model.get("api_base_url") or "").strip()
    if base:
        return base
    return "https://openrouter.ai/api/v1" if model.get("region") == "global" else "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _find_coze_same_family_cn(raw_model_name: str, workhorses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_low = str(raw_model_name or "").lower()
    if "deepseek-r1" in raw_low or "deepseek-reasoner" in raw_low or raw_low.endswith("/r1"):
        return [c for c in workhorses if "deepseek-r1" in c["id"].lower()]
    if "deepseek-v3" in raw_low or "deepseek-chat" in raw_low:
        return [c for c in workhorses if "deepseek-v3" in c["id"].lower()]
    if "qwen3-coder" in raw_low or "qwen-coder" in raw_low:
        return [c for c in workhorses if "qwen" in c["id"].lower() and "coder" in c["id"].lower()]
    if "qwen" in raw_low:
        return [c for c in workhorses if "qwen" in c["id"].lower()]
    if "glm" in raw_low:
        return [c for c in workhorses if "glm" in c["id"].lower()]
    if "kimi" in raw_low or "moonshot" in raw_low:
        return [c for c in workhorses if "kimi" in c["id"].lower()]
    if "minimax" in raw_low:
        return [c for c in workhorses if "minimax" in c["id"].lower()]
    if "doubao" in raw_low:
        return [c for c in workhorses if "doubao" in c["id"].lower()]
    if "hunyuan" in raw_low:
        return [c for c in workhorses if "hunyuan" in c["id"].lower()]
    return []


def _build_coze_migration_litellm_config(line_items: list[dict[str, Any]]) -> dict[str, Any]:
    yaml_lines = [
        "# AI Cost Radar — Zero-Code Multi-Model Bill Migration (LiteLLM Proxy)",
        "# Compliance: Use standard Pay-As-You-Go API keys ONLY (NEVER use sk-sp- Coding Plan keys).",
        "model_list:",
    ]
    req_vars: list[str] = []
    for item in line_items:
        alias_esc = str(item.get("raw_model") or "default").replace("\\", "\\\\").replace('"', '\\"')
        api_mid = str(item.get("recommended_api_model_id") or item.get("recommended_model_id") or "deepseek-v3")
        api_base = str(item.get("recommended_api_base_url") or "https://dashscope.aliyuncs.com/compatible-mode/v1")
        env_var = str(item.get("recommended_env_key_var") or "DASHSCOPE_API_KEY")
        if env_var not in req_vars:
            req_vars.append(env_var)
        yaml_lines.extend(
            [
                f'  - model_name: "{alias_esc}"',
                "    litellm_params:",
                f"      model: openai/{api_mid}",
                f"      api_base: {api_base}",
                f"      api_key: os.environ/{env_var}",
            ]
        )
    yaml_lines.extend(["", "router_settings:", "  routing_strategy: simple-shuffle", "  num_retries: 2", "  timeout: 60"])
    env_lines = [f'export {v}="sk-your-{v.lower().replace("_api_key", "")}-payg-key"' for v in req_vars]
    env_lines.extend(
        [
            'export LITELLM_MASTER_KEY="sk-local-bill-migration-proxy"',
            "",
            "# 启动本地零改代码迁移网关（业务代码无需改 model 名，仅需设 OPENAI_BASE_URL=http://127.0.0.1:4000/v1）",
            "uvx --from 'litellm[proxy]' litellm --config config.yaml --port 4000",
        ]
    )
    probe = str(line_items[0]["raw_model"] if line_items else "deepseek-v3").replace("\\", "\\\\").replace('"', '\\"')
    smoke_cmd = (
        'curl -fsS "http://127.0.0.1:4000/v1/chat/completions" '
        '-H "Authorization: Bearer sk-local-bill-migration-proxy" '
        '-H "Content-Type: application/json" '
        f'-d \'{{"model":"{probe}","max_tokens":1,"messages":[{{"role":"user","content":"ping"}}]}}\''
    )
    return {
        "config_yaml": "\n".join(yaml_lines),
        "env_snippet": "\n".join(env_lines),
        "smoke_test_cmd": smoke_cmd,
        "required_env_vars": req_vars,
        "distinct_providers_count": len(req_vars),
        "compliance_warning_zh": (
            "合规红线：此网关配置仅限填入各厂商标准「按量付费 API Key」（sk-...）；"
            "严禁将个人 Coding Plan 包月专属密钥（sk-sp-...）填入 LiteLLM 网关或团队共享服务。"
        ),
    }


def _audit_csv_bill_coze(
    models: list[dict[str, Any]],
    parsed: dict[str, Any],
    usage_mode: str,
    seats: int,
    offers: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    days = float(parsed["days_observed"])
    scale_30d = 30.0 / days
    norm_mode = "automated_backend" if str(usage_mode or "").strip().lower() in (
        "automated_backend", "backend", "api_service", "batch", "non_interactive"
    ) else "interactive_ide"
    workhorses = [
        m for m in models
        if m.get("region") == "cn_direct"
        and not m.get("is_free")
        and int(m.get("context_length") or 0) >= 64000
        and not any(tok in m["id"].lower() for tok in ("7b", "8b", "lite", "turbo", "mini", "flash"))
    ]
    line_items: list[dict[str, Any]] = []
    has_global_closed = False
    for grp in parsed.get("model_breakdown", []):
        raw_model_name = str(grp["model"])
        raw_low = raw_model_name.lower()
        m_reqs = max(1, int(round(float(grp["requests"]) * scale_30d)))
        m_in_m = (float(grp["input_tokens"]) * scale_30d) / 1_000_000.0
        m_out_m = (float(grp["output_tokens"]) * scale_30d) / 1_000_000.0
        hit_rate = float(grp["cache_hit_rate"])
        reported_monthly_rmb = round(float(grp["reported_cost_rmb"]) * scale_30d, 2)
        matched = _match_model_in_catalog(models, raw_model_name)
        matched_id_low = matched["id"].lower()
        if matched.get("region") == "global" and any(
            v in raw_low or v in matched_id_low
            for v in ("anthropic", "claude", "openai", "gpt-", "o1", "o3", "o4", "google", "gemini", "x-ai", "grok")
        ):
            has_global_closed = True
        m_hit = float(matched.get("cache_hit_factor") if matched.get("cache_hit_factor") is not None else (0.2 if matched.get("region") == "cn_direct" else 0.5))
        catalog_payg_rmb = round(
            _calc_token_bill(m_in_m, m_out_m, matched["input_rmb_per_1m"], matched["output_rmb_per_1m"], hit_rate, m_hit, 1.0, True)["total_cost"],
            2,
        )
        baseline_rmb = reported_monthly_rmb if reported_monthly_rmb > 0 else catalog_payg_rmb
        needs_reasoning = bool(
            grp.get("output_includes_reasoning")
            or any(k in raw_low for k in ("-r1", "/r1", "deepseek-r1", "o1", "o3", "o4", "qwq", "hunyuan-t1", "thinking", "reasoner"))
        )
        req_tag = "reasoning" if needs_reasoning else "coding"
        pool = [c for c in workhorses if req_tag in (c.get("tags") or [])] or workhorses
        best_cand = None
        best_cand_rmb = baseline_rmb
        best_cand_score = -1.0
        for cand in pool:
            c_hit = float(cand.get("cache_hit_factor") if cand.get("cache_hit_factor") is not None else 0.2)
            c_rmb = round(_calc_token_bill(m_in_m, m_out_m, cand["input_rmb_per_1m"], cand["output_rmb_per_1m"], hit_rate, c_hit, 1.0, True)["total_cost"], 2)
            c_score = float(cand.get("value_score") or 0.0)
            if best_cand is None or c_rmb < best_cand_rmb or (c_rmb == best_cand_rmb and c_score > best_cand_score):
                best_cand = cand
                best_cand_rmb = c_rmb
                best_cand_score = c_score

        sf_pool = _find_coze_same_family_cn(raw_model_name, workhorses)
        sf_best = None
        sf_rmb = None
        sf_score = -1.0
        for sfc in sf_pool:
            sf_hit = float(sfc.get("cache_hit_factor") if sfc.get("cache_hit_factor") is not None else 0.2)
            sfc_rmb = round(_calc_token_bill(m_in_m, m_out_m, sfc["input_rmb_per_1m"], sfc["output_rmb_per_1m"], hit_rate, sf_hit, 1.0, True)["total_cost"], 2)
            sfc_score = float(sfc.get("value_score") or 0.0)
            if sf_best is None or sfc_rmb < (sf_rmb or 0.0) or (sfc_rmb == sf_rmb and sfc_score > sf_score):
                sf_best = sfc
                sf_rmb = sfc_rmb
                sf_score = sfc_score

        if best_cand is not None and best_cand_rmb < baseline_rmb - 0.005:
            rec_model, opt_rmb, action = best_cand, round(best_cand_rmb, 2), "switch_cn_direct"
        else:
            rec_model, opt_rmb, action = matched, round(baseline_rmb, 2), "keep_current"
        sav_rmb = round(max(0.0, baseline_rmb - opt_rmb), 2)
        sav_pct = round((sav_rmb / baseline_rmb) * 100.0, 1) if baseline_rmb > 0 else 0.0
        line_items.append(
            {
                "raw_model": raw_model_name,
                "matched_model_id": matched["id"],
                "matched_model_name": matched["name"],
                "monthly_requests": m_reqs,
                "monthly_input_m": round(m_in_m, 4),
                "monthly_output_m": round(m_out_m, 4),
                "cache_hit_rate": hit_rate,
                "reported_monthly_rmb": reported_monthly_rmb,
                "catalog_payg_rmb": catalog_payg_rmb,
                "baseline_monthly_rmb": round(baseline_rmb, 2),
                "recommended_model_id": rec_model["id"],
                "recommended_model_name": rec_model["name"],
                "recommended_api_model_id": str(rec_model.get("api_model_id") or rec_model["id"]),
                "recommended_api_base_url": _resolve_coze_api_base(rec_model),
                "recommended_env_key_var": _resolve_coze_env_key_var(rec_model),
                "recommended_signup_url": rec_model.get("signup_url") or rec_model.get("affiliate_url") or "",
                "same_family_cn_model_id": sf_best["id"] if sf_best else None,
                "same_family_cn_model_name": sf_best["name"] if sf_best else None,
                "same_family_cn_api_model_id": str(sf_best.get("api_model_id") or sf_best["id"]) if sf_best else None,
                "same_family_cn_api_base_url": _resolve_coze_api_base(sf_best) if sf_best else None,
                "same_family_cn_env_key_var": _resolve_coze_env_key_var(sf_best) if sf_best else None,
                "same_family_cn_monthly_rmb": sf_rmb,
                "optimized_payg_rmb": opt_rmb,
                "savings_rmb": sav_rmb,
                "savings_pct": sav_pct,
                "action": action,
            }
        )

    total_m_reqs = sum(x["monthly_requests"] for x in line_items)
    total_base_rmb = round(sum(x["baseline_monthly_rmb"] for x in line_items), 2)
    total_cat_rmb = round(sum(x["catalog_payg_rmb"] for x in line_items), 2)
    total_opt_rmb = round(sum(x["optimized_payg_rmb"] for x in line_items), 2)
    total_sav_rmb = round(max(0.0, total_base_rmb - total_opt_rmb), 2)
    total_sav_pct = round((total_sav_rmb / total_base_rmb) * 100.0, 1) if total_base_rmb > 0 else 0.0

    coding_plan_option = None
    if norm_mode == "interactive_ide":
        sub_offers = [o for o in (offers or SUBSCRIPTION_OFFERS_2026) if isinstance(o, dict) and o.get("offer_type") == "subscription"] or SUBSCRIPTION_OFFERS_2026
        fits_lite = total_m_reqs <= (LITE_MONTHLY_CAP * seats)
        fits_pro = total_m_reqs <= (PRO_MONTHLY_CAP * seats)
        target_id = "tencent-coding-plan" if fits_lite else "aliyun-coding-plan"
        chosen_offer = next((o for o in sub_offers if o["id"] == target_id), sub_offers[0])
        tier_id = "lite" if (fits_lite and any(t.get("tier_id") == "lite" and t.get("purchasable") for t in chosen_offer.get("tiers", []))) else "pro"
        chosen_tier = next((t for t in chosen_offer.get("tiers", []) if t.get("tier_id") == tier_id), (chosen_offer.get("tiers") or [{}])[-1])
        raw_first = chosen_tier.get("first_month_rmb")
        unit_renew = float(chosen_tier.get("renewal_rmb") or 200.0)
        unit_first = float(raw_first) if raw_first is not None else unit_renew
        first_rmb = round(unit_first * seats, 2)
        renew_rmb = round(unit_renew * seats, 2)
        cap_monthly = int(chosen_tier.get("quota_monthly") or PRO_MONTHLY_CAP) * seats
        has_cross_caveat = bool(
            has_global_closed
            or any(not _plan_covers_model(chosen_offer, item["matched_model_id"]) for item in line_items)
        )
        coding_plan_option = {
            "plan_id": chosen_offer["id"],
            "plan_name": chosen_offer["name"],
            "official_source_url": chosen_offer.get("official_source_url", ""),
            "team_size": seats,
            "tier_id": tier_id,
            "tier_name": chosen_tier.get("name", "Pro"),
            "fits_monthly_cap": fits_pro,
            "combined_monthly_cap": cap_monthly,
            "first_month_rmb": first_rmb,
            "renewal_rmb": renew_rmb,
            "vs_baseline_renewal_savings_rmb": round(total_base_rmb - renew_rmb, 2) if fits_pro else None,
            "cheaper_than_optimized_payg_on_renewal": bool(fits_pro and renew_rmb < total_opt_rmb),
            "has_cross_model_caveat": has_cross_caveat,
            "caveat_zh": (
                "原账单含 Claude/GPT 等海外闭源或非套餐同系模型；国内 Coding Plan 仅覆盖千问/混元/豆包/Kimi/GLM/MiniMax/DeepSeek-V3，切换前请先评估代码质量差异。"
                if has_cross_caveat
                else "原账单模型均在国内 Coding Plan 覆盖体系内。"
            ),
        }

    return {
        "days_observed": days,
        "usage_mode": norm_mode,
        "team_size": seats,
        "line_items": line_items,
        "totals": {
            "distinct_models_count": len(line_items),
            "monthly_requests": total_m_reqs,
            "baseline_monthly_rmb": total_base_rmb,
            "catalog_payg_monthly_rmb": total_cat_rmb,
            "optimized_payg_monthly_rmb": total_opt_rmb,
            "payg_savings_rmb": total_sav_rmb,
            "payg_savings_pct": total_sav_pct,
            "has_global_closed_models": has_global_closed,
        },
        "coding_plan_option": coding_plan_option,
        "migration_litellm_config": _build_coze_migration_litellm_config(line_items),
    }


def _parse_usage_snippet(raw_text: str, days_observed: float = 30.0) -> dict[str, Any]:
    import re

    text = str(raw_text or "").strip()
    if not text or len(text) > 32000:
        raise ValueError("Invalid usage_snippet")
    days = float(days_observed if days_observed is not None else 30.0)
    if not math.isfinite(days) or days <= 0 or days > 365:
        days = 30.0

    json_rec_parsed = _try_parse_json_records_bill(text, days)
    if json_rec_parsed is not None:
        return json_rec_parsed

    total_input = 0.0
    cached_input = 0.0
    total_output = 0.0
    explicit_requests: float | None = None
    explicit_daily_requests: float | None = None
    output_includes_reasoning = False
    detected_format = "text_summary"

    json_obj: dict[str, Any] | None = None
    if "{" in text and "}" in text:
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if end_idx > start_idx:
            try:
                parsed = json.loads(text[start_idx : end_idx + 1])
                if isinstance(parsed, dict):
                    json_obj = parsed
            except json.JSONDecodeError:
                json_obj = None

    if json_obj is not None:
        u = dict(json_obj.get("usage")) if isinstance(json_obj.get("usage"), dict) else {}
        merged = {**json_obj, **u}
        for rk in ("requests", "total_requests", "calls", "total_calls", "api_calls", "num_requests"):
            if merged.get(rk) is not None:
                explicit_requests = _parse_scaled_num(merged[rk])
                break
        if explicit_requests is None and merged.get("daily_requests") is not None:
            explicit_daily_requests = _parse_scaled_num(merged["daily_requests"])
        if "cache_read_input_tokens" in merged or "cache_creation_input_tokens" in merged:
            detected_format = "anthropic_usage_json"
            uncached = _parse_scaled_num(merged.get("input_tokens") or 0)
            c_read = _parse_scaled_num(merged.get("cache_read_input_tokens") or 0)
            c_write = _parse_scaled_num(merged.get("cache_creation_input_tokens") or 0)
            total_input = uncached + c_read + c_write
            cached_input = c_read
        else:
            detected_format = "openai_usage_json"
            p_det = merged.get("prompt_tokens_details") if isinstance(merged.get("prompt_tokens_details"), dict) else {}
            in_det = merged.get("input_tokens_details") if isinstance(merged.get("input_tokens_details"), dict) else {}
            raw_in = merged.get("prompt_tokens") if merged.get("prompt_tokens") is not None else merged.get("input_tokens")
            if raw_in is not None:
                total_input = _parse_scaled_num(raw_in)
            raw_cached = (
                p_det.get("cached_tokens")
                if p_det.get("cached_tokens") is not None
                else (
                    in_det.get("cached_tokens")
                    if in_det.get("cached_tokens") is not None
                    else (merged.get("cached_tokens") if merged.get("cached_tokens") is not None else merged.get("cached_input_tokens"))
                )
            )
            if raw_cached is not None:
                cached_input = _parse_scaled_num(raw_cached)
                if total_input < cached_input:
                    total_input = cached_input
        raw_out = merged.get("completion_tokens") if merged.get("completion_tokens") is not None else merged.get("output_tokens")
        if raw_out is not None:
            total_output = _parse_scaled_num(raw_out)
        c_det = merged.get("completion_tokens_details") if isinstance(merged.get("completion_tokens_details"), dict) else {}
        o_det = merged.get("output_tokens_details") if isinstance(merged.get("output_tokens_details"), dict) else {}
        r_tok = (
            c_det.get("reasoning_tokens")
            if c_det.get("reasoning_tokens") is not None
            else (o_det.get("reasoning_tokens") if o_det.get("reasoning_tokens") is not None else merged.get("reasoning_tokens"))
        )
        if r_tok is not None and _parse_scaled_num(r_tok) > 0:
            output_includes_reasoning = True
    else:
        csv_parsed = _try_parse_csv_bill(text, days)
        if csv_parsed is not None:
            return csv_parsed
        num_pat = r"([0-9][0-9,._]*\s*(?:百万|亿|万|千|[kKmMbBwW])?)"
        m_in = re.search(
            r"(?:total\s+input(?:\s+tokens?)?|uncached\s+input|prompt\s+tokens?|\binput(?:\s+tokens?)?|输入\s*(?:token|tokens)?)\s*[:：=]?\s*" + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        m_cr = re.search(
            r"(?:cache\s*read(?:\s+input)?(?:\s+tokens?)?|cached(?:\s+input)?(?:\s+tokens?)?|缓存命中(?:\s*token|\s*tokens|\s*输入)?|命中缓存)\s*[:：=]?\s*" + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        m_cw = re.search(r"(?:cache\s*(?:write|creation)(?:\s+tokens?)?|缓存写入)\s*[:：=]?\s*" + num_pat, text, flags=re.IGNORECASE)
        m_out = re.search(
            r"(?:total\s+output(?:\s+tokens?)?|completion\s+tokens?|\boutput(?:\s+tokens?)?|输出\s*(?:token|tokens)?)\s*[:：=]?\s*" + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        m_rs = re.search(r"(?:reasoning\s+tokens?|思考\s*(?:token|tokens)?)\s*[:：=]?\s*" + num_pat, text, flags=re.IGNORECASE)
        m_rq = re.search(
            r"(?:total\s+requests?|api\s+calls?|total\s+calls?|\brequests?|\bturns?|调用(?:次数|量)?|请求(?:次数|数)?)\s*[:：=]?\s*" + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        raw_in_val = _parse_scaled_num(m_in.group(1)) if m_in else 0.0
        cr_val = _parse_scaled_num(m_cr.group(1)) if m_cr else 0.0
        cw_val = _parse_scaled_num(m_cw.group(1)) if m_cw else 0.0
        total_output = _parse_scaled_num(m_out.group(1)) if m_out else 0.0
        is_cc = bool(re.search(r"cache\s*read", text, flags=re.IGNORECASE)) and not bool(re.search(r"total\s+input", text, flags=re.IGNORECASE))
        if is_cc:
            detected_format = "claude_code_cost"
            total_input = raw_in_val + cr_val + cw_val
            cached_input = cr_val
        elif raw_in_val >= cr_val and raw_in_val > 0:
            total_input = raw_in_val
            cached_input = cr_val
        else:
            total_input = raw_in_val + cr_val + cw_val
            cached_input = cr_val
        if m_rs and _parse_scaled_num(m_rs.group(1)) > 0:
            output_includes_reasoning = True
        if m_rq:
            explicit_requests = _parse_scaled_num(m_rq.group(1))

    if total_input <= 0 and total_output <= 0:
        raise ValueError("Unable to find input/output token counts in usage_snippet")
    cached_input = min(total_input, max(0.0, cached_input))
    cache_hit_rate = round(cached_input / total_input, 4) if total_input > 0 else 0.0
    if explicit_daily_requests is not None and explicit_daily_requests > 0:
        daily_requests = max(1, int(round(explicit_daily_requests)))
        est_total_calls = max(1.0, explicit_daily_requests * days)
    elif explicit_requests is not None and explicit_requests > 0:
        est_total_calls = max(1.0, explicit_requests)
        daily_requests = max(1, int(round(est_total_calls / days)))
    else:
        est_total_calls = max(1.0, round(total_input / 4000.0) if total_input > 0 else round(total_output / 800.0))
        daily_requests = max(1, int(round(est_total_calls / days)))

    return {
        "detected_format": detected_format,
        "days_observed": days,
        "monthly_input_m": round(((total_input / days) * 30.0) / 1_000_000.0, 6),
        "monthly_output_m": round(((total_output / days) * 30.0) / 1_000_000.0, 6),
        "daily_requests": daily_requests,
        "avg_input_tokens": max(1, int(round(total_input / est_total_calls))) if total_input > 0 else 1500,
        "avg_output_tokens": max(1, int(round(total_output / est_total_calls))) if total_output > 0 else 500,
        "cache_hit_rate": cache_hit_rate,
        "output_includes_reasoning": output_includes_reasoning,
    }


def _run_budget(catalog: dict[str, Any], inp: Any) -> tuple[str, dict[str, Any], str]:
    models = catalog.get("models", [])
    q = str(_get_param(inp, "model_query", "deepseek-v3")).strip().lower()
    reqs = max(0.0, float(_get_param(inp, "daily_requests", 1000)))
    in_tok = max(0.0, float(_get_param(inp, "avg_input_tokens", 1500)))
    out_tok = max(0.0, float(_get_param(inp, "avg_output_tokens", 500)))
    hit_rate = min(1.0, max(0.0, float(_get_param(inp, "cache_hit_rate", 0.0))))
    r_mult = max(1.0, float(_get_param(inp, "reasoning_multiplier", 1.0)))
    inc_cot = str(_get_param(inp, "output_includes_reasoning", "false")).lower() in ("true", "1", "yes")
    usage_mode = str(_get_param(inp, "usage_mode", "interactive_ide"))
    wants_free = "free" in q

    raw_snippet = _get_param(inp, "usage_snippet", None)
    raw_days = float(_get_param(inp, "days_observed", 30.0))
    raw_m_reqs = _get_param(inp, "monthly_requests", None)
    raw_m_in = _get_param(inp, "monthly_input_m", None)
    raw_m_out = _get_param(inp, "monthly_output_m", None)
    raw_c_in = _get_param(inp, "cached_input_m", None)
    exact_monthly_in_m: float | None = None
    exact_monthly_out_m: float | None = None
    parsed_usage_summary: dict[str, Any] | None = None
    bill_audit: dict[str, Any] | None = None
    raw_seats = _get_param(inp, "team_size", 1)
    seats = max(1, min(50, int(round(float(raw_seats or 1)))))

    if raw_snippet is not None and str(raw_snippet).strip() != "":
        parsed_usage_summary = _parse_usage_snippet(str(raw_snippet), days_observed=raw_days)
        reqs = float(parsed_usage_summary["daily_requests"])
        in_tok = float(parsed_usage_summary["avg_input_tokens"])
        out_tok = float(parsed_usage_summary["avg_output_tokens"])
        hit_rate = float(parsed_usage_summary["cache_hit_rate"])
        exact_monthly_in_m = float(parsed_usage_summary["monthly_input_m"])
        exact_monthly_out_m = float(parsed_usage_summary["monthly_output_m"])
        if parsed_usage_summary.get("output_includes_reasoning"):
            inc_cot = True
        if parsed_usage_summary.get("detected_format") == "csv_multimodel_bill":
            if not q or q == "auto":
                bd = parsed_usage_summary.get("model_breakdown") or []
                if bd:
                    q = str(bd[0].get("model") or "deepseek-v3").strip().lower()
                    wants_free = "free" in q
            bill_audit = _audit_csv_bill_coze(
                models,
                parsed_usage_summary,
                usage_mode,
                seats,
                catalog.get("coding_plans") if isinstance(catalog.get("coding_plans"), list) else None,
            )
    elif any(v is not None for v in (raw_m_reqs, raw_m_in, raw_m_out, raw_c_in)):
        if raw_m_reqs is not None:
            m_reqs = max(1, int(round(float(raw_m_reqs))))
        elif raw_m_in is not None and float(raw_m_in) > 0:
            m_reqs = max(1, int(round((float(raw_m_in) * 1_000_000.0) / max(1.0, in_tok))))
        else:
            m_reqs = max(1, int(round(reqs * 30.0)))
        m_in = max(0.0, float(raw_m_in)) if raw_m_in is not None else (m_reqs * in_tok) / 1_000_000.0
        m_out = max(0.0, float(raw_m_out)) if raw_m_out is not None else (m_reqs * out_tok) / 1_000_000.0
        if raw_c_in is not None:
            c_in = max(0.0, float(raw_c_in))
            hit_rate = round(min(1.0, c_in / m_in), 4) if m_in > 0 else 0.0
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
            "daily_requests": int(reqs),
            "avg_input_tokens": int(in_tok),
            "avg_output_tokens": int(out_tok),
            "cache_hit_rate": hit_rate,
        }

    best_match = models[0]
    best_rank = -1.0
    norm_q = q
    if norm_q.startswith("aliyun/"):
        norm_q = "aliyun-bailian/" + norm_q.removeprefix("aliyun/")
    elif norm_q.startswith("tencent/"):
        norm_q = "tencent-cloud/" + norm_q.removeprefix("tencent/")
    q_tokens = [tok for tok in norm_q.replace("/", " ").replace("-", " ").split() if tok]
    for m in models:
        mid = m["id"].lower()
        api_id = str(m.get("api_model_id") or "").lower()
        mname = m["name"].lower()
        hay = f"{mid} {api_id} {mname} {m['provider'].lower()}"
        score = 0.0
        if mid == norm_q or mid == q:
            score = 1000.0
        elif api_id and (api_id == norm_q or api_id == q):
            score = 950.0 + (20.0 if m.get("region") == "cn_direct" else 0.0)
        elif mid.endswith("/" + norm_q) or mid.endswith("/" + q):
            score = 900.0 + (20.0 if m.get("region") == "cn_direct" else 0.0)
        elif norm_q in mid or q in mid:
            score = 700.0
        elif norm_q in mname or q in mname:
            score = 600.0
        elif q_tokens and all(tok in hay for tok in q_tokens):
            score = 500.0
        elif q_tokens:
            overlap = sum(1 for tok in q_tokens if tok in hay)
            if overlap > 0:
                score = overlap * 120.0
        if score > 0:
            if not wants_free and m.get("is_free"):
                score -= 50.0
            score += float(m.get("value_score", 0.0)) * 0.1
            if score > best_rank:
                best_rank = score
                best_match = m

    monthly_in_m = exact_monthly_in_m if exact_monthly_in_m is not None else ((reqs * in_tok * 30.0) / 1_000_000.0)
    monthly_out_m = exact_monthly_out_m if exact_monthly_out_m is not None else ((reqs * out_tok * 30.0) / 1_000_000.0)
    model_hit_factor = float(
        best_match.get("cache_hit_factor")
        if best_match.get("cache_hit_factor") is not None
        else (0.2 if best_match.get("region") == "cn_direct" else 0.5)
    )
    is_reasoning = "reasoning" in (best_match.get("tags") or [])
    effective_r_mult = 1.0 if (inc_cot or not is_reasoning) else r_mult

    bill_rmb = _calc_token_bill(
        monthly_in_m,
        monthly_out_m,
        best_match["input_rmb_per_1m"],
        best_match["output_rmb_per_1m"],
        hit_rate,
        model_hit_factor,
        effective_r_mult,
        inc_cot,
    )
    bill_usd = _calc_token_bill(
        monthly_in_m,
        monthly_out_m,
        best_match["input_usd_per_1m"],
        best_match["output_usd_per_1m"],
        hit_rate,
        model_hit_factor,
        effective_r_mult,
        inc_cot,
    )
    monthly_rmb = round(bill_rmb["total_cost"], 2)
    monthly_usd = round(bill_usd["total_cost"], 2)

    raw_peak = _get_param(inp, "peak_5h_calls", None)
    peak = max(0, int(raw_peak)) if raw_peak is not None else None
    raw_seats = _get_param(inp, "team_size", 1)
    seats = max(1, min(50, int(round(float(raw_seats or 1)))))
    coding_eval = _evaluate_coding_plan_verdict(
        int(round(reqs)),
        monthly_rmb,
        usage_mode,
        peak,
        model=best_match,
        offers=catalog.get("coding_plans") if isinstance(catalog.get("coding_plans"), list) else None,
        team_size=seats,
    )

    alts = []
    for cand in models:
        if cand["id"] == best_match["id"] or cand.get("is_free"):
            continue
        c_hit = float(
            cand.get("cache_hit_factor")
            if cand.get("cache_hit_factor") is not None
            else (0.2 if cand.get("region") == "cn_direct" else 0.5)
        )
        c_rmb = round(
            _calc_token_bill(
                monthly_in_m,
                monthly_out_m,
                cand["input_rmb_per_1m"],
                cand["output_rmb_per_1m"],
                hit_rate,
                c_hit,
                r_mult if "reasoning" in (cand.get("tags") or []) else 1.0,
                inc_cot,
            )["total_cost"],
            2,
        )
        if monthly_rmb > 0 and c_rmb < monthly_rmb * 0.90:
            alts.append(_compact_view(cand, {"monthly_rmb": c_rmb, "savings_rmb": round(monthly_rmb - c_rmb, 2)}))
    alts.sort(key=lambda x: x["monthly_rmb"])

    params_qs = urllib.parse.urlencode(
        {
            "calls": int(round(reqs)),
            "in": int(round(in_tok)),
            "out": int(round(out_tok)),
            "cache": hit_rate,
            "inc_cot": int(inc_cot),
            **({"peak5h": peak} if peak is not None else {}),
            **({"seats": seats} if seats > 1 else {}),
            "reason": r_mult if r_mult > 1 else 0,
            "mode": coding_eval["usage_mode"],
            "baseline": best_match["id"],
            "qv": QUOTE_VERIFIED_DATE,
        }
    )
    deep_url = f"{WEB_BASE_URL}coding-plan-2026/?{params_qs}"

    summary = (
        f"模型【{best_match['name']}】按日均 {int(reqs):,} 次模型调用测算："
        f"按量月账单约 ¥{monthly_rmb:.2f} (${monthly_usd:.2f})。"
        f"{coding_eval['headline_zh']} {coding_eval['window_note_zh']}"
    )
    out_data: dict[str, Any] = {
        "matched_model": _compact_view(best_match),
        "monthly_input_millions": round(monthly_in_m, 4),
        "monthly_output_millions": round(monthly_out_m, 4),
        "budget_estimate": {
            "daily_rmb": round(monthly_rmb / 30.0, 4),
            "monthly_rmb": monthly_rmb,
            "yearly_rmb": round((monthly_rmb / 30.0) * 365.0, 2),
            "monthly_usd": monthly_usd,
        },
        "coding_plan_evaluation": coding_eval,
        "cheaper_alternatives": alts[:4],
    }
    if parsed_usage_summary is not None:
        out_data["parsed_usage_summary"] = parsed_usage_summary
    if bill_audit is not None:
        out_data["bill_audit"] = bill_audit
    return (
        summary,
        out_data,
        deep_url,
    )


def _run_free_and_cheap(catalog: dict[str, Any], inp: Any) -> tuple[str, dict[str, Any], str]:
    models = catalog.get("models", [])
    region = _normalize_region(str(_get_param(inp, "region_preference", _get_param(inp, "region", "any"))))
    free_list = []
    cheap_list = []
    for m in models:
        if region != "any" and m.get("region") != region:
            continue
        if m.get("is_free") or "free" in m.get("tags", []):
            free_list.append(_compact_view(m))
        elif m.get("blended_usd_per_1m", 999.0) <= 0.50:
            cheap_list.append(_compact_view(m, {"blended_rmb_per_1m": m.get("blended_rmb_per_1m")}))

    summary = f"共找到 {len(free_list)} 款 ¥0/$0 免费 API 模型，以及 {len(cheap_list)} 款百万 Token 低于 ¥3.60 的低价主力模型。"
    return (
        summary,
        {
            "free_models": free_list[:12],
            "ultra_cheap_models": cheap_list[:12],
        },
        f"{WEB_BASE_URL}?filter=free&qv={QUOTE_VERIFIED_DATE}",
    )


def run_router(params: dict[str, Any] | Any, logger: Any = None) -> dict[str, Any]:
    raw_action = str(_get_param(params, "action", "recommend_cheapest_model")).strip().lower()
    catalog = _fetch_live_catalog(logger=logger)

    if raw_action in ("calculate_api_budget", "budget", "estimate_budget"):
        action = "calculate_api_budget"
        summary_cn, data, deep_url = _run_budget(catalog, params)
    elif raw_action in ("list_free_and_ultra_cheap_models", "free", "cheap"):
        action = "list_free_and_ultra_cheap_models"
        summary_cn, data, deep_url = _run_free_and_cheap(catalog, params)
    else:
        action = "recommend_cheapest_model"
        summary_cn, data, deep_url = _run_recommend(catalog, params)

    out: dict[str, Any] = {
        "status": "ok",
        "action": action,
        "updated_at": str(catalog.get("updated_at", "")),
        "quote_verified_date": str(catalog.get("quote_verified_date", QUOTE_VERIFIED_DATE)),
        "data_source": str(catalog.get("source", "")),
        "web_calculator_url": deep_url,
        "summary_cn": summary_cn,
        "data": data,
    }
    # Expose top-level convenience keys alongside `data` for seamless caller & test access
    for k, v in data.items():
        if k not in out:
            out[k] = v
    return out


def handler(args: Args) -> Output:
    """扣子 (Coze.cn) Python 云端工具标准入口函数。"""
    inp = getattr(args, "input", args)
    logger = getattr(args, "logger", None)
    if logger and hasattr(logger, "info"):
        logger.info("[AI-Cost-Radar v0.0.2] Executing Coze router")
    return run_router(inp, logger=logger)


if __name__ == "__main__":
    print(
        json.dumps(
            run_router(
                {
                    "action": "calculate_api_budget",
                    "model_query": "qwen3.5-plus",
                    "daily_requests": 5000,
                    "avg_input_tokens": 2000,
                    "avg_output_tokens": 800,
                }
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
