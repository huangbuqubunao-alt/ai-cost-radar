#!/usr/bin/env python3
"""
Shared Verifiable Pricing, Quota, Endpoint & Self-Host Calculation Core (v3.0).

Single source of truth imported by:
  - engine_a_mcp_actor/fetch_and_enrich.py
  - engine_a_mcp_actor/mcp_server.py
  - engine_b_affiliate_web/build_site.py
and mirrored verbatim in standalone `coze_cloud_tool.py`.

Zero third-party dependencies (Python 3.12+ stdlib only).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

QUOTE_VERIFIED_DATE: str = "2026-11-13"
DEFAULT_FX_USD_TO_RMB: float = 7.20
PRO_MONTHLY_CAP: int = 90_000
PRO_WEEKLY_CAP: int = 45_000
PRO_5H_CAP: int = 6_000
LITE_MONTHLY_CAP: int = 18_000
LITE_WEEKLY_CAP: int = 9_000
LITE_5H_CAP: int = 1_200


OFFERS_CATALOG_2026: list[dict[str, Any]] = [
    {
        "id": "aliyun-coding-plan",
        "offer_type": "subscription",
        "name": "阿里云百炼 Coding Plan 编程套餐",
        "vendor": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "official_source_url": "https://help.aliyun.com/zh/model-studio/coding-plan",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": True,
        "commission_status": "pending_console_verification",
        "commission_note_zh": "需在阿里云云大使后台按当月推广商品表核验百炼 Coding Plan 是否返佣；保留官方购买入口",
        "monthly_rmb": 39.90,
        "pro_monthly_rmb": 200.0,
        "renewal_rmb": 200.0,
        "models_covered": ["qwen3.5-plus", "qwen3-coder-next", "kimi-k2.5", "glm-5", "MiniMax-M2.5"],
        "speed_highlight": "Pro 月上限 90,000 次调用 · Lite 已停新购",
        "best_for": "仅限 Claude Code / Cursor / Cline / 通义灵码交互式编程；严禁用于自动化后端 API 服务",
        "featured_partner": True,
        "cta_zh": "查看阿里云百炼 Coding Plan 官方详情",
        "cta_en": "View Aliyun Bailian Coding Plan",
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
                "status_note_zh": "官方已停止 Lite 新购，仅存量续费",
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
                "status_note_zh": "新客首月特惠 ¥39.90（每日限量），次月起续费原价 ¥200/月",
            },
        ],
        "endpoints": {
            "claude_code": {
                "protocol": "anthropic",
                "base_url": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
                "env_url_name": "ANTHROPIC_BASE_URL",
                "env_key_name": "ANTHROPIC_AUTH_TOKEN",
                "env_model_name": "ANTHROPIC_MODEL",
                "key_prefix": "sk-sp-",
                "verified": True,
            },
            "openai_compat": {
                "protocol": "openai",
                "base_url": "https://coding.dashscope.aliyuncs.com/v1",
                "env_url_name": "OPENAI_BASE_URL",
                "env_key_name": "OPENAI_API_KEY",
                "env_model_name": "OPENAI_MODEL",
                "key_prefix": "sk-sp-",
                "verified": True,
            },
            "payg_openai": {
                "protocol": "openai",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "env_url_name": "OPENAI_BASE_URL",
                "env_key_name": "OPENAI_API_KEY",
                "env_model_name": "OPENAI_MODEL",
                "key_prefix": "sk-",
                "verified": True,
            },
        },
    },
    {
        "id": "tencent-coding-plan",
        "offer_type": "subscription",
        "name": "腾讯云 LKEAP Coding Plan 编程套餐",
        "vendor": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "official_source_url": "https://cloud.tencent.com/document/product/1823/130092",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": True,
        "commission_status": "pending_console_verification",
        "commission_note_zh": "需在腾讯云 CPS 后台确认 LKEAP Coding Plan 是否纳入当月返佣商品池；轻量云主机常规在返佣范围",
        "monthly_rmb": 40.0,
        "pro_monthly_rmb": 200.0,
        "renewal_rmb": 200.0,
        "models_covered": ["tc-code-latest", "hunyuan-t1", "kimi-k2.5", "glm-5", "MiniMax-M2.5"],
        "speed_highlight": "Lite 月限 18,000 次 (¥40) · Pro 月限 90,000 次 (¥200)",
        "best_for": "仅限 Claude Code / Cursor / Cline / CodeBuddy 交互式编程；严禁自动化脚本或后端业务调用",
        "featured_partner": True,
        "cta_zh": "查看腾讯云 Coding Plan 官方详情",
        "cta_en": "View Tencent Coding Plan",
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
                "status_note_zh": "目录原价 ¥40/月（以控制台当期活动为准），5h 限 1,200 次 / 月限 18,000 次",
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
                "status_note_zh": "目录原价 ¥200/月，5h 限 6,000 次 / 周限 45,000 次 / 月限 90,000 次",
            },
        ],
        "endpoints": {
            "claude_code": {
                "protocol": "anthropic",
                "base_url": "https://api.lkeap.cloud.tencent.com/coding/anthropic",
                "env_url_name": "ANTHROPIC_BASE_URL",
                "env_key_name": "ANTHROPIC_AUTH_TOKEN",
                "env_model_name": "ANTHROPIC_MODEL",
                "key_prefix": "sk-sp-",
                "verified": True,
            },
            "openai_compat": {
                "protocol": "openai",
                "base_url": "https://api.lkeap.cloud.tencent.com/coding/v3",
                "env_url_name": "OPENAI_BASE_URL",
                "env_key_name": "OPENAI_API_KEY",
                "env_model_name": "OPENAI_MODEL",
                "key_prefix": "sk-sp-",
                "verified": True,
            },
            "payg_openai": {
                "protocol": "openai",
                "base_url": "https://api.lkeap.cloud.tencent.com/v1",
                "env_url_name": "OPENAI_BASE_URL",
                "env_key_name": "OPENAI_API_KEY",
                "env_model_name": "OPENAI_MODEL",
                "key_prefix": "sk-",
                "verified": True,
            },
        },
    },
    {
        "id": "volcengine-coding-plan",
        "offer_type": "subscription",
        "name": "火山方舟 Coding Plan 编程套餐",
        "vendor": "字节跳动 · 火山引擎",
        "provider_config_key": "volcengine_ark_url",
        "official_source_url": "https://www.volcengine.com/docs/82379",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": True,
        "commission_status": "no_affiliate_program",
        "commission_note_zh": "无返佣参数，纯客观横评参考直达火山方舟官方控制台",
        "monthly_rmb": 40.0,
        "pro_monthly_rmb": 200.0,
        "renewal_rmb": 200.0,
        "models_covered": ["doubao-seed-2.0-pro", "deepseek-v3", "kimi-k2.5", "glm-5"],
        "speed_highlight": "Lite ¥40/月 (1.8万次) · Pro ¥200/月 (9万次)",
        "best_for": "仅限 Trae / Claude Code / Cursor / Cline 交互式编程；严禁挪作通用后端 API 转发",
        "featured_partner": False,
        "cta_zh": "查看火山方舟官方套餐说明",
        "cta_en": "View Volcengine Coding Plan",
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
                "status_note_zh": "原价 ¥40/月（新客活动以官网为准），月上限约 18,000 次请求",
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
                "status_note_zh": "原价 ¥200/月，5h 限 6,000 次 / 周限 45,000 次 / 月限 90,000 次请求",
            },
        ],
        "endpoints": {
            "claude_code": {
                "protocol": "anthropic",
                "base_url": "https://ark.cn-beijing.volces.com/api/coding",
                "env_url_name": "ANTHROPIC_BASE_URL",
                "env_key_name": "ANTHROPIC_AUTH_TOKEN",
                "env_model_name": "ANTHROPIC_MODEL",
                "key_prefix": "ark-",
                "verified": True,
            },
            "payg_openai": {
                "protocol": "openai",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "env_url_name": "OPENAI_BASE_URL",
                "env_key_name": "OPENAI_API_KEY",
                "env_model_name": "OPENAI_MODEL",
                "key_prefix": "ark-",
                "verified": True,
            },
        },
    },
    {
        "id": "aliyun-ecs-agent-host",
        "offer_type": "cloud_host",
        "name": "阿里云轻量 / ECS 服务器（自建 LiteLLM 缓存网关 / Dify）",
        "vendor": "阿里云云小站 (ECS/轻量云)",
        "provider_config_key": "aliyun_ambassador_url",
        "official_source_url": "https://www.aliyun.com/minisite/goods",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": False,
        "commission_status": "verified_cps_candidate",
        "commission_note_zh": "云主机新购属云大使常规现金返利品类（具体返利比例与活动机型以云大使当月规则表为准）",
        "monthly_rmb": 68.0,
        "pro_monthly_rmb": 199.0,
        "renewal_rmb": 68.0,
        "models_covered": ["LiteLLM 语义缓存网关", "Dify 工作流后端", "24h 自动化 API 服务"],
        "speed_highlight": "非包月 Token 套餐 · 需叠加未命中缓存的 API 费",
        "best_for": "适合自动化后端与高频重复问答：总成本 = 主机月租 + 未命中缓存 API 费 + 存储流量",
        "featured_partner": True,
        "cta_zh": "查看阿里云 ECS / 轻量云活动机型",
        "cta_en": "View Aliyun ECS / Cloud Server Deals",
        "tiers": [],
        "endpoints": {},
    },
    {
        "id": "siliconflow-coding-pack",
        "offer_type": "payg_pool",
        "name": "硅基流动多模型按量 API 池（非包月订阅）",
        "vendor": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "official_source_url": "https://docs.siliconflow.cn/",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": False,
        "commission_status": "invite_credit_only",
        "commission_note_zh": "邀请码注册奖励为平台算力余额抵扣券（非可提现人民币现金）",
        "monthly_rmb": 0.0,
        "pro_monthly_rmb": 0.0,
        "renewal_rmb": 0.0,
        "models_covered": ["Kimi-K2.5", "GLM-5", "MiniMax-M2.5", "DeepSeek-V3/R1", "Qwen2.5-7B (免费)"],
        "speed_highlight": "¥0 月租按量计费 · 允许自动化后端与脚本调用",
        "best_for": "用量波动大、不想受 5 小时窗口或编程客户端协议限制的场景",
        "featured_partner": False,
        "cta_zh": "前往硅基流动按量 API 控制台",
        "cta_en": "Open SiliconFlow Pay-As-You-Go Console",
        "tiers": [],
        "endpoints": {
            "payg_openai": {
                "protocol": "openai",
                "base_url": "https://api.siliconflow.cn/v1",
                "env_url_name": "OPENAI_BASE_URL",
                "env_key_name": "OPENAI_API_KEY",
                "env_model_name": "OPENAI_MODEL",
                "key_prefix": "sk-",
                "verified": True,
            }
        },
    },
    {
        "id": "openrouter-global-coding",
        "offer_type": "gateway_example",
        "name": "OpenRouter 海外多模型按量路由（非包月订阅）",
        "vendor": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "official_source_url": "https://openrouter.ai/docs",
        "verified_date": QUOTE_VERIFIED_DATE,
        "interactive_only": False,
        "commission_status": "no_affiliate_program",
        "commission_note_zh": "无返佣计划，提供海外 Claude / GPT / Gemini 按量统一网关对比",
        "monthly_rmb": 0.0,
        "pro_monthly_rmb": 0.0,
        "renewal_rmb": 0.0,
        "models_covered": ["Claude Sonnet 4", "GPT-4.1", "Gemini 2.5 Pro", "DeepSeek R1 (:free)"],
        "speed_highlight": "$0 月租按实际 Token 计费 · 支持生产后端与自动 Fallback",
        "best_for": "出海产品或需要混用海外闭源旗舰模型的团队",
        "featured_partner": False,
        "cta_zh": "前往 OpenRouter 官网",
        "cta_en": "Visit OpenRouter",
        "tiers": [],
        "endpoints": {
            "payg_openai": {
                "protocol": "openai",
                "base_url": "https://openrouter.ai/api/v1",
                "env_url_name": "OPENAI_BASE_URL",
                "env_key_name": "OPENAI_API_KEY",
                "env_model_name": "OPENAI_MODEL",
                "key_prefix": "sk-or-",
                "verified": True,
            }
        },
    },
]


def get_offers_catalog() -> list[dict[str, Any]]:
    return deepcopy(OFFERS_CATALOG_2026)


def resolve_model_query(models: list[dict[str, Any]], raw_query: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """
    Resolve a model ID, vendor-prefixed alias (e.g. `aliyun/qwen3.5-plus`, `tencent/hunyuan-t1`),
    exact `api_model_id` (e.g. `hunyuan-t1-latest`, `doubao-seed-2-0-pro-250415`), or fuzzy query.
    Returns (matched_model, match_note_or_None).
    """
    if not models:
        return None, "Model catalog is empty."

    raw = str(raw_query or "deepseek-v3").strip()
    if not raw:
        raw = "deepseek-v3"

    # 1. Exact ID match
    for m in models:
        if m.get("id") == raw:
            return m, None

    # 2. Normalized vendor prefix & case-insensitive ID match
    norm_id = raw.lower()
    if norm_id.startswith("aliyun/"):
        norm_id = "aliyun-bailian/" + norm_id[len("aliyun/") :]
    elif norm_id.startswith("tencent/"):
        norm_id = "tencent-cloud/" + norm_id[len("tencent/") :]

    for m in models:
        if str(m.get("id") or "").lower() == norm_id:
            return m, None

    # 3. Exact `api_model_id` or `/<slug>` suffix match (prefer `cn_direct`, paid, higher `value_score`)
    q_lower = raw.lower()
    suffix_matches = [
        m
        for m in models
        if str(m.get("api_model_id") or "").lower() == q_lower
        or str(m.get("id") or "").lower().endswith("/" + q_lower)
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
        return suffix_matches[0], None

    # 4. Fuzzy token & substring ranking
    wants_free = "free" in q_lower
    best_match: dict[str, Any] | None = None
    best_rank = -1.0
    q_tokens = [tok for tok in norm_id.replace("/", " ").replace("-", " ").split() if tok]

    for m in models:
        mid = str(m.get("id") or "").lower()
        mname = str(m.get("name") or "").lower()
        api_mid = str(m.get("api_model_id") or "").lower()
        hay = f"{mid} {api_mid} {mname} {str(m.get('provider') or '').lower()}"

        score = 0.0
        if norm_id in mid or q_lower in api_mid:
            score = 700.0
        elif q_lower in mname:
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
            score += float(m.get("value_score") or 0.0) * 0.1
            if score > best_rank:
                best_rank = score
                best_match = m

    if best_match is not None:
        return best_match, None

    fallback = models[0]
    return fallback, f"No direct match for '{raw_query}'; defaulted to top-value model '{fallback['id']}'."


def plan_covers_model(plan_or_id: str | dict[str, Any], model_id_or_obj: str | dict[str, Any] | None) -> bool:
    """
    Determine whether a Coding Plan subscription natively includes the selected model's family
    (same-family direct coverage vs cross-model domestic replacement).
    """
    if model_id_or_obj is None:
        return False
    if isinstance(plan_or_id, str):
        plan = next((o for o in OFFERS_CATALOG_2026 if o["id"] == plan_or_id), None)
    else:
        plan = plan_or_id
    if not plan or plan.get("offer_type") != "subscription":
        return False

    if isinstance(model_id_or_obj, dict):
        model_text = f"{model_id_or_obj.get('id', '')} {model_id_or_obj.get('api_model_id', '')} {model_id_or_obj.get('name', '')}".lower()
    else:
        model_text = str(model_id_or_obj).strip().lower()
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


def calculate_token_bill(
    *,
    monthly_input_m: float,
    monthly_output_m: float,
    input_price_per_1m: float,
    output_price_per_1m: float,
    cache_hit_rate: float = 0.0,
    cache_hit_factor: float = 0.2,
    reasoning_multiplier: float = 1.0,
    output_includes_reasoning: bool = False,
) -> dict[str, float]:
    """
    Exact verifiable token billing formula shared across Web, MCP, Coze & SSR:
      - Uncached input portion `(1 - cache_hit_rate)` pays `1.0 * input_price_per_1m`
      - Cached input portion `cache_hit_rate` pays `cache_hit_factor * input_price_per_1m`
      - Output tokens multiply by `reasoning_multiplier` ONLY when `output_includes_reasoning` is False.
    """
    in_m = max(0.0, float(monthly_input_m or 0.0))
    out_m = max(0.0, float(monthly_output_m or 0.0))
    in_price = max(0.0, float(input_price_per_1m or 0.0))
    out_price = max(0.0, float(output_price_per_1m or 0.0))

    hit_rate = min(1.0, max(0.0, float(cache_hit_rate or 0.0)))
    hit_factor = min(1.0, max(0.0, float(cache_hit_factor if cache_hit_factor is not None else 1.0)))
    effective_in_factor = (1.0 - hit_rate) + (hit_rate * hit_factor)

    raw_mult = max(1.0, float(reasoning_multiplier or 1.0))
    effective_out_factor = 1.0 if output_includes_reasoning else raw_mult

    input_cost = in_m * effective_in_factor * in_price
    output_cost = out_m * effective_out_factor * out_price
    total_cost = input_cost + output_cost

    return {
        "monthly_input_m": round(in_m, 6),
        "monthly_output_m": round(out_m, 6),
        "effective_input_factor": round(effective_in_factor, 6),
        "effective_output_factor": round(effective_out_factor, 6),
        "input_cost": round(input_cost, 4),
        "output_cost": round(output_cost, 4),
        "total_cost": round(total_cost, 4),
    }


def _fmt_wan_calls(calls: int) -> str:
    if calls % 10_000 == 0:
        return f"{calls // 10_000} 万次"
    return f"{calls / 10_000:.1f} 万次"


def evaluate_coding_plans(
    *,
    daily_calls: float,
    payg_monthly_rmb: float,
    usage_mode: str = "interactive_ide",
    peak_5h_calls: int | None = None,
    model_id: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate 2026 Coding Plan subscriptions against same-model Pay-As-You-Go cost and hard call caps.
    """
    d_calls = max(0, int(round(float(daily_calls or 0))))
    monthly_calls = d_calls * 30
    payg_rmb = round(max(0.0, float(payg_monthly_rmb or 0.0)), 2)
    norm_mode = "automated_backend" if str(usage_mode or "").strip().lower() in (
        "automated_backend",
        "backend",
        "api_service",
        "batch",
        "non_interactive",
    ) else "interactive_ide"

    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for offer in OFFERS_CATALOG_2026:
        if offer["offer_type"] != "subscription":
            continue
        if norm_mode == "automated_backend" and offer.get("interactive_only"):
            excluded.append(
                {
                    "plan_id": offer["id"],
                    "name": offer["name"],
                    "reason_zh": "官方条款仅限交互式 AI 编程工具（Claude Code / Cursor / Cline 等），禁止用于非交互式后端、批处理或 API 服务。",
                    "official_source_url": offer["official_source_url"],
                }
            )
            continue

        purchasable_tiers = [t for t in offer.get("tiers", []) if t.get("purchasable")]
        chosen_tier: dict[str, Any] | None = None
        for tier in purchasable_tiers:
            if monthly_calls <= int(tier["quota_monthly"]) and (d_calls * 7) <= int(tier["quota_weekly"]):
                if peak_5h_calls is None or peak_5h_calls <= int(tier["quota_5h"]):
                    chosen_tier = tier
                    break

        exceeds_pro_by = max(0, monthly_calls - PRO_MONTHLY_CAP)
        pro_tier = next((t for t in purchasable_tiers if t["tier_id"] == "pro"), purchasable_tiers[-1] if purchasable_tiers else None)
        ref_tier = chosen_tier or pro_tier
        if ref_tier is None:
            continue

        covers_model = plan_covers_model(offer, model_id) if model_id is not None else True
        first_rmb = ref_tier.get("first_month_rmb")
        renewal_rmb = float(ref_tier["renewal_rmb"])
        effective_first_rmb = float(first_rmb) if first_rmb is not None else renewal_rmb

        if chosen_tier is None and monthly_calls <= ref_tier["quota_monthly"]:
            status = "exceeds_5h_cap"
            verdict_zh = f"5 小时峰值 {peak_5h_calls:,} 次，超过 {ref_tier['name']} 的 {ref_tier['quota_5h']:,} 次窗口上限。"
            first_month_saving = None
            renewal_saving = None
        elif chosen_tier is None:
            status = "exceeds_monthly_cap"
            verdict_zh = (
                f"按 30 天预计 {_fmt_wan_calls(monthly_calls)}（{monthly_calls:,} 次），"
                f"超出 Pro 月额度 {_fmt_wan_calls(exceeds_pro_by)}（上限 {PRO_MONTHLY_CAP:,} 次/月）；"
                "单靠个人包月套餐不够用，超出部分需走按量 API 或拆分多账号/企业方案。"
            )
            first_month_saving = None
            renewal_saving = None
        else:
            first_month_saving = round(payg_rmb - effective_first_rmb, 2)
            renewal_saving = round(payg_rmb - renewal_rmb, 2)
            cov_prefix = "套餐含同系模型，" if covers_model else "跨模型国产平替（套餐不含所选原模型），"
            if renewal_saving > 0:
                status = "recommended_even_on_renewal"
                verdict_zh = (
                    f"{cov_prefix}匹配 {chosen_tier['name']}（月上限 {chosen_tier['quota_monthly']:,} 次）："
                    f"同基准按量预计 ¥{payg_rmb:.2f}/月，"
                    + (f"首月 ¥{effective_first_rmb:.2f} 省 ¥{first_month_saving:.2f}，" if first_rmb is not None else "")
                    + f"续费 ¥{renewal_rmb:.0f}/月 仍净省 ¥{renewal_saving:.2f}。"
                )
            elif first_rmb is not None and first_month_saving > 0:
                status = "first_month_only"
                verdict_zh = (
                    f"{cov_prefix}仅首月特惠划算：按量预计 ¥{payg_rmb:.2f}/月，"
                    f"首月 ¥{effective_first_rmb:.2f} 可省 ¥{first_month_saving:.2f}，"
                    f"但次月续费恢复 ¥{renewal_rmb:.0f}/月 后将比按量贵 ¥{abs(renewal_saving):.2f}。"
                )
            else:
                status = "payg_cheaper"
                verdict_zh = (
                    f"建议直接按量付费：按量仅需 ¥{payg_rmb:.2f}/月，"
                    f"低于 {chosen_tier['name']} 价格（¥{effective_first_rmb:.2f}～¥{renewal_rmb:.0f}/月）。"
                )

        eligible.append(
            {
                "plan_id": offer["id"],
                "name": offer["name"],
                "vendor": offer["vendor"],
                "featured_partner": bool(offer.get("featured_partner")),
                "covers_selected_model": covers_model,
                "official_source_url": offer["official_source_url"],
                "verified_date": offer["verified_date"],
                "status": status,
                "matched_tier": chosen_tier["tier_id"] if chosen_tier else "exceeds_pro",
                "matched_tier_name": chosen_tier["name"] if chosen_tier else verdict_zh,
                "first_month_rmb": effective_first_rmb,
                "has_first_month_promo": first_rmb is not None,
                "renewal_rmb": renewal_rmb,
                "quota_5h": ref_tier["quota_5h"],
                "quota_weekly": ref_tier["quota_weekly"],
                "quota_monthly": ref_tier["quota_monthly"],
                "first_month_savings_rmb": first_month_saving,
                "renewal_savings_rmb": renewal_saving,
                "verdict_zh": verdict_zh,
            }
        )

    same_family_candidates = [
        item for item in eligible
        if item["covers_selected_model"] and item["status"] == "recommended_even_on_renewal"
    ]
    same_family_candidates.sort(
        key=lambda x: (float(x["renewal_savings_rmb"] or 0.0), 1 if x.get("featured_partner") else 0),
        reverse=True,
    )
    recommended_same_family_plan_id = same_family_candidates[0]["plan_id"] if same_family_candidates else None

    if norm_mode == "automated_backend":
        headline_zh = (
            "当前选择「非交互式后端 / 批处理 API」场景：已自动排除阿里云百炼、腾讯云与火山方舟个人 Coding Plan"
            "（官方条款仅限交互式编程工具），请使用下方按量付费 API 或自建缓存网关。"
        )
        window_note_zh = "非交互式后端不适用个人套餐的 5 小时滚动窗口。"
    elif monthly_calls > PRO_MONTHLY_CAP:
        over = monthly_calls - PRO_MONTHLY_CAP
        headline_zh = (
            f"按 30 天预计 {_fmt_wan_calls(monthly_calls)}（{monthly_calls:,} 次模型调用），"
            f"超出 Pro 月额度 {_fmt_wan_calls(over)}（百炼/腾讯/火山 Pro 月上限均为 {PRO_MONTHLY_CAP:,} 次）——"
            "切勿误以为 ¥200 包月可无限封顶！"
        )
        window_note_zh = (
            f"除月上限 {PRO_MONTHLY_CAP:,} 次外，Pro 每 5 小时限 {PRO_5H_CAP:,} 次、每周限 {PRO_WEEKLY_CAP:,} 次。"
        )
    else:
        if peak_5h_calls is None:
            window_note_zh = (
                f"月额度足够，5 小时窗口待确认（Pro 每 5 小时上限 {PRO_5H_CAP:,} 次 / 腾讯及火山 Lite 每 5 小时上限 {LITE_5H_CAP:,} 次；"
                "注意单位为模型调用次数，单次用户提问在 Claude Code/Cline 中可能触发 5～30 次调用）。"
            )
        elif peak_5h_calls > PRO_5H_CAP:
            window_note_zh = f"5 小时峰值（{peak_5h_calls:,} 次）已超出 Pro 窗口上限（{PRO_5H_CAP:,} 次/5h），高峰期将触发限流。"
        else:
            window_note_zh = f"月额度与 5 小时峰值窗口（{peak_5h_calls:,} 次）均在套餐上限内。"

        if monthly_calls > LITE_MONTHLY_CAP:
            over_lite = monthly_calls - LITE_MONTHLY_CAP
            headline_zh = (
                f"按 30 天预计 {monthly_calls:,} 次模型调用：已超出腾讯/火山 Lite 月额度 {over_lite:,} 次（Lite 上限 {LITE_MONTHLY_CAP:,} 次/月），"
                f"需对标 Pro 档（上限 {PRO_MONTHLY_CAP:,} 次/月，续费原价 ¥200/月）评估盈亏。"
            )
        else:
            headline_zh = (
                f"按 30 天预计 {monthly_calls:,} 次模型调用：在腾讯/火山 Lite（18,000 次/月，¥40/月）与各家 Pro（90,000 次/月）月度总额度内。"
            )

    return {
        "usage_mode": norm_mode,
        "daily_calls": d_calls,
        "monthly_calls_30d": monthly_calls,
        "payg_baseline_rmb": payg_rmb,
        "unit_warning_zh": "额度单位为「模型 API 调用次数」而非「用户提问次数」；一次 Agent 提问往往触发 5～30 次模型调用。",
        "headline_zh": headline_zh,
        "window_note_zh": window_note_zh,
        "eligible_subscriptions": eligible,
        "excluded_subscriptions": excluded,
        "recommended_same_family_plan_id": recommended_same_family_plan_id,
        "quote_verified_date": QUOTE_VERIFIED_DATE,
    }


def get_client_endpoint_config(
    *,
    vendor_or_plan: str,
    client_type: str = "claude_code",
    billing_mode: str = "payg",
    model_id: str = "qwen3.5-plus",
    fallback_base_url: str | None = None,
) -> dict[str, Any]:
    """
    Return protocol-accurate endpoint & environment variables for (vendor, client_type, billing_mode).
    Prevents the critical bug where Coding Plan subscribers copy a Pay-As-You-Go endpoint and incur extra bills!
    """
    vp = str(vendor_or_plan or "").strip().lower()
    client = str(client_type or "claude_code").strip().lower()
    mode = "coding_plan" if str(billing_mode or "").strip().lower() in ("coding_plan", "subscription", "plan") else "payg"

    plan_key: str | None = None
    if "aliyun" in vp or "bailian" in vp or "qwen" in vp:
        plan_key = "aliyun-coding-plan"
    elif "tencent" in vp or "lkeap" in vp or "hunyuan" in vp or "qcloud" in vp:
        plan_key = "tencent-coding-plan"
    elif "volcengine" in vp or "doubao" in vp or "ark" in vp:
        plan_key = "volcengine-coding-plan"
    elif "siliconflow" in vp:
        plan_key = "siliconflow-coding-pack"
    elif "openrouter" in vp:
        plan_key = "openrouter-global-coding"

    offer_map = {o["id"]: o for o in OFFERS_CATALOG_2026}
    offer = offer_map.get(plan_key or "")

    is_anthropic_client = client in ("claude_code", "anthropic")
    if mode == "coding_plan" and offer and offer["offer_type"] == "subscription":
        if plan_key == "tencent-coding-plan":
            model_id = offer["models_covered"][0]
        endpoints = offer.get("endpoints") or {}
        ep_key = "claude_code" if is_anthropic_client else "openai_compat"
        ep = endpoints.get(ep_key)
        if not ep:
            return {
                "verified": False,
                "protocol": "official_doc_required",
                "base_url": "",
                "official_doc_url": offer["official_source_url"],
                "warning_zh": (
                    f"{offer['name']} 在当前客户端（{client_type}）下暂无已核验的专属兼容端点，"
                    "请勿混用普通按量端点，直接按官方教程配置："
                ),
                "gui_snippet": f"请查阅官方接入文档：{offer['official_source_url']}",
                "env_snippet": f"# 请参阅官方文档获取专属端点：\n# {offer['official_source_url']}",
            }

        base_url = ep["base_url"]
        key_placeholder = f"{ep['key_prefix']}your-coding-plan-key"
        if ep["protocol"] == "anthropic":
            gui_snippet = (
                f"Protocol: Anthropic Messages API (Coding Plan 专属)\n"
                f"Base URL: {base_url}\n"
                f"API Key 格式: {key_placeholder} (切勿填入普通按量 Key)\n"
                f"Model ID: {model_id}"
            )
            env_snippet = (
                f'export {ep["env_url_name"]}="{base_url}"\n'
                f'export {ep["env_key_name"]}="{key_placeholder}"\n'
                f'export {ep["env_model_name"]}="{model_id}"'
            )
        else:
            gui_snippet = (
                f"Protocol: OpenAI Compatible (Coding Plan 专属端点)\n"
                f"Base URL: {base_url}\n"
                f"API Key 格式: {key_placeholder}\n"
                f"Model ID: {model_id}"
            )
            env_snippet = (
                f'export {ep["env_url_name"]}="{base_url}"\n'
                f'export {ep["env_key_name"]}="{key_placeholder}"\n'
                f'export {ep["env_model_name"]}="{model_id}"'
            )
        return {
            "verified": True,
            "billing_mode": "coding_plan",
            "protocol": ep["protocol"],
            "base_url": base_url,
            "key_prefix": ep["key_prefix"],
            "official_doc_url": offer["official_source_url"],
            "warning_zh": "⚠️ 已切换为 Coding Plan 包月专属端点与专属 Key（如 sk-sp- 开头）；若误填通用按量端点将继续产生按量扣费！",
            "gui_snippet": gui_snippet,
            "env_snippet": env_snippet,
        }

    if mode == "coding_plan" or is_anthropic_client:
        doc = offer["official_source_url"] if offer else "https://openrouter.ai/docs"
        return {"verified": False, "billing_mode": mode, "protocol": "official_doc_required",
                "base_url": "", "official_doc_url": doc, "warning_zh": "当前组合缺少已核验的端点。",
                "gui_snippet": f"请按厂商教程核对配置：{doc}", "env_snippet": "# 请按厂商文档配置。"}

    # Pay-As-You-Go mode
    payg_defaults = {
        "aliyun-coding-plan": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "https://help.aliyun.com/zh/model-studio/"),
        "tencent-coding-plan": ("https://api.lkeap.cloud.tencent.com/v1", "https://cloud.tencent.com/document/product/1772"),
        "volcengine-coding-plan": ("https://ark.cn-beijing.volces.com/api/v3", "https://www.volcengine.com/docs/82379"),
        "siliconflow-coding-pack": ("https://api.siliconflow.cn/v1", "https://docs.siliconflow.cn/"),
        "openrouter-global-coding": ("https://openrouter.ai/api/v1", "https://openrouter.ai/docs"),
    }
    base_url, doc_url = payg_defaults.get(
        plan_key or "",
        (fallback_base_url or "https://openrouter.ai/api/v1", "https://openrouter.ai/docs"),
    )
    if fallback_base_url and not plan_key:
        base_url = fallback_base_url

    gui_snippet = (
        f"Protocol: OpenAI Compatible (按量付费标准端点)\n"
        f"Base URL: {base_url}\n"
        f"Model ID: {model_id}"
    )
    env_snippet = (
        f'export OPENAI_BASE_URL="{base_url}"\n'
        f'export OPENAI_API_KEY="sk-your-payg-api-key"\n'
        f'export OPENAI_MODEL="{model_id}"'
    )
    return {
        "verified": True,
        "billing_mode": "payg",
        "protocol": "openai",
        "base_url": base_url,
        "key_prefix": "sk-",
        "official_doc_url": doc_url,
        "warning_zh": "当前为「按量付费 API」通用端点；若您购买了 Coding Plan 包月套餐，请切到「Coding Plan 包月专属」以防产生按量账单。",
        "gui_snippet": gui_snippet,
        "env_snippet": env_snippet,
    }


def evaluate_self_host_vs_payg(
    *,
    current_payg_rmb: float,
    semantic_cache_hit_rate: float = 0.35,
    gateway_host_rmb: float = 68.0,
    storage_egress_rmb: float = 15.0,
    gpu_hourly_rmb: float = 11.5,
    gpu_monthly_hours: float = 240.0,
    gpu_spec_label: str = "单卡 24GB GPU (如 RTX 4090 / A10 级别，按日均 8h 弹性开机共 240h/月，吞吐假设 ~35 tok/s)",
) -> dict[str, Any]:
    """
    Transparently compare current Pay-As-You-Go API spend against:
      1. Cloud CPU server hosting Dify / LiteLLM semantic cache:
         Total = gateway_host_rmb + (1 - semantic_cache_hit_rate) * current_payg_rmb + storage_egress_rmb
      2. Dedicated / elastic GPU self-hosting open-weight models:
         Total = gpu_hourly_rmb * gpu_monthly_hours + storage_egress_rmb
    """
    payg = round(max(0.0, float(current_payg_rmb or 0.0)), 2)
    hit = min(0.85, max(0.0, float(semantic_cache_hit_rate or 0.0)))
    host = round(max(0.0, float(gateway_host_rmb or 0.0)), 2)
    egress = round(max(0.0, float(storage_egress_rmb or 0.0)), 2)

    uncached_api_rmb = round(payg * (1.0 - hit), 2)
    gateway_total_rmb = round(host + uncached_api_rmb + egress, 2)
    gateway_net_savings_rmb = round(payg - gateway_total_rmb, 2)

    gpu_compute_rmb = round(max(0.0, float(gpu_hourly_rmb)) * max(0.0, float(gpu_monthly_hours)), 2)
    gpu_total_rmb = round(gpu_compute_rmb + egress, 2)
    gpu_net_savings_rmb = round(payg - gpu_total_rmb, 2)

    gateway_saves = gateway_net_savings_rmb > 20.0
    gpu_saves = gpu_net_savings_rmb > 50.0

    if not gateway_saves and not gpu_saves:
        rec_zh = (
            f"建议继续按量付费 API：当前按量月账单约 ¥{payg:.2f}，"
            f"而「自建缓存网关总成本」约 ¥{gateway_total_rmb:.2f}/月（主机 ¥{host:.0f} + 未命中 API ¥{uncached_api_rmb:.2f} + 存储流量 ¥{egress:.0f}），"
            f"「弹性 GPU 自建」约 ¥{gpu_total_rmb:.2f}/月，自建总成本高于当前按量账单，无需买服务器。"
        )
    elif gateway_saves and not gpu_saves:
        rec_zh = (
            f"可考虑轻量云部署 LiteLLM/Dify 语义缓存（预计月省 ¥{gateway_net_savings_rmb:.2f}）："
            f"主机 ¥{host:.0f} + 未命中缓存 API ¥{uncached_api_rmb:.2f}（按 {int(hit*100)}% 拦截率假设）+ 存储流量 ¥{egress:.0f} = ¥{gateway_total_rmb:.2f}/月；"
            f"但尚不足以回本独立 GPU 租用（约 ¥{gpu_total_rmb:.2f}/月）。"
        )
    else:
        rec_zh = (
            f"高消耗已达弹性 GPU / 缓存网关评估线：当前按量 ¥{payg:.2f}/月；"
            f"缓存网关方案约 ¥{gateway_total_rmb:.2f}/月，弹性 GPU 自建（{gpu_spec_label}）约 ¥{gpu_total_rmb:.2f}/月（预计月省 ¥{gpu_net_savings_rmb:.2f}）。"
        )

    return {
        "current_payg_rmb": payg,
        "semantic_cache_hit_rate": hit,
        "gateway_breakdown": {
            "host_rmb": host,
            "uncached_api_rmb": uncached_api_rmb,
            "storage_egress_rmb": egress,
            "total_rmb": gateway_total_rmb,
            "net_savings_rmb": gateway_net_savings_rmb,
        },
        "gpu_breakdown": {
            "spec_assumption": gpu_spec_label,
            "hourly_rmb": gpu_hourly_rmb,
            "monthly_hours": gpu_monthly_hours,
            "compute_rmb": gpu_compute_rmb,
            "storage_egress_rmb": egress,
            "total_rmb": gpu_total_rmb,
            "net_savings_rmb": gpu_net_savings_rmb,
        },
        "gateway_saves_money": gateway_saves,
        "gpu_saves_money": gpu_saves,
        "recommendation_zh": rec_zh,
    }
