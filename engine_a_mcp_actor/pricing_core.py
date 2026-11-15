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
import math
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
        "official_source_url": "https://www.volcengine.com/docs/82379/1925114",
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
            "openai_compat": {
                "protocol": "openai",
                "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
                "env_url_name": "OPENAI_BASE_URL",
                "env_key_name": "OPENAI_API_KEY",
                "env_model_name": "OPENAI_MODEL",
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

    # 3.5 Strip release date suffixes (e.g. `-20250514`, `-2025-04-14`) & map official API aliases
    import re as _re

    stripped_q = _re.sub(r"-(?:20\d{2}-\d{2}-\d{2}|20\d{6}|\d{4})$", "", q_lower)
    slug_base = stripped_q.split("/")[-1]
    alias_candidates: list[str] = []
    if stripped_q != q_lower:
        alias_candidates.extend([stripped_q, slug_base])
    if slug_base in ("deepseek-reasoner", "r1"):
        alias_candidates.append("deepseek-r1")
    elif slug_base in ("deepseek-chat", "v3"):
        alias_candidates.append("deepseek-v3")
    elif slug_base in ("gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano", "o1-mini", "o3-mini", "o4-mini"):
        alias_candidates.extend(["openai/gpt-5.4-mini", "openai/gpt-5-mini"])
    elif slug_base.startswith(("gpt-4", "chatgpt-4o")) or slug_base in ("o1", "o3", "o3-pro"):
        alias_candidates.extend(["openai/gpt-5.4", "openai/gpt-5.5"])
    elif "claude" in slug_base and "sonnet" in slug_base:
        alias_candidates.extend(["anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5"])
    elif "claude" in slug_base and "opus" in slug_base:
        alias_candidates.extend(["anthropic/claude-opus-5.5", "anthropic/claude-opus-5"])
    elif "claude" in slug_base and "haiku" in slug_base:
        alias_candidates.append("anthropic/claude-haiku-5.5")

    for cand_alias in alias_candidates:
        ca_low = cand_alias.lower()
        ca_hits = [
            m
            for m in models
            if str(m.get("id") or "").lower() == ca_low
            or str(m.get("api_model_id") or "").lower() == ca_low
            or str(m.get("id") or "").lower().endswith("/" + ca_low)
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
            return ca_hits[0], None

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


def _compute_overflow_hybrid(
    *,
    monthly_calls: int,
    payg_rmb: float,
    pro_tier: dict[str, Any],
    peak_5h_calls: int | None,
    seats: int = 1,
) -> dict[str, Any] | None:
    """
    Compute exact "N Pro Base (up to N * 90k calls) + PayG Overflow" hybrid monthly bill
    when interactive usage exceeds the combined Pro monthly cap without exceeding the 5h window.
    """
    s = max(1, min(50, int(seats or 1)))
    quota_monthly = int(pro_tier.get("quota_monthly") or 0) * s
    quota_5h = int(pro_tier.get("quota_5h") or 0) * s
    if quota_monthly <= 0 or monthly_calls <= quota_monthly:
        return None
    if peak_5h_calls is not None and peak_5h_calls > quota_5h:
        return None

    covered_calls = quota_monthly
    overflow_calls = monthly_calls - covered_calls
    overflow_share = overflow_calls / float(monthly_calls)
    overflow_payg_rmb = round(payg_rmb * overflow_share, 2)

    raw_first = pro_tier.get("first_month_rmb")
    unit_renewal = float(pro_tier["renewal_rmb"])
    unit_first = float(raw_first) if raw_first is not None else unit_renewal
    renewal_plan_rmb = round(unit_renewal * s, 2)
    first_plan_rmb = round(unit_first * s, 2)

    first_total = round(first_plan_rmb + overflow_payg_rmb, 2)
    renewal_total = round(renewal_plan_rmb + overflow_payg_rmb, 2)
    first_saving = round(payg_rmb - first_total, 2)
    renewal_saving = round(payg_rmb - renewal_total, 2)

    return {
        "seats_count": s,
        "covered_calls": covered_calls,
        "overflow_calls": overflow_calls,
        "overflow_payg_rmb": overflow_payg_rmb,
        "first_month_plan_rmb": first_plan_rmb,
        "renewal_plan_rmb": renewal_plan_rmb,
        "first_month_total_rmb": first_total,
        "renewal_total_rmb": renewal_total,
        "first_month_saving_rmb": first_saving,
        "renewal_saving_rmb": renewal_saving,
        "saves_on_renewal": bool(renewal_saving > 0),
    }


def evaluate_coding_plans(
    *,
    daily_calls: float,
    payg_monthly_rmb: float,
    usage_mode: str = "interactive_ide",
    peak_5h_calls: int | None = None,
    model_id: str | dict[str, Any] | None = None,
    team_size: int = 1,
) -> dict[str, Any]:
    """
    Evaluate 2026 Coding Plan subscriptions against same-model Pay-As-You-Go cost and hard call caps
    for 1..50 interactive IDE developer seats.
    """
    seats = max(1, min(50, int(round(float(team_size or 1)))))
    d_calls = max(0, int(round(float(daily_calls or 0))))
    monthly_calls = d_calls * 30
    per_seat_monthly_calls = math.ceil(monthly_calls / seats) if monthly_calls > 0 else 0
    payg_rmb = round(max(0.0, float(payg_monthly_rmb or 0.0)), 2)
    norm_mode = "automated_backend" if str(usage_mode or "").strip().lower() in (
        "automated_backend",
        "backend",
        "api_service",
        "batch",
        "non_interactive",
    ) else "interactive_ide"

    total_pro_monthly_cap = PRO_MONTHLY_CAP * seats
    total_pro_5h_cap = PRO_5H_CAP * seats
    total_pro_weekly_cap = PRO_WEEKLY_CAP * seats
    total_lite_monthly_cap = LITE_MONTHLY_CAP * seats
    total_lite_5h_cap = LITE_5H_CAP * seats

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
            if (
                monthly_calls <= int(tier["quota_monthly"]) * seats
                and (d_calls * 7) <= int(tier["quota_weekly"]) * seats
            ):
                if peak_5h_calls is None or peak_5h_calls <= int(tier["quota_5h"]) * seats:
                    chosen_tier = tier
                    break

        exceeds_pro_by = max(0, monthly_calls - total_pro_monthly_cap)
        pro_tier = next((t for t in purchasable_tiers if t["tier_id"] == "pro"), purchasable_tiers[-1] if purchasable_tiers else None)
        ref_tier = chosen_tier or pro_tier
        if ref_tier is None:
            continue

        covers_model = plan_covers_model(offer, model_id) if model_id is not None else True
        first_rmb = ref_tier.get("first_month_rmb")
        unit_renewal = float(ref_tier["renewal_rmb"])
        unit_first = float(first_rmb) if first_rmb is not None else unit_renewal
        renewal_rmb = round(unit_renewal * seats, 2)
        effective_first_rmb = round(unit_first * seats, 2)

        overflow_hybrid = (
            _compute_overflow_hybrid(
                monthly_calls=monthly_calls,
                payg_rmb=payg_rmb,
                pro_tier=pro_tier,
                peak_5h_calls=peak_5h_calls,
                seats=seats,
            )
            if (norm_mode == "interactive_ide" and pro_tier is not None)
            else None
        )

        seat_prefix = f"{seats} 席 " if seats > 1 else ""
        tier_cap_monthly = int(ref_tier["quota_monthly"]) * seats
        tier_cap_5h = int(ref_tier["quota_5h"]) * seats

        if chosen_tier is None and monthly_calls <= tier_cap_monthly:
            status = "exceeds_5h_cap"
            verdict_zh = f"5 小时峰值 {peak_5h_calls:,} 次，超过 {seat_prefix}{ref_tier['name']} 的 {tier_cap_5h:,} 次窗口上限。"
            first_month_saving = None
            renewal_saving = None
        elif chosen_tier is None:
            status = "exceeds_monthly_cap"
            pro_label = f"{seats} 份 Pro" if seats > 1 else "1 份 Pro"
            cap_label = f"{seats} 席 Pro 合计月额度" if seats > 1 else "Pro 月额度"
            if overflow_hybrid and overflow_hybrid["saves_on_renewal"] and covers_model:
                verdict_zh = (
                    f"按 30 天预计 {_fmt_wan_calls(monthly_calls)}（{monthly_calls:,} 次），"
                    f"超出 {cap_label} {_fmt_wan_calls(exceeds_pro_by)}（上限 {total_pro_monthly_cap:,} 次/月，不能按 ¥{renewal_rmb:.0f} 全包封顶）；"
                    f"但可采用「{pro_label} 打底前 {_fmt_wan_calls(overflow_hybrid['covered_calls'])} + 超额 {_fmt_wan_calls(overflow_hybrid['overflow_calls'])}走按量 API」："
                    f"首月约 ¥{overflow_hybrid['first_month_total_rmb']:.2f}（省 ¥{overflow_hybrid['first_month_saving_rmb']:.2f}），"
                    f"续费月约 ¥{overflow_hybrid['renewal_total_rmb']:.2f}（仍净省 ¥{overflow_hybrid['renewal_saving_rmb']:.2f}）。"
                )
            else:
                verdict_zh = (
                    f"按 30 天预计 {_fmt_wan_calls(monthly_calls)}（{monthly_calls:,} 次），"
                    f"超出 {cap_label} {_fmt_wan_calls(exceeds_pro_by)}（上限 {total_pro_monthly_cap:,} 次/月）；"
                    "单靠个人包月套餐不够用，超出部分需走按量 API 或拆分多账号/企业方案。"
                )
            first_month_saving = None
            renewal_saving = None
        else:
            first_month_saving = round(payg_rmb - effective_first_rmb, 2)
            renewal_saving = round(payg_rmb - renewal_rmb, 2)
            cov_prefix = "套餐含同系模型，" if covers_model else "跨模型国产平替（套餐不含所选原模型），"
            chosen_cap_monthly = int(chosen_tier["quota_monthly"]) * seats
            tier_display = f"{seat_prefix}{chosen_tier['name']}"
            if renewal_saving > 0:
                status = "recommended_even_on_renewal"
                verdict_zh = (
                    f"{cov_prefix}匹配 {tier_display}（月上限 {chosen_cap_monthly:,} 次）："
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
                    f"低于 {tier_display} 价格（¥{effective_first_rmb:.2f}～¥{renewal_rmb:.0f}/月）。"
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
                "seats_count": seats,
                "matched_tier": chosen_tier["tier_id"] if chosen_tier else "exceeds_pro",
                "matched_tier_name": (f"{seat_prefix}{chosen_tier['name']}" if chosen_tier else verdict_zh),
                "unit_first_month_rmb": unit_first,
                "unit_renewal_rmb": unit_renewal,
                "first_month_rmb": effective_first_rmb,
                "has_first_month_promo": first_rmb is not None,
                "renewal_rmb": renewal_rmb,
                "quota_5h": int(ref_tier["quota_5h"]) * seats,
                "quota_weekly": int(ref_tier["quota_weekly"]) * seats,
                "quota_monthly": tier_cap_monthly,
                "first_month_savings_rmb": first_month_saving,
                "renewal_savings_rmb": renewal_saving,
                "overflow_hybrid": overflow_hybrid,
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
    best_hybrid_plan = hybrid_candidates[0] if hybrid_candidates else None
    recommended_overflow_hybrid_plan_id = best_hybrid_plan["plan_id"] if best_hybrid_plan else None

    if norm_mode == "automated_backend":
        headline_zh = (
            "当前选择「非交互式后端 / 批处理 API」场景：已自动排除阿里云百炼、腾讯云与火山方舟个人 Coding Plan"
            "（官方条款仅限交互式编程工具），请使用下方按量付费 API 或自建缓存网关。"
        )
        window_note_zh = "非交互式后端不适用个人套餐的 5 小时滚动窗口。"
    elif monthly_calls > total_pro_monthly_cap:
        over = monthly_calls - total_pro_monthly_cap
        if seats == 1:
            base_warn = (
                f"按 30 天预计 {_fmt_wan_calls(monthly_calls)}（{monthly_calls:,} 次模型调用），"
                f"超出 Pro 月额度 {_fmt_wan_calls(over)}（百炼/腾讯/火山 Pro 月上限均为 {PRO_MONTHLY_CAP:,} 次）——"
                "切勿误以为 ¥200 包月可无限封顶！"
            )
            pro_phrase = f"1 份 {best_hybrid_plan['name']} Pro 打底前 9 万次" if best_hybrid_plan else ""
            window_note_zh = (
                f"除月上限 {PRO_MONTHLY_CAP:,} 次外，Pro 每 5 小时限 {PRO_5H_CAP:,} 次、每周限 {PRO_WEEKLY_CAP:,} 次。"
            )
        else:
            base_warn = (
                f"按 {seats} 人团队 30 天合计 {_fmt_wan_calls(monthly_calls)}（人均约 {per_seat_monthly_calls:,} 次/月），"
                f"超出 {seats} 席 Pro 合计月上限 {_fmt_wan_calls(over)}（合计上限 {total_pro_monthly_cap:,} 次/月）——"
            )
            pro_phrase = (
                f"{seats} 份 {best_hybrid_plan['name']} Pro 打底前 {_fmt_wan_calls(best_hybrid_plan['overflow_hybrid']['covered_calls'])}"
                if best_hybrid_plan
                else ""
            )
            window_note_zh = (
                f"{seats} 席独立订阅合计每 5 小时限 {total_pro_5h_cap:,} 次、每周限 {total_pro_weekly_cap:,} 次（每席严禁跨人共用 sk-sp- 密钥）。"
            )
        if best_hybrid_plan is not None:
            bh = best_hybrid_plan["overflow_hybrid"]
            headline_zh = (
                base_warn
                + f"但可采用「{pro_phrase} + 超额 {_fmt_wan_calls(bh['overflow_calls'])}走按量 API」："
                f"首月约 ¥{bh['first_month_total_rmb']:.2f} / 续费月约 ¥{bh['renewal_total_rmb']:.2f}，"
                f"比全程纯按量（¥{payg_rmb:.2f}）仍净省 ¥{bh['renewal_saving_rmb']:.2f}/月。"
            )
        else:
            headline_zh = base_warn + f"当前模型全程纯按量仅约 ¥{payg_rmb:.2f}/月，无需叠加包月。"
    else:
        if peak_5h_calls is None:
            window_note_zh = (
                f"月额度足够，5 小时窗口待确认（{'合计 ' if seats > 1 else ''}Pro 每 5 小时上限 {total_pro_5h_cap:,} 次 / 腾讯及火山 Lite 每 5 小时上限 {total_lite_5h_cap:,} 次；"
                "注意单位为模型调用次数，单次用户提问在 Claude Code/Cline 中可能触发 5～30 次调用）。"
            )
        elif peak_5h_calls > total_pro_5h_cap:
            window_note_zh = f"5 小时峰值（{peak_5h_calls:,} 次）已超出 {'合计 ' if seats > 1 else ''}Pro 窗口上限（{total_pro_5h_cap:,} 次/5h），高峰期将触发限流。"
        else:
            window_note_zh = f"月额度与 5 小时峰值窗口（{peak_5h_calls:,} 次）均在套餐上限内。"

        if seats == 1:
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
        else:
            if monthly_calls > total_lite_monthly_cap:
                headline_zh = (
                    f"按 {seats} 人团队 30 天合计 {monthly_calls:,} 次调用（人均约 {per_seat_monthly_calls:,} 次/月）："
                    f"已超 {seats} 席 Lite 合计上限（{total_lite_monthly_cap:,} 次/月），"
                    f"需对标 {seats} 席独立 Pro（合计上限 {total_pro_monthly_cap:,} 次/月，续费合计 ¥{200 * seats:,}/月）对比团队共享按量池（¥{payg_rmb:.2f}/月）。"
                )
            else:
                headline_zh = (
                    f"按 {seats} 人团队 30 天合计 {monthly_calls:,} 次调用（人均约 {per_seat_monthly_calls:,} 次/月）："
                    f"处于 {seats} 席腾讯/火山 Lite（合计 {total_lite_monthly_cap:,} 次/月，¥{40 * seats:,}/月）与各家 Pro（合计 {total_pro_monthly_cap:,} 次/月）额度内。"
                )

    return {
        "usage_mode": norm_mode,
        "team_size": seats,
        "per_seat_monthly_calls": per_seat_monthly_calls,
        "daily_calls": d_calls,
        "monthly_calls_30d": monthly_calls,
        "payg_baseline_rmb": payg_rmb,
        "unit_warning_zh": "额度单位为「模型 API 调用次数」而非「用户提问次数」；一次 Agent 提问往往触发 5～30 次模型调用。",
        "headline_zh": headline_zh,
        "window_note_zh": window_note_zh,
        "eligible_subscriptions": eligible,
        "excluded_subscriptions": excluded,
        "recommended_same_family_plan_id": recommended_same_family_plan_id,
        "recommended_overflow_hybrid_plan_id": recommended_overflow_hybrid_plan_id,
        "quote_verified_date": QUOTE_VERIFIED_DATE,
    }


def _strip_gateway_model_prefix(raw_model_id: str | None) -> str:
    val = str(raw_model_id or "qwen3.5-plus").strip() or "qwen3.5-plus"
    lower = val.lower()
    for prefix in ("aliyun-bailian/", "tencent-cloud/", "volcengine/", "siliconflow/", "aliyun/", "tencent/"):
        if lower.startswith(prefix):
            return val[len(prefix) :]
    return val


def get_client_endpoint_config(
    *,
    vendor_or_plan: str,
    client_type: str = "claude_code",
    billing_mode: str = "payg",
    model_id: str = "qwen3.5-plus",
    fallback_base_url: str | None = None,
) -> dict[str, Any]:
    """
    Return protocol-accurate endpoint, `~/.claude/settings.json` payload, `unset ANTHROPIC_API_KEY`
    conflict guard, covered-model remapping, and 1-token connectivity smoke test for (vendor, client, mode).
    Prevents the critical bug where Coding Plan subscribers copy a Pay-As-You-Go endpoint or leave a global
    `ANTHROPIC_API_KEY` active and incur unexpected bills.
    """
    import json
    import re

    vp = str(vendor_or_plan or "").strip().lower()
    client = str(client_type or "claude_code").strip().lower()
    mode = "coding_plan" if str(billing_mode or "").strip().lower() in ("coding_plan", "subscription", "plan") else "payg"
    raw_mid = str(model_id or "qwen3.5-plus").strip() or "qwen3.5-plus"
    clean_mid = _strip_gateway_model_prefix(raw_mid)

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
        covered = [str(m) for m in (offer.get("models_covered") or [])]
        model_remapped = False
        if plan_key == "tencent-coding-plan":
            effective_model_id = covered[0] if covered else "tc-code-latest"
            model_remapped = clean_mid.lower() != effective_model_id.lower()
        else:
            norm_cand = clean_mid
            if re.match(r"^doubao-seed-2[.-]0-pro", norm_cand, flags=re.IGNORECASE):
                norm_cand = "doubao-seed-2.0-pro"
            matched_cov = next((c for c in covered if c.lower() == norm_cand.lower()), None)
            if matched_cov is not None:
                effective_model_id = matched_cov
            else:
                effective_model_id = covered[0] if covered else norm_cand
                model_remapped = True

        endpoints = offer.get("endpoints") or {}
        ep_key = "claude_code" if is_anthropic_client else "openai_compat"
        ep = endpoints.get(ep_key)
        if not ep:
            return {
                "verified": False,
                "billing_mode": "coding_plan",
                "protocol": "official_doc_required",
                "base_url": "",
                "effective_model_id": effective_model_id,
                "model_remapped": model_remapped,
                "claude_settings_json": None,
                "smoke_test_cmd": None,
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
        warning_zh = "⚠️ 已切换为 Coding Plan 包月专属端点与专属 Key（如 sk-sp- 开头）；若误填通用按量端点将继续产生按量扣费！"
        if model_remapped:
            warning_zh += f" 原模型 {raw_mid} 不在套餐覆盖列表内，已自动映射为套餐支持的 {effective_model_id}。"

        if ep["protocol"] == "anthropic":
            settings_payload = {
                "env": {
                    "ANTHROPIC_BASE_URL": base_url,
                    "ANTHROPIC_AUTH_TOKEN": key_placeholder,
                    "ANTHROPIC_MODEL": effective_model_id,
                    "ANTHROPIC_SMALL_FAST_MODEL": effective_model_id,
                }
            }
            claude_settings_json: str | None = json.dumps(settings_payload, ensure_ascii=False, indent=2)
            gui_snippet = (
                f"Protocol: Anthropic Messages API (Coding Plan 专属)\n"
                f"Base URL: {base_url}\n"
                f"API Key 格式: {key_placeholder} (切勿填入普通按量 Key)\n"
                f"Model ID: {effective_model_id}"
            )
            env_snippet = (
                "unset ANTHROPIC_API_KEY\n"
                f'export {ep["env_url_name"]}="{base_url}"\n'
                f'export {ep["env_key_name"]}="{key_placeholder}"\n'
                f'export {ep["env_model_name"]}="{effective_model_id}"\n'
                f'export ANTHROPIC_SMALL_FAST_MODEL="{effective_model_id}"'
            )
            smoke_test_cmd = (
                f'curl -fsS "{base_url.rstrip("/")}/v1/messages" '
                f'-H "x-api-key: {key_placeholder}" '
                '-H "anthropic-version: 2023-06-01" '
                '-H "content-type: application/json" '
                f'-d \'{{"model":"{effective_model_id}","max_tokens":1,"messages":[{{"role":"user","content":"ping"}}]}}\''
            )
        else:
            claude_settings_json = None
            gui_snippet = (
                f"Protocol: OpenAI Compatible (Coding Plan 专属端点)\n"
                f"Base URL: {base_url}\n"
                f"API Key 格式: {key_placeholder}\n"
                f"Model ID: {effective_model_id}"
            )
            env_snippet = (
                f'export {ep["env_url_name"]}="{base_url}"\n'
                f'export {ep["env_key_name"]}="{key_placeholder}"\n'
                f'export {ep["env_model_name"]}="{effective_model_id}"'
            )
            smoke_test_cmd = (
                f'curl -fsS "{base_url.rstrip("/")}/chat/completions" '
                f'-H "Authorization: Bearer {key_placeholder}" '
                '-H "Content-Type: application/json" '
                f'-d \'{{"model":"{effective_model_id}","max_tokens":1,"messages":[{{"role":"user","content":"ping"}}]}}\''
            )
        return {
            "verified": True,
            "billing_mode": "coding_plan",
            "protocol": ep["protocol"],
            "base_url": base_url,
            "key_prefix": ep["key_prefix"],
            "effective_model_id": effective_model_id,
            "model_remapped": model_remapped,
            "claude_settings_json": claude_settings_json,
            "smoke_test_cmd": smoke_test_cmd,
            "official_doc_url": offer["official_source_url"],
            "warning_zh": warning_zh,
            "gui_snippet": gui_snippet,
            "env_snippet": env_snippet,
        }

    if mode == "coding_plan" or is_anthropic_client:
        doc = offer["official_source_url"] if offer else "https://openrouter.ai/docs"
        return {
            "verified": False,
            "billing_mode": mode,
            "protocol": "official_doc_required",
            "base_url": "",
            "effective_model_id": clean_mid,
            "model_remapped": False,
            "claude_settings_json": None,
            "smoke_test_cmd": None,
            "official_doc_url": doc,
            "warning_zh": "当前组合缺少已核验的端点。",
            "gui_snippet": f"请按厂商教程核对配置：{doc}",
            "env_snippet": "# 请按厂商文档配置。",
        }

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

    payg_key_ph = "sk-or-your-openrouter-key" if "openrouter.ai" in base_url else "sk-your-payg-api-key"
    gui_snippet = (
        f"Protocol: OpenAI Compatible (按量付费标准端点)\n"
        f"Base URL: {base_url}\n"
        f"Model ID: {clean_mid}"
    )
    env_snippet = (
        f'export OPENAI_BASE_URL="{base_url}"\n'
        f'export OPENAI_API_KEY="{payg_key_ph}"\n'
        f'export OPENAI_MODEL="{clean_mid}"'
    )
    smoke_test_cmd = (
        f'curl -fsS "{base_url.rstrip("/")}/chat/completions" '
        f'-H "Authorization: Bearer {payg_key_ph}" '
        '-H "Content-Type: application/json" '
        f'-d \'{{"model":"{clean_mid}","max_tokens":1,"messages":[{{"role":"user","content":"ping"}}]}}\''
    )
    return {
        "verified": True,
        "billing_mode": "payg",
        "protocol": "openai",
        "base_url": base_url,
        "key_prefix": "sk-or-" if "openrouter.ai" in base_url else "sk-",
        "effective_model_id": clean_mid,
        "model_remapped": False,
        "claude_settings_json": None,
        "smoke_test_cmd": smoke_test_cmd,
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


def _parse_scaled_number(raw_val: Any) -> float:
    if isinstance(raw_val, (int, float)):
        return max(0.0, float(raw_val))
    s = str(raw_val or "").strip().replace(",", "").replace("_", "")
    if not s:
        raise ValueError("empty_number")
    import re

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
    val = _parse_scaled_number(cleaned)
    return val if is_rmb else val * fx_rate


def _try_parse_csv_bill(
    text: str,
    days: float,
    fx_rate: float = DEFAULT_FX_USD_TO_RMB,
) -> dict[str, Any] | None:
    """
    Detect and parse multi-row CSV / TSV / semicolon / Markdown pipe billing exports
    (OpenRouter Activity CSV, per-generation CSV, Mainland China cloud console CSV).
    Returns `None` if `text` is not a tabular CSV/TSV with recognized token headers.
    Raises `ValueError` if a valid CSV token header is matched by zero positive token rows.
    """
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

    if is_pipe:
        rows = [
            [cell.strip().strip('"').strip("'") for cell in ln.strip("|").split("|")]
            for ln in raw_lines
        ]
    else:
        rows = list(csv.reader(io.StringIO("\n".join(raw_lines)), delimiter=delim))

    if len(rows) < 2:
        return None

    raw_headers = [str(c or "").strip().lstrip("\ufeff").strip('"').strip("'") for c in rows[0]]
    if len(raw_headers) < 2:
        return None
    if any(re.match(r"^[0-9.]+$", h) for h in raw_headers if h):
        return None

    compact_headers = [re.sub(r"[\s_\-()/（）]+", "", h.lower()) for h in raw_headers]

    model_aliases = {
        "model", "modelid", "modelname", "modelpermaslug", "modelslug", "permaslug", "endpoint",
        "模型", "模型名称", "模型id", "调用模型",
    }
    req_aliases = {
        "requests", "requestcount", "numrequests", "calls", "apicalls", "totalrequests", "totalcalls", "count",
        "调用次数", "请求次数", "请求数", "调用量",
    }
    in_aliases = {
        "tokensprompt", "nativetokensprompt", "prompttokens", "inputtokens", "totalinputtokens", "input", "prompt",
        "输入token", "输入tokens", "输入token数", "提问token", "入参token",
    }
    out_aliases = {
        "tokenscompletion", "nativetokenscompletion", "completiontokens", "outputtokens", "totaloutputtokens", "output", "completion",
        "输出token", "输出tokens", "输出token数", "回答token", "出参token",
    }
    cached_sub_aliases = {
        "nativetokenscached", "cachedtokens", "cachedinputtokens", "prompttokenscached", "cachehit",
        "缓存命中token", "缓存命中tokens", "命中缓存token", "缓存token", "缓存输入token", "命中缓存",
    }
    cache_read_aliases = {"cachereadinputtokens", "cachereadtokens", "cacheread"}
    cache_write_aliases = {"cachecreationinputtokens", "cachewritetokens", "cachewrite", "缓存写入token"}
    reason_aliases = {
        "nativetokensreasoning", "reasoningtokens", "thinkingtokens",
        "思考token", "思考tokens", "推理token",
    }
    cost_aliases = {
        "usage", "cost", "totalcost", "spend", "amount", "bill", "costusd", "spendusd", "costrmb", "costcny",
        "应付金额", "账单金额", "消费金额", "费用", "金额", "花费", "总费用",
    }

    def _find_col(alias_set: set[str]) -> int | None:
        for idx, ch in enumerate(compact_headers):
            if ch in alias_set:
                return idx
        return None

    col_model = _find_col(model_aliases)
    col_req = _find_col(req_aliases)
    col_in = _find_col(in_aliases)
    col_out = _find_col(out_aliases)
    col_cached = _find_col(cached_sub_aliases)
    col_cread = _find_col(cache_read_aliases)
    col_cwrite = _find_col(cache_write_aliases)
    col_reason = _find_col(reason_aliases)
    col_cost = _find_col(cost_aliases)

    if col_in is None and col_out is None:
        return None

    summary_labels = {"total", "totals", "sum", "summary", "合计", "总计", "汇总", "小计"}
    groups: dict[str, dict[str, Any]] = {}

    def _cell_num(r: list[str], idx: int | None) -> float:
        if idx is None or idx >= len(r):
            return 0.0
        v = str(r[idx] or "").strip()
        if not v or v in ("-", "N/A", "na", "null", "None"):
            return 0.0
        return _parse_scaled_number(v)

    cost_header_compact = compact_headers[col_cost] if col_cost is not None else ""
    header_signature = tuple(compact_headers)

    for r in rows[1:]:
        if not r or all(not str(c or "").strip() for c in r):
            continue
        row_compact = tuple(
            re.sub(r"[\s_\-()/（）]+", "", str(c or "").strip().lstrip("\ufeff").strip('"').strip("'").lower())
            for c in r
        )
        if row_compact == header_signature:
            continue
        if (col_in is not None and col_in < len(row_compact) and row_compact[col_in] in in_aliases) or (
            col_out is not None and col_out < len(row_compact) and row_compact[col_out] in out_aliases
        ):
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

        if col_req is not None:
            req_val = _cell_num(r, col_req)
            row_reqs = req_val if req_val > 0 else 1.0
        else:
            row_reqs = 1.0

        row_cost_rmb = (
            _parse_currency_rmb(r[col_cost], cost_header_compact, fx_rate=fx_rate)
            if (col_cost is not None and col_cost < len(r))
            else 0.0
        )

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
    total_reqs = 0.0
    total_in = 0.0
    total_cached = 0.0
    total_out = 0.0
    total_reason = 0.0
    total_cost_rmb = 0.0

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

    cache_hit_rate = round(total_cached / total_in, 4) if total_in > 0 else 0.0
    daily_requests = max(1, int(round(total_reqs / days)))
    monthly_requests = max(1, int(round((total_reqs / days) * 30.0)))
    avg_input_tokens = max(1, int(round(total_in / max(1.0, total_reqs)))) if total_in > 0 else 1500
    avg_output_tokens = max(1, int(round(total_out / max(1.0, total_reqs)))) if total_out > 0 else 500
    monthly_input_m = round(((total_in / days) * 30.0) / 1_000_000.0, 6)
    monthly_output_m = round(((total_out / days) * 30.0) / 1_000_000.0, 6)

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
        "monthly_input_m": monthly_input_m,
        "monthly_output_m": monthly_output_m,
        "daily_requests": daily_requests,
        "avg_input_tokens": avg_input_tokens,
        "avg_output_tokens": avg_output_tokens,
        "cache_hit_rate": cache_hit_rate,
        "output_includes_reasoning": bool(total_reason > 0),
        "calls_estimated": False,
        "reported_cost_rmb": round(total_cost_rmb, 2),
        "monthly_reported_cost_rmb": round((total_cost_rmb / days) * 30.0, 2),
        "model_breakdown": model_breakdown,
    }


def _extract_json_records_raw(text: str) -> tuple[list[dict[str, Any]], str] | None:
    import json

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
            parsed_single = json.loads(text)
            if isinstance(parsed_single, dict):
                for list_key in ("data", "records", "logs", "items", "generations"):
                    cand_list = parsed_single.get(list_key)
                    if isinstance(cand_list, list) and any(isinstance(x, dict) for x in cand_list):
                        raw_records = [x for x in cand_list if isinstance(x, dict)]
                        source_format = "json_array_multimodel"
                        break
                if raw_records is None:
                    msg_obj = parsed_single.get("message")
                    resp_obj = parsed_single.get("response")
                    if (isinstance(msg_obj, dict) and (isinstance(msg_obj.get("usage"), dict) or parsed_single.get("type") in ("user", "assistant", "summary", "system"))) or (
                        isinstance(resp_obj, dict) and isinstance(resp_obj.get("body"), dict)
                    ):
                        raw_records = [parsed_single]
                        source_format = "jsonl_multimodel"
        except json.JSONDecodeError:
            lines = [
                ln.strip()
                for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            if len(lines) >= 2:
                parsed_lines: list[dict[str, Any]] = []
                all_json_lines = True
                for ln in lines:
                    if ln.startswith("{") and ln.endswith("}"):
                        try:
                            obj = json.loads(ln)
                            if isinstance(obj, dict):
                                parsed_lines.append(obj)
                            else:
                                all_json_lines = False
                        except json.JSONDecodeError:
                            all_json_lines = False
                    else:
                        all_json_lines = False
                if len(parsed_lines) >= 2 or (all_json_lines and len(parsed_lines) >= 1):
                    raw_records = parsed_lines
                    source_format = "jsonl_multimodel"

    if raw_records is None or source_format is None:
        return None
    return raw_records, source_format


def _collect_json_record_entries(
    raw_records: list[dict[str, Any]],
    *,
    fx_rate: float = DEFAULT_FX_USD_TO_RMB,
) -> tuple[list[dict[str, Any]], int]:
    def _safe_num(val: Any) -> float:
        if val is None or isinstance(val, (dict, list, bool)):
            return 0.0
        try:
            return _parse_scaled_number(val)
        except ValueError:
            return 0.0

    def _first_val(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for k in keys:
            if d.get(k) is not None and not isinstance(d.get(k), (dict, list, bool)):
                return d.get(k)
        return None

    skip_types = {"user", "summary", "system", "file-history-snapshot", "queue-operation"}
    summary_labels = {"total", "totals", "sum", "summary", "合计", "总计", "汇总", "小计"}
    deduped_entries: dict[str, dict[str, Any]] = {}
    anon_entries: list[dict[str, Any]] = []
    deduplicated_chunks = 0

    for rec in raw_records:
        if str(rec.get("type") or "").strip().lower() in skip_types:
            continue
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        resp = rec.get("response") if isinstance(rec.get("response"), dict) else {}
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}

        u_msg = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
        u_body = body.get("usage") if isinstance(body.get("usage"), dict) else None
        u_rec = rec.get("usage") if isinstance(rec.get("usage"), dict) else None
        u = u_msg or u_body or u_rec or {}

        model_raw = (
            _first_val(rec, ("model_permaslug", "model", "model_id", "model_name", "api_model_id"))
            or _first_val(msg, ("model", "model_id"))
            or _first_val(body, ("model", "model_id"))
            or "unknown"
        )
        model_label = str(model_raw).strip() or "unknown"
        if model_label.lower() in summary_labels:
            continue

        merged: dict[str, Any] = {**rec, **body, **msg, **u}
        if "cache_read_input_tokens" in merged or "cache_creation_input_tokens" in merged:
            uncached = _safe_num(merged.get("input_tokens"))
            c_read = _safe_num(merged.get("cache_read_input_tokens"))
            c_write = _safe_num(merged.get("cache_creation_input_tokens"))
            row_in = uncached + c_read + c_write
            row_cached = c_read
        else:
            p_det = merged.get("prompt_tokens_details") if isinstance(merged.get("prompt_tokens_details"), dict) else {}
            in_det = merged.get("input_tokens_details") if isinstance(merged.get("input_tokens_details"), dict) else {}
            in_val = _safe_num(
                _first_val(merged, ("prompt_tokens", "native_tokens_prompt", "tokens_prompt", "input_tokens", "total_input_tokens"))
            )
            c_raw = (
                p_det.get("cached_tokens")
                if p_det.get("cached_tokens") is not None
                else (
                    in_det.get("cached_tokens")
                    if in_det.get("cached_tokens") is not None
                    else _first_val(merged, ("native_tokens_cached", "cached_tokens", "cached_input_tokens", "cache_hit_tokens"))
                )
            )
            c_val = _safe_num(c_raw)
            row_in = max(in_val, c_val)
            row_cached = min(row_in, c_val)

        out_val = _safe_num(
            _first_val(merged, ("completion_tokens", "native_tokens_completion", "tokens_completion", "output_tokens", "total_output_tokens"))
        )
        c_det = merged.get("completion_tokens_details") if isinstance(merged.get("completion_tokens_details"), dict) else {}
        o_det = merged.get("output_tokens_details") if isinstance(merged.get("output_tokens_details"), dict) else {}
        r_raw = (
            c_det.get("reasoning_tokens")
            if c_det.get("reasoning_tokens") is not None
            else (
                o_det.get("reasoning_tokens")
                if o_det.get("reasoning_tokens") is not None
                else _first_val(merged, ("native_tokens_reasoning", "reasoning_tokens", "thinking_tokens"))
            )
        )
        reason_val = _safe_num(r_raw)

        if row_in <= 0 and out_val <= 0:
            continue

        req_raw = _first_val(rec, ("requests", "total_requests", "calls", "api_calls", "num_requests", "request_count"))
        row_reqs = max(1.0, _safe_num(req_raw)) if req_raw is not None else 1.0

        rmb_cost_raw = _first_val(rec, ("cost_rmb", "spend_rmb", "cost_cny", "应付金额", "账单金额"))
        usd_cost_raw = _first_val(rec, ("spend", "response_cost", "cost_usd", "costUSD", "total_cost", "cost"))
        if usd_cost_raw is None and rec.get("usage") is not None and not isinstance(rec.get("usage"), (dict, list, bool)):
            usd_cost_raw = rec.get("usage")
        if rmb_cost_raw is not None:
            row_cost_rmb = _parse_currency_rmb(rmb_cost_raw, "costrmb", fx_rate=fx_rate)
        elif usd_cost_raw is not None:
            row_cost_rmb = _parse_currency_rmb(usd_cost_raw, "costusd", fx_rate=fx_rate)
        else:
            row_cost_rmb = 0.0

        dedupe_id: str | None = None
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

        entry = {
            "model": model_label,
            "requests": row_reqs,
            "input_tokens": row_in,
            "cached_input_tokens": row_cached,
            "output_tokens": out_val,
            "reasoning_tokens": reason_val,
            "reported_cost_rmb": row_cost_rmb,
            "source_file_idx": rec.get("_src_file_idx"),
        }
        if dedupe_id is not None:
            if dedupe_id in deduped_entries:
                deduplicated_chunks += 1
                prev = deduped_entries[dedupe_id]
                for num_k in ("requests", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "reported_cost_rmb"):
                    prev[num_k] = max(prev[num_k], entry[num_k])
                if prev["model"] == "unknown" and entry["model"] != "unknown":
                    prev["model"] = entry["model"]
            else:
                deduped_entries[dedupe_id] = entry
        else:
            anon_entries.append(entry)

    return list(deduped_entries.values()) + anon_entries, deduplicated_chunks


def _build_multimodel_portfolio_from_entries(
    all_entries: list[dict[str, Any]],
    *,
    days: float,
    source_format: str,
    deduplicated_chunks: int = 0,
    merged_files_count: int | None = None,
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for ent in all_entries:
        g_key = str(ent["model"]).lower()
        if g_key not in groups:
            groups[g_key] = {
                "model": str(ent["model"]),
                "requests": 0.0,
                "input_tokens": 0.0,
                "cached_input_tokens": 0.0,
                "output_tokens": 0.0,
                "reasoning_tokens": 0.0,
                "reported_cost_rmb": 0.0,
            }
        grp = groups[g_key]
        grp["requests"] += float(ent["requests"])
        grp["input_tokens"] += float(ent["input_tokens"])
        grp["cached_input_tokens"] += float(ent["cached_input_tokens"])
        grp["output_tokens"] += float(ent["output_tokens"])
        grp["reasoning_tokens"] += float(ent.get("reasoning_tokens") or 0.0)
        grp["reported_cost_rmb"] += float(ent.get("reported_cost_rmb") or 0.0)

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
    out = {
        "detected_format": "csv_multimodel_bill",
        "source_format": source_format,
        "deduplicated_chunks": deduplicated_chunks,
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
    if merged_files_count is not None:
        out["merged_files_count"] = merged_files_count
    return out


def _try_parse_json_records_bill(
    text: str,
    days: float,
    *,
    fx_rate: float = DEFAULT_FX_USD_TO_RMB,
) -> dict[str, Any] | None:
    """
    Parse multi-record JSON Array (`[...]`, `{"data": [...]}`) or multi-line JSONL (`{...}\\n{...}`)
    logs/bills into the exact `csv_multimodel_bill` portfolio schema.
    Supports Claude Code `~/.claude/projects/*.jsonl` (streaming `message.id` deduplication + additive cache),
    OpenAI Batch `.jsonl` (`response.body`), LiteLLM spend logs, and OpenRouter JSON exports.
    """
    extracted = _extract_json_records_raw(text)
    if extracted is None:
        return None
    raw_records, source_format = extracted
    all_entries, deduplicated_chunks = _collect_json_record_entries(raw_records, fx_rate=fx_rate)
    if not all_entries:
        raise ValueError("JSON/JSONL bill contains zero positive token records")
    return _build_multimodel_portfolio_from_entries(
        all_entries,
        days=days,
        source_format=source_format,
        deduplicated_chunks=deduplicated_chunks,
    )


def _resolve_model_env_key_var(model: dict[str, Any]) -> str:
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


def _resolve_model_api_base(model: dict[str, Any]) -> str:
    base = str(model.get("api_base_url") or "").strip()
    if base:
        return base
    return "https://openrouter.ai/api/v1" if model.get("region") == "global" else "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _find_same_family_cn_candidates(raw_model_name: str, workhorses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_low = str(raw_model_name or "").lower()
    if "deepseek-r1" in raw_low or "deepseek-reasoner" in raw_low or raw_low.endswith("/r1"):
        return [c for c in workhorses if "deepseek-r1" in str(c.get("id") or "").lower()]
    if "deepseek-v3" in raw_low or "deepseek-chat" in raw_low:
        return [c for c in workhorses if "deepseek-v3" in str(c.get("id") or "").lower()]
    if "qwen3-coder" in raw_low or "qwen-coder" in raw_low:
        return [c for c in workhorses if "coder" in str(c.get("id") or "").lower() and "qwen" in str(c.get("id") or "").lower()]
    if "qwen" in raw_low:
        return [c for c in workhorses if "qwen" in str(c.get("id") or "").lower()]
    if "glm" in raw_low:
        return [c for c in workhorses if "glm" in str(c.get("id") or "").lower()]
    if "kimi" in raw_low or "moonshot" in raw_low:
        return [c for c in workhorses if "kimi" in str(c.get("id") or "").lower()]
    if "minimax" in raw_low:
        return [c for c in workhorses if "minimax" in str(c.get("id") or "").lower()]
    if "doubao" in raw_low:
        return [c for c in workhorses if "doubao" in str(c.get("id") or "").lower()]
    if "hunyuan" in raw_low:
        return [c for c in workhorses if "hunyuan" in str(c.get("id") or "").lower()]
    return []


def build_bill_migration_litellm_config(line_items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Generate a zero-code-change LiteLLM Proxy `config.yaml`, deduplicated `export` env snippet,
    and 1-token proxy verification `curl` mapping every exact `raw_model` in the user's bill
    to its recommended Pay-As-You-Go API route.
    """
    yaml_lines = [
        "# AI Cost Radar — Zero-Code Multi-Model Bill Migration (LiteLLM Proxy)",
        "# Compliance: Use standard Pay-As-You-Go API keys ONLY (NEVER use sk-sp- Coding Plan keys).",
        "model_list:",
    ]
    required_env_vars: list[str] = []
    for item in line_items:
        alias_escaped = str(item.get("raw_model") or "default").replace("\\", "\\\\").replace('"', '\\"')
        api_mid = str(item.get("recommended_api_model_id") or item.get("recommended_model_id") or "deepseek-v3")
        api_base = str(item.get("recommended_api_base_url") or "https://dashscope.aliyuncs.com/compatible-mode/v1")
        env_var = str(item.get("recommended_env_key_var") or "DASHSCOPE_API_KEY")
        if env_var not in required_env_vars:
            required_env_vars.append(env_var)
        yaml_lines.extend(
            [
                f'  - model_name: "{alias_escaped}"',
                "    litellm_params:",
                f"      model: openai/{api_mid}",
                f"      api_base: {api_base}",
                f"      api_key: os.environ/{env_var}",
            ]
        )

    yaml_lines.extend(
        [
            "",
            "router_settings:",
            "  routing_strategy: simple-shuffle",
            "  num_retries: 2",
            "  timeout: 60",
        ]
    )
    config_yaml = "\n".join(yaml_lines)

    env_lines = [
        f'export {var}="sk-your-{var.lower().replace("_api_key", "")}-payg-key"'
        for var in required_env_vars
    ]
    env_lines.extend(
        [
            'export LITELLM_MASTER_KEY="sk-local-bill-migration-proxy"',
            "",
            "# 启动本地零改代码迁移网关（业务代码无需改 model 名，仅需设 OPENAI_BASE_URL=http://127.0.0.1:4000/v1）",
            "uvx --from 'litellm[proxy]' litellm --config config.yaml --port 4000",
        ]
    )
    env_snippet = "\n".join(env_lines)

    probe_model = str(line_items[0]["raw_model"] if line_items else "deepseek-v3").replace("\\", "\\\\").replace('"', '\\"')
    smoke_test_cmd = (
        'curl -fsS "http://127.0.0.1:4000/v1/chat/completions" '
        '-H "Authorization: Bearer sk-local-bill-migration-proxy" '
        '-H "Content-Type: application/json" '
        f'-d \'{{"model":"{probe_model}","max_tokens":1,"messages":[{{"role":"user","content":"ping"}}]}}\''
    )

    return {
        "config_yaml": config_yaml,
        "env_snippet": env_snippet,
        "smoke_test_cmd": smoke_test_cmd,
        "required_env_vars": required_env_vars,
        "distinct_providers_count": len(required_env_vars),
        "compliance_warning_zh": (
            "合规红线：此网关配置仅限填入各厂商标准「按量付费 API Key」（sk-...）；"
            "严禁将个人 Coding Plan 包月专属密钥（sk-sp-...）填入 LiteLLM 网关或团队共享服务。"
        ),
    }


def _is_workhorse_cn_candidate(model: dict[str, Any]) -> bool:
    if model.get("region") != "cn_direct" or model.get("is_free"):
        return False
    if int(model.get("context_length") or 0) < 64000:
        return False
    mid_low = str(model.get("id") or "").lower()
    if any(tok in mid_low for tok in ("7b", "8b", "lite", "turbo", "mini", "flash")):
        return False
    return True


def audit_csv_bill(
    models: list[dict[str, Any]],
    raw_text: str | dict[str, Any],
    *,
    days_observed: float = 30.0,
    usage_mode: str = "interactive_ide",
    team_size: int = 1,
    offers: list[dict[str, Any]] | None = None,
    fx_rate: float = DEFAULT_FX_USD_TO_RMB,
) -> dict[str, Any]:
    """
    Audit a multi-model CSV/TSV/JSON/JSONL billing statement:
      1. Extrapolate each model's requests, input/output/cached tokens, and spend to 30 days.
      2. Match each row against real workhorse Mainland China direct models (>=64K ctx, non-toy),
         separating reasoning vs coding workloads and never recommending a costlier replacement,
         while also surfacing exact same-family CN direct routes when available.
      3. Generate a zero-code-change LiteLLM Proxy `migration_litellm_config` & evaluate Coding Plan options.
    """
    if isinstance(raw_text, dict) and raw_text.get("detected_format") == "csv_multimodel_bill":
        parsed = raw_text
    else:
        parsed = parse_usage_log_snippet(str(raw_text), days_observed=days_observed)
        if parsed.get("detected_format") != "csv_multimodel_bill":
            raise ValueError("audit_csv_bill requires a multi-model CSV/TSV/JSONL snippet")

    days = float(parsed["days_observed"])
    scale_30d = 30.0 / days
    seats = max(1, min(50, int(round(float(team_size or 1)))))
    norm_mode = "automated_backend" if str(usage_mode or "").strip().lower() in (
        "automated_backend", "backend", "api_service", "batch", "non_interactive"
    ) else "interactive_ide"

    workhorses = [m for m in models if _is_workhorse_cn_candidate(m)]
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

        matched, _ = resolve_model_query(models, raw_model_name)
        if matched is None:
            continue

        matched_id_low = str(matched.get("id") or "").lower()
        if matched.get("region") == "global" and any(
            v in raw_low or v in matched_id_low
            for v in ("anthropic", "claude", "openai", "gpt-", "o1", "o3", "o4", "google", "gemini", "x-ai", "grok")
        ):
            has_global_closed = True

        m_hit_factor = float(
            matched.get("cache_hit_factor")
            if matched.get("cache_hit_factor") is not None
            else (0.2 if matched.get("region") == "cn_direct" else 0.5)
        )
        catalog_payg_rmb = round(
            calculate_token_bill(
                monthly_input_m=m_in_m,
                monthly_output_m=m_out_m,
                input_price_per_1m=float(matched["input_rmb_per_1m"]),
                output_price_per_1m=float(matched["output_rmb_per_1m"]),
                cache_hit_rate=hit_rate,
                cache_hit_factor=m_hit_factor,
                reasoning_multiplier=1.0,
                output_includes_reasoning=True,
            )["total_cost"],
            2,
        )
        baseline_rmb = reported_monthly_rmb if reported_monthly_rmb > 0 else catalog_payg_rmb

        needs_reasoning = bool(
            grp.get("output_includes_reasoning")
            or any(k in raw_low for k in ("-r1", "/r1", "deepseek-r1", "o1", "o3", "o4", "qwq", "hunyuan-t1", "thinking", "reasoner"))
        )
        required_tag = "reasoning" if needs_reasoning else "coding"
        pool = [c for c in workhorses if required_tag in (c.get("tags") or [])] or workhorses

        best_cand: dict[str, Any] | None = None
        best_cand_rmb = baseline_rmb
        best_cand_score = -1.0
        for cand in pool:
            c_hit_factor = float(
                cand.get("cache_hit_factor")
                if cand.get("cache_hit_factor") is not None
                else 0.2
            )
            c_rmb = round(
                calculate_token_bill(
                    monthly_input_m=m_in_m,
                    monthly_output_m=m_out_m,
                    input_price_per_1m=float(cand["input_rmb_per_1m"]),
                    output_price_per_1m=float(cand["output_rmb_per_1m"]),
                    cache_hit_rate=hit_rate,
                    cache_hit_factor=c_hit_factor,
                    reasoning_multiplier=1.0,
                    output_includes_reasoning=True,
                )["total_cost"],
                2,
            )
            c_score = float(cand.get("value_score") or 0.0)
            if best_cand is None or (c_rmb < best_cand_rmb) or (c_rmb == best_cand_rmb and c_score > best_cand_score):
                best_cand = cand
                best_cand_rmb = c_rmb
                best_cand_score = c_score

        same_fam_pool = _find_same_family_cn_candidates(raw_model_name, workhorses)
        same_fam_best: dict[str, Any] | None = None
        same_fam_rmb: float | None = None
        same_fam_score = -1.0
        for sf_cand in same_fam_pool:
            sf_hit = float(sf_cand.get("cache_hit_factor") if sf_cand.get("cache_hit_factor") is not None else 0.2)
            sf_cost = round(
                calculate_token_bill(
                    monthly_input_m=m_in_m,
                    monthly_output_m=m_out_m,
                    input_price_per_1m=float(sf_cand["input_rmb_per_1m"]),
                    output_price_per_1m=float(sf_cand["output_rmb_per_1m"]),
                    cache_hit_rate=hit_rate,
                    cache_hit_factor=sf_hit,
                    reasoning_multiplier=1.0,
                    output_includes_reasoning=True,
                )["total_cost"],
                2,
            )
            sf_score = float(sf_cand.get("value_score") or 0.0)
            if same_fam_best is None or (sf_cost < (same_fam_rmb or 0.0)) or (sf_cost == same_fam_rmb and sf_score > same_fam_score):
                same_fam_best = sf_cand
                same_fam_rmb = sf_cost
                same_fam_score = sf_score

        if best_cand is not None and best_cand_rmb < baseline_rmb - 0.005:
            rec_model = best_cand
            opt_rmb = round(best_cand_rmb, 2)
            action = "switch_cn_direct"
        else:
            rec_model = matched
            opt_rmb = round(baseline_rmb, 2)
            action = "keep_current"

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
                "recommended_api_base_url": _resolve_model_api_base(rec_model),
                "recommended_env_key_var": _resolve_model_env_key_var(rec_model),
                "recommended_signup_url": rec_model.get("signup_url") or rec_model.get("affiliate_url") or "",
                "same_family_cn_model_id": same_fam_best["id"] if same_fam_best else None,
                "same_family_cn_model_name": same_fam_best["name"] if same_fam_best else None,
                "same_family_cn_api_model_id": str(same_fam_best.get("api_model_id") or same_fam_best["id"]) if same_fam_best else None,
                "same_family_cn_api_base_url": _resolve_model_api_base(same_fam_best) if same_fam_best else None,
                "same_family_cn_env_key_var": _resolve_model_env_key_var(same_fam_best) if same_fam_best else None,
                "same_family_cn_monthly_rmb": same_fam_rmb,
                "optimized_payg_rmb": opt_rmb,
                "savings_rmb": sav_rmb,
                "savings_pct": sav_pct,
                "action": action,
            }
        )

    total_m_reqs = sum(item["monthly_requests"] for item in line_items)
    total_base_rmb = round(sum(item["baseline_monthly_rmb"] for item in line_items), 2)
    total_cat_rmb = round(sum(item["catalog_payg_rmb"] for item in line_items), 2)
    total_opt_rmb = round(sum(item["optimized_payg_rmb"] for item in line_items), 2)
    total_sav_rmb = round(max(0.0, total_base_rmb - total_opt_rmb), 2)
    total_sav_pct = round((total_sav_rmb / total_base_rmb) * 100.0, 1) if total_base_rmb > 0 else 0.0

    coding_plan_option: dict[str, Any] | None = None
    if norm_mode == "interactive_ide":
        sub_offers = [
            o for o in (offers or OFFERS_CATALOG_2026)
            if isinstance(o, dict) and o.get("offer_type") == "subscription"
        ] or [o for o in OFFERS_CATALOG_2026 if o["offer_type"] == "subscription"]

        fits_lite = total_m_reqs <= (LITE_MONTHLY_CAP * seats)
        fits_pro = total_m_reqs <= (PRO_MONTHLY_CAP * seats)
        target_plan_id = "tencent-coding-plan" if fits_lite else "aliyun-coding-plan"
        chosen_offer = next((o for o in sub_offers if o["id"] == target_plan_id), sub_offers[0])
        tier_id = "lite" if (fits_lite and any(t.get("tier_id") == "lite" and t.get("purchasable") for t in chosen_offer.get("tiers", []))) else "pro"
        chosen_tier = next(
            (t for t in chosen_offer.get("tiers", []) if t.get("tier_id") == tier_id),
            (chosen_offer.get("tiers") or [{}])[-1],
        )
        raw_first = chosen_tier.get("first_month_rmb")
        unit_renew = float(chosen_tier.get("renewal_rmb") or 200.0)
        unit_first = float(raw_first) if raw_first is not None else unit_renew
        first_rmb = round(unit_first * seats, 2)
        renew_rmb = round(unit_renew * seats, 2)
        cap_monthly = int(chosen_tier.get("quota_monthly") or PRO_MONTHLY_CAP) * seats

        has_cross_caveat = bool(
            has_global_closed
            or any(not plan_covers_model(chosen_offer, item["matched_model_id"]) for item in line_items)
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
        "migration_litellm_config": build_bill_migration_litellm_config(line_items),
    }


def parse_usage_log_snippet(
    raw_text: str,
    *,
    days_observed: float = 30.0,
    default_tokens_per_call: int = 4000,
) -> dict[str, Any]:
    """
    Deterministically parse real LLM usage logs, multi-model CSV/TSV/JSON/JSONL bills, or billing summaries into calculator parameters.
    Supports:
      1. Multi-model CSV / TSV / pipe-table / JSON Array / JSONL billing exports (`detected_format="csv_multimodel_bill"`,
         incl. Claude Code `~/.claude/projects/*.jsonl` transcripts & OpenAI Batch `.jsonl`)
      2. Anthropic / Claude Code `/cost` plaintext or JSON (where `input_tokens` and `cache_read` are additive)
      3. OpenAI / OpenRouter / Bailian / DeepSeek `usage` JSON (where `cached_tokens` is a subset of `prompt_tokens`,
         and `reasoning_tokens` inside `completion_tokens_details` triggers `output_includes_reasoning=True`)
      4. Chinese & English cloud console text summaries (`输入 Token 28M（缓存命中 14M），输出 Token 7M`)
    """
    import json
    import re

    text = str(raw_text or "").strip()
    if not text or len(text) > 32000:
        raise ValueError("Empty or oversized usage_snippet")

    days = float(days_observed if days_observed is not None else 30.0)
    if not math.isfinite(days) or days <= 0 or days > 365:
        raise ValueError("Invalid days_observed (must be between 0.1 and 365)")

    json_records_parsed = _try_parse_json_records_bill(text, days)
    if json_records_parsed is not None:
        return json_records_parsed

    total_input = 0.0
    cached_input = 0.0
    total_output = 0.0
    explicit_requests: float | None = None
    explicit_daily_requests: float | None = None
    output_includes_reasoning = False
    detected_format = "text_summary"

    # Try JSON object parsing first if snippet contains `{...}`
    json_obj: dict[str, Any] | None = None
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                json_obj = parsed
        except json.JSONDecodeError:
            json_obj = None
    elif "{" in text and "}" in text:
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

        if merged.get("days_observed") is not None and days_observed == 30.0:
            try:
                d_cand = float(merged["days_observed"])
                if 0 < d_cand <= 365:
                    days = d_cand
            except (TypeError, ValueError):
                pass

        for rk in ("requests", "total_requests", "calls", "total_calls", "api_calls", "num_requests"):
            if merged.get(rk) is not None:
                explicit_requests = _parse_scaled_number(merged[rk])
                break
        if explicit_requests is None and merged.get("daily_requests") is not None:
            explicit_daily_requests = _parse_scaled_number(merged["daily_requests"])

        has_anthropic_cache = (
            "cache_read_input_tokens" in merged or "cache_creation_input_tokens" in merged
        )
        if has_anthropic_cache:
            detected_format = "anthropic_usage_json"
            uncached = _parse_scaled_number(merged.get("input_tokens") or 0)
            c_read = _parse_scaled_number(merged.get("cache_read_input_tokens") or 0)
            c_write = _parse_scaled_number(merged.get("cache_creation_input_tokens") or 0)
            total_input = uncached + c_read + c_write
            cached_input = c_read
        else:
            detected_format = "openai_usage_json"
            p_details = merged.get("prompt_tokens_details") if isinstance(merged.get("prompt_tokens_details"), dict) else {}
            in_details = merged.get("input_tokens_details") if isinstance(merged.get("input_tokens_details"), dict) else {}
            raw_in = merged.get("prompt_tokens")
            if raw_in is None:
                raw_in = merged.get("input_tokens")
            if raw_in is not None:
                total_input = _parse_scaled_number(raw_in)
            elif merged.get("monthly_input_m") is not None:
                total_input = _parse_scaled_number(merged["monthly_input_m"]) * 1_000_000.0

            raw_cached = (
                p_details.get("cached_tokens")
                if p_details.get("cached_tokens") is not None
                else (
                    in_details.get("cached_tokens")
                    if in_details.get("cached_tokens") is not None
                    else (merged.get("cached_tokens") if merged.get("cached_tokens") is not None else merged.get("cached_input_tokens"))
                )
            )
            if raw_cached is not None:
                cached_input = _parse_scaled_number(raw_cached)
                if total_input < cached_input:
                    total_input = cached_input

        raw_out = merged.get("completion_tokens")
        if raw_out is None:
            raw_out = merged.get("output_tokens")
        if raw_out is not None:
            total_output = _parse_scaled_number(raw_out)
        elif merged.get("monthly_output_m") is not None:
            total_output = _parse_scaled_number(merged["monthly_output_m"]) * 1_000_000.0

        c_details = merged.get("completion_tokens_details") if isinstance(merged.get("completion_tokens_details"), dict) else {}
        o_details = merged.get("output_tokens_details") if isinstance(merged.get("output_tokens_details"), dict) else {}
        r_tok = (
            c_details.get("reasoning_tokens")
            if c_details.get("reasoning_tokens") is not None
            else (o_details.get("reasoning_tokens") if o_details.get("reasoning_tokens") is not None else merged.get("reasoning_tokens"))
        )
        if r_tok is not None and _parse_scaled_number(r_tok) > 0:
            output_includes_reasoning = True
    else:
        csv_parsed = _try_parse_csv_bill(text, days)
        if csv_parsed is not None:
            return csv_parsed

        num_pat = r"([0-9][0-9,._]*\s*(?:百万|亿|万|千|[kKmMbBwW])?)"

        m_in = re.search(
            r"(?:total\s+input(?:\s+tokens?)?|uncached\s+input|prompt\s+tokens?|\binput(?:\s+tokens?)?|输入\s*(?:token|tokens)?)\s*[:：=]?\s*"
            + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        m_cache_read = re.search(
            r"(?:cache\s*read(?:\s+input)?(?:\s+tokens?)?|cached(?:\s+input)?(?:\s+tokens?)?|缓存命中(?:\s*token|\s*tokens|\s*输入)?|命中缓存)\s*[:：=]?\s*"
            + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        m_cache_write = re.search(
            r"(?:cache\s*(?:write|creation)(?:\s+tokens?)?|缓存写入)\s*[:：=]?\s*" + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        m_out = re.search(
            r"(?:total\s+output(?:\s+tokens?)?|completion\s+tokens?|\boutput(?:\s+tokens?)?|输出\s*(?:token|tokens)?)\s*[:：=]?\s*"
            + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        m_reason = re.search(
            r"(?:reasoning\s+tokens?|思考\s*(?:token|tokens)?)\s*[:：=]?\s*" + num_pat,
            text,
            flags=re.IGNORECASE,
        )
        m_req = re.search(
            r"(?:total\s+requests?|api\s+calls?|total\s+calls?|\brequests?|\bturns?|调用(?:次数|量)?|请求(?:次数|数)?)\s*[:：=]?\s*"
            + num_pat,
            text,
            flags=re.IGNORECASE,
        )

        raw_in_val = _parse_scaled_number(m_in.group(1)) if m_in else 0.0
        cache_read_val = _parse_scaled_number(m_cache_read.group(1)) if m_cache_read else 0.0
        cache_write_val = _parse_scaled_number(m_cache_write.group(1)) if m_cache_write else 0.0
        total_output = _parse_scaled_number(m_out.group(1)) if m_out else 0.0

        is_claude_code_style = bool(re.search(r"cache\s*read", text, flags=re.IGNORECASE)) and not bool(
            re.search(r"total\s+input", text, flags=re.IGNORECASE)
        )
        if is_claude_code_style:
            detected_format = "claude_code_cost"
            total_input = raw_in_val + cache_read_val + cache_write_val
            cached_input = cache_read_val
        else:
            if raw_in_val >= cache_read_val and raw_in_val > 0:
                total_input = raw_in_val
                cached_input = cache_read_val
            else:
                total_input = raw_in_val + cache_read_val + cache_write_val
                cached_input = cache_read_val

        if m_reason and _parse_scaled_number(m_reason.group(1)) > 0:
            output_includes_reasoning = True
        if m_req:
            explicit_requests = _parse_scaled_number(m_req.group(1))

    if total_input <= 0 and total_output <= 0:
        raise ValueError("Unable to find input/output token counts in usage_snippet")

    cached_input = min(total_input, max(0.0, cached_input))
    cache_hit_rate = round(cached_input / total_input, 4) if total_input > 0 else 0.0

    calls_estimated = False
    if explicit_daily_requests is not None and explicit_daily_requests > 0:
        daily_requests = max(1, int(round(explicit_daily_requests)))
        est_total_calls = max(1.0, explicit_daily_requests * days)
    elif explicit_requests is not None and explicit_requests > 0:
        est_total_calls = max(1.0, explicit_requests)
        daily_requests = max(1, int(round(est_total_calls / days)))
    else:
        calls_estimated = True
        denom = max(200, int(default_tokens_per_call or 4000))
        est_total_calls = max(1.0, round(total_input / denom) if total_input > 0 else round(total_output / 800.0))
        daily_requests = max(1, int(round(est_total_calls / days)))

    avg_input_tokens = max(1, int(round(total_input / est_total_calls))) if total_input > 0 else 1500
    avg_output_tokens = max(1, int(round(total_output / est_total_calls))) if total_output > 0 else 500
    monthly_input_m = round(((total_input / days) * 30.0) / 1_000_000.0, 6)
    monthly_output_m = round(((total_output / days) * 30.0) / 1_000_000.0, 6)

    return {
        "detected_format": detected_format,
        "days_observed": days,
        "total_input_tokens": int(round(total_input)),
        "cached_input_tokens": int(round(cached_input)),
        "total_output_tokens": int(round(total_output)),
        "monthly_input_m": monthly_input_m,
        "monthly_output_m": monthly_output_m,
        "daily_requests": daily_requests,
        "avg_input_tokens": avg_input_tokens,
        "avg_output_tokens": avg_output_tokens,
        "cache_hit_rate": cache_hit_rate,
        "output_includes_reasoning": output_includes_reasoning,
        "calls_estimated": calls_estimated,
    }


_CACHED_DEFAULT_MODELS: list[dict[str, Any]] | None = None


def _load_default_models_for_pricing() -> list[dict[str, Any]]:
    global _CACHED_DEFAULT_MODELS
    if _CACHED_DEFAULT_MODELS is not None:
        return _CACHED_DEFAULT_MODELS
    import json as _json
    from pathlib import Path as _Path

    here = _Path(__file__).resolve().parent
    for cand in (here.parent / "shared_data" / "models_live.json", here / "models_live.json"):
        if cand.is_file():
            try:
                data = _json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("models"), list) and data["models"]:
                    _CACHED_DEFAULT_MODELS = data["models"]
                    return _CACHED_DEFAULT_MODELS
            except (OSError, ValueError):
                continue

    _CACHED_DEFAULT_MODELS = [
        {
            "id": "anthropic/claude-opus-5.5",
            "api_model_id": "anthropic/claude-opus-5.5",
            "name": "Anthropic: Claude Opus 5.5",
            "provider": "OpenRouter",
            "region": "global",
            "input_rmb_per_1m": 28.80,
            "output_rmb_per_1m": 144.00,
            "cache_hit_factor": 0.50,
            "is_free": False,
            "value_score": 82.0,
        },
        {
            "id": "anthropic/claude-sonnet-5.5",
            "api_model_id": "anthropic/claude-sonnet-5.5",
            "name": "Anthropic: Claude Sonnet 5.5",
            "provider": "OpenRouter",
            "region": "global",
            "input_rmb_per_1m": 14.40,
            "output_rmb_per_1m": 72.00,
            "cache_hit_factor": 0.50,
            "is_free": False,
            "value_score": 88.0,
        },
        {
            "id": "tencent-cloud/deepseek-r1",
            "api_model_id": "deepseek-r1",
            "name": "腾讯云 · DeepSeek-R1",
            "provider": "腾讯云",
            "region": "cn_direct",
            "input_rmb_per_1m": 4.00,
            "output_rmb_per_1m": 16.00,
            "cache_hit_factor": 0.20,
            "is_free": False,
            "value_score": 93.0,
        },
        {
            "id": "tencent-cloud/deepseek-v3",
            "api_model_id": "deepseek-v3",
            "name": "腾讯云 · DeepSeek-V3",
            "provider": "腾讯云",
            "region": "cn_direct",
            "input_rmb_per_1m": 2.00,
            "output_rmb_per_1m": 8.00,
            "cache_hit_factor": 0.20,
            "is_free": False,
            "value_score": 94.0,
        },
    ]
    return _CACHED_DEFAULT_MODELS


def sanitize_usage_file_label(raw_name: Any, fallback_idx: int = 1) -> str:
    """
    Sanitize an uploaded/scanned file path so OS usernames and host home prefixes never leak:
      - `.../.claude/projects/<project>/<session>.jsonl` -> `<project>/<session>.jsonl`
      - Any other absolute/home/drive path (`/Users/alice/...`, `C:\\Users\\alice\\...`) -> `<basename>`
      - Relative 1-2 segment labels (`alpha/sess1.jsonl`) -> preserved safely
    """
    import re as _re

    raw = str(raw_name or "").strip()
    raw = _re.sub(r"[\x00-\x1f\x7f]+", "", raw)
    if not raw:
        return f"file_{fallback_idx}"

    norm = raw.replace("\\", "/")
    is_abs_or_home = bool(
        norm.startswith(("/", "~"))
        or _re.match(r"^[A-Za-z]:(?:/|$)", norm)
    )
    parts = [
        p.strip()
        for p in norm.split("/")
        if p.strip() and p.strip() not in (".", "..") and not _re.match(r"^[A-Za-z]:$", p.strip())
    ]
    if not parts:
        return f"file_{fallback_idx}"

    for idx in range(len(parts) - 1):
        if parts[idx].lower() == ".claude" and parts[idx + 1].lower() == "projects" and (idx + 2) < len(parts):
            tail = parts[idx + 2 :]
            label = "/".join(tail[-2:]) if len(tail) >= 2 else tail[-1]
            return label[:80] or f"file_{fallback_idx}"

    host_roots = {"users", "home", "var", "tmp", "private", "mnt", "opt", "etc", "root", "downloads", "documents", "desktop"}
    if is_abs_or_home or any(seg.lower() in host_roots for seg in parts[:-1]):
        return parts[-1][:80] or f"file_{fallback_idx}"

    label = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    return label[:80] or f"file_{fallback_idx}"


def _build_file_breakdown(
    all_entries: list[dict[str, Any]],
    *,
    file_labels: list[str],
    days: float,
    models: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    catalog_models = models if (isinstance(models, list) and models) else _load_default_models_for_pricing()
    scale_30d = 30.0 / days

    per_file: dict[int, dict[str, Any]] = {
        idx: {
            "file_name": label,
            "requests": 0.0,
            "input_tokens": 0.0,
            "cached_input_tokens": 0.0,
            "output_tokens": 0.0,
            "reported_cost_rmb": 0.0,
            "by_model": {},
        }
        for idx, label in enumerate(file_labels)
    }

    for ent in all_entries:
        raw_idx = ent.get("source_file_idx")
        f_idx = int(raw_idx) if isinstance(raw_idx, int) and raw_idx in per_file else 0
        fg = per_file[f_idx]
        fg["requests"] += float(ent["requests"])
        fg["input_tokens"] += float(ent["input_tokens"])
        fg["cached_input_tokens"] += float(ent["cached_input_tokens"])
        fg["output_tokens"] += float(ent["output_tokens"])
        fg["reported_cost_rmb"] += float(ent.get("reported_cost_rmb") or 0.0)
        mk = str(ent["model"]).lower()
        if mk not in fg["by_model"]:
            fg["by_model"][mk] = {
                "model": str(ent["model"]),
                "input_tokens": 0.0,
                "cached_input_tokens": 0.0,
                "output_tokens": 0.0,
                "reported_cost_rmb": 0.0,
            }
        sbm = fg["by_model"][mk]
        sbm["input_tokens"] += float(ent["input_tokens"])
        sbm["cached_input_tokens"] += float(ent["cached_input_tokens"])
        sbm["output_tokens"] += float(ent["output_tokens"])
        sbm["reported_cost_rmb"] += float(ent.get("reported_cost_rmb") or 0.0)

    breakdown: list[dict[str, Any]] = []
    for fg in per_file.values():
        f_in = fg["input_tokens"]
        f_cached = min(f_in, max(0.0, fg["cached_input_tokens"]))
        f_out = fg["output_tokens"]
        f_hit = round(f_cached / f_in, 4) if f_in > 0 else 0.0

        est_monthly_rmb = 0.0
        top_model = "-"
        top_weight = (-1.0, -1.0)
        for sub in fg["by_model"].values():
            sub_in = sub["input_tokens"]
            sub_cached = min(sub_in, max(0.0, sub["cached_input_tokens"]))
            sub_hit = (sub_cached / sub_in) if sub_in > 0 else 0.0
            if sub["reported_cost_rmb"] > 0:
                sub_m_rmb = sub["reported_cost_rmb"] * scale_30d
            else:
                matched, _ = resolve_model_query(catalog_models, sub["model"])
                if matched is not None:
                    m_hit = float(
                        matched.get("cache_hit_factor")
                        if matched.get("cache_hit_factor") is not None
                        else (0.2 if matched.get("region") == "cn_direct" else 0.5)
                    )
                    sub_m_rmb = calculate_token_bill(
                        monthly_input_m=(sub_in * scale_30d) / 1_000_000.0,
                        monthly_output_m=(sub["output_tokens"] * scale_30d) / 1_000_000.0,
                        input_price_per_1m=float(matched["input_rmb_per_1m"]),
                        output_price_per_1m=float(matched["output_rmb_per_1m"]),
                        cache_hit_rate=sub_hit,
                        cache_hit_factor=m_hit,
                        reasoning_multiplier=1.0,
                        output_includes_reasoning=True,
                    )["total_cost"]
                else:
                    sub_m_rmb = 0.0
            est_monthly_rmb += sub_m_rmb
            w = (sub_m_rmb, sub_in + sub["output_tokens"])
            if w > top_weight:
                top_weight = w
                top_model = sub["model"]

        breakdown.append(
            {
                "file_name": fg["file_name"],
                "requests": int(round(fg["requests"])),
                "input_tokens": int(round(f_in)),
                "cached_input_tokens": int(round(f_cached)),
                "output_tokens": int(round(f_out)),
                "cache_hit_rate": f_hit,
                "top_model": top_model,
                "reported_cost_rmb": round(fg["reported_cost_rmb"], 4),
                "estimated_monthly_rmb": round(est_monthly_rmb, 2),
            }
        )

    breakdown.sort(
        key=lambda x: (x["estimated_monthly_rmb"], x["input_tokens"] + x["output_tokens"]),
        reverse=True,
    )
    return breakdown


def merge_usage_log_snippets(
    snippets: list[str],
    *,
    days_observed: float = 30.0,
    default_tokens_per_call: int = 4000,
    fx_rate: float = DEFAULT_FX_USD_TO_RMB,
    file_names: list[str] | None = None,
    models: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Merge 1..50 local session transcripts or billing files (Claude Code `~/.claude/projects/*.jsonl`,
    OpenAI Batch `.jsonl`, OpenRouter/Cloud `.csv`/`.tsv` bills, or `/cost` summaries) into a single
    unified `csv_multimodel_bill` portfolio with cross-file `message.id`/`request_id` deduplication
    and per-file `file_breakdown` cost ranking.
    """
    if not isinstance(snippets, list):
        raise ValueError("usage_snippets must be a list of strings")

    raw_names = list(file_names) if isinstance(file_names, list) else []
    cleaned_items: list[tuple[str, str]] = []
    seen_labels: dict[str, int] = {}
    for raw_idx, raw_s in enumerate(snippets):
        s_trim = str(raw_s or "").strip()
        if not s_trim:
            continue
        raw_lbl = raw_names[raw_idx] if raw_idx < len(raw_names) else None
        base_lbl = sanitize_usage_file_label(raw_lbl, len(cleaned_items) + 1)
        if base_lbl in seen_labels:
            seen_labels[base_lbl] += 1
            uniq_lbl = f"{base_lbl} (#{seen_labels[base_lbl]})"
        else:
            seen_labels[base_lbl] = 1
            uniq_lbl = base_lbl
        cleaned_items.append((s_trim, uniq_lbl))

    if not cleaned_items or len(cleaned_items) > 50:
        raise ValueError("usage_snippets must contain between 1 and 50 non-empty items")

    days = float(days_observed if days_observed is not None else 30.0)
    if not math.isfinite(days) or days <= 0 or days > 365:
        raise ValueError("Invalid days_observed (must be between 0.1 and 365)")

    total_chars = sum(len(s) for s, _ in cleaned_items)
    if total_chars > 1_000_000 or any(len(s) > 250_000 for s, _ in cleaned_items):
        raise ValueError("Oversized usage_snippets payload")

    if len(cleaned_items) == 1:
        single = parse_usage_log_snippet(
            cleaned_items[0][0],
            days_observed=days,
            default_tokens_per_call=default_tokens_per_call,
        )
        return {**single, "merged_files_count": 1}

    combined_json_records: list[dict[str, Any]] = []
    other_entries: list[dict[str, Any]] = []

    for clean_idx, (snippet, _file_lbl) in enumerate(cleaned_items):
        extracted = _extract_json_records_raw(snippet)
        if extracted is not None:
            recs, _fmt = extracted
            for rec in recs:
                combined_json_records.append({**rec, "_src_file_idx": clean_idx})
            continue

        try:
            csv_parsed = _try_parse_csv_bill(snippet, days, fx_rate=fx_rate)
        except ValueError:
            csv_parsed = None
        if csv_parsed is not None:
            for row in csv_parsed.get("model_breakdown", []):
                other_entries.append(
                    {
                        "model": row["model"],
                        "requests": float(row["requests"]),
                        "input_tokens": float(row["input_tokens"]),
                        "cached_input_tokens": float(row["cached_input_tokens"]),
                        "output_tokens": float(row["output_tokens"]),
                        "reasoning_tokens": float(row.get("reasoning_tokens") or 0),
                        "reported_cost_rmb": float(row.get("reported_cost_rmb") or 0.0),
                        "source_file_idx": clean_idx,
                    }
                )
            continue

        try:
            single_parsed = parse_usage_log_snippet(
                snippet,
                days_observed=days,
                default_tokens_per_call=default_tokens_per_call,
            )
        except ValueError:
            continue

        if single_parsed.get("detected_format") == "csv_multimodel_bill":
            for row in single_parsed.get("model_breakdown", []):
                other_entries.append(
                    {
                        "model": row["model"],
                        "requests": float(row["requests"]),
                        "input_tokens": float(row["input_tokens"]),
                        "cached_input_tokens": float(row["cached_input_tokens"]),
                        "output_tokens": float(row["output_tokens"]),
                        "reasoning_tokens": float(row.get("reasoning_tokens") or 0),
                        "reported_cost_rmb": float(row.get("reported_cost_rmb") or 0.0),
                        "source_file_idx": clean_idx,
                    }
                )
        else:
            est_reqs = max(1.0, round(float(single_parsed.get("daily_requests") or 1) * days))
            other_entries.append(
                {
                    "model": "claude-sonnet-4" if single_parsed.get("detected_format") in ("claude_code_cost", "anthropic_usage_json") else "deepseek-v3",
                    "requests": est_reqs,
                    "input_tokens": float(single_parsed.get("total_input_tokens") or 0),
                    "cached_input_tokens": float(single_parsed.get("cached_input_tokens") or 0),
                    "output_tokens": float(single_parsed.get("total_output_tokens") or 0),
                    "reasoning_tokens": 1.0 if single_parsed.get("output_includes_reasoning") else 0.0,
                    "reported_cost_rmb": 0.0,
                    "source_file_idx": clean_idx,
                }
            )

    json_entries, dedup_cnt = (
        _collect_json_record_entries(combined_json_records, fx_rate=fx_rate)
        if combined_json_records
        else ([], 0)
    )
    all_entries = json_entries + other_entries
    if not all_entries:
        raise ValueError("Merged usage_snippets contain zero positive token records")

    portfolio = _build_multimodel_portfolio_from_entries(
        all_entries,
        days=days,
        source_format="multifile_merged",
        deduplicated_chunks=dedup_cnt,
        merged_files_count=len(cleaned_items),
    )
    portfolio["file_breakdown"] = _build_file_breakdown(
        all_entries,
        file_labels=[lbl for _, lbl in cleaned_items],
        days=days,
        models=models,
    )
    return portfolio
