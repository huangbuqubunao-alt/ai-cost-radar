#!/usr/bin/env python3
"""
Engine B — Bilingual Interactive AI API & Cloud Cost Calculator + Affiliate Monetization Site Builder
Python 3.14 standard library ONLY · Zero third-party pip/npm dependencies.

Inputs:
  1. ../config.json                  (Domestic RMB & Global USD affiliate links)
  2. ../shared_data/models_live.json (Live pricing feed from Engine A; falls back to rich 15-model built-in dataset)

Outputs (ready for 1-click free static hosting on Cloudflare Pages / Vercel / GitHub Pages / Aliyun / Tencent):
  - dist/index.html
  - dist/sitemap.xml
  - dist/robots.txt
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import sys
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ENGINE_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
LIVE_MODELS_PATH = PROJECT_ROOT / "shared_data" / "models_live.json"
DIST_DIR = ENGINE_DIR / "dist"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from ui_template import render_html_template  # noqa: E402

DEFAULT_FX_USD_TO_RMB = 7.25
DEFAULT_SITE_URL = "https://huangbuqubunao-alt.github.io/ai-cost-radar/"

DEFAULT_AFFILIATES: dict[str, str] = {
    # Domestic RMB channels (clean official URLs when unconfigured)
    "aliyun_ambassador_url": "https://www.aliyun.com/minisite/goods",
    "aliyun_bailian_url": "https://bailian.console.aliyun.com/",
    "tencent_cps_url": "https://cloud.tencent.com/product/lkeap",
    "siliconflow_invite_url": "https://cloud.siliconflow.cn/",
    "volcengine_ark_url": "https://console.volcengine.com/ark",
    # Global USD channels (clean official URLs when unconfigured)
    "runpod_affiliate_url": "https://www.runpod.io",
    "digitalocean_affiliate_url": "https://www.digitalocean.com",
    "railway_affiliate_url": "https://railway.com",
    "openrouter_url": "https://openrouter.ai",
}

# Rich 15-model built-in fallback dataset (9 Global + 6 Domestic CN Direct)
FALLBACK_MODELS: list[dict[str, Any]] = [
    {
        "id": "anthropic/claude-opus-4",
        "name": "Anthropic: Claude Opus 4 (顶配推理旗舰)",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 15.0,
        "output_usd_per_1m": 75.0,
        "context_length": 200000,
        "supports_tools": True,
        "is_free": False,
        "value_score": 84.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "anthropic/claude-sonnet-4",
        "name": "Anthropic: Claude Sonnet 4 (SWE编程标杆)",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 3.0,
        "output_usd_per_1m": 15.0,
        "context_length": 200000,
        "supports_tools": True,
        "is_free": False,
        "value_score": 92.5,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "openai/gpt-4.1",
        "name": "OpenAI: GPT-4.1 (1M超长上下文旗舰)",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 2.0,
        "output_usd_per_1m": 8.0,
        "context_length": 1048576,
        "supports_tools": True,
        "is_free": False,
        "value_score": 91.0,
        "tags": ["coding", "global"],
    },
    {
        "id": "openai/o3",
        "name": "OpenAI: o3 (深度数学与架构推理)",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 2.0,
        "output_usd_per_1m": 8.0,
        "context_length": 200000,
        "supports_tools": True,
        "is_free": False,
        "value_score": 93.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "google/gemini-2.5-pro",
        "name": "Google: Gemini 2.5 Pro (多模态推理王)",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 1.25,
        "output_usd_per_1m": 10.0,
        "context_length": 1048576,
        "supports_tools": True,
        "is_free": False,
        "value_score": 94.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "google/gemini-2.5-flash",
        "name": "Google: Gemini 2.5 Flash (高频Agent极速版)",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 0.15,
        "output_usd_per_1m": 0.60,
        "context_length": 1048576,
        "supports_tools": True,
        "is_free": False,
        "value_score": 97.5,
        "tags": ["coding", "cheap", "global"],
    },
    {
        "id": "openai/gpt-4.1-mini",
        "name": "OpenAI: GPT-4.1 mini (轻量主力模型)",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 0.40,
        "output_usd_per_1m": 1.60,
        "context_length": 1048576,
        "supports_tools": True,
        "is_free": False,
        "value_score": 95.0,
        "tags": ["coding", "cheap", "global"],
    },
    {
        "id": "meta-llama/llama-4-maverick",
        "name": "Meta: Llama 4 Maverick 17B-128E",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 0.18,
        "output_usd_per_1m": 0.60,
        "context_length": 1048576,
        "supports_tools": True,
        "is_free": False,
        "value_score": 96.2,
        "tags": ["coding", "cheap", "global"],
    },
    {
        "id": "deepseek/deepseek-r1:free",
        "name": "DeepSeek: DeepSeek-R1 (OpenRouter 免费路由池)",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 0.0,
        "output_usd_per_1m": 0.0,
        "context_length": 128000,
        "supports_tools": False,
        "is_free": True,
        "value_score": 98.0,
        "tags": ["coding", "reasoning", "free", "global"],
    },
    {
        "id": "aliyun-bailian/qwen3-235b-a22b",
        "name": "阿里云百炼: Qwen3-235B-A22B (旗舰混合推理)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 2.0,
        "output_rmb_per_1m": 8.0,
        "context_length": 131072,
        "supports_tools": True,
        "is_free": False,
        "value_score": 97.2,
        "tags": ["coding", "reasoning", "cheap", "cn_direct"],
    },
    {
        "id": "aliyun-bailian/qwen3-coder-plus",
        "name": "阿里云百炼: Qwen-Coder-Plus (代码Agent专精)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 1.5,
        "output_rmb_per_1m": 6.0,
        "context_length": 131072,
        "supports_tools": True,
        "is_free": False,
        "value_score": 97.8,
        "tags": ["coding", "reasoning", "cheap", "cn_direct"],
    },
    {
        "id": "siliconflow/deepseek-ai/DeepSeek-V3",
        "name": "硅基流动 SiliconFlow: DeepSeek-V3 高速专线",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 2.0,
        "output_rmb_per_1m": 8.0,
        "context_length": 65536,
        "supports_tools": True,
        "is_free": False,
        "value_score": 96.8,
        "tags": ["coding", "cheap", "cn_direct"],
    },
    {
        "id": "siliconflow/Qwen/Qwen2.5-7B-Instruct",
        "name": "硅基流动 SiliconFlow: Qwen2.5-7B-Instruct (永久免费API)",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 0.0,
        "output_rmb_per_1m": 0.0,
        "context_length": 32768,
        "supports_tools": True,
        "is_free": True,
        "value_score": 98.5,
        "tags": ["coding", "cheap", "free", "cn_direct"],
    },
    {
        "id": "tencent-cloud/deepseek-r1",
        "name": "腾讯云: DeepSeek-R1 满血专线版 (送体验额度)",
        "provider": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 4.0,
        "output_rmb_per_1m": 16.0,
        "context_length": 65536,
        "supports_tools": True,
        "is_free": False,
        "value_score": 95.6,
        "tags": ["coding", "reasoning", "cn_direct"],
    },
    {
        "id": "volcengine/doubao-1.5-pro-32k",
        "name": "火山引擎方舟: 豆包 Doubao-1.5-Pro 32K (超低价)",
        "provider": "火山引擎 (Volcengine Ark)",
        "provider_config_key": "volcengine_ark_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 0.8,
        "output_rmb_per_1m": 2.0,
        "context_length": 32768,
        "supports_tools": True,
        "is_free": False,
        "value_score": 98.2,
        "tags": ["coding", "cheap", "free", "cn_direct"],
    },
]

FAQ_ENTRIES: list[dict[str, str]] = [
    {
        "q": "大模型 API 每月真实账单是怎么计算的？（输入 Token vs 输出 Token）",
        "a": "主流大模型均按百万 Token（1M Tokens）分别对输入（Prompt）与输出（Completion）计费。标准月账单公式为：月费用 = 30天 × 日请求量 × [(单次输入Token × 输入单价 + 单次输出Token × 输出单价) ÷ 1,000,000]。由于输出 Token 单价通常是输入的 3～5 倍，控制输出冗余并开启 Prompt Cache（上下文缓存）往往能直接降低 35%～60% 账单。",
    },
    {
        "q": "国内开发者与企业如何免海外信用卡、低延迟合规直连顶级大模型？",
        "a": "推荐优先接入国内四大合规云厂商通道：阿里云百炼（通义千问 Qwen3 全系 + DeepSeek）、硅基流动 SiliconFlow（高速开源推理 + 永久免费小模型池）、腾讯云知识引擎（满血 DeepSeek-R1/V3 + 混元 Lite 免费版）以及字节火山方舟（豆包 Doubao-Pro 高并发专线）。均支持微信/支付宝人民币结算、国内低延迟直连及企业增值税发票，且新客注册即可领取百万级免费 Token。",
    },
    {
        "q": "什么是「80/20 智能混合模型路由」，为什么能省下 75% 以上预算？",
        "a": "在实际生产业务（如 AI 客服、RAG 知识库、Coding Agent）中，约 80% 的请求属于意图分类、摘要提取、常规代码补全等轻量任务，仅 20% 属于复杂架构设计或多步逻辑推理。通过 OpenRouter 或自建 LiteLLM 网关将 80% 流量分发给 Qwen-Coder-Plus / DeepSeek-V3 / Gemini Flash，20% 流量保留给旗舰模型，可在几乎不损失业务效果的前提下削减 75%～90% 成本。",
    },
    {
        "q": "每月 API 消耗超过多少美元（$100/月临界点）时，应该改用 GPU 云服务器私有化自建？",
        "a": "当团队每月 API 账单稳定超过 $100～$300（约 ¥725～¥2,200/月）且调用集中在开源权重模型（如 DeepSeek、Qwen3、Llama 4）时，按量付费的边际成本开始高于包月/按秒算力。此时海外团队可在 RunPod 按秒租用 RTX 4090 / A100 运行 vLLM 或 SGLang，国内团队可通过阿里云 GPU/ECS 云大使补贴或腾讯云轻量/HAI 服务器私有化部署，实现固定成本不限 Token 调用。",
    },
    {
        "q": "如何领取阿里云百炼、硅基流动、腾讯云与 DigitalOcean / RunPod 的官方算力补贴？",
        "a": "在本工具站算出最适合您业务流量的目标模型后，直接点击对应模型卡片或补贴矩阵中的官方活动按钮（如「领阿里云百炼免费Token/算力券」、「硅基流动注册送Token」、「腾讯云DeepSeek/轻量云特惠」或「DigitalOcean $200 赠金」），即可直达各平台官方控制台自动激活新客免费额度或折扣券，无任何中间差价。",
    },
]


def safe_json_for_html_script(obj: Any) -> str:
    """Serialize JSON safely for embedding inside <script> tags (prevents </script> breakouts)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _sanitize_affiliate_url(key: str, raw_val: Any) -> str:
    fallback = DEFAULT_AFFILIATES.get(key, "https://openrouter.ai")
    s = str(raw_val or "").strip()
    if not s or "YOUR_" in s.upper() or not s.startswith(("http://", "https://")):
        return fallback
    return s


def load_affiliates(config_path: Path) -> dict[str, str]:
    affiliates = dict(DEFAULT_AFFILIATES)
    if not config_path.exists():
        return affiliates

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return affiliates

    for section_key in ("domestic_affiliates_rmb", "global_affiliates_usd"):
        sub = raw.get(section_key)
        if isinstance(sub, dict):
            for k, v in sub.items():
                if k in affiliates and isinstance(v, str) and v.strip():
                    affiliates[k] = _sanitize_affiliate_url(k, v)

    # Also support flat top-level overrides if present
    for k in list(affiliates.keys()):
        val = raw.get(k)
        if isinstance(val, str) and val.strip():
            affiliates[k] = _sanitize_affiliate_url(k, val)

    return affiliates


def infer_config_key(raw_model: dict[str, Any], region: str) -> str:
    explicit = str(raw_model.get("provider_config_key") or raw_model.get("affiliate_key") or "").strip()
    if explicit in DEFAULT_AFFILIATES:
        return explicit

    hay = f"{raw_model.get('id', '')} {raw_model.get('provider', '')} {raw_model.get('affiliate_url', '')}".lower()
    if "bailian" in hay or "aliyun" in hay or "百炼" in hay or "阿里云" in hay:
        return "aliyun_bailian_url"
    if "siliconflow" in hay or "硅基" in hay:
        return "siliconflow_invite_url"
    if "tencent" in hay or "qcloud" in hay or "hunyuan" in hay or "腾讯" in hay or "混元" in hay:
        return "tencent_cps_url"
    if "volcengine" in hay or "doubao" in hay or "火山" in hay or "豆包" in hay:
        return "volcengine_ark_url"
    if region == "cn_direct":
        return "aliyun_bailian_url"
    return "openrouter_url"


def detect_open_weights(model_id: str, name: str) -> bool:
    hay = f"{model_id} {name}".lower()
    open_keywords = (
        "deepseek",
        "qwen",
        "llama",
        "mistral",
        "mixtral",
        "gemma",
        "nemotron",
        "glm",
        "yi-",
        "phi-",
        "flint",
        "lfm",
        "hunyuan-lite",
    )
    return any(k in hay for k in open_keywords)


def channel_bonus_notes(config_key: str, is_free: bool) -> tuple[str, str]:
    if is_free:
        return ("🆓 永久 ¥0 免费调用", "🆓 $0 Free API Tier")
    mapping = {
        "aliyun_bailian_url": ("🎁 新客送百万免费Token", "🎁 1M+ Free Signup Tokens"),
        "siliconflow_invite_url": ("🎁 注册即送免费Token", "🎁 Free Token Signup Bonus"),
        "tencent_cps_url": ("🎁 腾讯云新客特惠包", "🎁 Tencent Cloud Promo"),
        "volcengine_ark_url": ("🎁 送50万免费体验Token", "🎁 500K Free Trial Tokens"),
        "openrouter_url": ("🌐 统一API免绑多卡", "🌐 Unified Multi-LLM API"),
    }
    return mapping.get(config_key, ("", ""))


def normalize_model(raw: dict[str, Any], affiliates: dict[str, str], fx_rate: float) -> dict[str, Any]:
    model_id = str(raw.get("id") or raw.get("model_id") or "unknown/model").strip()
    name = str(raw.get("name") or raw.get("display_name") or model_id).strip()
    provider = str(raw.get("provider") or "API Gateway").strip()

    raw_region = str(raw.get("region") or "").lower().strip()
    raw_tags = [str(t).lower().strip() for t in (raw.get("tags") or []) if str(t).strip()]
    if raw_region in ("cn", "cn_direct", "domestic", "china") or "cn_direct" in raw_tags:
        region = "cn_direct"
    else:
        region = "global"

    # Extract pricing (handle USD and/or RMB inputs gracefully)
    in_usd = raw.get("input_usd_per_1m")
    out_usd = raw.get("output_usd_per_1m")
    in_rmb = raw.get("input_rmb_per_1m")
    out_rmb = raw.get("output_rmb_per_1m")

    if in_usd is None and isinstance(raw.get("pricing"), dict):
        p = raw["pricing"]
        if "prompt" in p:
            val = float(p.get("prompt") or 0.0)
            in_usd = val * 1_000_000 if 0 < val < 0.005 else val
        if "completion" in p:
            val = float(p.get("completion") or 0.0)
            out_usd = val * 1_000_000 if 0 < val < 0.005 else val

    if in_usd is None and in_rmb is not None:
        in_usd = float(in_rmb) / fx_rate
    if out_usd is None and out_rmb is not None:
        out_usd = float(out_rmb) / fx_rate

    in_usd_f = round(max(0.0, float(in_usd or 0.0)), 4)
    out_usd_f = round(max(0.0, float(out_usd or 0.0)), 4)

    in_rmb_f = round(max(0.0, float(in_rmb if in_rmb is not None else in_usd_f * fx_rate)), 4)
    out_rmb_f = round(max(0.0, float(out_rmb if out_rmb is not None else out_usd_f * fx_rate)), 4)

    blended_usd = round(0.75 * in_usd_f + 0.25 * out_usd_f, 4)
    blended_rmb = round(0.75 * in_rmb_f + 0.25 * out_rmb_f, 4)

    is_free = bool(raw.get("is_free")) or (in_usd_f == 0.0 and out_usd_f == 0.0) or ("free" in raw_tags)
    is_batch = ":batch" in model_id.lower() or "(batch)" in name.lower()

    # Enrich tags for clean filter pills: coding, reasoning, cn_direct, free
    tags_set = set(raw_tags)
    hay = f"{model_id} {name}".lower()
    if region == "cn_direct":
        tags_set.add("cn_direct")
    if is_free:
        tags_set.add("free")
    if any(k in hay for k in ("coder", "codex", "claude", "gpt-4", "gpt-5", "gpt-6", "deepseek", "qwen", "gemini", "llama-4")):
        if not any(audio_k in hay for audio_k in ("lyria", "whisper", "tts")):
            tags_set.add("coding")
    if any(k in hay for k in ("r1", "o1", "o3", "o4", "thinking", "reason", "opus", "sonnet", "qwen3-235b", "gemini-2.5-pro")):
        tags_set.add("reasoning")

    config_key = infer_config_key(raw, region)
    affiliate_url = affiliates.get(config_key, DEFAULT_AFFILIATES["openrouter_url"])
    bonus_zh, bonus_en = channel_bonus_notes(config_key, is_free)

    default_base_map = {
        "aliyun_bailian_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "tencent_cps_url": "https://api.lkeap.cloud.tencent.com/v1",
        "siliconflow_invite_url": "https://api.siliconflow.cn/v1",
        "volcengine_ark_url": "https://ark.cn-beijing.volces.com/api/v3",
        "openrouter_url": "https://openrouter.ai/api/v1",
    }
    api_base_url = str(raw.get("api_base_url") or default_base_map.get(config_key, "https://openrouter.ai/api/v1"))
    api_model_id = str(raw.get("api_model_id") or (model_id.split("/", 1)[-1] if region == "cn_direct" and not model_id.startswith("siliconflow/") else model_id.removeprefix("siliconflow/")))
    cache_hit_factor = float(raw.get("cache_hit_factor", 0.2 if region == "cn_direct" and not is_free else (0.5 if not is_free else 1.0)))
    perf_note = str(raw.get("perf_note") or "")

    return {
        "id": model_id,
        "name": name,
        "provider": provider,
        "provider_config_key": config_key,
        "api_base_url": api_base_url,
        "api_model_id": api_model_id,
        "cache_hit_factor": cache_hit_factor,
        "perf_note": perf_note,
        "affiliate_url": affiliate_url,
        "region": region,
        "input_usd_per_1m": in_usd_f,
        "output_usd_per_1m": out_usd_f,
        "input_rmb_per_1m": in_rmb_f,
        "output_rmb_per_1m": out_rmb_f,
        "blended_usd_per_1m": blended_usd,
        "blended_rmb_per_1m": blended_rmb,
        "context_length": int(raw.get("context_length") or raw.get("context_window") or 128000),
        "supports_tools": bool(raw.get("supports_tools", True)),
        "is_free": is_free,
        "has_free_quota": is_free or ("free" in tags_set),
        "is_batch": is_batch,
        "open_weights": detect_open_weights(model_id, name),
        "value_score": float(raw.get("value_score") or 88.0),
        "tags": sorted(tags_set),
        "bonus_note": bonus_zh,
        "bonus_note_en": bonus_en,
    }


def load_models_dataset(
    live_path: Path,
    affiliates: dict[str, str],
    force_fallback: bool = False,
) -> tuple[list[dict[str, Any]], float, str, str]:
    """
    Returns (normalized_models, fx_rate, updated_date_str, source_label).
    """
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not force_fallback and live_path.exists():
        try:
            payload = json.loads(live_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                raw_list = payload
                fx_rate = DEFAULT_FX_USD_TO_RMB
                updated_raw = now_date
                source_label = "models_live.json"
            elif isinstance(payload, dict):
                raw_list = (
                    payload.get("models")
                    or payload.get("data")
                    or (payload.get("domestic_models", []) + payload.get("global_models", []))
                )
                fx_rate = float(payload.get("fx_rate_usd_to_rmb") or payload.get("usd_to_rmb") or DEFAULT_FX_USD_TO_RMB)
                updated_raw = str(payload.get("updated_at") or now_date)[:10]
                source_label = str(payload.get("source") or "models_live.json")
            else:
                raw_list = []
                fx_rate = DEFAULT_FX_USD_TO_RMB
                updated_raw = now_date
                source_label = "fallback"

            if raw_list:
                normalized = [normalize_model(m, affiliates, fx_rate) for m in raw_list if isinstance(m, dict)]
                # Ensure domestic CN channels are always present even if an external feed only had global models
                has_cn = any(m["region"] == "cn_direct" for m in normalized)
                if not has_cn:
                    cn_fallbacks = [
                        normalize_model(m, affiliates, fx_rate)
                        for m in FALLBACK_MODELS
                        if m.get("region") == "cn_direct"
                    ]
                    normalized.extend(cn_fallbacks)
                if normalized:
                    return normalized, fx_rate, updated_raw, source_label
        except Exception as exc:
            print(f"⚠️ 读取 {live_path} 出错 ({exc})，自动启用内置 15 款旗舰模型保底数据集。")

    fallback_normalized = [normalize_model(m, affiliates, DEFAULT_FX_USD_TO_RMB) for m in FALLBACK_MODELS]
    return fallback_normalized, DEFAULT_FX_USD_TO_RMB, now_date, "builtin_15_fallback"


DEFAULT_CODING_PLANS: list[dict[str, Any]] = [
    {
        "id": "aliyun-coding-plan",
        "name": "阿里云百炼 Coding Plan 包月套餐",
        "vendor": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "monthly_rmb": 39.0,
        "pro_monthly_rmb": 99.0,
        "models_covered": ["qwen3-coder-next", "qwen3.5-plus", "deepseek-v3.2", "qwen3-235b"],
        "speed_highlight": "峰值 147 TPS 全场最快输出",
        "best_for": "Claude Code / Cline / 通义灵码高频重构，企业合规可开增值税专票",
        "featured_partner": True,
        "cta_zh": "特惠开通百炼 Coding Plan / 领算力券",
        "cta_en": "Get Aliyun Bailian Coding Plan",
    },
    {
        "id": "tencent-coding-plan",
        "name": "腾讯云 LKEAP Coding Plan 编程套餐",
        "vendor": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "monthly_rmb": 29.0,
        "pro_monthly_rmb": 89.0,
        "models_covered": ["hunyuan-t1", "hunyuan-2.0-thinking", "deepseek-v3.2", "deepseek-r1"],
        "speed_highlight": "首字 1.05s 极速响应 · 专线稳定",
        "best_for": "微信生态/小程序/云原生全栈开发，可搭配轻量云一键部署 OpenClaw/Dify",
        "featured_partner": True,
        "cta_zh": "抢腾讯云 Coding Plan & 轻量云特惠",
        "cta_en": "Claim Tencent Coding Plan & Cloud Deal",
    },
    {
        "id": "aliyun-ecs-agent-host",
        "name": "阿里云 2核4G / GPU 专属部署包 (OpenClaw / Dify)",
        "vendor": "阿里云云小站特惠",
        "provider_config_key": "aliyun_ambassador_url",
        "monthly_rmb": 19.0,
        "pro_monthly_rmb": 199.0,
        "models_covered": ["私有化 LiteLLM 缓存网关", "Dify 企业工作流", "OpenClaw 24h Agent"],
        "speed_highlight": "语义缓存直降 30%~60% 重复 API 请求",
        "best_for": "需要 24 小时挂机跑自动化 Agent、自建语义缓存网关或团队共享中转台",
        "featured_partner": True,
        "cta_zh": "领阿里云服务器新客隐藏补贴券",
        "cta_en": "Claim Aliyun Cloud Server Subsidy",
    },
    {
        "id": "volcengine-coding-plan",
        "name": "火山方舟 Coding Plan 畅享包",
        "vendor": "字节跳动 · 火山引擎",
        "provider_config_key": "volcengine_ark_url",
        "monthly_rmb": 39.0,
        "pro_monthly_rmb": 99.0,
        "models_covered": ["doubao-seed-2.0-pro", "deepseek-v3.2", "kimi-k2.5"],
        "speed_highlight": "Trae 同源底座 · 百万 TPM 大并发",
        "best_for": "Trae / Cursor 多文件并发 Agent 任务，新客另赠 50 万体验 Token",
        "featured_partner": False,
        "cta_zh": "开通火山方舟 Coding 套餐",
        "cta_en": "Explore Volcengine Coding Plan",
    },
    {
        "id": "siliconflow-coding-pack",
        "name": "硅基流动多模型极速按量池 (赠 ¥16 额度)",
        "vendor": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "monthly_rmb": 0.0,
        "pro_monthly_rmb": 50.0,
        "models_covered": ["Kimi-K2.5 (0.99s)", "GLM-5 (157 TPS)", "MiniMax-M2.5", "DeepSeek-R1"],
        "speed_highlight": "Kimi-K2.5 首字 0.99s 全网最快秒回",
        "best_for": "不想被固定包月绑定的灵活开发者，一个 API Key 随时切 Kimi / GLM-5 / MiniMax",
        "featured_partner": False,
        "cta_zh": "注册领免费 Token 测速体验",
        "cta_en": "Claim SiliconFlow Free Token Bonus",
    },
    {
        "id": "openrouter-global-coding",
        "name": "OpenRouter 海外顶配混合路由 (Claude + GPT-6)",
        "vendor": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "monthly_rmb": 72.0,
        "pro_monthly_rmb": 288.0,
        "models_covered": ["Claude Sonnet 5.5", "GPT-6.1", "Gemini 3.8 Flash", "DeepSeek V4.1"],
        "speed_highlight": "免绑多家外卡 · 自动 Fallback 防宕机",
        "best_for": "出海项目与疑难架构攻坚（20% 难题调 Claude/GPT，80% 常规调国产低价模型）",
        "featured_partner": False,
        "cta_zh": "接入 OpenRouter 全球网关",
        "cta_en": "Connect OpenRouter Unified API",
    },
]

SEO_ROUTES: list[dict[str, Any]] = [
    {
        "slug": "",
        "nav_label": "比价总览",
        "priority": "1.0",
        "title": "大模型 API 成本计算器 & Coding Plan 省钱比价台 (2026) | DeepSeek / 千问 / 豆包 / Claude 实时测算",
        "description": "免费在线测算海内外 80+ 款主流大模型 API 月账单与 2026 国内 Coding Plan 包月套餐临界点，支持一键复制 Claude Code / Cursor 接入配置，直通阿里云百炼、腾讯云、硅基流动官方补贴。",
        "hero_main": "一秒算清大模型 API 与 Coding Plan 月账单，",
        "hero_accent": "最高立省 95% 算力成本",
        "hero_sub": "同屏精算国内直连（阿里云百炼 / 腾讯云 / 硅基流动 / 火山方舟 ¥）与海外网关（OpenRouter $），内置 Prompt 缓存、思考 Token 倍率与一键复制 Claude Code / Cursor 接入参数。",
        "preset": {"region": "all", "filter": "all", "dailyCalls": 2500, "inputTokens": 2000, "outputTokens": 800, "cacheEnabled": False, "reasoningEnabled": False},
    },
    {
        "slug": "claude-code-domestic/",
        "nav_label": "Claude Code 国内平替",
        "priority": "0.9",
        "title": "2026 Claude Code / Cline / Cursor 国内平替 API 最省钱配置指南与账单计算器",
        "description": "解决 Claude Code 与 Cline 多轮调用账单破千痛点！实测对比阿里云百炼 Qwen3-Coder-Next、腾讯混元 T1、Kimi-K2.5、GLM-5 成本与速度，附一键复制环境变量配置与新客补贴券。",
        "hero_main": "Claude Code / Cline 国内平替专线测算，",
        "hero_accent": "告别按量破千账单",
        "hero_sub": "AI 编程单次指令平均触发 10~25 轮长上下文调用。下方已为您预设典型 Agent 编程负载（开启缓存命中折扣），支持一键复制 Base URL 贴入终端或 Cursor。",
        "preset": {"region": "cn", "filter": "coding", "dailyCalls": 3000, "inputTokens": 6000, "outputTokens": 1200, "cacheEnabled": True, "reasoningEnabled": False},
    },
    {
        "slug": "coding-plan-2026/",
        "nav_label": "Coding Plan 包月横评",
        "priority": "0.9",
        "title": "2026 国内大厂 Coding Plan 包月套餐横评：阿里云百炼 vs 腾讯云 vs 火山方舟谁最划算？",
        "description": "按量付费还是买 ¥29~¥99 Coding Plan 包月套餐？实时输入你的日代码请求量，一秒算出盈亏临界线，覆盖百炼 Qwen3-Coder-Next (147 TPS)、腾讯混元 T1、豆包 2.0 实测对比。",
        "hero_main": "2026 国内 Coding Plan 包月 vs 按量计费，",
        "hero_accent": "一秒算出回本临界线",
        "hero_sub": "重度使用 Claude Code / Cursor / Trae 时，开通阿里云百炼（¥39起）或腾讯云（¥29起）Coding Plan 往往比按量 API 省下 70% 以上预算。",
        "preset": {"region": "cn", "filter": "coding", "dailyCalls": 4500, "inputTokens": 5000, "outputTokens": 1000, "cacheEnabled": True, "reasoningEnabled": False},
    },
    {
        "slug": "deepseek-vs-qwen/",
        "nav_label": "DeepSeek vs 千问对比",
        "priority": "0.85",
        "title": "DeepSeek-V3.2 / R1 vs 通义千问 Qwen3-Coder / Qwen3.5 真实 API 价格与思考 Token 测算",
        "description": "深度对比满血 DeepSeek-R1/V3 与阿里云通义千问 Qwen3.5-Plus / Qwen3-235B 在开启深度推理（Reasoning 2.5x 输出开销）与缓存命中下的真实人民币月度成本。",
        "hero_main": "DeepSeek 满血版 vs 通义千问 Qwen3 全系，",
        "hero_accent": "含隐式思考 Token 真实比价",
        "hero_sub": "深度推理模型的隐式思维链（CoT）按输出高价计费！下方已默认开启「2.5x 思考 Token 负载」，帮您看清真实生产账单。",
        "preset": {"region": "cn", "filter": "reasoning", "dailyCalls": 4000, "inputTokens": 3000, "outputTokens": 1200, "cacheEnabled": True, "reasoningEnabled": True},
    },
    {
        "slug": "dify-openclaw-cloud-server/",
        "nav_label": "OpenClaw/Dify 云服务器部署",
        "priority": "0.85",
        "title": "2026 部署 OpenClaw / Dify / LiteLLM 语义缓存服务器选型与 GPU 自建回本计算器",
        "description": "月 API 消耗超 $100 (¥725) 怎么封顶成本？对比阿里云云小站 2核4G/GPU 补贴券与腾讯云轻量应用服务器 HAI 特惠，一键部署 LiteLLM 缓存网关或 vLLM 私有化模型。",
        "hero_main": "部署 OpenClaw / Dify / vLLM 算力精算，",
        "hero_accent": "用云服务器补贴封顶 API 账单",
        "hero_sub": "高并发 SaaS 与 24 小时挂机 Agent 场景下，租用特惠云服务器挂一层 LiteLLM 语义缓存或私有化跑开源模型，立砍 50%+ 重复 Token 开销。",
        "preset": {"region": "cn", "filter": "all", "dailyCalls": 18000, "inputTokens": 2500, "outputTokens": 800, "cacheEnabled": False, "reasoningEnabled": False},
    },
]


def load_coding_plans(live_path: Path, affiliates: dict[str, str], fx_rate: float, force_fallback: bool = False) -> list[dict[str, Any]]:
    raw_plans: list[dict[str, Any]] = []
    if not force_fallback and live_path.exists():
        try:
            payload = json.loads(live_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("coding_plans"), list):
                raw_plans = payload["coding_plans"]
        except Exception:
            raw_plans = []

    source_list = raw_plans if len(raw_plans) >= 4 else DEFAULT_CODING_PLANS
    enriched: list[dict[str, Any]] = []
    for item in source_list:
        cfg_key = str(item.get("provider_config_key") or "aliyun_bailian_url")
        url = affiliates.get(cfg_key, DEFAULT_AFFILIATES["aliyun_bailian_url"])
        m_rmb = float(item.get("monthly_rmb") or 0.0)
        p_rmb = float(item.get("pro_monthly_rmb") or m_rmb)
        enriched.append(
            {
                **item,
                "url": url,
                "monthly_rmb": m_rmb,
                "pro_monthly_rmb": p_rmb,
                "monthly_usd": round(m_rmb / fx_rate, 2),
                "pro_monthly_usd": round(p_rmb / fx_rate, 2),
            }
        )
    return enriched


def build_json_ld(site_url: str, updated_date: str, total_models: int, page_title: str, page_description: str) -> tuple[str, str]:
    webapp_ld = {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": page_title,
        "url": site_url,
        "dateModified": updated_date,
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "All",
        "inLanguage": ["zh-CN", "en"],
        "description": page_description,
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD",
        },
        "featureList": [
            "1-Click Domestic RMB (¥) vs Global USD ($) Region & Currency Switcher",
            "2026 Domestic Coding Plan Monthly Subscription vs Pay-As-You-Go Breakeven Calculator",
            "1-Click Claude Code, Cursor, Cline & Cherry Studio API Config Copy",
            "Reasoning Token Overhead & Provider-Specific Prompt Cache Simulator",
            "Automatic >$100/mo Cloud GPU Self-Hosting Breakeven Advisor",
        ],
    }

    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item["a"],
                },
            }
            for item in FAQ_ENTRIES
        ],
    }

    return safe_json_for_html_script(webapp_ld), safe_json_for_html_script(faq_ld)


def build_faq_html() -> str:
    blocks: list[str] = []
    for idx, item in enumerate(FAQ_ENTRIES):
        open_attr = " open" if idx == 0 else ""
        q_esc = html.escape(item["q"])
        a_esc = html.escape(item["a"])
        blocks.append(
            f'<details class="faq-item"{open_attr}>'
            f"<summary>{q_esc}</summary>"
            f'<div class="faq-answer">{a_esc}</div>'
            f"</details>"
        )
    return "\n        ".join(blocks)


def build_sitemap_xml(site_url: str, updated_date: str) -> str:
    base = site_url.rstrip("/") + "/"
    url_entries: list[str] = []
    for route in SEO_ROUTES:
        loc = base + route["slug"]
        prio = route["priority"]
        url_entries.append(
            f"""  <url>
    <loc>{html.escape(loc)}</loc>
    <lastmod>{html.escape(updated_date)}</lastmod>
    <changefreq>daily</changefreq>
    <priority>{prio}</priority>
  </url>"""
        )
    joined = "\n".join(url_entries)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{joined}
</urlset>
"""


def build_robots_txt(site_url: str) -> str:
    sitemap_url = site_url.rstrip("/") + "/sitemap.xml"
    return f"""User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Baiduspider
Allow: /

Sitemap: {sitemap_url}
"""


def build_seo_nav_html(base_prefix: str, active_slug: str) -> str:
    links: list[str] = []
    for r in SEO_ROUTES:
        href = f"{base_prefix}{r['slug']}" if r["slug"] else (base_prefix or "./")
        cls = "seo-topic-link active" if r["slug"] == active_slug else "seo-topic-link"
        links.append(f'<a class="{cls}" href="{html.escape(href)}">{html.escape(r["nav_label"])}</a>')
    return "\n          ".join(links)


def build_site(*, force_fallback: bool = False, site_url: str | None = None) -> dict[str, Any]:
    affiliates = load_affiliates(CONFIG_PATH)
    models, fx_rate, updated_date, source_label = load_models_dataset(
        LIVE_MODELS_PATH,
        affiliates,
        force_fallback=force_fallback,
    )
    coding_plans = load_coding_plans(LIVE_MODELS_PATH, affiliates, fx_rate, force_fallback=force_fallback)

    resolved_site_url = (
        site_url
        or os.environ.get("SITE_BASE_URL")
        or DEFAULT_SITE_URL
    ).strip()
    if not resolved_site_url.endswith("/"):
        resolved_site_url += "/"

    cn_count = sum(1 for m in models if m["region"] == "cn_direct")
    global_count = sum(1 for m in models if m["region"] == "global")
    faq_html = build_faq_html()

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    index_path = DIST_DIR / "index.html"

    for route in SEO_ROUTES:
        slug = route["slug"]
        is_root = slug == ""
        base_prefix = "" if is_root else "../"
        route_canonical = resolved_site_url + slug

        app_payload = {
            "updated_at": updated_date,
            "source": source_label,
            "fx_rate_usd_to_rmb": fx_rate,
            "affiliates": affiliates,
            "coding_plans": coding_plans,
            "page_preset": route["preset"],
            "models": models,
        }
        embedded_json = safe_json_for_html_script(app_payload)
        json_ld_webapp, json_ld_faq = build_json_ld(
            route_canonical,
            updated_date,
            len(models),
            route["title"],
            route["description"],
        )
        seo_nav_html = build_seo_nav_html(base_prefix, slug)

        html_output = render_html_template(
            embedded_json=embedded_json,
            json_ld_webapp=json_ld_webapp,
            json_ld_faq=json_ld_faq,
            page_title=html.escape(route["title"]),
            page_description=html.escape(route["description"]),
            canonical_url=html.escape(route_canonical),
            updated_date=html.escape(updated_date),
            total_models=len(models),
            cn_models_count=cn_count,
            global_models_count=global_count,
            faq_html_items=faq_html,
            hero_title_main=html.escape(route["hero_main"]),
            hero_title_accent=html.escape(route["hero_accent"]),
            hero_subtitle=html.escape(route["hero_sub"]),
            seo_nav_html=seo_nav_html,
            sitemap_href=f"{base_prefix}sitemap.xml",
        )

        out_file = DIST_DIR / "index.html" if is_root else (DIST_DIR / slug.strip("/") / "index.html")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(html_output, encoding="utf-8")

    sitemap_path = DIST_DIR / "sitemap.xml"
    robots_path = DIST_DIR / "robots.txt"
    sitemap_path.write_text(build_sitemap_xml(resolved_site_url, updated_date), encoding="utf-8")
    robots_path.write_text(build_robots_txt(resolved_site_url), encoding="utf-8")

    return {
        "index_path": str(index_path),
        "sitemap_path": str(sitemap_path),
        "robots_path": str(robots_path),
        "seo_pages_count": len(SEO_ROUTES),
        "total_models": len(models),
        "cn_models": cn_count,
        "global_models": global_count,
        "source": source_label,
        "fx_rate": fx_rate,
        "index_bytes": index_path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Engine B static bilingual AI API & Cloud Cost Calculator site."
    )
    parser.add_argument(
        "--fallback-only",
        action="store_true",
        help="Ignore shared_data/models_live.json and compile using the built-in fallback dataset.",
    )
    parser.add_argument(
        "--site-url",
        default=None,
        help="Canonical public URL for sitemap.xml, robots.txt, and JSON-LD.",
    )
    args = parser.parse_args()

    summary = build_site(force_fallback=args.fallback_only, site_url=args.site_url)
    print(
        f"✅ Engine B 静态比价矩阵站编译成功！\n"
        f"   - 数据源: {summary['source']} (共 {summary['total_models']} 款模型: 国内直连 {summary['cn_models']} 款 / 海外 Global {summary['global_models']} 款)\n"
        f"   - 静态 SEO 页面数: {summary['seo_pages_count']} 页 (全量收录进 sitemap.xml)\n"
        f"   - 汇率基准: 1 USD = {summary['fx_rate']} RMB\n"
        f"   - 主页体积: {summary['index_path']} ({summary['index_bytes']:,} bytes)\n"
        f"   - SEO 索引: {summary['sitemap_path']} & {summary['robots_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
