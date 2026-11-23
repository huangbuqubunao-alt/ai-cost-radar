#!/usr/bin/env python3
"""
Engine B — Verifiable AI API & Coding Plan Cost Calculator + Build-Time SSR & Attribution Site Builder (v3.0)
Python 3.12+ standard library ONLY · Zero third-party pip/npm dependencies.

Inputs:
  1. ../config.json                         (Domestic RMB & Global USD affiliate links)
  2. ../shared_data/models_live.json        (Live pricing feed from Engine A)
  3. ../engine_a_mcp_actor/pricing_core.py  (Shared single source of truth for quotas, math, endpoints & self-host)

Outputs (ready for Cloudflare Pages + D1 / static hosting):
  - dist/index.html + 4 topic subpages (with build-time SSR HTML <table>s readable without JS)
  - dist/api/models_live.json
  - dist/badges/coding-plan-status.svg
  - dist/feeds/price-changes.xml
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
import re
import sys
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ENGINE_DIR.parent
ENGINE_A_DIR = PROJECT_ROOT / "engine_a_mcp_actor"
CONFIG_PATH = PROJECT_ROOT / "config.json"
LIVE_MODELS_PATH = PROJECT_ROOT / "shared_data" / "models_live.json"
DIST_DIR = ENGINE_DIR / "dist"

for _p in (ENGINE_DIR, ENGINE_A_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pricing_core  # noqa: E402
from ui_template import render_html_template  # noqa: E402

DEFAULT_FX_USD_TO_RMB = pricing_core.DEFAULT_FX_USD_TO_RMB
DEFAULT_SITE_URL = "https://ai-cost-radar-nlu.pages.dev/"

DEFAULT_AFFILIATES: dict[str, str] = {
    # Domestic RMB channels (clean official URLs when unconfigured)
    "aliyun_ambassador_url": "https://www.aliyun.com/minisite/goods",
    "aliyun_bailian_url": "https://bailian.console.aliyun.com/",
    "tencent_cps_url": "https://cloud.tencent.com/product/lkeap",
    "siliconflow_invite_url": "https://cloud.siliconflow.cn/",
    "volcengine_ark_url": "https://console.volcengine.com/ark",
    # Global USD channels (clean official URLs when unconfigured)
    "novita_affiliate_url": "https://novita.ai",
    "railway_affiliate_url": "https://railway.com",
    "runpod_affiliate_url": "https://www.runpod.io",
    "apify_affiliate_url": "https://apify.com",
    "digitalocean_affiliate_url": "https://www.digitalocean.com",
    "openrouter_url": "https://openrouter.ai",
}

# Built-in fallback dataset (shares the same verified pricing_core catalog)
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
        "name": "Google: Gemini 2.5 Pro (多模态长上下文)",
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
        "name": "Google: Gemini 2.5 Flash (轻量高频)",
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
        "id": "deepseek/deepseek-v4.1-flash",
        "name": "DeepSeek: DeepSeek V4.1 Flash",
        "provider": "OpenRouter (Global)",
        "provider_config_key": "openrouter_url",
        "region": "global",
        "input_usd_per_1m": 0.0498,
        "output_usd_per_1m": 0.1992,
        "cache_hit_factor": 0.5,
        "context_length": 1048576,
        "supports_tools": True,
        "is_free": False,
        "value_score": 95.1,
        "tags": ["coding", "cheap", "global"],
    },
    {
        "id": "aliyun-bailian/qwen3.5-plus",
        "name": "阿里云百炼: Qwen3.5-Plus (1M上下文推理主力)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 0.8,
        "output_rmb_per_1m": 2.0,
        "cache_hit_factor": 0.2,
        "context_length": 1000000,
        "supports_tools": True,
        "is_free": False,
        "value_score": 98.6,
        "tags": ["coding", "reasoning", "cheap", "cn_direct"],
    },
    {
        "id": "aliyun-bailian/qwen3-coder-next",
        "name": "阿里云百炼: Qwen3-Coder-Next (SWE编程Agent主力)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 1.2,
        "output_rmb_per_1m": 4.8,
        "cache_hit_factor": 0.2,
        "context_length": 262144,
        "supports_tools": True,
        "is_free": False,
        "value_score": 99.2,
        "tags": ["coding", "cheap", "cn_direct"],
    },
    {
        "id": "siliconflow/deepseek-ai/DeepSeek-V3",
        "name": "硅基流动 SiliconFlow: DeepSeek-V3 按量直连",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 2.0,
        "output_rmb_per_1m": 8.0,
        "cache_hit_factor": 0.25,
        "context_length": 65536,
        "supports_tools": True,
        "is_free": False,
        "value_score": 96.8,
        "tags": ["coding", "cheap", "cn_direct"],
    },
    {
        "id": "siliconflow/Qwen/Qwen2.5-7B-Instruct",
        "name": "硅基流动 SiliconFlow: Qwen2.5-7B-Instruct (免费API)",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "region": "cn_direct",
        "input_rmb_per_1m": 0.0,
        "output_rmb_per_1m": 0.0,
        "cache_hit_factor": 1.0,
        "context_length": 32768,
        "supports_tools": True,
        "is_free": True,
        "value_score": 98.5,
        "tags": ["coding", "cheap", "free", "cn_direct"],
    },
    {
        "id": "tencent-cloud/deepseek-v3",
        "name": "腾讯云: DeepSeek-V3.2 满血专线版",
        "provider": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "api_model_id": "deepseek-v3",
        "region": "cn_direct",
        "input_rmb_per_1m": 2.0,
        "output_rmb_per_1m": 8.0,
        "cache_hit_factor": 0.2,
        "context_length": 131072,
        "supports_tools": True,
        "is_free": False,
        "value_score": 97.4,
        "tags": ["coding", "cheap", "cn_direct"],
    },
    {
        "id": "tencent-cloud/hunyuan-t1",
        "name": "腾讯云 LKEAP: Hunyuan-T1 深度思考旗舰",
        "provider": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "api_model_id": "hunyuan-t1-latest",
        "region": "cn_direct",
        "input_rmb_per_1m": 1.0,
        "output_rmb_per_1m": 4.0,
        "cache_hit_factor": 0.2,
        "context_length": 256000,
        "supports_tools": True,
        "is_free": False,
        "value_score": 98.4,
        "tags": ["coding", "reasoning", "cn_direct"],
    },
    {
        "id": "volcengine/doubao-seed-2.0-pro",
        "name": "火山引擎方舟: 豆包 Doubao-Seed-2.0-Pro (旗舰高并发)",
        "provider": "火山引擎 (Volcengine Ark)",
        "provider_config_key": "volcengine_ark_url",
        "api_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_model_id": "doubao-seed-2-0-pro-250415",
        "region": "cn_direct",
        "input_rmb_per_1m": 0.8,
        "output_rmb_per_1m": 2.0,
        "cache_hit_factor": 0.2,
        "context_length": 256000,
        "supports_tools": True,
        "is_free": False,
        "value_score": 98.1,
        "tags": ["coding", "cheap", "cn_direct"],
    },
]

DEFAULT_CODING_PLANS: list[dict[str, Any]] = pricing_core.get_offers_catalog()

FAQ_ENTRIES: list[dict[str, str]] = [
    {
        "q": "为什么每天 5,000 次模型调用时，¥200/月的 Coding Plan Pro 仍然不够用？",
        "a": "根据阿里云百炼与腾讯云官方公布的套餐规则，Pro 档上限均为每 5 小时 6,000 次、每周 45,000 次、每月 90,000 次模型调用（腾讯云 Lite 为 1,200 / 9,000 / 18,000 次，百炼 Lite 已停新购）。按每月 30 天折算，每天 5,000 次模型调用等于每月 15 万次，直接超出 Pro 月上限 6 万次。尤其需要注意：官方统计单位是「模型 API 调用次数」而非「用户提问次数」，在 Claude Code、Cline 或 Cursor 中发出一句指令往往连续触发 5～30 次模型调用。",
        "q_en": "Why is a ¥200/mo Coding Plan Pro still not enough at 5,000 model calls/day?",
        "a_en": "Per official Aliyun Bailian and Tencent Cloud rules, Pro tiers cap usage at 6,000 calls per 5 hours, 45,000 calls per week, and 90,000 calls per month (Tencent Lite is 1,200 / 9,000 / 18,000; Aliyun Lite is closed to new buyers). On a 30-day basis, 5,000 model calls/day equals 150,000 calls/month — exceeding the 90,000 Pro monthly cap by 60,000 calls. Note that quotas count underlying model API calls rather than user prompts: one agent prompt in Claude Code, Cline, or Cursor typically triggers 5–30 model calls.",
    },
    {
        "q": "Prompt 缓存命中率与隐式思考（Reasoning）Token 是如何影响真实月账单的？",
        "a": "开启缓存并不意味着 100% 输入都按折扣价结算。真实输入费用 = 未命中比例 × 普通输入价 + 命中比例 × 缓存命中价（例如输入 100 万 Token、普通价 ¥1.0、命中价 ¥0.2、命中率 50% 时，输入成本为 ¥0.60）。此外，深度推理模型（如 DeepSeek-R1、Qwen3.5-Plus、Hunyuan-T1）产生的隐式思维链 Token 按输出单价计费；若您的统计值尚未包含思考部分，可开启 1.5x～3.5x 可调倍率估算，若日志已包含思考 Token 则勾选「已含推理 Token」避免重复放大。",
        "q_en": "How do prompt-cache hit rates and hidden reasoning tokens affect my real monthly bill?",
        "a_en": "Enabling prompt caching does not discount 100% of input tokens. Effective input cost = uncached share × regular input rate + hit share × cached input rate (for example, 1M input tokens at ¥1.0 regular, ¥0.2 cached, and 50% hit rate costs ¥0.60, not ¥0.20). Likewise, reasoning models (DeepSeek-R1, Qwen3.5-Plus, Hunyuan-T1) bill hidden chain-of-thought tokens at the output rate; apply a 1.5x–3.5x multiplier if your average output count only measures visible text, or check 'already include reasoning' if your API logs already include reasoning_tokens.",
    },
    {
        "q": "买了百炼或腾讯云 Coding Plan 后，为什么复制错 Base URL 会继续产生按量扣费？",
        "a": "各大厂的个人 Coding Plan 均采用独立计费网关与专属密钥（如 sk-sp- 开头），不能填入通用按量端点。例如在 Claude Code 中使用腾讯云 Coding Plan 必须配置 ANTHROPIC_BASE_URL=https://api.lkeap.cloud.tencent.com/coding/anthropic（百炼为 https://coding.dashscope.aliyuncs.com/apps/anthropic），而在 OpenAI 兼容客户端中需配置对应 coding 专属路径。若误填通用按量兼容地址，请求会直接走账户余额按量计费。",
        "q_en": "Why am I still billed pay-as-you-go after buying an Aliyun or Tencent Coding Plan?",
        "a_en": "Personal Coding Plans run on isolated gateways with dedicated keys (such as sk-sp-) and must never be paired with generic pay-as-you-go Base URLs. For Claude Code, Tencent Coding Plan requires ANTHROPIC_BASE_URL=https://api.lkeap.cloud.tencent.com/coding/anthropic (Aliyun requires https://coding.dashscope.aliyuncs.com/apps/anthropic), while OpenAI-compatible IDEs require the dedicated /coding path. Pasting a standard /v1 pay-as-you-go endpoint bills your cash balance directly.",
    },
    {
        "q": "非交互式自动化后端、定时批处理或 SaaS 接口能买个人 Coding Plan 省钱吗？",
        "a": "不能。阿里云百炼、腾讯云与火山方舟官方文档均明确规定个人 Coding Plan 仅限交互式 AI 编程工具（Claude Code、Cursor、Cline、通义灵码、CodeBuddy、Trae 等）人工辅助开发使用，严禁用于自动化脚本、后端业务 API 或对外代调用。本计算器在您选择「非交互式自动化后端」场景时会自动排除上述个人套餐，并对比合规按量 API 与自建语义缓存网关方案。",
        "q_en": "Can automated backends, cron pipelines, or SaaS APIs use personal Coding Plans?",
        "a_en": "No. Official terms from Aliyun Bailian, Tencent Cloud, and Volcengine Ark strictly restrict personal Coding Plans to human-in-the-loop interactive coding IDEs (Claude Code, Cursor, Cline, Tongyi Lingma, CodeBuddy, Trae) and prohibit automated scripts, backend APIs, or proxy resale. Selecting 'Automated Backend / Batch API' in this calculator automatically excludes personal Coding Plans and compares compliant pay-as-you-go pools and semantic-cache cloud hosts.",
    },
    {
        "q": "什么时候适合买云服务器部署 LiteLLM / Dify 缓存网关或租用弹性 GPU 自建？",
        "a": "自建并非零成本：缓存网关月总成本 = 云主机月租（约 ¥68）+ 未命中缓存的剩余 API 账单 + 存储与流量开销（约 ¥15）；弹性 GPU 自建总成本 = 实例小时单价 × 月开机小时数 + 存储流量。只有当自建总成本稳定低于当前按量付费 API 月账单时，页面才会建议购买云主机或弹性 GPU；若当前按量账单更低，直接继续按量付费即可。",
        "q_en": "When does hosting a LiteLLM / Dify cache gateway or renting an elastic GPU actually save money?",
        "a_en": "Self-hosting is never zero-cost: Cache Gateway Monthly Total = cloud server rent (~¥68) + uncached API spend + storage/egress (~¥15); Elastic GPU Monthly Total = hourly GPU rate × monthly active hours + storage/egress. This tool only recommends a cloud server or GPU when total self-hosted cost is meaningfully lower than your current pay-as-you-go API bill; otherwise staying on pay-as-you-go is cheaper.",
    },
    {
        "q": "多人研发团队或月调用超 90,000 次时，怎么选「多席位 Coding Plan」与「Pro 打底＋按量溢出」？",
        "a": "个人 Coding Plan 专属密钥（如 sk-sp-）严禁接入共享网关供多人混用。多人研发团队需按实际 IDE 开发者人数采购独立席位（N × Pro / Lite），并与「团队共享按量 API 池 + LiteLLM 缓存」对比续费总账单：若人均调用较轻（共享按量总费低于 N × ¥200），直接共用按量池更省钱；若单人或团队总调用超出 N × 90,000 次/月上限，系统会自动测算「N 份 Pro 打底前 N×9 万次 + 超额部分走按量 API」混合账单，仅在续费月仍净省时才推荐。",
        "q_en": "How should multi-developer teams or >90,000-call workloads choose between multi-seat Coding Plans and 'Pro Base + PayG Overflow'?",
        "a_en": "Personal Coding Plan keys (such as sk-sp-) cannot be pooled behind a shared team proxy. Multi-developer teams must purchase one compliant subscription seat per IDE developer (N × Pro / Lite) and compare total renewal cost against a shared Pay-As-You-Go API pool: when average per-developer volume is light (shared PayG < N × ¥200), a shared PayG pool is cheaper; when total interactive calls exceed N × 90,000/month, this calculator models 'N × Pro Base + PayG Overflow' and only recommends it if renewal months still yield net savings.",
    },
]

SEO_ROUTES: list[dict[str, Any]] = [
    {
        "slug": "",
        "nav_label": "比价总览",
        "priority": "1.0",
        "title": "大模型 API 成本计算器 & Coding Plan 额度验算台 (2026) | 百炼 / 腾讯云 / DeepSeek / 千问核验",
        "description": "在线验算海内外 80+ 款主流大模型 API 月账单与 2026 国内 Coding Plan 真实调用上限（9万次/月 Pro 边界、首月与续费价拆分、缓存命中率拆分），支持区分 Claude Code Anthropic 专属端点与按量端点。",
        "hero_main": "算准大模型 API 与 Coding Plan 真实账单，",
        "hero_accent": "避开额度超支与端点误配",
        "hero_sub": "基于阿里云百炼、腾讯云、火山方舟与 OpenRouter 官方公开规则核验：支持同模型按量基准对比、缓存命中率拆分、思考倍率防重算及 Claude Code 专属端点一键生成。",
        "preset": {
            "region": "all",
            "filter": "all",
            "dailyCalls": 2500,
            "inputTokens": 2000,
            "outputTokens": 800,
            "cacheEnabled": False,
            "cacheHitRate": 0.5,
            "reasoningEnabled": False,
            "reasoningMultiplier": 2.5,
            "usageMode": "interactive_ide",
            "baselineId": "aliyun-bailian/qwen3.5-plus",
        },
    },
    {
        "slug": "coding-plan-2026/",
        "nav_label": "Coding Plan 额度横评",
        "priority": "0.95",
        "title": "2026 国内 Coding Plan 包月套餐核验：每天 5,000 次调用为什么 ¥200 Pro 仍不够用？",
        "description": "核对阿里云百炼（Lite 已停新购，Pro 首月 ¥39.90 / 续费 ¥200，月限 90,000 次）与腾讯云（Lite ¥40 月限 18,000 次 / Pro ¥200 月限 90,000 次）官方额度窗口，区分首月与续费盈亏及专属接入端点。",
        "hero_main": "2026 国内 Coding Plan 包月 vs 同模型按量，",
        "hero_accent": "看清 90,000 次/月硬上限与续费原价",
        "hero_sub": "下方默认演示每天 5,000 次模型调用（30 天预计 15 万次，超出 Pro 月额度 6 万次）。支持切换你的日调用量与当前基准模型，分别核算首月活动价与 ¥200 续费月真实盈亏。",
        "preset": {
            "region": "cn",
            "filter": "coding",
            "dailyCalls": 5000,
            "inputTokens": 4000,
            "outputTokens": 1000,
            "cacheEnabled": True,
            "cacheHitRate": 0.5,
            "reasoningEnabled": False,
            "reasoningMultiplier": 2.5,
            "usageMode": "interactive_ide",
            "baselineId": "aliyun-bailian/qwen3-coder-next",
        },
    },
    {
        "slug": "deepseek-vs-qwen/",
        "nav_label": "DeepSeek vs 千问精算",
        "priority": "0.90",
        "title": "DeepSeek-V3 / R1 vs 通义千问 Qwen3.5 / Qwen3-Coder 同输入输出与缓存命中率比价 (2026)",
        "description": "在相同日调用量、输入输出 Token、50% Prompt 缓存命中率与可调思考 Token 倍率下，逐项对比 DeepSeek-R1/V3 与通义千问 Qwen3.5-Plus / Qwen3-Coder-Next 真实人民币月成本。",
        "hero_main": "DeepSeek 系列 vs 通义千问 Qwen3 系列，",
        "hero_accent": "同参数、同缓存命中率透明对账",
        "hero_sub": "已拆分「缓存命中率（默认 50%）」与「思考 Token 可调倍率（2.5x，支持勾选输入已含思考 Token 防重算）」，免 JS 亦可直接查阅下方全量单价表。",
        "preset": {
            "region": "cn",
            "filter": "reasoning",
            "dailyCalls": 3000,
            "inputTokens": 3000,
            "outputTokens": 1200,
            "cacheEnabled": True,
            "cacheHitRate": 0.5,
            "reasoningEnabled": True,
            "reasoningMultiplier": 2.5,
            "usageMode": "interactive_ide",
            "baselineId": "tencent-cloud/deepseek-r1",
            "compareIds": [
                "tencent-cloud/deepseek-r1",
                "aliyun-bailian/qwen3.5-plus",
                "aliyun-bailian/qwen3-coder-next",
            ],
        },
    },
    {
        "slug": "deepseek-v4-vs-claude-code/",
        "nav_label": "DeepSeek V4 vs Claude",
        "priority": "0.95",
        "title": "DeepSeek V4.1 Flash vs Claude Code (Sonnet) vs Qwen3-Coder-Next 50% 缓存实测账单对比 (2026)",
        "description": "基于 models_live.json 实时价格动态渲染：在 50% Prompt 缓存命中下逐档对比 DeepSeek V4.1 Flash、Claude Sonnet 与 Qwen3-Coder-Next 日/月账单，明确按量路由 vs Coding Plan 选型边界，并附本地只读审计脚本与 Agent Guardian 双账号隔离指南。",
        "hero_main": "DeepSeek V4.1 Flash vs Claude Code 成本对账，",
        "hero_accent": "50% 缓存命中实算与按量/包月边界",
        "hero_sub": "动态读取最新在线模型报价，同负载横评 DeepSeek V4.1 Flash、Claude Sonnet 与 Qwen3-Coder-Next 日/月账单；明确何时选按量路由 vs Coding Plan，并附本地审计与 Agent Guardian 多账号隔离闭环。",
        "preset": {
            "region": "all",
            "filter": "coding",
            "dailyCalls": 2500,
            "inputTokens": 4000,
            "outputTokens": 1000,
            "cacheEnabled": True,
            "cacheHitRate": 0.5,
            "reasoningEnabled": False,
            "reasoningMultiplier": 2.5,
            "usageMode": "interactive_ide",
            "baselineId": "anthropic/claude-sonnet-5.5",
            "compareIds": [
                "deepseek/deepseek-v4.1-flash",
                "anthropic/claude-sonnet-5.5",
                "aliyun-bailian/qwen3-coder-next",
            ],
            "heroEnMain": "DeepSeek V4.1 Flash vs Claude Code Cost Benchmark, ",
            "heroEnAccent": "50% Cache Hit Math & PayG vs Coding Plan",
            "heroEnSub": "Live models_live.json pricing comparison across DeepSeek V4.1 Flash, Claude Sonnet, and Qwen3-Coder-Next at 50% prompt-cache hit rate — plus when to choose PayG routing vs Coding Plan, local spend auditing, and Agent Guardian dual-account isolation.",
            "heroZhMain": "DeepSeek V4.1 Flash vs Claude Code 成本对账，",
            "heroZhAccent": "50% 缓存命中实算与按量/包月边界",
            "heroZhSub": "动态读取最新在线模型报价，同负载横评 DeepSeek V4.1 Flash、Claude Sonnet 与 Qwen3-Coder-Next 日/月账单；明确何时选按量路由 vs Coding Plan，并附本地审计与 Agent Guardian 多账号隔离闭环。",
        },
    },
    {
        "slug": "claude-code-domestic/",
        "nav_label": "Claude Code 专属端点",
        "priority": "0.85",
        "title": "2026 Claude Code / Cursor / Cline 国内模型接入配置与 Coding Plan 专属端点核对",
        "description": "区分阿里云百炼、腾讯云与火山方舟 Coding Plan 的 Anthropic 原生专属端点（sk-sp- / ark-）与普通按量 OpenAI 兼容端点，防止买了包月仍误走按量扣费。",
        "hero_main": "Claude Code / Cursor 国内模型接入与算账，",
        "hero_accent": "严格区分包月专属端点与按量端点",
        "hero_sub": "默认横评百炼 Qwen3-Coder-Next、腾讯云 DeepSeek-V3 与火山方舟 Doubao-Seed-2.0-Pro 三厂编码主力；点击「配置专属端点」按客户端与计费方式一键复制协议变量。",
        "preset": {
            "region": "cn",
            "filter": "coding",
            "dailyCalls": 1500,
            "inputTokens": 5000,
            "outputTokens": 1000,
            "cacheEnabled": True,
            "cacheHitRate": 0.5,
            "reasoningEnabled": False,
            "reasoningMultiplier": 2.5,
            "usageMode": "interactive_ide",
            "baselineId": "aliyun-bailian/qwen3-coder-next",
            "compareIds": [
                "aliyun-bailian/qwen3-coder-next",
                "tencent-cloud/deepseek-v3",
                "volcengine/doubao-seed-2.0-pro",
            ],
        },
    },
    {
        "slug": "dify-openclaw-cloud-server/",
        "nav_label": "后端缓存网关与自建测算",
        "priority": "0.85",
        "title": "非交互式后端 API：LiteLLM / Dify 语义缓存云主机总成本 vs 按量 API 盈亏计算器",
        "description": "非交互式后端不可使用个人 Coding Plan。按「主机月租 + 未命中缓存 API 费 + 存储流量」与弹性 GPU 实例工时吞吐假设，实算何时该自建、何时该继续按量。",
        "hero_main": "自动化后端与 Dify / LiteLLM 缓存网关测算，",
        "hero_accent": "算清主机费＋未命中 API 费真实总账",
        "hero_sub": "下方已切换为「非交互式自动化后端」模式（自动排除受限个人编程套餐）。当自建总成本高于当前按量账单时，系统会明确建议继续按量付费。",
        "preset": {
            "region": "cn",
            "filter": "all",
            "dailyCalls": 15000,
            "inputTokens": 2500,
            "outputTokens": 800,
            "cacheEnabled": False,
            "cacheHitRate": 0.5,
            "reasoningEnabled": False,
            "reasoningMultiplier": 2.5,
            "usageMode": "automated_backend",
            "baselineId": "siliconflow/deepseek-ai/DeepSeek-V3",
            "compareIds": [
                "siliconflow/deepseek-ai/DeepSeek-V3",
                "aliyun-bailian/qwen3.5-plus",
                "volcengine/doubao-seed-2.0-pro",
            ],
        },
    },
    {
        "slug": "ai-coding-spend-auditor/",
        "nav_label": "海外账单体检",
        "html_lang": "en",
        "priority": "0.95",
        "title": "AI Coding & Agent Spend Auditor (2026) — Claude Code, Codex, Antigravity, OpenCode & Grok vs RunPod GPU",
        "description": "Zero-dependency local read-only CLI auditor for Claude Code, OpenAI Codex (.jsonl & .zst), Google Antigravity, OpenCode SQLite, xAI Grok CLI & Cline — plus live USD API vs RunPod GPU & Railway LiteLLM cache break-even calculator.",
        "hero_main": "Audit Real Claude Code, Codex & Agent Spend Locally, ",
        "hero_accent": "Compare USD APIs vs RunPod GPU Break-Even",
        "hero_sub": "100% read-only Python stdlib scanner across Claude Code, Codex (.jsonl/.zst), Antigravity, OpenCode SQLite, Grok CLI & Cline — zero prompts uploaded. Model exact prompt-cache savings, Railway LiteLLM proxy, and RunPod elastic GPU break-even.",
        "preset": {
            "lang": "en",
            "region": "global",
            "filter": "coding",
            "dailyCalls": 2000,
            "inputTokens": 4500,
            "outputTokens": 900,
            "cacheEnabled": True,
            "cacheHitRate": 0.75,
            "reasoningEnabled": False,
            "reasoningMultiplier": 2.5,
            "usageMode": "interactive_ide",
            "baselineId": "anthropic/claude-sonnet-5.5",
            "compareIds": [
                "anthropic/claude-sonnet-5.5",
                "openai/gpt-5.3-codex",
                "x-ai/grok-code-fast-1",
            ],
            "heroEnMain": "Audit Real Claude Code, Codex & Agent Spend Locally, ",
            "heroEnAccent": "Compare USD APIs vs RunPod GPU Break-Even",
            "heroEnSub": "100% read-only Python stdlib scanner across Claude Code, Codex (.jsonl/.zst), Antigravity, OpenCode SQLite, Grok CLI & Cline — zero prompts uploaded. Model exact prompt-cache savings, Railway LiteLLM proxy, and RunPod elastic GPU break-even.",
            "heroZhMain": "一行命令只读审计海内外 8 大 AI 编程客户端账单，",
            "heroZhAccent": "实算海外 USD 按量 vs RunPod GPU 回本线",
            "heroZhSub": "零依赖本地扫描 Claude Code、Codex（含 .zst 归档）、Antigravity、OpenCode、Grok、WorkBuddy、Qwen 与 Cline，精准对比海外低价 API、Railway 缓存网关与 RunPod 弹性 GPU。",
        },
    },
    {
        "slug": "agent-guardian/",
        "nav_label": "Agent Guardian 隔离台",
        "page_kind": "product_landing",
        "priority": "0.95",
        "title": "Agent Guardian (v3.20.0) — macOS 原生 AI Agent 多账号零污染隔离与安全工作台",
        "description": "面向 Claude Code、OpenAI Codex CLI、Google Gemini CLI 与 OpenCode 的 macOS Apple Silicon 原生多账号零污染隔离、XNU Seatbelt (Mode A) + Apple VZ HostNetworkBroker (Mode B) 双模沙箱、Fail-Closed 502 零直连回退、403 零载荷出站域名防火墙、离线 5h 额度雷达与并行 Git Worktree 工作台。",
        "hero_main": "Agent Guardian (v3.20.0)：",
        "hero_accent": "AI Agent 多账号零污染隔离与安全工作台",
        "hero_sub": "macOS Apple Silicon 原生（Rust 2021 + Swift Cocoa，MIT 开源）：并发隔离 Claude Code / Codex CLI / Gemini CLI / OpenCode 多账号，提供 XNU Seatbelt 与 Apple VZ 双模沙箱、Fail-Closed 502 零直连回退、403 出站域名防火墙与离线 5h 滚动额度雷达。",
        "preset": {
            "lang": "zh",
            "heroEnMain": "Agent Guardian (v3.20.0): ",
            "heroEnAccent": "Zero-Pollution Multi-Account Isolation & Sandbox Workbench",
            "heroEnSub": "Native macOS Apple Silicon (Rust 2021 + Swift Cocoa, MIT): Concurrent isolation for Claude Code, Codex CLI, Gemini CLI & OpenCode with XNU Seatbelt (Mode A) & Apple VZ HostNetworkBroker (Mode B), Fail-Closed 502, 403 zero-payload domain firewall, offline 5h quota radar & Git Worktree guardrails.",
            "heroZhMain": "Agent Guardian (v3.20.0)：",
            "heroZhAccent": "AI Agent 多账号零污染隔离与安全工作台",
            "heroZhSub": "macOS Apple Silicon 原生（Rust 2021 + Swift Cocoa，MIT 开源）：并发隔离 Claude Code / Codex CLI / Gemini CLI / OpenCode 多账号，提供 XNU Seatbelt 与 Apple VZ 双模沙箱、Fail-Closed 502 零直连回退、403 出站域名防火墙与离线 5h 滚动额度雷达。",
        },
    },
]


AGENT_GUARDIAN_FAQ_ENTRIES: list[dict[str, str]] = [
    {
        "q": "为什么需要 Fail-Closed 502 零直连回退，而不是在代理断线时回退本地宽带？",
        "a": "当上游 SOCKS5 / HTTP CONNECT 代理断线或握手超时时，若静默回退宿主机物理宽带直连，会立即暴露真实住宅/办公 IP 与出口国家错配，触发平台风控或跨区关联。Agent Guardian 为主备上游连接、鉴权与握手设置统一截止时间，异常即刻返回 502 Bad Gateway（X-Claude-Guardian-Fail-Closed: 1）并切断流，绝不回退宿主机直连。",
        "q_en": "Why enforce Fail-Closed 502 instead of falling back to direct host broadband when a proxy drops?",
        "a_en": "Silent fallback to host broadband exposes your physical IP and breaks region/timezone hygiene, risking cross-account correlation. Agent Guardian enforces a unified deadline across upstream SOCKS5 / HTTP CONNECT connect, auth, and handshake, immediately returning 502 Bad Gateway (X-Claude-Guardian-Fail-Closed: 1) and severing the stream without ever falling back to direct egress.",
    },
    {
        "q": "Mode A (XNU Seatbelt) 与 Mode B (Apple VZ + HostNetworkBroker) 怎么选？",
        "a": "Mode A 是日常主力模式，零毫秒启动，通过 macOS XNU Sandbox.kext 内核级拦截一切非代理直连 Socket、禁读 ~/.ssh / ~/.aws / ~/.config/gh / Keychain / 跨账号目录，并锁死工作区控制面文件（.guardian.toml、.mcp.json、.claude/settings*.json、.codex/config.toml 等）。Mode B 用于高敏任务，通过 Apple Virtualization.framework 为每个安全域分配独立 Linux VM、gn-<domain> 虚拟交换机与宿主用户态帧级过滤（零 gvproxy NAT、单网卡零默认路由），仅在受管 VM 通过帧级往返验证（verified_roundtrips > 0）时才显示 PROTECTED。",
        "q_en": "When should I use Mode A (XNU Seatbelt) vs Mode B (Apple VZ + HostNetworkBroker)?",
        "a_en": "Mode A is the zero-millisecond daily driver: macOS XNU Sandbox.kext blocks non-proxy direct sockets, denies reads to ~/.ssh / ~/.aws / ~/.config/gh / Keychain / sibling account directories, and write-locks workspace control files (.guardian.toml, .mcp.json, .claude/settings*.json, .codex/config.toml). Mode B isolates high-sensitivity tasks inside per-domain Apple VZ Linux VMs with a gn-<domain> virtual switch and host user-space ARP/DHCP/TCP frame filtering (zero gvproxy NAT, single NIC with no default route), reporting PROTECTED only when verified_roundtrips > 0.",
    },
    {
        "q": "四大 AI CLI 多账号隔离会污染宿主的 ~/.zshrc 或已有真实 HOME 吗？",
        "a": "不会。每个 Claude Code、Codex CLI、Gemini CLI（GEMINI_CLI_HOME）与 OpenCode（OPENCODE_HOME + XDG_* 保留真实 HOME）账号均拥有独立 0700 目录与 0600 凭据保险箱（Keychain + AES-256-GCM），派生子进程前会自动清洗宿主机残留 API Key 环境变量；eval \"$(ag shell-hook zsh)\" 仅在进入绑定工作区时设置轻量上下文，离开目录自动 unset，绝不污染全局 HTTP_PROXY。",
        "q_en": "Does isolating 4 AI CLIs pollute ~/.zshrc or overwrite my real HOME directory?",
        "a_en": "No. Each Claude Code, Codex CLI, Gemini CLI (GEMINI_CLI_HOME), and OpenCode (OPENCODE_HOME + XDG_* preserving real HOME) profile lives in an isolated 0700 directory with a 0600 Keychain + AES-256-GCM vault. Residual host API keys are scrubbed before spawning, and eval \"$(ag shell-hook zsh)\" sets lightweight directory-scoped context that unsets on exit without polluting global HTTP_PROXY.",
    },
    {
        "q": "离线 5h 滚动额度雷达如何做到零联网统计 Codex SQLite 与 90% 缓存折扣？",
        "a": "Agent Guardian 100% 本地只读解析 .jsonl / .json 会话日志、2026 新版 Codex state_*.sqlite（SQLITE_OPEN_READ_ONLY + PRAGMA query_only = ON，联动 rollout_path 提取 cached_input_tokens 90% 提示词缓存折扣）以及 OpenCode opencode.db，并按 account_id 与 thread_id 去重，避免长上下文缓存命中导致的额度虚高，支持 ag workspace usage --export 导出防公式注入的 CSV/JSON 报表。",
        "q_en": "How does the 100% offline 5h quota radar parse Codex SQLite & 90% prompt cache discounts without network calls?",
        "a_en": "It reads local .jsonl/.json logs, Codex state_*.sqlite (SQLITE_OPEN_READ_ONLY + PRAGMA query_only = ON, joining rollout_path tail metrics for 90% cached_input_tokens discounts), and OpenCode opencode.db, deduplicating by account_id and thread_id so long-context cache hits do not inflate 5h load. You can export formula-injection-safe CSV/JSON FinOps reports via ag workspace usage --export.",
    },
    {
        "q": "ag mcp vault-secrets 如何在不停用 MCP 服务的前提下消除明文密钥泄漏风险？",
        "a": "运行 ag mcp vault-secrets <account> 会把 MCP 配置中内嵌的明文 API Key 迁入 XNU 内核沙箱不可读的 mcp_vault/<account>.enc（0600 AES-256-GCM），并将配置文件自动改写为四大 CLI 原生动态环境变量占位符（Codex env_vars、Claude/Gemini ${VAR}、OpenCode {env:VAR}），在受管会话启动前安全注入；对于无需保留的高危服务，也可使用 ag mcp quarantine 一键无损停用。",
        "q_en": "How does ag mcp vault-secrets remove plaintext MCP keys without disabling active MCP servers?",
        "a_en": "ag mcp vault-secrets <account> migrates embedded plaintext API keys into mcp_vault/<account>.enc (0600 AES-256-GCM, unreadable inside XNU Seatbelt), rewrites configs to native dynamic env syntax (Codex env_vars, Claude/Gemini ${VAR}, OpenCode {env:VAR}), and injects them only when launching a managed session. High-risk servers can also be non-destructively disabled via ag mcp quarantine.",
    },
]

DEEPSEEK_V4_CLAUDE_FAQ_ENTRIES: list[dict[str, str]] = [
    {
        "q": "在 50% Prompt 缓存命中下，DeepSeek V4.1 Flash 比 Claude Code 主力 Sonnet 省多少？",
        "a": "本页直接读取 shared_data/models_live.json 中的实时单价：DeepSeek V4.1 Flash 与 Claude Sonnet 在 50% 缓存命中、每次 4K 输入 + 1K 输出的相同负载下，月账单差距通常在数十倍量级（详见上方表 1 与表 2 的动态实算结果）。工程上常用 80/20 混合路由：日常代码检索、单测补全与文档生成走 DeepSeek V4.1 Flash 或 Qwen3-Coder-Next，复杂跨文件架构重构再切回 Claude Sonnet。",
        "q_en": "At a 50% prompt-cache hit rate, how much cheaper is DeepSeek V4.1 Flash than Claude Sonnet?",
        "a_en": "This page dynamically reads live rates from shared_data/models_live.json: under identical 4K input + 1K output workloads at 50% cache hit rate, DeepSeek V4.1 Flash cuts monthly API spend by more than an order of magnitude compared to Claude Sonnet (exact live figures appear in Tables 1 & 2 above). Many teams adopt 80/20 routing—handling routine edits and tests on DeepSeek V4.1 Flash or Qwen3-Coder-Next while reserving Claude Sonnet for complex refactors.",
    },
    {
        "q": "什么时候应该选按量路由（DeepSeek V4.1 Flash / Qwen3-Coder-Next），什么时候买国内 Coding Plan？",
        "a": "当您使用 DeepSeek V4.1 Flash 按量直连/OpenRouter 时，即使每天 2,500 次甚至 5,000 次调用，按量月费仍可能远低于 ¥200/月包月续费价；而如果您高频使用 Qwen3-Coder-Next 或多模型交互式 IDE 开发且日均 1,500～3,000 次（月 4.5 万～9 万次），阿里云百炼 Pro 首月 ¥39.90 性价比突出。但只要超出 90,000 次/月或用于自动化脚本/后端 API（官方明确禁止），就必须切回按量路由或按「Pro 打底 + 按量溢出」拆分。",
        "q_en": "When should I use PayG routing (DeepSeek V4.1 Flash / Qwen3-Coder-Next) vs a domestic Coding Plan?",
        "a_en": "If your workload routes mainly to DeepSeek V4.1 Flash PayG, even 2,500–5,000 daily calls can cost well below a ¥200/mo Pro renewal. Conversely, heavy interactive IDE developers running Qwen3-Coder-Next within the 90,000 calls/month cap benefit from Aliyun Bailian Pro's ¥39.90 first-month promo—while >90,000 calls/month or non-interactive backend/cron scripts (strictly prohibited by personal Coding Plan terms) must stay on PayG or hybrid overflow routing.",
    },
    {
        "q": "双账号切换（Claude 官方号 + DeepSeek/百炼按量号）为什么容易串号或误扣余额？如何用 Agent Guardian 隔离？",
        "a": "裸奔切换环境变量时，宿主机残留的 ANTHROPIC_API_KEY 或共享 ~/.claude 目录极易导致误走按量余额、串号或 VPN 断线直连泄漏。在 macOS Apple Silicon 上，可先用零上传脚本 audit_ai_spend.py 摸清本地过去 30 天真实消耗，再使用 Agent Guardian (v3.20.0) 为每个账号分配独立 0700 目录（Claude Code 使用 CLAUDE_CONFIG_DIR）与 0600 凭据仓，启动前自动清洗宿主残留 Key，配合 XNU Seatbelt (Mode A) / Apple VZ (Mode B)、Fail-Closed 502 零直连回退与 403 出站域名防火墙安全隔离运行。",
        "q_en": "Why does switching between a Claude account and a DeepSeek/PayG profile risk cross-billing, and how does Agent Guardian isolate them?",
        "a_en": "Bare env switching often leaves residual ANTHROPIC_API_KEY variables or shared ~/.claude state, causing accidental PayG billing or direct broadband leaks on VPN drops. After auditing 30-day local usage with audit_ai_spend.py (zero upload), Agent Guardian (v3.20.0) on macOS Apple Silicon isolates each Claude Code / Codex / Gemini / OpenCode profile in its own 0700 directory (CLAUDE_CONFIG_DIR) and 0600 vault, scrubs residual host keys before spawn, enforces XNU Seatbelt (Mode A) or Apple VZ (Mode B), Fail-Closed 502 zero-direct-fallback, and a 403 domain firewall.",
    },
]


def safe_json_for_html_script(obj: Any) -> str:
    """Serialize JSON safely for embedding inside <script> tags (prevents </script> breakouts)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _model_anchor_id(model_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", model_id.strip()).strip("-").lower()
    return f"model-{slug or 'item'}"


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
    if "novita" in hay:
        return "novita_affiliate_url"
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


SPONSORED_URL_TOKENS = (
    "userCode=",
    "curl.qcloud.com",
    "siliconflow.cn/i/",
    "referralCode=",
    "ref=",
    "aff=",
    "invite=",
)


def is_sponsored_link(url: str, config_key: str = "", commission_status: str = "") -> bool:
    """Return True only when an outbound link carries referral/affiliate attribution."""
    if commission_status == "none":
        return False
    raw_url = str(url or "")
    if any(tok in raw_url for tok in SPONSORED_URL_TOKENS):
        return True
    if config_key in (
        "aliyun_bailian_url",
        "aliyun_ambassador_url",
        "tencent_cps_url",
        "siliconflow_invite_url",
        "novita_affiliate_url",
        "railway_affiliate_url",
    ) and "?" in raw_url:
        return True
    return False


def channel_bonus_notes(config_key: str, is_free: bool) -> tuple[str, str]:
    if is_free:
        return ("¥0 免费调用层", "$0 Free API Tier")
    mapping = {
        "aliyun_bailian_url": ("新客免费 Token 额度", "Free Signup Tokens"),
        "siliconflow_invite_url": ("按量池含免费小模型", "Pay-As-You-Go + Free Models"),
        "tencent_cps_url": ("腾讯云官方通道", "Tencent Cloud Official"),
        "volcengine_ark_url": ("火山方舟官方通道", "Volcengine Ark Official"),
        "novita_affiliate_url": ("Claude Code/OpenCode 直连 + 弹性 GPU", "Claude Code / OpenCode + Elastic GPU"),
        "openrouter_url": ("统一多模型按量网关", "Unified Multi-LLM API"),
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

    tags_set = set(raw_tags)
    hay = f"{model_id} {name}".lower()
    if region == "cn_direct":
        tags_set.add("cn_direct")
    if is_free:
        tags_set.add("free")
    if any(k in hay for k in ("coder", "codex", "claude", "gpt-4", "gpt-5", "gpt-6", "deepseek", "qwen", "gemini", "llama-4")):
        if not any(audio_k in hay for audio_k in ("lyria", "whisper", "tts")):
            tags_set.add("coding")
    if any(k in hay for k in ("r1", "o1", "o3", "o4", "thinking", "reason", "opus", "sonnet", "qwen3-235b", "qwen3.5-plus", "hunyuan-t1", "gemini-2.5-pro")):
        tags_set.add("reasoning")

    config_key = infer_config_key(raw, region)
    affiliate_url = affiliates.get(config_key, DEFAULT_AFFILIATES["openrouter_url"])
    bonus_zh, bonus_en = channel_bonus_notes(config_key, is_free)

    default_base_map = {
        "aliyun_bailian_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "tencent_cps_url": "https://api.lkeap.cloud.tencent.com/v1",
        "siliconflow_invite_url": "https://api.siliconflow.cn/v1",
        "volcengine_ark_url": "https://ark.cn-beijing.volces.com/api/v3",
        "novita_affiliate_url": "https://api.novita.ai/openai",
        "openrouter_url": "https://openrouter.ai/api/v1",
    }
    api_base_url = str(raw.get("api_base_url") or default_base_map.get(config_key, "https://openrouter.ai/api/v1"))
    api_model_id = str(
        raw.get("api_model_id")
        or (
            model_id.split("/", 1)[-1]
            if region == "cn_direct" and not model_id.startswith("siliconflow/")
            else model_id.removeprefix("siliconflow/").removeprefix("novita/")
        )
    )
    cache_hit_factor = float(
        raw.get("cache_hit_factor", 0.2 if region == "cn_direct" and not is_free else (0.5 if not is_free else 1.0))
    )
    perf_note = str(raw.get("perf_note") or "")

    return {
        "id": model_id,
        "anchor_id": _model_anchor_id(model_id),
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
    """Returns (normalized_models, fx_rate, updated_date_str, source_label)."""
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
            print(f"⚠️ 读取 {live_path} 出错 ({exc})，自动启用内置模型保底数据集。")

    fallback_normalized = [normalize_model(m, affiliates, DEFAULT_FX_USD_TO_RMB) for m in FALLBACK_MODELS]
    return fallback_normalized, DEFAULT_FX_USD_TO_RMB, now_date, "builtin_15_fallback"


def load_quote_metadata(live_path: Path, force_fallback: bool = False) -> tuple[str, str]:
    """Return (quote_verified_date, last_live_verified_at) preserving last verified timestamp."""
    verified_date = pricing_core.QUOTE_VERIFIED_DATE
    last_live = verified_date
    if not force_fallback and live_path.exists():
        try:
            payload = json.loads(live_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                if payload.get("quote_verified_date"):
                    verified_date = str(payload["quote_verified_date"])[:10]
                if payload.get("last_live_verified_at"):
                    last_live = str(payload["last_live_verified_at"])[:19].replace("T", " ")
        except Exception:
            pass
    return verified_date, last_live


def load_price_changes(live_path: Path, force_fallback: bool = False) -> list[dict[str, Any]]:
    if force_fallback or not live_path.exists():
        return []
    try:
        payload = json.loads(live_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("price_changes"), list):
            return [dict(item) for item in payload["price_changes"] if isinstance(item, dict)]
    except Exception:
        pass
    return []


def load_official_rule_audit(live_path: Path, force_fallback: bool = False) -> dict[str, Any]:
    default_audit = {"checked_at": f"{pricing_core.QUOTE_VERIFIED_DATE}T00:00:00Z", "vendors": []}
    if force_fallback or not live_path.exists():
        return default_audit
    try:
        payload = json.loads(live_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("official_rule_audit"), dict):
            raw_audit = payload["official_rule_audit"]
            return {
                "checked_at": str(raw_audit.get("checked_at") or default_audit["checked_at"]),
                "vendors": [dict(v) for v in (raw_audit.get("vendors") or []) if isinstance(v, dict)],
            }
    except Exception:
        pass
    return default_audit


def load_coding_plans(
    live_path: Path,
    affiliates: dict[str, str],
    fx_rate: float,
    force_fallback: bool = False,
) -> list[dict[str, Any]]:
    raw_plans: list[dict[str, Any]] = []
    if not force_fallback and live_path.exists():
        try:
            payload = json.loads(live_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("coding_plans"), list):
                raw_plans = payload["coding_plans"]
        except Exception:
            raw_plans = []

    # Require v3 offer_type schema; otherwise fall back to pricing_core.get_offers_catalog()
    has_v3_schema = len(raw_plans) >= 4 and all(isinstance(p, dict) and "offer_type" in p for p in raw_plans)
    source_list = raw_plans if has_v3_schema else pricing_core.get_offers_catalog()

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


def build_ssr_coding_plan_tables_html(
    coding_plans: list[dict[str, Any]],
    affiliates: dict[str, str],
    quote_verified_date: str,
    models: list[dict[str, Any]] | None = None,
) -> str:
    """
    Compile static, JS-free HTML <table>s for Coding Plan official rules & worked examples
    using pricing_core so SSR output and JS/Coze/MCP math are guaranteed identical.
    """
    qwen_coder = next(
        (m for m in (models or []) if m.get("id") == "aliyun-bailian/qwen3-coder-next"),
        {"input_rmb_per_1m": 1.2, "output_rmb_per_1m": 4.8, "cache_hit_factor": 0.2},
    )
    qc_in = float(qwen_coder.get("input_rmb_per_1m") or 1.2)
    qc_out = float(qwen_coder.get("output_rmb_per_1m") or 4.8)
    qc_hit_factor = float(qwen_coder.get("cache_hit_factor") if qwen_coder.get("cache_hit_factor") is not None else 0.2)

    eval_5k = pricing_core.evaluate_coding_plans(
        daily_calls=5000,
        payg_monthly_rmb=768.0,
        usage_mode="interactive_ide",
    )
    bill_800 = pricing_core.calculate_token_bill(
        monthly_input_m=(800 * 30 * 4000) / 1_000_000,
        monthly_output_m=(800 * 30 * 1000) / 1_000_000,
        input_price_per_1m=qc_in,
        output_price_per_1m=qc_out,
        cache_hit_rate=0.5,
        cache_hit_factor=qc_hit_factor,
        reasoning_multiplier=1.0,
    )
    eval_800 = pricing_core.evaluate_coding_plans(
        daily_calls=800,
        payg_monthly_rmb=bill_800["total_cost"],
        usage_mode="interactive_ide",
    )
    bill_cache_demo = pricing_core.calculate_token_bill(
        monthly_input_m=1.0,
        monthly_output_m=0.0,
        input_price_per_1m=1.0,
        output_price_per_1m=4.0,
        cache_hit_rate=0.5,
        cache_hit_factor=0.2,
    )
    bill_team5 = pricing_core.calculate_token_bill(
        monthly_input_m=(6000 * 30 * 4000) / 1_000_000,
        monthly_output_m=(6000 * 30 * 1000) / 1_000_000,
        input_price_per_1m=qc_in,
        output_price_per_1m=qc_out,
        cache_hit_rate=0.5,
        cache_hit_factor=qc_hit_factor,
        reasoning_multiplier=1.0,
    )
    eval_team5 = pricing_core.evaluate_coding_plans(
        daily_calls=6000,
        payg_monthly_rmb=bill_team5["total_cost"],
        usage_mode="interactive_ide",
        model_id="aliyun-bailian/qwen3-coder-next",
        team_size=5,
    )
    team5_aliyun = next(
        p for p in eval_team5["eligible_subscriptions"] if p.get("plan_id") == "aliyun-coding-plan"
    )
    team5_first = float(team5_aliyun.get("first_month_rmb") or 199.5)
    team5_renew = float(team5_aliyun.get("renewal_rmb") or 1000.0)
    team5_save = float(team5_aliyun.get("renewal_savings_rmb") or (bill_team5["total_cost"] - team5_renew))

    plan_rows: list[str] = []
    for offer in coding_plans:
        if offer.get("offer_type") != "subscription":
            continue
        vendor_esc = html.escape(str(offer.get("vendor") or offer.get("name")))
        src_url = html.escape(str(offer.get("official_source_url") or ""))
        raw_buy_url = str(offer.get("url") or offer.get("official_source_url") or "")
        buy_url = html.escape(raw_buy_url)
        buy_rel = (
            "noopener sponsored"
            if is_sponsored_link(
                raw_buy_url,
                str(offer.get("provider_config_key") or ""),
                str(offer.get("commission_status") or ""),
            )
            else "noopener"
        )
        ep_cc = ((offer.get("endpoints") or {}).get("claude_code") or {}).get("base_url", "见官方文档")
        ep_oai = ((offer.get("endpoints") or {}).get("openai_compat") or {}).get("base_url", "见官方文档")
        for tier in offer.get("tiers") or []:
            tier_name = html.escape(f"{offer.get('name')} · {tier.get('name')}")
            purchasable = bool(tier.get("purchasable"))
            status_txt = "开放新购" if purchasable else "已停止新购（仅存量续费）"
            first_rmb = tier.get("first_month_rmb")
            renewal_rmb = float(tier.get("renewal_rmb") or 0.0)
            if first_rmb is not None and purchasable:
                price_txt = f"新客首月 ¥{float(first_rmb):.2f} / 次月续费 ¥{renewal_rmb:.0f}/月"
            else:
                price_txt = f"目录原价 ¥{renewal_rmb:.0f}/月"
            q5h = f"{int(tier.get('quota_5h') or 0):,}"
            qwk = f"{int(tier.get('quota_weekly') or 0):,}"
            qmo = f"{int(tier.get('quota_monthly') or 0):,}"
            quota_txt = f"5h 限 {q5h} 次 / 周限 {qwk} 次 / 月限 {qmo} 次"
            ep_txt = f"Anthropic: {html.escape(ep_cc)}" + (
                f" | OpenAI兼容: {html.escape(ep_oai)}" if ep_oai != "见官方文档" else ""
            )
            plan_rows.append(
                f"<tr>"
                f"<td><strong>{tier_name}</strong><br><span class=\"table-sub\">{vendor_esc}</span></td>"
                f"<td>{html.escape(status_txt)}</td>"
                f"<td class=\"num-cell\">{html.escape(price_txt)}</td>"
                f"<td class=\"num-cell\">{html.escape(quota_txt)}</td>"
                f"<td class=\"mono-cell\">{ep_txt}</td>"
                f"<td><a href=\"{src_url}\" target=\"_blank\" rel=\"noopener\">官方套餐规则</a> · "
                f"<a href=\"{buy_url}\" target=\"_blank\" rel=\"{buy_rel}\">控制台入口</a></td>"
                f"</tr>"
            )

    non_sub_rows: list[str] = []
    type_labels = {
        "cloud_host": "云主机自建缓存网关（非包月Token）",
        "payg_pool": "按量付费API池（¥0月租）",
        "gateway_example": "海外统一按量网关（$0月租）",
    }
    for offer in coding_plans:
        otype = str(offer.get("offer_type") or "")
        if otype == "subscription":
            continue
        label = type_labels.get(otype, otype)
        src_url = html.escape(str(offer.get("official_source_url") or ""))
        raw_buy_url = str(offer.get("url") or offer.get("official_source_url") or "")
        buy_url = html.escape(raw_buy_url)
        buy_rel = (
            "noopener sponsored"
            if is_sponsored_link(
                raw_buy_url,
                str(offer.get("provider_config_key") or ""),
                str(offer.get("commission_status") or ""),
            )
            else "noopener"
        )
        price_str = (
            f"主机约 ¥{float(offer.get('monthly_rmb') or 68):.0f}/月起 + 未命中缓存 API 费"
            if otype == "cloud_host"
            else "¥0 月租 · 按实际 Token 消耗计费"
        )
        non_sub_rows.append(
            f"<tr>"
            f"<td><strong>{html.escape(str(offer.get('name')))}</strong></td>"
            f"<td>{html.escape(label)}</td>"
            f"<td class=\"num-cell\">{html.escape(price_str)}</td>"
            f"<td>支持交互式开发与非交互式自动化后端 API 服务</td>"
            f"<td class=\"mono-cell\">{html.escape(str(offer.get('commission_note_zh') or ''))}</td>"
            f"<td><a href=\"{src_url}\" target=\"_blank\" rel=\"noopener\">官方说明</a> · "
            f"<a href=\"{buy_url}\" target=\"_blank\" rel=\"{buy_rel}\" data-offer-id=\"{html.escape(str(offer.get('id')))}\">前往官网</a></td>"
            f"</tr>"
        )

    qver = html.escape(quote_verified_date)
    h5k = html.escape(eval_5k["headline_zh"])
    w800 = html.escape(eval_800["window_note_zh"])

    cp_sum_zh = f"展开官方规则与固定验算案例静态核对表（报价核验日：{qver} · 关闭 JS 亦可直接阅读）"
    cp_sum_en = f"Expand Static Official Rules & Worked Examples Reference Ledger (Quotes Verified: {qver} · No-JS Ready)"

    return f"""
      <details class="ssr-directory-details" open id="ssrCodingPlanDetails">
        <summary data-zh="{cp_sum_zh}" data-en="{html.escape(cp_sum_en)}">{cp_sum_zh}</summary>
        <div class="ssr-ledger-wrap" id="ssrCodingPlanLedger" style="margin-top:12px;">
          <div class="table-scroll">
            <table class="ssr-table" id="ssrOfficialPlansTable">
              <caption>2026 国内大厂个人 Coding Plan 订阅官方价格、额度窗口与专属端点核验表（报价核验日：{qver}；额度单位均为「模型 API 调用次数」，单次用户提问常触发 5～30 次模型调用）</caption>
              <thead>
                <tr>
                  <th scope="col">厂商与套餐档位</th>
                  <th scope="col">可购状态</th>
                  <th scope="col">首月价 / 续费原价</th>
                  <th scope="col">额度上限（5小时 / 周 / 月）</th>
                  <th scope="col">专属协议端点（勿混用通用按量端点）</th>
                  <th scope="col">官方规则依据</th>
                </tr>
              </thead>
              <tbody>
                {''.join(plan_rows)}
              </tbody>
            </table>
          </div>

          <div class="table-scroll" style="margin-top:14px;">
            <table class="ssr-table" id="ssrWorkedExamplesTable">
              <caption>典型开发场景可复算基准结论表（关闭 JavaScript 亦可直接核对）</caption>
              <thead>
                <tr>
                  <th scope="col">验算场景与输入条件</th>
                  <th scope="col">30 天折算用量与同模型按量账单</th>
                  <th scope="col">核验结论（首月 / 续费 / 超额边界）</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>案例 A：高频 Agent 编程（每天 5,000 次模型调用）</strong><br><span class="table-sub">交互式 IDE · 输入 4K / 输出 1K · 50% 缓存命中</span></td>
                  <td class="num-cell">150,000 次/月</td>
                  <td><strong>{h5k}</strong></td>
                </tr>
                <tr>
                  <td><strong>案例 B：常规独立开发（每天 800 次模型调用）</strong><br><span class="table-sub">对比 Qwen3-Coder-Next 同模型按量（输入 ¥{qc_in:g}/M，输出 ¥{qc_out:g}/M，50% 缓存命中）</span></td>
                  <td class="num-cell">24,000 次/月 · 同模型按量约 ¥{bill_800['total_cost']:.2f}/月</td>
                  <td>超出腾讯/火山 Lite 月上限（18,000 次），匹配 Pro 档（90,000 次/月）：百炼 Pro 首月 ¥39.90 可省 ¥{max(0.0, bill_800['total_cost'] - 39.90):.2f}，但次月恢复 ¥200/月续费后比按量贵 ¥{abs(bill_800['total_cost'] - 200.0):.2f}；{w800}</td>
                </tr>
                <tr>
                  <td><strong>案例 C：非交互式自动化后端 / 批处理 API（每天 1,000 次）</strong><br><span class="table-sub">生产业务接口 / 定时流水线 / 对外服务</span></td>
                  <td class="num-cell">30,000 次/月</td>
                  <td><strong>自动排除百炼、腾讯云与火山方舟个人 Coding Plan</strong>（官方条款明确仅限交互式编程工具，严禁用于自动化后端服务），应选按量付费池或云服务器自建缓存网关。</td>
                </tr>
                <tr>
                  <td><strong>案例 D：Prompt 缓存命中率拆分验算</strong><br><span class="table-sub">输入 100 万 Token · 普通输入单价 ¥1.0/M · 命中单价 ¥0.2/M · 命中率 50%</span></td>
                  <td class="num-cell">输入实付 ¥{bill_cache_demo['input_cost']:.2f}</td>
                  <td>未命中 50% 按 ¥1.0 计（¥0.50）＋ 命中 50% 按 ¥0.2 计（¥0.10）＝ <strong>¥{bill_cache_demo['total_cost']:.2f}</strong>，避免将全部输入误按 2 折计算。</td>
                </tr>
                <tr>
                  <td><strong>案例 E：5 人研发团队合规多席位采购（合计每天 6,000 次调用）</strong><br><span class="table-sub">5 个独立 IDE 席位 · 对比 Qwen3-Coder-Next 共享按量（输入 4K / 输出 1K · 50% 缓存命中）</span></td>
                  <td class="num-cell">180,000 次/月 · 团队共享按量约 ¥{bill_team5['total_cost']:,.2f}/月</td>
                  <td>一人一席配置 5 份独立 Pro（合计上限 450,000 次/月，严禁混用单个 <code>sk-sp-</code> 密钥）：百炼 5×Pro 新客首月 <strong>¥{team5_first:.2f}</strong>、续费 <strong>¥{team5_renew:,.0f}/月</strong>，续费月仍比纯按量净省 <strong>¥{team5_save:.2f}/月</strong>。</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="table-scroll" style="margin-top:14px;">
            <table class="ssr-table" id="ssrNonSubOffersTable">
              <caption>非包月替代方案对比表（云主机缓存网关 / 按量付费池 / 海外多模型路由 — 严禁与个人包月混同）</caption>
              <thead>
                <tr>
                  <th scope="col">方案名称</th>
                  <th scope="col">计费类别</th>
                  <th scope="col">费用结构</th>
                  <th scope="col">适用场景</th>
                  <th scope="col">推广与结算说明</th>
                  <th scope="col">入口</th>
                </tr>
              </thead>
              <tbody>
                {''.join(non_sub_rows)}
              </tbody>
            </table>
          </div>
        </div>
      </details>
    """


def build_ssr_models_table_html(
    models: list[dict[str, Any]],
    quote_verified_date: str,
    open_by_default: bool = False,
) -> str:
    """Render static HTML <table> of all models with #model-<slug> anchors for crawlers & No-JS users."""
    sorted_models = sorted(
        models,
        key=lambda m: (0 if m["region"] == "cn_direct" else 1, m["blended_rmb_per_1m"], m["id"]),
    )
    rows: list[str] = []
    for m in sorted_models:
        anchor = html.escape(m["anchor_id"])
        name_esc = html.escape(m["name"])
        id_esc = html.escape(m["id"])
        prov_esc = html.escape(m["provider"])
        reg_label = "国内直连 (RMB)" if m["region"] == "cn_direct" else "海外网关 (USD)"
        in_str = f"¥{m['input_rmb_per_1m']:.3f} (${m['input_usd_per_1m']:.3f})"
        out_str = f"¥{m['output_rmb_per_1m']:.3f} (${m['output_usd_per_1m']:.3f})"
        cache_pct = f"{int(round(float(m['cache_hit_factor']) * 100))}%"
        ctx_k = f"{int(m['context_length']) // 1000}K" if int(m["context_length"]) < 1_000_000 else f"{int(m['context_length']) / 1_000_000:.1f}M"
        raw_aff_url = str(m.get("affiliate_url") or "")
        aff_url = html.escape(raw_aff_url)
        aff_rel = (
            "noopener sponsored"
            if is_sponsored_link(raw_aff_url, str(m.get("provider_config_key") or ""))
            else "noopener"
        )
        rows.append(
            f'<tr id="{anchor}">'
            f'<td><a href="#{anchor}" class="anchor-link">{name_esc}</a><br><code class="table-code">{id_esc}</code></td>'
            f"<td>{prov_esc}<br><span class=\"table-sub\">{reg_label}</span></td>"
            f'<td class="num-cell">{html.escape(in_str)}</td>'
            f'<td class="num-cell">{html.escape(out_str)}</td>'
            f'<td class="num-cell">{html.escape(cache_pct)} 单价</td>'
            f'<td class="num-cell">{html.escape(ctx_k)}</td>'
            f'<td><a href="{aff_url}" target="_blank" rel="{aff_rel}">官方通道</a></td>'
            f"</tr>"
        )

    open_attr = " open" if open_by_default else ""
    qver = html.escape(quote_verified_date)
    dir_sum_zh = f"查阅全量 {len(sorted_models)} 款海内外模型静态核验价格表（报价核验日：{qver} · 支持页内 #model 锚点直链与无 JS 阅读）"
    dir_sum_en = f"Expand All {len(sorted_models)} Global & CN Models Static Price Ledger (Quotes Verified: {qver} · #model Anchor & No-JS Ready)"
    return f"""
      <details class="ssr-directory-details"{open_attr} id="ssrModelsDirectory">
        <summary data-zh="{dir_sum_zh}" data-en="{html.escape(dir_sum_en)}">{dir_sum_zh}</summary>
        <div class="table-scroll" style="margin-top:12px;">
          <table class="ssr-table" id="ssrAllModelsTable">
            <caption>全量 {len(sorted_models)} 款大模型输入/输出百万 Token 价格与缓存系数核验目录（核验日：{qver}）</caption>
            <thead>
              <tr>
                <th scope="col">模型名称与标准 ID</th>
                <th scope="col">服务商与区域</th>
                <th scope="col">输入单价 / 1M Tokens</th>
                <th scope="col">输出单价 / 1M Tokens</th>
                <th scope="col">缓存命中系数</th>
                <th scope="col">上下文窗口</th>
                <th scope="col">官方入口</th>
              </tr>
            </thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>
        </div>
      </details>
    """


def build_agent_guardian_main_html(base_prefix: str, quote_verified_date: str) -> str:
    """
    Build SSR HTML for /agent-guardian/ using strictly verified facts from Agent Guardian v3.20.0.
    Includes >= 4 structured comparison <table>s, 6 core capability pillars, and first-party
    offer_impression / affiliate_click conversion hooks.
    """
    calc_home = html.escape(base_prefix or "./")
    auditor_href = html.escape(f"{base_prefix}ai-coding-spend-auditor/")
    qver = html.escape(quote_verified_date)

    return f"""<section class="hero">
      <div class="hero-top">
        <div>
          <h1>
            <span data-i18n="heroTitleMain">Agent Guardian (v3.20.0)：</span><span class="hero-accent" data-i18n="heroTitleAccent">AI Agent 多账号零污染隔离与安全工作台</span>
          </h1>
          <p data-i18n="heroSubtitle">macOS Apple Silicon 原生（Rust 2021 + Swift Cocoa，MIT 开源）：并发隔离 Claude Code / Codex CLI / Gemini CLI / OpenCode 多账号，提供 XNU Seatbelt 与 Apple VZ 双模沙箱、Fail-Closed 502 零直连回退、403 出站域名防火墙与离线 5h 滚动额度雷达。</p>
          <div class="guardian-cta-row">
            <a href="#guardian-dmg-panel" class="guardian-cta-btn primary" data-offer-id="agent-guardian-mac-dmg" data-card-slot="guardian_hero_dmg" data-zh="获取 macOS Apple Silicon (v3.20.0) 安装指引" data-en="Get macOS Apple Silicon (v3.20.0) DMG Guide">获取 macOS Apple Silicon (v3.20.0) 安装指引</a>
            <a href="#guardian-waitlist-panel" class="guardian-cta-btn secondary" data-offer-id="agent-guardian-waitlist" data-card-slot="guardian_hero_waitlist" data-zh="源码构建 / 团队发行版意向登记" data-en="Source Build &amp; Team Release Intent">源码构建 / 团队发行版意向登记</a>
          </div>
          <div id="guardianIntentStatus" class="guardian-status-toast" role="status" hidden></div>
        </div>
        <nav class="quick-jumps" aria-label="Agent Guardian sections">
          <a href="#agBareCompareSection" class="jump-chip" data-zh="裸奔多号 vs 隔离台" data-en="Bare vs Isolated">裸奔多号 vs 隔离台</a>
          <a href="#agModeCompareSection" class="jump-chip" data-zh="Mode A vs Mode B" data-en="Mode A vs Mode B">Mode A vs Mode B</a>
          <a href="#agCliMatrixSection" class="jump-chip" data-zh="四大 CLI 矩阵" data-en="4-CLI Matrix">四大 CLI 矩阵</a>
          <a href="#agReleaseSection" class="jump-chip" data-zh="交付与快速上手" data-en="Install &amp; CLI">交付与快速上手</a>
          <a href="#faqSection" class="jump-chip" data-zh="安全与隔离 FAQ" data-en="Security FAQ">安全与隔离 FAQ</a>
        </nav>
      </div>

      <div class="guardian-pillar-grid">
        <article class="guardian-pillar-card">
          <h3 data-zh="1. 四大 CLI 隔离 + 零密钥 MCP 保险箱" data-en="1. 4-CLI Isolation + Zero-Key MCP Vault">1. 四大 CLI 隔离 + 零密钥 MCP 保险箱</h3>
          <p data-zh="同机并发运行 Claude Code / Codex CLI / Gemini CLI (GEMINI_CLI_HOME) / OpenCode (OPENCODE_HOME + XDG_* 保真实 HOME)；0700 目录与 0600 AES-256-GCM 凭据仓，支持 ag mcp vault-secrets 迁出明文密钥与 ag mcp quarantine 无损停用。" data-en="Run Claude Code, Codex CLI, Gemini CLI (GEMINI_CLI_HOME), and OpenCode (OPENCODE_HOME + XDG_* preserving real HOME) concurrently in 0700/0600 AES-256-GCM sandboxes; migrate plaintext MCP keys via ag mcp vault-secrets or disable safely via ag mcp quarantine.">同机并发运行 Claude Code / Codex CLI / Gemini CLI (GEMINI_CLI_HOME) / OpenCode (OPENCODE_HOME + XDG_* 保真实 HOME)；0700 目录与 0600 AES-256-GCM 凭据仓，支持 ag mcp vault-secrets 迁出明文密钥与 ag mcp quarantine 无损停用。</p>
        </article>
        <article class="guardian-pillar-card">
          <h3 data-zh="2. Fail-Closed 502 + 403 出站域名防火墙" data-en="2. Fail-Closed 502 + 403 Domain Firewall">2. Fail-Closed 502 + 403 出站域名防火墙</h3>
          <p data-zh="上游 SOCKS5 / HTTP CONNECT 共享统一截止时间，断线直返 502 Bad Gateway 绝不回退宿主宽带；内置 Mihomo 托管核心 (:17896..=17915) 与 ag doctor --probe-ai，支持零载荷 403 会话域名白名单（ai_and_git_only / ai_git_and_pkg）。" data-en="Unified deadline across upstream SOCKS5/HTTP CONNECT handshakes returns 502 Bad Gateway with zero direct fallback; built-in Mihomo Managed Core (:17896..=17915), ag doctor --probe-ai, and zero-payload 403 outbound domain allowlists (ai_and_git_only / ai_git_and_pkg).">上游 SOCKS5 / HTTP CONNECT 共享统一截止时间，断线直返 502 Bad Gateway 绝不回退宿主宽带；内置 Mihomo 托管核心 (:17896..=17915) 与 ag doctor --probe-ai，支持零载荷 403 会话域名白名单（ai_and_git_only / ai_git_and_pkg）。</p>
        </article>
        <article class="guardian-pillar-card">
          <h3 data-zh="3. XNU Seatbelt + Apple VZ 双模沙箱" data-en="3. XNU Seatbelt + Apple VZ Dual Sandbox">3. XNU Seatbelt + Apple VZ 双模沙箱</h3>
          <p data-zh="Mode A 零毫秒启动内核拦截非代理直连 Socket、禁读 ~/.ssh / ~/.aws / ~/.config/gh / Keychain 并写锁 .guardian.toml 与 .mcp.json；Mode B 为每个安全域启动独立 Apple VZ Linux VM 与 HostNetworkBroker 宿主帧级门禁。" data-en="Mode A boots in 0ms using macOS XNU Sandbox.kext to block direct sockets, deny reads to ~/.ssh, ~/.aws, ~/.config/gh &amp; Keychain, and write-lock .guardian.toml / .mcp.json; Mode B runs per-domain Apple VZ Linux VMs behind host frame-level filtering.">Mode A 零毫秒启动内核拦截非代理直连 Socket、禁读 ~/.ssh / ~/.aws / ~/.config/gh / Keychain 并写锁 .guardian.toml 与 .mcp.json；Mode B 为每个安全域启动独立 Apple VZ Linux VM 与 HostNetworkBroker 宿主帧级门禁。</p>
        </article>
        <article class="guardian-pillar-card">
          <h3 data-zh="4. 100% 离线缓存感知 5h 滚动额度雷达" data-en="4. 100% Offline Cache-Aware 5h Quota Radar">4. 100% 离线缓存感知 5h 滚动额度雷达</h3>
          <p data-zh="零联网只读解析 .jsonl / .json、Codex state_*.sqlite（提取 cached_input_tokens 90% 缓存折扣）与 OpenCode opencode.db，按 account_id / thread_id 去重，提供 14 天周环比预警、--smart 避峰换号与防公式注入 CSV 导出。" data-en="Offline read-only parsing of .jsonl/.json logs, Codex state_*.sqlite (90% cached_input_tokens discount), and OpenCode opencode.db with account_id/thread_id dedupe, 14-day WoW surge alerts, --smart failover, and formula-safe CSV export.">零联网只读解析 .jsonl / .json、Codex state_*.sqlite（提取 cached_input_tokens 90% 缓存折扣）与 OpenCode opencode.db，按 account_id / thread_id 去重，提供 14 天周环比预警、--smart 避峰换号与防公式注入 CSV 导出。</p>
        </article>
        <article class="guardian-pillar-card">
          <h3 data-zh="5. 工作区四维护栏与并行 Git Worktree" data-en="5. Workspace Guardrails &amp; Parallel Worktrees">5. 工作区四维护栏与并行 Git Worktree</h3>
          <p data-zh="内置 strict_core / balanced_dev / open_experiment 三档预设与 .guardian.toml 单调收窄校验；--worktree &lt;slug&gt; 自动隔离至 .ag-worktrees/&lt;repo&gt;/&lt;slug&gt;（分支 ag/&lt;slug&gt;），XNU 内核阻断篡改 main 或兄弟分支。" data-en="Ships strict_core / balanced_dev / open_experiment presets and monotonic .guardian.toml tightening; --worktree &lt;slug&gt; isolates into .ag-worktrees/&lt;repo&gt;/&lt;slug&gt; (branch ag/&lt;slug&gt;) with XNU locks preventing main or sibling branch tampering.">内置 strict_core / balanced_dev / open_experiment 三档预设与 .guardian.toml 单调收窄校验；--worktree &lt;slug&gt; 自动隔离至 .ag-worktrees/&lt;repo&gt;/&lt;slug&gt;（分支 ag/&lt;slug&gt;），XNU 内核阻断篡改 main 或兄弟分支。</p>
        </article>
        <article class="guardian-pillar-card">
          <h3 data-zh="6. 原生 Swift 桌面端与零弹窗静默运维" data-en="6. Native Swift Cocoa App &amp; Quiet Diagnostics">6. 原生 Swift 桌面端与零弹窗静默运维</h3>
          <p data-zh="Swift Cocoa + WKWebView 严格校验 /api/daemon/info 服务身份防伪握手，默认端口冲突自动协商 18765..=18779 / 18443..=18459；采用 1.1.1.1 字面 IP 防 DNS 泄漏探测，支持边沿锁存悬停单次「知道了」永久消音。" data-en="Swift Cocoa + WKWebView enforces /api/daemon/info anti-spoof handshake and conflict-free port negotiation (18765..=18779 / 18443..=18459); uses literal 1.1.1.1 probes to eliminate plaintext DNS leaks and replaces popup spam with edge-triggered dismissible cards.">Swift Cocoa + WKWebView 严格校验 /api/daemon/info 服务身份防伪握手，默认端口冲突自动协商 18765..=18779 / 18443..=18459；采用 1.1.1.1 字面 IP 防 DNS 泄漏探测，支持边沿锁存悬停单次「知道了」永久消音。</p>
        </article>
      </div>
    </section>

    <section class="section-block" id="agBareCompareSection">
      <div class="section-head">
        <h2 data-zh="1. 裸奔多账号切换 vs Agent Guardian (v3.20.0) 安全与可靠性对比" data-en="1. Bare Multi-Account Switching vs Agent Guardian (v3.20.0)">1. 裸奔多账号切换 vs Agent Guardian (v3.20.0) 安全与可靠性对比</h2>
        <p data-zh="以下全部对比条目均来自 v3.20.0 已实测架构边界（绝不虚标状态或依赖宿主机全局代理）。" data-en="Every capability row below reflects verified v3.20.0 architecture guarantees with honest status reporting.">以下全部对比条目均来自 v3.20.0 已实测架构边界（绝不虚标状态或依赖宿主机全局代理）。</p>
      </div>
      <div class="table-scroll">
        <table class="ssr-table" id="agBareVsGuardianTable">
          <caption data-zh="表 1：同机多账号运行 AI Coding CLI 时「裸奔环境变量」与「Agent Guardian 隔离工作台」核心差异（核验基线：{qver}）" data-en="Table 1: Bare CLI multi-account switching vs Agent Guardian v3.20.0 isolation workbench (Verified: {qver})">表 1：同机多账号运行 AI Coding CLI 时「裸奔环境变量」与「Agent Guardian 隔离工作台」核心差异（核验基线：{qver}）</caption>
          <thead>
            <tr>
              <th scope="col" data-zh="风险与工程维度" data-en="Risk &amp; Engineering Dimension">风险与工程维度</th>
              <th scope="col" data-zh="传统裸奔 / 手动切环境变量" data-en="Bare CLI / Manual Env Switching">传统裸奔 / 手动切环境变量</th>
              <th scope="col" data-zh="Agent Guardian (v3.20.0)" data-en="Agent Guardian (v3.20.0)">Agent Guardian (v3.20.0)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong data-zh="凭据目录与环境变量污染" data-en="Credential &amp; Env Pollution">凭据目录与环境变量污染</strong></td>
              <td data-zh="共享 ~/.claude / ~/.codex / ~/.gemini，残留 ANTHROPIC_API_KEY 或 OPENAI_API_KEY 极易串号或误走按量余额" data-en="Shared ~/.claude / ~/.codex / ~/.gemini dirs; stale API key env vars easily cross-contaminate profiles">共享 ~/.claude / ~/.codex / ~/.gemini，残留 ANTHROPIC_API_KEY 或 OPENAI_API_KEY 极易串号或误走按量余额</td>
              <td data-zh="每账号独立 0700 目录 + 0600 保险箱（Keychain + AES-256-GCM），启动前自动清洗宿主残留 Key，支持两阶段可恢复删号" data-en="Isolated 0700 profile dirs + 0600 Keychain &amp; AES-256-GCM vault; scrubs host API keys before spawn and supports 2-stage recoverable deletion">每账号独立 0700 目录 + 0600 保险箱（Keychain + AES-256-GCM），启动前自动清洗宿主残留 Key，支持两阶段可恢复删号</td>
            </tr>
            <tr>
              <td><strong data-zh="代理断流与直连泄漏" data-en="Proxy Drop &amp; Direct Fallback">代理断流与直连泄漏</strong></td>
              <td data-zh="VPN 断开或端口变更时，CLI 静默回退宿主机物理宽带直连，暴露真实 IP 与时区" data-en="Silent fallback to physical host broadband on VPN drop, exposing host IP and mismatched locale">VPN 断开或端口变更时，CLI 静默回退宿主机物理宽带直连，暴露真实 IP 与时区</td>
              <td data-zh="Fail-Closed 502 硬熔断（X-Claude-Guardian-Fail-Closed: 1）严禁直连回退；Stealth 自动对齐实测出口国家 TZ / LANG / LC_CTYPE" data-en="Fail-Closed 502 (X-Claude-Guardian-Fail-Closed: 1) severs stream with zero direct fallback; Stealth aligns TZ / LANG / LC_CTYPE to probed egress country">Fail-Closed 502 硬熔断（X-Claude-Guardian-Fail-Closed: 1）严禁直连回退；Stealth 自动对齐实测出口国家 TZ / LANG / LC_CTYPE</td>
            </tr>
            <tr>
              <td><strong data-zh="未授权外联与密钥外泄" data-en="Unauthorized Egress &amp; Secret Exfil">未授权外联与密钥外泄</strong></td>
              <td data-zh="受管 Agent 可直接访问 ~/.ssh、~/.aws、Keychain 或将源码发往任意第三方 webhook" data-en="Agent subprocesses can read ~/.ssh, ~/.aws, Keychain, or exfiltrate payloads to arbitrary webhooks">受管 Agent 可直接访问 ~/.ssh、~/.aws、Keychain 或将源码发往任意第三方 webhook</td>
              <td data-zh="XNU 内核禁读敏感凭证目录 + 控制面文件不可变写锁 + 零载荷 403 出站域名防火墙（ai_and_git_only / 自定义黑名单）" data-en="XNU kernel blocks ~/.ssh, ~/.aws &amp; Keychain reads, write-locks control files, and enforces zero-payload 403 domain allowlists/blocklists">XNU 内核禁读敏感凭证目录 + 控制面文件不可变写锁 + 零载荷 403 出站域名防火墙（ai_and_git_only / 自定义黑名单）</td>
            </tr>
            <tr>
              <td><strong data-zh="5h 滚动额度与并行分支" data-en="5h Rolling Quota &amp; Parallel Worktree">5h 滚动额度与并行分支</strong></td>
              <td data-zh="手工估测是否接近 5h 限额；同目录多 Agent 并发改文件极易互相覆盖或污染 main" data-en="Guessing 5h limits manually; concurrent agents in one checkout overwrite files or mutate main">手工估测是否接近 5h 限额；同目录多 Agent 并发改文件极易互相覆盖或污染 main</td>
              <td data-zh="100% 离线 5h 雷达（含 Codex 90% 缓存折扣）+ --smart 避峰换号 + --worktree 内核收窄防篡改 main/兄弟分支" data-en="100% offline 5h radar (with Codex 90% cache discount), --smart failover, and --worktree XNU lock protecting main &amp; sibling branches">100% 离线 5h 雷达（含 Codex 90% 缓存折扣）+ --smart 避峰换号 + --worktree 内核收窄防篡改 main/兄弟分支</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="section-block" id="agModeCompareSection">
      <div class="section-head">
        <h2 data-zh="2. Mode A (XNU Seatbelt) vs Mode B (Apple VZ + HostNetworkBroker) 双模架构对比" data-en="2. Mode A (XNU Seatbelt) vs Mode B (Apple VZ + HostNetworkBroker)">2. Mode A (XNU Seatbelt) vs Mode B (Apple VZ + HostNetworkBroker) 双模架构对比</h2>
        <p data-zh="支持日常高频编码与高敏源码审计按需切换，守护未验证连通性时绝不虚标 PROTECTED。" data-en="Switch between 0ms daily sandboxing and hardware-isolated Linux VMs without dishonest PROTECTED badges.">支持日常高频编码与高敏源码审计按需切换，守护未验证连通性时绝不虚标 PROTECTED。</p>
      </div>
      <div class="table-scroll">
        <table class="ssr-table" id="agModeCompareTable">
          <caption data-zh="表 2：Agent Guardian v3.20.0 双模强制隔离边界与适用场景对比" data-en="Table 2: Mode A vs Mode B enforcement boundaries and operational characteristics">表 2：Agent Guardian v3.20.0 双模强制隔离边界与适用场景对比</caption>
          <thead>
            <tr>
              <th scope="col" data-zh="技术指标" data-en="Architecture Aspect">技术指标</th>
              <th scope="col" data-zh="Mode A：XNU Seatbelt 内核沙箱（日常主力）" data-en="Mode A: XNU Seatbelt Kernel Sandbox (Daily Driver)">Mode A：XNU Seatbelt 内核沙箱（日常主力）</th>
              <th scope="col" data-zh="Mode B：Apple VZ + HostNetworkBroker（高敏隔离）" data-en="Mode B: Apple VZ + HostNetworkBroker (High-Sensitivity)">Mode B：Apple VZ + HostNetworkBroker（高敏隔离）</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong data-zh="底层隔离技术" data-en="Isolation Primitive">底层隔离技术</strong></td>
              <td data-zh="macOS XNU Sandbox.kext 内核强制策略（零 Root）" data-en="macOS XNU Sandbox.kext kernel mandatory policy (rootless)">macOS XNU Sandbox.kext 内核强制策略（零 Root）</td>
              <td data-zh="Apple Virtualization.framework Linux VM + 宿主用户态帧级门禁" data-en="Apple Virtualization.framework Linux VM + host user-space frame broker">Apple Virtualization.framework Linux VM + 宿主用户态帧级门禁</td>
            </tr>
            <tr>
              <td><strong data-zh="启动延迟与触发命令" data-en="Startup Latency &amp; Command">启动延迟与触发命令</strong></td>
              <td data-zh="零毫秒瞬时启动：ag claude / ag codex / ag gemini / ag opencode" data-en="0ms instant launch: ag claude / ag codex / ag gemini / ag opencode">零毫秒瞬时启动：ag claude / ag codex / ag gemini / ag opencode</td>
              <td data-zh="支持黄金基础 VM 秒级克隆（ag domain clone）与 ag exec --mode vm" data-en="Second-level clone from golden base VM (ag domain clone) + ag exec --mode vm">支持黄金基础 VM 秒级克隆（ag domain clone）与 ag exec --mode vm</td>
            </tr>
            <tr>
              <td><strong data-zh="网络旁路阻断方式" data-en="Network Bypass Blocking">网络旁路阻断方式</strong></td>
              <td data-zh="内核级阻断一切非本地受控代理网关（:8443）直连 Socket" data-en="Kernel-blocks all direct outbound sockets outside local proxy gateway (:8443)">内核级阻断一切非本地受控代理网关（:8443）直连 Socket</td>
              <td data-zh="独立 gn-&lt;domain&gt; 虚拟交换机，单网卡零默认路由、无 gvproxy NAT，公网 IP 直连与 UDP 帧物理丢弃" data-en="Dedicated gn-&lt;domain&gt; vSwitch, single NIC zero default route, no gvproxy NAT; direct public IP &amp; UDP frames dropped on host">独立 gn-&lt;domain&gt; 虚拟交换机，单网卡零默认路由、无 gvproxy NAT，公网 IP 直连与 UDP 帧物理丢弃</td>
            </tr>
            <tr>
              <td><strong data-zh="文件系统与控制面保护" data-en="Filesystem &amp; Control-Plane Lock">文件系统与控制面保护</strong></td>
              <td data-zh="禁读 ~/.ssh / ~/.aws / ~/.config/gh / Keychain；写锁 .guardian.toml、.mcp.json、.claude/settings*.json 等" data-en="Denies ~/.ssh, ~/.aws, ~/.config/gh &amp; Keychain; write-locks .guardian.toml, .mcp.json, .claude/settings*.json">禁读 ~/.ssh / ~/.aws / ~/.config/gh / Keychain；写锁 .guardian.toml、.mcp.json、.claude/settings*.json 等</td>
              <td data-zh="工作区按白名单授权挂载、强制 .git 只读选项、自动回收 Guest NOPASSWD 免密 sudo" data-en="Allowlisted workspace mounts, forced .git read-only option, and automatic Guest NOPASSWD sudo revocation">工作区按白名单授权挂载、强制 .git 只读选项、自动回收 Guest NOPASSWD 免密 sudo</td>
            </tr>
            <tr>
              <td><strong data-zh="诚实健康探针" data-en="Honest Liveness Probe">诚实健康探针</strong></td>
              <td data-zh="非阻塞 flock 锁 + :8443 TCP 探活，离线诚实报告 OFFLINE" data-en="Non-blocking flock + :8443 TCP probe; reports OFFLINE when daemon is stopped">非阻塞 flock 锁 + :8443 TCP 探活，离线诚实报告 OFFLINE</td>
              <td data-zh="仅当受管 guardian-&lt;domain&gt; VM 通过 verified_roundtrips &gt; 0 才亮 PROTECTED，否则报告 DEGRADED" data-en="Reports PROTECTED only when managed guardian-&lt;domain&gt; VM passes verified_roundtrips &gt; 0; otherwise DEGRADED">仅当受管 guardian-&lt;domain&gt; VM 通过 verified_roundtrips &gt; 0 才亮 PROTECTED，否则报告 DEGRADED</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="section-block" id="agCliMatrixSection">
      <div class="section-head">
        <h2 data-zh="3. 四大 AI CLI 支持与离线审计矩阵" data-en="3. 4-CLI Isolation, MCP Vault &amp; Offline Radar Matrix">3. 四大 AI CLI 支持与离线审计矩阵</h2>
        <p data-zh="覆盖主流终端 AI 编程工具的隔离环境变量、MCP 密钥托管与 5h 离线用量数据源。" data-en="Isolation paths, MCP secret injection formats, and offline 5h usage data sources across all 4 supported CLIs.">覆盖主流终端 AI 编程工具的隔离环境变量、MCP 密钥托管与 5h 离线用量数据源。</p>
      </div>
      <div class="table-scroll">
        <table class="ssr-table" id="agCliMatrixTable">
          <caption data-zh="表 3：Agent Guardian v3.20.0 对 Claude Code、Codex CLI、Gemini CLI 与 OpenCode 的全链路适配规格" data-en="Table 3: Full-stack support matrix for Claude Code, Codex CLI, Gemini CLI, and OpenCode">表 3：Agent Guardian v3.20.0 对 Claude Code、Codex CLI、Gemini CLI 与 OpenCode 的全链路适配规格</caption>
          <thead>
            <tr>
              <th scope="col" data-zh="受管客户端" data-en="Managed CLI">受管客户端</th>
              <th scope="col" data-zh="隔离目录与环境变量机制" data-en="Profile &amp; Env Isolation">隔离目录与环境变量机制</th>
              <th scope="col" data-zh="MCP 保险箱动态占位符" data-en="MCP Vault Dynamic Syntax">MCP 保险箱动态占位符</th>
              <th scope="col" data-zh="离线 5h 额度数据源与特殊适配" data-en="Offline 5h Radar &amp; Special Adapter">离线 5h 额度数据源与特殊适配</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Claude Code</strong><br><span class="table-sub">ag claude</span></td>
              <td class="mono-cell">CLAUDE_CONFIG_DIR + 0700 目录（自动清洗宿主 ANTHROPIC_API_KEY）</td>
              <td class="mono-cell">${{VAR}} + mcp_vault/&lt;account&gt;.enc</td>
              <td data-zh="只读 .jsonl 会话日志 + 增量游标缓存 + --worktree / --smart 避峰换号" data-en="Read-only .jsonl logs + incremental cursor cache + --worktree / --smart failover">只读 .jsonl 会话日志 + 增量游标缓存 + --worktree / --smart 避峰换号</td>
            </tr>
            <tr>
              <td><strong>OpenAI Codex CLI</strong><br><span class="table-sub">ag codex</span></td>
              <td class="mono-cell">CODEX_HOME + 0700 目录（无损保留 config.toml 嵌套子表）</td>
              <td class="mono-cell">env_vars + mcp_vault/&lt;account&gt;.enc</td>
              <td data-zh="state_*.sqlite 只读解析（90% cached_input_tokens 折扣）+ auth.json.bak 0600 桌面原子交接 + ag desktop doctor Fake-IP 排障" data-en="state_*.sqlite read-only parsing (90% cached_input_tokens discount) + 0600 auth.json.bak desktop handoff + ag desktop doctor Fake-IP diagnostics">state_*.sqlite 只读解析（90% cached_input_tokens 折扣）+ 0600 auth.json.bak 桌面原子交接 + ag desktop doctor Fake-IP 排障</td>
            </tr>
            <tr>
              <td><strong>Google Gemini CLI</strong><br><span class="table-sub">ag gemini</span></td>
              <td class="mono-cell">GEMINI_CLI_HOME（独立隔离 .gemini，不碰宿主全局目录）</td>
              <td class="mono-cell">${{VAR}} + mcp_vault/&lt;account&gt;.enc</td>
              <td data-zh="本地会话日志解析 + 内置 xterm.js 一键 OAuth 登录核验入库 + Stealth TZ/LANG 对齐" data-en="Local session log parsing + built-in xterm.js OAuth login verification + Stealth TZ/LANG alignment">本地会话日志解析 + 内置 xterm.js 一键 OAuth 登录核验入库 + Stealth TZ/LANG 对齐</td>
            </tr>
            <tr>
              <td><strong>OpenCode</strong><br><span class="table-sub">ag opencode</span></td>
              <td class="mono-cell">OPENCODE_HOME + XDG_*（完整保留真实 $HOME）</td>
              <td class="mono-cell">{{env:VAR}} + 原生 opencode.jsonc 解析</td>
              <td data-zh="opencode.db SQLite 只读聚合 + 字符串感知 JSONC 解析（保留注释与尾随逗号）" data-en="opencode.db SQLite read-only aggregation + string-aware JSONC parser (preserves comments &amp; trailing commas)">opencode.db SQLite 只读聚合 + 字符串感知 JSONC 解析（保留注释与尾随逗号）</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="section-block" id="agReleaseSection">
      <div class="section-head">
        <h2 data-zh="4. Agent Guardian v3.20.0 交付形态、高频命令与源码构建矩阵" data-en="4. Distribution, CLI Quick Reference &amp; Source Build Matrix">4. Agent Guardian v3.20.0 交付形态、高频命令与源码构建矩阵</h2>
        <p data-zh="MIT 开源协议，支持 Apple Silicon 原生 DMG、Homebrew Cask 与 Rust 2021 + Swift Cocoa 离线自编译。" data-en="Licensed under MIT; available as macOS Apple Silicon DMG, Homebrew Cask recipe, or offline Rust 2021 + Swift Cocoa source build.">MIT 开源协议，支持 Apple Silicon 原生 DMG、Homebrew Cask 与 Rust 2021 + Swift Cocoa 离线自编译。</p>
      </div>
      <div class="table-scroll">
        <table class="ssr-table" id="agReleaseMatrixTable">
          <caption data-zh="表 4：Agent Guardian v3.20.0 交付包、工作区护栏预设与本地校验入口" data-en="Table 4: Agent Guardian v3.20.0 distribution artifacts, presets, and local verification gates">表 4：Agent Guardian v3.20.0 交付包、工作区护栏预设与本地校验入口</caption>
          <thead>
            <tr>
              <th scope="col" data-zh="交付形态 / 模块" data-en="Artifact / Module">交付形态 / 模块</th>
              <th scope="col" data-zh="文件路径或核心命令" data-en="Artifact Path or Command">文件路径或核心命令</th>
              <th scope="col" data-zh="关键约束与校验方式" data-en="Guarantees &amp; Verification">关键约束与校验方式</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong data-zh="macOS 原生桌面端 DMG" data-en="Native macOS Desktop DMG">macOS 原生桌面端 DMG</strong></td>
              <td class="mono-cell">dist/Agent-Guardian-3.20.0-arm64.dmg</td>
              <td data-zh="Swift Cocoa + WKWebView，拖入 /Applications 即用；内置默认 0700 体验沙箱，无需先建账号即可启动" data-en="Swift Cocoa + WKWebView; drag to /Applications; includes default 0700 sandbox terminal for instant Day-0 trial">Swift Cocoa + WKWebView，拖入 /Applications 即用；内置默认 0700 体验沙箱，无需先建账号即可启动</td>
            </tr>
            <tr>
              <td><strong data-zh="Homebrew Cask 配方" data-en="Homebrew Cask Recipe">Homebrew Cask 配方</strong></td>
              <td class="mono-cell">packaging/homebrew/Cask/agent-guardian.rb</td>
              <td data-zh="通过 scripts/generate_homebrew_cask.sh 与 ag release-check 自动校验版本号与 DMG SHA-256 一致性" data-en="Version &amp; SHA-256 parity verified via scripts/generate_homebrew_cask.sh and ag release-check">通过 scripts/generate_homebrew_cask.sh 与 ag release-check 自动校验版本号与 DMG SHA-256 一致性</td>
            </tr>
            <tr>
              <td><strong data-zh="终端零污染 Shell Hook" data-en="Zero-Pollution Shell Hook">终端零污染 Shell Hook</strong></td>
              <td class="mono-cell">eval "$(ag shell-hook zsh)"</td>
              <td data-zh="提供 ag / ag-claude / ag-codex / ag-gemini / ag-opencode，离开绑定目录自动 unset，绝不污染全局代理" data-en="Provides ag / ag-claude / ag-codex / ag-gemini / ag-opencode; auto-unsets outside bound workspaces">提供 ag / ag-claude / ag-codex / ag-gemini / ag-opencode，离开绑定目录自动 unset，绝不污染全局代理</td>
            </tr>
            <tr>
              <td><strong data-zh="全量离线测试与发版自检" data-en="Offline Tests &amp; Release Check">全量离线测试与发版自检</strong></td>
              <td class="mono-cell">cargo test --locked --offline &amp;&amp; ag release-check</td>
              <td data-zh="自动隔离临时目录运行测试，绝不触碰本机 ~/.agent-guardian；核验 Entitlements 与签名边界" data-en="Runs in isolated temp dirs without touching ~/.agent-guardian; verifies Entitlements and signing boundaries">自动隔离临时目录运行测试，绝不触碰本机 ~/.agent-guardian；核验 Entitlements 与签名边界</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="guardian-action-grid">
        <article class="guardian-action-card" id="guardian-dmg-panel" data-offer-id="agent-guardian-mac-dmg" data-card-slot="guardian_dmg_card">
          <div class="partner-title">
            <span data-zh="macOS Apple Silicon (v3.20.0) 快速启用" data-en="macOS Apple Silicon (v3.20.0) Quick Setup">macOS Apple Silicon (v3.20.0) 快速启用</span>
            <span class="badge badge-save">macOS arm64 · MIT</span>
          </div>
          <p class="partner-desc" data-zh="拖入 /Applications 后，将以下两行写入 ~/.zshrc 即可启用零污染 ag 终端命令，并在守护未运行时自动按需唤醒：" data-en="After dragging Agent Guardian.app into /Applications, add these two lines to ~/.zshrc to enable zero-pollution ag commands with on-demand daemon auto-bootstrap:">拖入 /Applications 后，将以下两行写入 ~/.zshrc 即可启用零污染 ag 终端命令，并在守护未运行时自动按需唤醒：</p>
          <pre class="cfg-code-block" id="agZshHookCode">export PATH="$HOME/.local/bin:/Applications/Agent Guardian.app/Contents/MacOS:$PATH"
eval "$(ag shell-hook zsh)"</pre>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button type="button" class="cta-copy-cfg" style="flex:1 1 180px;" data-copy-target="#agZshHookCode" data-copy-slot="guardian_zsh_hook" data-zh="复制 ~/.zshrc 配置片段" data-en="Copy ~/.zshrc Hook Snippet">复制 ~/.zshrc 配置片段</button>
            <a href="#agCliQuickCmds" class="guardian-cta-btn primary" style="flex:1 1 180px;" data-offer-id="agent-guardian-mac-dmg" data-card-slot="guardian_dmg_card" data-zh="确认 DMG 接入步骤" data-en="Use DMG Setup Guide">确认 DMG 接入步骤</a>
          </div>
        </article>

        <article class="guardian-action-card" id="guardian-waitlist-panel" data-offer-id="agent-guardian-waitlist" data-card-slot="guardian_waitlist_card">
          <div class="partner-title">
            <span data-zh="源码自编译 &amp; 团队发行意向记录" data-en="Source Build &amp; Team Release Intent">源码自编译 &amp; 团队发行意向记录</span>
            <span class="badge badge-global">Rust 2021 + Swift</span>
          </div>
          <p class="partner-desc" data-zh="支持完全离线校验与打包（cargo test --locked --offline 与 package_commercial_dmg.sh）；若需团队策略模板或 Linux/CI 版优先通知，可点击下方按钮记录意向：" data-en="Build and verify 100% offline (cargo test --locked --offline &amp; package_commercial_dmg.sh). Click below to record team/release interest or copy the full build pipeline:">支持完全离线校验与打包（cargo test --locked --offline 与 package_commercial_dmg.sh）；若需团队策略模板或 Linux/CI 版优先通知，可点击下方按钮记录意向：</p>
          <pre class="cfg-code-block" id="agSourceBuildCode">python3 scripts/build_ui_v3.py &amp;&amp; cargo test --locked --offline
bash scripts/build_mac_app.sh &amp;&amp; bash scripts/package_commercial_dmg.sh</pre>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button type="button" class="cta-copy-cfg" style="flex:1 1 180px;" data-copy-target="#agSourceBuildCode" data-copy-slot="guardian_source_build" data-zh="复制构建与离线测试命令" data-en="Copy Build &amp; Test Commands">复制构建与离线测试命令</button>
            <button type="button" class="guardian-cta-btn secondary" style="flex:1 1 180px;" data-offer-id="agent-guardian-waitlist" data-card-slot="guardian_waitlist_card" data-zh="登记 v3.20+ 发行与团队意向" data-en="Record Release / Team Intent">登记 v3.20+ 发行与团队意向</button>
          </div>
        </article>
      </div>

      <div class="panel" id="agCliQuickCmds" style="margin-top:14px;">
        <div class="panel-header">
          <div class="panel-title" data-zh="日常高频 ag CLI 实战命令速查" data-en="Daily High-Frequency ag CLI Cheat Sheet">日常高频 ag CLI 实战命令速查</div>
          <button type="button" class="icon-btn" data-copy-target="#agDailyCmdsBlock" data-copy-slot="guardian_daily_cmds" data-zh="复制常用命令" data-en="Copy CLI Commands">复制常用命令</button>
        </div>
        <pre class="cfg-code-block" id="agDailyCmdsBlock">ag status                                                   # Real daemon liveness &amp; 4-State check
ag claude --smart --worktree feat-auth                      # Offline 5h load failover + isolated Git worktree
ag workspace audit --fix-unmanaged --preset balanced_dev    # Zero-trust audit &amp; batch guardrail binding
ag mcp vault-secrets codex-plus                             # Move plaintext MCP keys into 0600 XNU vault
ag doctor --probe-ai                                        # Zero-key probe across 4 AI endpoints &amp; DNS leaks
ag workspace usage --export /tmp/ag-finops.csv              # Offline 5h/7d FinOps export (formula-safe CSV)</pre>
        <div class="guardian-companion-strip">
          <span data-zh="想先盘点过去 30 天本地 Claude / Codex / Antigravity / OpenCode 的真实 Token 花费并对比省钱模型？" data-en="Want to audit your last 30 days of local Claude / Codex / Antigravity / OpenCode spend and find cheaper API routes?">想先盘点过去 30 天本地 Claude / Codex / Antigravity / OpenCode 的真实 Token 花费并对比省钱模型？</span>
          <span>
            <a href="{auditor_href}" data-zh="打开海外账单体检台 (USD) →" data-en="Open Global Spend Auditor (USD) →">打开海外账单体检台 (USD) →</a>
            &nbsp;·&nbsp;
            <a href="{calc_home}" data-zh="国内模型 &amp; Coding Plan 比价 →" data-en="CN Models &amp; Coding Plan Calculator →">国内模型 &amp; Coding Plan 比价 →</a>
          </span>
        </div>
      </div>
    </section>"""


def _resolve_model_for_comparison(models: list[dict[str, Any]], candidates: list[str]) -> dict[str, Any]:
    """Resolve the best matching live or fallback model from the catalog for SSR comparison tables."""
    for cand in candidates:
        cand_low = cand.lower()
        exact = next((m for m in models if str(m.get("id") or "").lower() == cand_low), None)
        if exact is not None:
            return exact
    for cand in candidates:
        resolved, _ = pricing_core.resolve_model_query(models, cand)
        if resolved is not None:
            return resolved
    return models[0]


def build_deepseek_v4_vs_claude_sections(
    *,
    models: list[dict[str, Any]],
    fx_rate: float,
    quote_verified_date: str,
    last_live_verified_at: str,
    base_prefix: str,
) -> tuple[str, str]:
    """
    Build live-priced SSR HTML sections for /deepseek-v4-vs-claude-code/ using shared_data/models_live.json:
      - Upper section (3 <table>s): live unit pricing, 50% cache hit daily/monthly bills across 3 tiers,
        and PayG Routing vs Coding Plan decision matrix.
      - Bottom section (1 <table> + 2 action cards): local zero-upload audit CLI + Agent Guardian v3.20.0
        dual-account isolation guide (strictly grounded in verified Agent Guardian README facts).
    """
    ds_v4 = _resolve_model_for_comparison(
        models,
        ["deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4-flash", "tencent-cloud/deepseek-v3"],
    )
    claude_sonnet = _resolve_model_for_comparison(
        models,
        ["anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-4", "anthropic/claude-sonnet-5"],
    )
    qwen_coder = _resolve_model_for_comparison(
        models,
        ["aliyun-bailian/qwen3-coder-next", "novita/qwen/qwen3-coder-next"],
    )
    ds_v3_cn = _resolve_model_for_comparison(
        models,
        ["tencent-cloud/deepseek-v3", "siliconflow/deepseek-ai/DeepSeek-V3"],
    )

    compared = [
        ("DeepSeek V4.1 Flash (OpenRouter / API)", "DeepSeek V4.1 Flash (Global API)", ds_v4),
        ("Claude Sonnet (Claude Code 主力基准)", "Claude Sonnet (Claude Code Baseline)", claude_sonnet),
        ("Qwen3-Coder-Next (阿里云百炼直连)", "Qwen3-Coder-Next (Aliyun Direct)", qwen_coder),
        ("DeepSeek-V3.2 (腾讯云直连参考)", "DeepSeek-V3.2 (Tencent Direct Ref)", ds_v3_cn),
    ]

    # Pre-compute 50% cache hit unit & 3-tier daily/monthly bills via pricing_core
    claude_ref_bill = pricing_core.calculate_token_bill(
        monthly_input_m=(2500 * 30 * 4000) / 1_000_000,
        monthly_output_m=(2500 * 30 * 1000) / 1_000_000,
        input_price_per_1m=float(claude_sonnet["input_rmb_per_1m"]),
        output_price_per_1m=float(claude_sonnet["output_rmb_per_1m"]),
        cache_hit_rate=0.5,
        cache_hit_factor=float(claude_sonnet.get("cache_hit_factor") if claude_sonnet.get("cache_hit_factor") is not None else 0.5),
    )

    unit_rows_html: list[str] = []
    for role_zh, role_en, m in compared:
        in_rmb = float(m["input_rmb_per_1m"])
        out_rmb = float(m["output_rmb_per_1m"])
        in_usd = float(m["input_usd_per_1m"])
        out_usd = float(m["output_usd_per_1m"])
        hit_factor = float(m.get("cache_hit_factor") if m.get("cache_hit_factor") is not None else 0.5)
        ctx_len = int(m.get("context_length") or 128000)
        ctx_label = f"{ctx_len / 1_000_000:.2f}M" if ctx_len >= 1_000_000 else f"{ctx_len // 1000}K"

        # 1 call = 4,000 input + 1,000 output @ 50% cache hit
        per_1k_calls_rmb = pricing_core.calculate_token_bill(
            monthly_input_m=(1000 * 4000) / 1_000_000,
            monthly_output_m=(1000 * 1000) / 1_000_000,
            input_price_per_1m=in_rmb,
            output_price_per_1m=out_rmb,
            cache_hit_rate=0.5,
            cache_hit_factor=hit_factor,
        )["total_cost"]
        per_1k_calls_usd = per_1k_calls_rmb / fx_rate if fx_rate > 0 else 0.0

        main_mo_rmb = per_1k_calls_rmb * 75.0  # 2,500 calls/day * 30 = 75,000 calls/mo
        if m["id"] == claude_sonnet["id"]:
            ratio_zh = "基准 1.0x"
            ratio_en = "1.0x Baseline"
        elif main_mo_rmb > 0 and claude_ref_bill["total_cost"] > 0:
            mult = claude_ref_bill["total_cost"] / main_mo_rmb
            ratio_zh = f"便宜 {mult:.1f}x"
            ratio_en = f"{mult:.1f}x cheaper"
        else:
            ratio_zh = "--"
            ratio_en = "--"

        raw_aff = str(m.get("affiliate_url") or "")
        aff_rel = "noopener sponsored" if is_sponsored_link(raw_aff, str(m.get("provider_config_key") or "")) else "noopener"
        unit_rows_html.append(
            f"<tr>"
            f"<td><strong data-zh=\"{html.escape(role_zh)}\" data-en=\"{html.escape(role_en)}\">{html.escape(role_zh)}</strong>"
            f"<br><code class=\"table-code\">{html.escape(m['id'])}</code>"
            f"<br><span class=\"table-sub\">{html.escape(m['name'])}</span></td>"
            f"<td class=\"num-cell\">¥{in_rmb:.4f} / ¥{out_rmb:.4f}<br><span class=\"table-sub\">${in_usd:.4f} / ${out_usd:.4f}</span></td>"
            f"<td class=\"num-cell\">{int(round(hit_factor * 100))}%<br><span class=\"table-sub\">{ctx_label} ctx</span></td>"
            f"<td class=\"num-cell\">¥{per_1k_calls_rmb:.3f}<br><span class=\"table-sub\">${per_1k_calls_usd:.4f}</span></td>"
            f"<td class=\"num-cell\"><strong data-zh=\"{html.escape(ratio_zh)}\" data-en=\"{html.escape(ratio_en)}\">{html.escape(ratio_zh)}</strong></td>"
            f"<td><a href=\"{html.escape(raw_aff)}\" target=\"_blank\" rel=\"{aff_rel}\" data-zh=\"查看通道\" data-en=\"Open Channel\">查看通道</a></td>"
            f"</tr>"
        )

    workloads = [
        ("轻度独立开发 (800 次/天 · 2.4万次/月)", "Indie Dev (800/day · 24k/mo)", 800, 4000, 1000, "腾讯 Lite ¥40/月 (限1.8万超额) / 按量更灵活", "Exceeds Lite 18k cap; PayG stays flexible"),
        ("编程主力负载 (2,500 次/天 · 7.5万次/月)", "Core Coding IDE (2,500/day · 75k/mo)", 2500, 4000, 1000, "百炼 Pro 首月 ¥39.90 / 续费 ¥200 (限9万次)", "Bailian Pro ¥39.90 1st mo / ¥200 renewal (90k cap)"),
        ("重度 Agent 超限 (5,000 次/天 · 15万次/月)", "Heavy Agent Over-Cap (5,000/day · 150k/mo)", 5000, 4000, 1000, "超出单个 Pro 9万次上限 6万次（需按量/混合溢出）", "Exceeds Pro 90k cap by 60k (needs PayG / Hybrid)"),
    ]

    bill_rows_html: list[str] = []
    for w_zh, w_en, d_calls, in_tok, out_tok, plan_zh, plan_en in workloads:
        m_calls = d_calls * 30
        in_m = (m_calls * in_tok) / 1_000_000
        out_m = (m_calls * out_tok) / 1_000_000
        cells: list[str] = []
        for m in (ds_v4, claude_sonnet, qwen_coder):
            bill_rmb = pricing_core.calculate_token_bill(
                monthly_input_m=in_m,
                monthly_output_m=out_m,
                input_price_per_1m=float(m["input_rmb_per_1m"]),
                output_price_per_1m=float(m["output_rmb_per_1m"]),
                cache_hit_rate=0.5,
                cache_hit_factor=float(m.get("cache_hit_factor") if m.get("cache_hit_factor") is not None else 0.5),
            )["total_cost"]
            day_rmb = bill_rmb / 30.0
            bill_usd = bill_rmb / fx_rate if fx_rate > 0 else 0.0
            day_usd = day_rmb / fx_rate if fx_rate > 0 else 0.0
            cells.append(
                f"<td class=\"num-cell\"><strong>¥{day_rmb:.2f}/天</strong> · <strong>¥{bill_rmb:,.2f}/月</strong>"
                f"<br><span class=\"table-sub\">${day_usd:.2f}/day · ${bill_usd:,.2f}/mo</span></td>"
            )
        bill_rows_html.append(
            f"<tr>"
            f"<td><strong data-zh=\"{html.escape(w_zh)}\" data-en=\"{html.escape(w_en)}\">{html.escape(w_zh)}</strong>"
            f"<br><span class=\"table-sub\" data-zh=\"每次 {in_tok:,} 输入 + {out_tok:,} 输出 · 50% 缓存命中\" data-en=\"{in_tok:,} in + {out_tok:,} out / call · 50% cache hit\">每次 {in_tok:,} 输入 + {out_tok:,} 输出 · 50% 缓存命中</span></td>"
            f"{''.join(cells)}"
            f"<td data-zh=\"{html.escape(plan_zh)}\" data-en=\"{html.escape(plan_en)}\">{html.escape(plan_zh)}</td>"
            f"</tr>"
        )

    # Calculate 2,500 calls/day exact headline numbers for decision matrix copy
    ds_main_bill = pricing_core.calculate_token_bill(
        monthly_input_m=(2500 * 30 * 4000) / 1_000_000,
        monthly_output_m=(2500 * 30 * 1000) / 1_000_000,
        input_price_per_1m=float(ds_v4["input_rmb_per_1m"]),
        output_price_per_1m=float(ds_v4["output_rmb_per_1m"]),
        cache_hit_rate=0.5,
        cache_hit_factor=float(ds_v4.get("cache_hit_factor") if ds_v4.get("cache_hit_factor") is not None else 0.5),
    )["total_cost"]
    qwen_main_bill = pricing_core.calculate_token_bill(
        monthly_input_m=(2500 * 30 * 4000) / 1_000_000,
        monthly_output_m=(2500 * 30 * 1000) / 1_000_000,
        input_price_per_1m=float(qwen_coder["input_rmb_per_1m"]),
        output_price_per_1m=float(qwen_coder["output_rmb_per_1m"]),
        cache_hit_rate=0.5,
        cache_hit_factor=float(qwen_coder.get("cache_hit_factor") if qwen_coder.get("cache_hit_factor") is not None else 0.2),
    )["total_cost"]

    live_ts = html.escape((last_live_verified_at or quote_verified_date)[:19].replace("T", " "))
    qver = html.escape(quote_verified_date)
    guardian_href = html.escape(f"{base_prefix}agent-guardian/")
    auditor_href = html.escape(f"{base_prefix}ai-coding-spend-auditor/")
    coding_plan_href = html.escape(f"{base_prefix}coding-plan-2026/")

    upper_html = f"""
    <section class="section-block" id="dsV4LiveComparisonSection">
      <div class="section-head">
        <h2 data-zh="DeepSeek V4.1 Flash vs Claude Sonnet vs Qwen3-Coder-Next 实时比价与 50% 缓存账单" data-en="Live Pricing &amp; 50% Cache Bill Benchmark: DeepSeek V4.1 Flash vs Claude Sonnet vs Qwen3-Coder-Next">DeepSeek V4.1 Flash vs Claude Sonnet vs Qwen3-Coder-Next 实时比价与 50% 缓存账单</h2>
        <p data-zh="以下价格直接读取 shared_data/models_live.json（最近在线刷新：{live_ts} UTC；国内规则核验：{qver}），并采用与 /api/budget 完全一致的计费公式测算。" data-en="Rates rendered directly from shared_data/models_live.json (Live feed: {live_ts} UTC; CN rules verified: {qver}) using the exact /api/budget billing formula.">以下价格直接读取 shared_data/models_live.json（最近在线刷新：{live_ts} UTC；国内规则核验：{qver}），并采用与 /api/budget 完全一致的计费公式测算。</p>
      </div>

      <div class="table-scroll">
        <table class="ssr-table" id="dsV4LiveUnitPriceTable">
          <caption data-zh="表 1：实时模型单价、Prompt 缓存命中系数与千次编程调用（4K 输入 + 1K 输出 @ 50% 缓存命中）成本对比" data-en="Table 1: Live unit pricing, prompt-cache hit factor, and per-1,000 coding calls (4K in + 1K out @ 50% cache hit)">表 1：实时模型单价、Prompt 缓存命中系数与千次编程调用（4K 输入 + 1K 输出 @ 50% 缓存命中）成本对比</caption>
          <thead>
            <tr>
              <th scope="col" data-zh="模型定位与标准 ID" data-en="Model Role &amp; Standard ID">模型定位与标准 ID</th>
              <th scope="col" data-zh="输入 / 输出单价 (每 1M Tokens)" data-en="Input / Output Rate (per 1M)">输入 / 输出单价 (每 1M Tokens)</th>
              <th scope="col" data-zh="缓存系数与上下文" data-en="Cache Factor &amp; Context">缓存系数与上下文</th>
              <th scope="col" data-zh="每 1,000 次调用 (50% 缓存)" data-en="Per 1,000 Calls (50% Cache)">每 1,000 次调用 (50% 缓存)</th>
              <th scope="col" data-zh="相对 Claude Sonnet" data-en="vs Claude Sonnet">相对 Claude Sonnet</th>
              <th scope="col" data-zh="通道入口" data-en="Channel">通道入口</th>
            </tr>
          </thead>
          <tbody>
            {''.join(unit_rows_html)}
          </tbody>
        </table>
      </div>

      <div class="table-scroll" style="margin-top:14px;">
        <table class="ssr-table" id="dsV4MonthlyBillTable">
          <caption data-zh="表 2：50% Prompt 缓存命中下三档编程强度的「日账单与 30 天月账单」动态测算（均按每次 4,000 输入 + 1,000 输出）" data-en="Table 2: Daily &amp; 30-day monthly bills at 50% cache hit rate across 3 coding intensities (4K in + 1K out / call)">表 2：50% Prompt 缓存命中下三档编程强度的「日账单与 30 天月账单」动态测算（均按每次 4,000 输入 + 1,000 输出）</caption>
          <thead>
            <tr>
              <th scope="col" data-zh="编程负载档位" data-en="Workload Intensity">编程负载档位</th>
              <th scope="col" data-zh="DeepSeek V4.1 Flash (50% 缓存)" data-en="DeepSeek V4.1 Flash (50% Cache)">DeepSeek V4.1 Flash (50% 缓存)</th>
              <th scope="col" data-zh="Claude Sonnet (50% 缓存)" data-en="Claude Sonnet (50% Cache)">Claude Sonnet (50% 缓存)</th>
              <th scope="col" data-zh="Qwen3-Coder-Next (50% 缓存)" data-en="Qwen3-Coder-Next (50% 缓存)">Qwen3-Coder-Next (50% 缓存)</th>
              <th scope="col" data-zh="Coding Plan 包月参照" data-en="Coding Plan Benchmark">Coding Plan 包月参照</th>
            </tr>
          </thead>
          <tbody>
            {''.join(bill_rows_html)}
          </tbody>
        </table>
      </div>

      <div class="table-scroll" style="margin-top:14px;">
        <table class="ssr-table" id="dsV4PaygVsPlanTable">
          <caption data-zh="表 3：何时选「按量路由」vs「国内 Coding Plan 包月」vs「80/20 混合分层」决策矩阵" data-en="Table 3: Decision Matrix — When to choose PayG Routing vs Domestic Coding Plan vs 80/20 Hybrid">表 3：何时选「按量路由」vs「国内 Coding Plan 包月」vs「80/20 混合分层」决策矩阵</caption>
          <thead>
            <tr>
              <th scope="col" data-zh="研发场景与调用特征" data-en="Engineering Scenario">研发场景与调用特征</th>
              <th scope="col" data-zh="推荐计费路线" data-en="Recommended Route">推荐计费路线</th>
              <th scope="col" data-zh="量化算账依据（基于上方实时单价）" data-en="Quantitative Rationale (Live Rates)">量化算账依据（基于上方实时单价）</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong data-zh="主力高频编程但追求极致按量性价比（2,500 次/天）" data-en="High-Frequency Coding Optimizing PayG Cost (2,500/day)">主力高频编程但追求极致按量性价比（2,500 次/天）</strong></td>
              <td data-zh="按量路由（DeepSeek V4.1 Flash 主力 + 复杂任务切 Claude）" data-en="PayG Routing (DeepSeek V4.1 Flash + Claude for hard tasks)">按量路由（DeepSeek V4.1 Flash 主力 + 复杂任务切 Claude）</td>
              <td data-zh="DeepSeek V4.1 Flash 在 50% 缓存命中下月费仅约 ¥{ds_main_bill:.2f}（对比 Claude Sonnet 约 ¥{claude_ref_bill['total_cost']:,.2f}），无需被 ¥200/月包月续费绑定，且无 5h/周/月调用次数封顶。" data-en="DeepSeek V4.1 Flash costs ~¥{ds_main_bill:.2f}/mo at 50% cache hit (vs ~¥{claude_ref_bill['total_cost']:,.2f}/mo for Claude Sonnet), beating ¥200/mo Coding Plan renewals with zero 5h/monthly call caps.">DeepSeek V4.1 Flash 在 50% 缓存命中下月费仅约 ¥{ds_main_bill:.2f}（对比 Claude Sonnet 约 ¥{claude_ref_bill['total_cost']:,.2f}），无需被 ¥200/月包月续费绑定，且无 5h/周/月调用次数封顶。</td>
            </tr>
            <tr>
              <td><strong data-zh="重度使用 Qwen3-Coder-Next / 国产旗舰模型（月 3万～9万次内）" data-en="Heavy Qwen3-Coder-Next / CN IDE Usage (30k–90k/mo)">重度使用 Qwen3-Coder-Next / 国产旗舰模型（月 3万～9万次内）</strong></td>
              <td data-zh="交互式 IDE 选 Coding Plan Pro（首月 ¥39.90 / 续费 ¥200）" data-en="Coding Plan Pro for Interactive IDEs (¥39.90 1st mo / ¥200 renew)">交互式 IDE 选 Coding Plan Pro（首月 ¥39.90 / 续费 ¥200）</td>
              <td data-zh="7.5 万次/月下 Qwen3-Coder-Next 纯按量约 ¥{qwen_main_bill:,.2f}/月，百炼 Coding Plan Pro 首月 ¥39.90（续费 ¥200/月，限 90,000 次）显著省钱；注意在 Claude Code 中必须配置专属端点 sk-sp-，详见 Coding Plan 核验页。" data-en="At 75k calls/mo, Qwen3-Coder-Next PayG runs ~¥{qwen_main_bill:,.2f}/mo; Bailian Pro at ¥39.90 first month (¥200/mo renewal, 90k cap) saves substantially when paired with dedicated sk-sp- endpoints.">7.5 万次/月下 Qwen3-Coder-Next 纯按量约 ¥{qwen_main_bill:,.2f}/月，百炼 Coding Plan Pro 首月 ¥39.90（续费 ¥200/月，限 90,000 次）显著省钱；注意在 Claude Code 中必须配置专属端点 <code>sk-sp-</code>，详见 <a href="{coding_plan_href}" style="text-decoration:underline;">Coding Plan 核验页</a>。</td>
            </tr>
            <tr>
              <td><strong data-zh="自动化脚本 / CI Cron / 后端 API 或月超 90,000 次调用" data-en="Automated Scripts / CI Cron / Backend APIs or &gt;90k/mo">自动化脚本 / CI Cron / 后端 API 或月超 90,000 次调用</strong></td>
              <td data-zh="严禁买个人 Coding Plan · 仅用按量池或 LiteLLM 混合溢出" data-en="Never Buy Personal Plans · Use PayG Pool or Hybrid Overflow">严禁买个人 Coding Plan · 仅用按量池或 LiteLLM 混合溢出</td>
              <td data-zh="百炼、腾讯云与火山方舟个人套餐均限定仅用于交互式编程工具，非交互式脚本或代理池混用存在封号/限流风险；超 90,000 次的交互开发也应把超出部分路由至 DeepSeek V4.1 Flash / 按量 API。" data-en="Official Aliyun/Tencent/Volcengine personal plans prohibit non-interactive scripts, backend APIs, or shared keys; interactive workloads above 90,000 calls/mo should route overflow to DeepSeek V4.1 Flash / PayG APIs.">百炼、腾讯云与火山方舟个人套餐均限定仅用于交互式编程工具，非交互式脚本或代理池混用存在封号/限流风险；超 90,000 次的交互开发也应把超出部分路由至 DeepSeek V4.1 Flash / 按量 API。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>"""

    bottom_html = f"""
    <section class="section-block" id="dsV4AuditGuardianSection">
      <div class="section-head">
        <h2 data-zh="下一步实战闭环：先本地只读审计真实账单，再用 Agent Guardian 隔离双账号" data-en="Next Step: Audit Local Spend Read-Only First, Then Isolate Dual Accounts with Agent Guardian">下一步实战闭环：先本地只读审计真实账单，再用 Agent Guardian 隔离双账号</h2>
        <p data-zh="测算理论账单只是第一步。落地切换「Claude 官方号 + DeepSeek / 百炼按量号」时，先扫描本地真实缓存命中率与 5h 峰值，再在沙箱中隔离运行防串号与误走余额。" data-en="Theoretical math is step one. Before splitting workloads across Claude and DeepSeek/PayG accounts, audit your real local cache hit rate first, then isolate profiles against env leaks and wrong-key billing.">测算理论账单只是第一步。落地切换「Claude 官方号 + DeepSeek / 百炼按量号」时，先扫描本地真实缓存命中率与 5h 峰值，再在沙箱中隔离运行防串号与误走余额。</p>
      </div>

      <div class="table-scroll">
        <table class="ssr-table" id="dsV4AuditAndGuardianTable">
          <caption data-zh="表 4：从「本地账单体检」到「Agent Guardian v3.20.0 双账号零污染隔离」执行清单" data-en="Table 4: Execution Checklist — Local Zero-Upload Spend Audit + Agent Guardian v3.20.0 Dual-Account Isolation">表 4：从「本地账单体检」到「Agent Guardian v3.20.0 双账号零污染隔离」执行清单</caption>
          <thead>
            <tr>
              <th scope="col" data-zh="落地阶段" data-en="Stage">落地阶段</th>
              <th scope="col" data-zh="推荐工具与核心命令" data-en="Tool &amp; Key Command">推荐工具与核心命令</th>
              <th scope="col" data-zh="解决的真实工程风险（已核验能力）" data-en="Verified Engineering Guarantees">解决的真实工程风险（已核验能力）</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong data-zh="1. 本地零上传摸底" data-en="1. Zero-Upload Local Audit">1. 本地零上传摸底</strong></td>
              <td class="mono-cell">curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_ai_spend.py | python3 - --days 30</td>
              <td data-zh="100% 本地只读扫描 Claude Code、Codex (.jsonl.zst)、Antigravity、OpenCode (opencode.db)、Grok、WorkBuddy、Qwen 与 Cline，精准统计过去 30 天缓存命中率与稳态 5h 峰值，绝不上传源码或提示词。" data-en="100% read-only local scan across Claude Code, Codex (.jsonl.zst), Antigravity, OpenCode (opencode.db), Grok, WorkBuddy, Qwen &amp; Cline; reports true 30-day cache hits and 5h peaks with zero uploads.">100% 本地只读扫描 Claude Code、Codex (.jsonl.zst)、Antigravity、OpenCode (opencode.db)、Grok、WorkBuddy、Qwen 与 Cline，精准统计过去 30 天缓存命中率与稳态 5h 峰值，绝不上传源码或提示词。</td>
            </tr>
            <tr>
              <td><strong data-zh="2. 双账号零污染隔离" data-en="2. Zero-Pollution Dual Accounts">2. 双账号零污染隔离</strong></td>
              <td class="mono-cell">ag claude --smart --worktree feat-routing</td>
              <td data-zh="macOS Apple Silicon 原生 Agent Guardian (v3.20.0)：为每个 Claude Code / Codex / Gemini / OpenCode 账号分配独立 CLAUDE_CONFIG_DIR（0700 目录 + 0600 Keychain/AES-256-GCM 凭据仓），启动前自动清洗宿主残留 ANTHROPIC_API_KEY，彻底避免包月与按量串号误扣。" data-en="Agent Guardian (v3.20.0) on macOS Apple Silicon gives each Claude Code / Codex / Gemini / OpenCode profile an isolated CLAUDE_CONFIG_DIR (0700 dir + 0600 Keychain/AES-256-GCM vault) and scrubs residual host API keys before launch.">macOS Apple Silicon 原生 Agent Guardian (v3.20.0)：为每个 Claude Code / Codex / Gemini / OpenCode 账号分配独立 <code>CLAUDE_CONFIG_DIR</code>（<code>0700</code> 目录 + <code>0600</code> Keychain/AES-256-GCM 凭据仓），启动前自动清洗宿主残留 <code>ANTHROPIC_API_KEY</code>，彻底避免包月与按量串号误扣。</td>
            </tr>
            <tr>
              <td><strong data-zh="3. 断线防泄漏与出站门禁" data-en="3. Fail-Closed &amp; Domain Firewall">3. 断线防泄漏与出站门禁</strong></td>
              <td class="mono-cell">ag exec --mode vm --domain domain-default</td>
              <td data-zh="支持 XNU Seatbelt (Mode A，零毫秒启动) 与 Apple VZ + HostNetworkBroker (Mode B 硬件隔离)；代理断线直返 Fail-Closed 502 零直连回退，配合零载荷 403 出站域名防火墙与离线 5h 滚动额度雷达。" data-en="Supports XNU Seatbelt (Mode A, 0ms boot) and Apple VZ + HostNetworkBroker (Mode B); enforces Fail-Closed 502 zero direct broadband fallback, a zero-payload 403 domain firewall, and an offline 5h rolling quota radar.">支持 XNU Seatbelt (Mode A，零毫秒启动) 与 Apple VZ + HostNetworkBroker (Mode B 硬件隔离)；代理断线直返 Fail-Closed <code>502</code> 零直连回退，配合零载荷 <code>403</code> 出站域名防火墙与离线 5h 滚动额度雷达。</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="guardian-action-grid">
        <article class="guardian-action-card">
          <div class="partner-title">
            <span data-zh="第一步：一行命令导出本地 30 天真实账单" data-en="Step 1: Audit Local 30-Day Spend in One Command">第一步：一行命令导出本地 30 天真实账单</span>
            <span class="badge badge-save">Zero Upload · Stdlib</span>
          </div>
          <p class="partner-desc" data-zh="自动去重并识别真实 Prompt 缓存命中率，复制下方命令到终端运行后，再把结果粘贴回上方计算器核对最省路由：" data-en="Deduplicates local sessions and calculates your real cache hit rate. Run below, then compare routes in the calculator or Global Spend Auditor:">自动去重并识别真实 Prompt 缓存命中率，复制下方命令到终端运行后，再把结果粘贴回上方计算器核对最省路由：</p>
          <pre class="cfg-code-block" id="dsV4LocalAuditCmd">curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_ai_spend.py | python3 - --days 30</pre>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button type="button" class="cta-copy-cfg" style="flex:1 1 180px;" data-copy-target="#dsV4LocalAuditCmd" data-copy-slot="ds_v4_local_audit_cli" data-zh="复制 8 客户端本地审计命令" data-en="Copy 8-Client Local Audit CLI">复制 8 客户端本地审计命令</button>
            <a href="{auditor_href}" class="guardian-cta-btn secondary" style="flex:1 1 180px;" data-zh="打开海外账单体检页 (USD) →" data-en="Open Global Spend Auditor (USD) →">打开海外账单体检页 (USD) →</a>
          </div>
        </article>

        <article class="guardian-action-card" data-offer-id="agent-guardian-mac-dmg" data-card-slot="ds_v4_guardian_card">
          <div class="partner-title">
            <span data-zh="第二步：用 Agent Guardian 隔离双账号" data-en="Step 2: Isolate Dual Accounts with Agent Guardian">第二步：用 Agent Guardian 隔离双账号</span>
            <span class="badge badge-global">v3.20.0 · macOS arm64</span>
          </div>
          <p class="partner-desc" data-zh="同时维护「Claude 官方主力号 + DeepSeek/百炼按量号」时，使用 Agent Guardian 的 0700 独立目录、XNU Seatbelt 写锁与 Fail-Closed 502 防代理断线直连：" data-en="When running both an official Claude profile and a DeepSeek/PayG profile, use Agent Guardian's 0700 isolation, XNU Seatbelt control-plane locks, and Fail-Closed 502 proxy protection:">同时维护「Claude 官方主力号 + DeepSeek/百炼按量号」时，使用 Agent Guardian 的 <code>0700</code> 独立目录、XNU Seatbelt 写锁与 Fail-Closed <code>502</code> 防代理断线直连：</p>
          <pre class="cfg-code-block" id="dsV4GuardianQuickCmd">ag account add -i claude-us2 -p claude -a "Claude US #2" --tier pro --proxy 127.0.0.1:9674 --country US
ag claude --smart --worktree feat-deepseek-route</pre>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button type="button" class="cta-copy-cfg" style="flex:1 1 180px;" data-copy-target="#dsV4GuardianQuickCmd" data-copy-slot="ds_v4_guardian_cli" data-zh="复制双账号隔离命令" data-en="Copy Dual-Account CLI">复制双账号隔离命令</button>
            <a href="{guardian_href}" class="guardian-cta-btn primary" style="flex:1 1 180px;" data-offer-id="agent-guardian-mac-dmg" data-card-slot="ds_v4_guardian_cta" data-zh="查看 Agent Guardian 隔离台 →" data-en="Explore Agent Guardian Sandbox →">查看 Agent Guardian 隔离台 →</a>
          </div>
        </article>
      </div>
    </section>"""

    return upper_html, bottom_html


def build_status_badge_svg(quote_verified_date: str, total_models: int) -> str:
    left_text = "AI Cost Radar"
    right_text = f"报价核验 {quote_verified_date} · {total_models} models"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="310" height="20" role="img" aria-label="{html.escape(left_text)}: {html.escape(right_text)}">
  <title>{html.escape(left_text)}: {html.escape(right_text)}</title>
  <rect width="96" height="20" rx="3" fill="#1e293b"/>
  <rect x="96" width="214" height="20" rx="3" fill="#047857"/>
  <rect x="93" width="6" height="20" fill="#047857"/>
  <g fill="#ffffff" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="11">
    <text x="48" y="14" font-weight="600">{html.escape(left_text)}</text>
    <text x="203" y="14">{html.escape(right_text)}</text>
  </g>
</svg>
"""


def build_atom_feed_xml(
    site_url: str,
    build_date: str,
    quote_verified_date: str,
    total_models: int,
    price_changes: list[dict[str, Any]] | None = None,
) -> str:
    base = site_url.rstrip("/") + "/"
    feed_url = base + "feeds/price-changes.xml"
    cp_url = base + "coding-plan-2026/"
    ds_url = base + "deepseek-vs-qwen/"
    changes = price_changes or []
    feed_updated_iso = (
        str(changes[0].get("detected_at"))
        if changes and changes[0].get("detected_at")
        else f"{quote_verified_date}T00:00:00Z"
    )
    verified_iso = f"{quote_verified_date}T00:00:00Z"

    dynamic_entries_xml = ""
    for idx, chg in enumerate(changes[:12]):
        cid = str(chg.get("id") or f"change-{idx}")
        cname = str(chg.get("name") or cid)
        det_iso = str(chg.get("detected_at") or verified_iso)
        summary_zh = str(chg.get("summary_zh") or "")
        is_plan = chg.get("entity_type") == "coding_plan"
        is_rule_drift = chg.get("change_type") == "plan_rule_drift_warning"
        tag_prefix = "规则巡检预警" if is_rule_drift else "价格异动"
        target_href = cp_url if is_plan else f"{base}#{_model_anchor_id(cid)}"
        entry_id = f"{feed_url}#delta-{idx}-{re.sub(r'[^a-zA-Z0-9._-]+', '-', cid)}-{det_iso[:10]}"
        dynamic_entries_xml += f"""  <entry>
    <title>[{tag_prefix} {html.escape(det_iso[:10])}] {html.escape(cname)} ({html.escape(cid)})</title>
    <id>{html.escape(entry_id)}</id>
    <link href="{html.escape(target_href)}"/>
    <updated>{html.escape(det_iso)}</updated>
    <summary>{html.escape(summary_zh)}</summary>
  </entry>
"""

    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>智算省钱路由台 (AI Cost Radar) — 模型与 Coding Plan 价格核验更新订阅</title>
  <id>{html.escape(feed_url)}</id>
  <link href="{html.escape(feed_url)}" rel="self" type="application/atom+xml"/>
  <link href="{html.escape(base)}" rel="alternate" type="text/html"/>
  <updated>{html.escape(feed_updated_iso)}</updated>
  <author>
    <name>AI Cost Radar</name>
  </author>
{dynamic_entries_xml}  <entry>
    <title>[报价核验 {html.escape(quote_verified_date)}] 修正国内三大厂 Coding Plan 月上限 (90,000次/月) 与首购/续费价格口径</title>
    <id>{html.escape(cp_url)}#verified-{html.escape(quote_verified_date)}</id>
    <link href="{html.escape(cp_url)}"/>
    <updated>{html.escape(verified_iso)}</updated>
    <summary>核验阿里云百炼（Lite 停新购，Pro 首月 ¥39.90 / 续费 ¥200，上限 6,000/5h · 45,000/周 · 90,000/月）、腾讯云（Lite ¥40 限 18,000/月，Pro ¥200 限 90,000/月）与火山方舟官方规则，同步 {total_models} 款海内外模型报价（构建日 {html.escape(build_date)}）。</summary>
  </entry>
  <entry>
    <title>[计费模型升级 {html.escape(quote_verified_date)}] Prompt 缓存拆分为「命中率 × 命中单价」并新增思考倍率防重算保护</title>
    <id>{html.escape(ds_url)}#math-{html.escape(quote_verified_date)}</id>
    <link href="{html.escape(ds_url)}"/>
    <updated>{html.escape(verified_iso)}</updated>
    <summary>修正全量输入默认按命中价打折的偏差：支持 0%~85% 缓存命中率调节，并区分 Claude Code Anthropic 专属端点与通用按量端点。</summary>
  </entry>
</feed>
"""


def build_json_ld(
    site_url: str,
    updated_date: str,
    quote_verified_date: str,
    total_models: int,
    page_title: str,
    page_description: str,
    *,
    page_kind: str = "calculator",
    faq_entries: list[dict[str, str]] | None = None,
) -> tuple[str, str]:
    entries = faq_entries if faq_entries is not None else FAQ_ENTRIES
    if page_kind == "product_landing":
        webapp_ld = {
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": page_title,
            "url": site_url,
            "dateModified": updated_date,
            "softwareVersion": "3.20.0",
            "applicationCategory": "DeveloperApplication",
            "operatingSystem": "macOS 12+ (Apple Silicon arm64)",
            "license": "https://opensource.org/licenses/MIT",
            "inLanguage": ["zh-CN", "en"],
            "description": page_description,
            "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "USD",
            },
            "featureList": [
                "Concurrent Zero-Pollution Multi-Account Isolation for Claude Code, Codex CLI, Gemini CLI & OpenCode",
                "Dual-Mode Sandboxing: XNU Seatbelt (Mode A) & Apple VZ + HostNetworkBroker (Mode B)",
                "Fail-Closed 502 Zero Direct Broadband Fallback & 403 Zero-Payload Outbound Domain Firewall",
                "4-CLI Zero-Key MCP Secrets Vault (AES-256-GCM) & Quarantine",
                "100% Offline Cache-Aware 5h Rolling Quota Radar & Parallel Git Worktree Guardrails",
            ],
        }
    else:
        webapp_ld = {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": page_title,
            "url": site_url,
            "dateModified": updated_date,
            "schemaVersion": f"quote-verified-{quote_verified_date}",
            "applicationCategory": "DeveloperApplication",
            "operatingSystem": "All",
            "inLanguage": ["zh-CN", "en"],
            "description": page_description,
            "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "CNY",
            },
            "featureList": [
                f"Verified {total_models} Global & Domestic CN LLM API Pricing Table (No-JS SSR HTML)",
                "2026 Domestic Coding Plan Official Call Quota (90,000/mo Pro, 18,000/mo Lite) & First-Month vs Renewal Calculator",
                "Protocol-Specific Claude Code (Anthropic sk-sp-) vs OpenAI-Compatible Pay-As-You-Go Endpoint Generator",
                "Split Prompt Cache Hit-Rate Simulator & Adjustable Reasoning Multiplier",
                "Shareable Reproducible URLSearchParams Calculation Links",
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
            for item in entries
        ],
    }

    return safe_json_for_html_script(webapp_ld), safe_json_for_html_script(faq_ld)


def build_faq_html(faq_entries: list[dict[str, str]] | None = None) -> str:
    entries = faq_entries if faq_entries is not None else FAQ_ENTRIES
    blocks: list[str] = []
    for idx, item in enumerate(entries):
        open_attr = " open" if idx == 0 else ""
        q_esc = html.escape(item["q"])
        a_esc = html.escape(item["a"])
        q_en_esc = html.escape(item.get("q_en", item["q"]))
        a_en_esc = html.escape(item.get("a_en", item["a"]))
        blocks.append(
            f'<details class="faq-item"{open_attr}>'
            f'<summary data-zh="{q_esc}" data-en="{q_en_esc}">{q_esc}</summary>'
            f'<div class="faq-answer" data-zh="{a_esc}" data-en="{a_en_esc}">{a_esc}</div>'
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
    slug_i18n_map = {
        "": "navTopicRoot",
        "coding-plan-2026/": "navTopicCodingPlan",
        "deepseek-vs-qwen/": "navTopicDeepseekQwen",
        "deepseek-v4-vs-claude-code/": "navTopicDeepseekV4Claude",
        "claude-code-domestic/": "navTopicClaudeCode",
        "dify-openclaw-cloud-server/": "navTopicDifyHost",
        "ai-coding-spend-auditor/": "navTopicGlobalSpend",
        "agent-guardian/": "navTopicAgentGuardian",
    }
    links: list[str] = []
    for r in SEO_ROUTES:
        href = f"{base_prefix}{r['slug']}" if r["slug"] else (base_prefix or "./")
        cls = "seo-topic-link active" if r["slug"] == active_slug else "seo-topic-link"
        i18n_key = slug_i18n_map.get(r["slug"], "")
        i18n_attr = f' data-i18n="{i18n_key}"' if i18n_key else ""
        links.append(f'<a class="{cls}" href="{html.escape(href)}"{i18n_attr}>{html.escape(r["nav_label"])}</a>')
    return "\n          ".join(links)


def build_site(
    *,
    force_fallback: bool = False,
    site_url: str | None = None,
    dist_dir: Path | None = None,
    output_dir: Path | None = None,
    models_path: Path | None = None,
) -> dict[str, Any]:
    live_models_file = Path(models_path) if models_path is not None else LIVE_MODELS_PATH
    affiliates = load_affiliates(CONFIG_PATH)
    models, fx_rate, updated_date, source_label = load_models_dataset(
        live_models_file,
        affiliates,
        force_fallback=force_fallback,
    )
    quote_verified_date, last_live_verified_at = load_quote_metadata(live_models_file, force_fallback=force_fallback)
    price_changes = load_price_changes(live_models_file, force_fallback=force_fallback)
    official_rule_audit = load_official_rule_audit(live_models_file, force_fallback=force_fallback)
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    coding_plans = load_coding_plans(live_models_file, affiliates, fx_rate, force_fallback=force_fallback)

    resolved_site_url = (site_url or os.environ.get("SITE_BASE_URL") or DEFAULT_SITE_URL).strip()
    if not resolved_site_url.endswith("/"):
        resolved_site_url += "/"

    cn_count = sum(1 for m in models if m["region"] == "cn_direct")
    global_count = sum(1 for m in models if m["region"] == "global")
    faq_html = build_faq_html()
    ssr_coding_plan_tables_html = build_ssr_coding_plan_tables_html(
        coding_plans=coding_plans,
        affiliates=affiliates,
        quote_verified_date=quote_verified_date,
        models=models,
    )

    resolved_out = output_dir if output_dir is not None else dist_dir
    target_dist = Path(resolved_out) if resolved_out is not None else DIST_DIR
    target_dist.mkdir(parents=True, exist_ok=True)
    index_path = target_dist / "index.html"

    for route in SEO_ROUTES:
        slug = route["slug"]
        is_root = slug == ""
        base_prefix = "" if is_root else "../"
        route_canonical = resolved_site_url + slug
        route_key = "/" + slug
        page_kind = str(route.get("page_kind") or "calculator")
        is_product = page_kind == "product_landing"
        is_ds_v4_claude = slug == "deepseek-v4-vs-claude-code/"

        route_preset = dict(route["preset"])
        extra_ssr_section_html = ""
        extra_bottom_section_html = ""
        if is_ds_v4_claude:
            ds_m = _resolve_model_for_comparison(
                models, ["deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4-flash", "tencent-cloud/deepseek-v3"]
            )
            cl_m = _resolve_model_for_comparison(
                models, ["anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-4", "anthropic/claude-sonnet-5"]
            )
            qw_m = _resolve_model_for_comparison(
                models, ["aliyun-bailian/qwen3-coder-next", "novita/qwen/qwen3-coder-next"]
            )
            route_preset["baselineId"] = cl_m["id"]
            route_preset["compareIds"] = [ds_m["id"], cl_m["id"], qw_m["id"]]
            extra_ssr_section_html, extra_bottom_section_html = build_deepseek_v4_vs_claude_sections(
                models=models,
                fx_rate=fx_rate,
                quote_verified_date=quote_verified_date,
                last_live_verified_at=last_live_verified_at,
                base_prefix=base_prefix,
            )

        app_payload = {
            "build_date": build_date,
            "updated_at": updated_date,
            "quote_verified_date": quote_verified_date,
            "last_live_verified_at": last_live_verified_at,
            "source": source_label,
            "fx_rate_usd_to_rmb": fx_rate,
            "route_path": route_key,
            "page_kind": page_kind,
            "affiliates": affiliates,
            "coding_plans": coding_plans if not is_product else [],
            "page_preset": route_preset,
            "models": models if not is_product else [],
        }
        embedded_json = safe_json_for_html_script(app_payload)
        if is_product:
            route_faq_entries = AGENT_GUARDIAN_FAQ_ENTRIES
            route_faq_html = build_faq_html(route_faq_entries)
        elif is_ds_v4_claude:
            route_faq_entries = DEEPSEEK_V4_CLAUDE_FAQ_ENTRIES
            route_faq_html = build_faq_html(route_faq_entries)
        else:
            route_faq_entries = FAQ_ENTRIES
            route_faq_html = faq_html
        json_ld_webapp, json_ld_faq = build_json_ld(
            route_canonical,
            build_date,
            quote_verified_date,
            len(models),
            route["title"],
            route["description"],
            page_kind=page_kind,
            faq_entries=route_faq_entries,
        )
        seo_nav_html = build_seo_nav_html(base_prefix, slug)
        ssr_models_table_html = (
            ""
            if is_product
            else build_ssr_models_table_html(
                models=models,
                quote_verified_date=quote_verified_date,
                open_by_default=(slug == "deepseek-vs-qwen/"),
            )
        )
        custom_main_html = (
            build_agent_guardian_main_html(base_prefix, quote_verified_date) if is_product else ""
        )

        html_output = render_html_template(
            embedded_json=embedded_json,
            json_ld_webapp=json_ld_webapp,
            json_ld_faq=json_ld_faq,
            page_title=html.escape(route["title"]),
            page_description=html.escape(route["description"]),
            canonical_url=html.escape(route_canonical),
            updated_date=html.escape(build_date),
            quote_verified_date=html.escape(quote_verified_date),
            total_models=len(models),
            cn_models_count=cn_count,
            global_models_count=global_count,
            faq_html_items=route_faq_html,
            ssr_coding_plan_tables_html="" if is_product else ssr_coding_plan_tables_html,
            ssr_models_table_html=ssr_models_table_html,
            hero_title_main=html.escape(route["hero_main"]),
            hero_title_accent=html.escape(route["hero_accent"]),
            hero_subtitle=html.escape(route["hero_sub"]),
            seo_nav_html=seo_nav_html,
            sitemap_href=f"{base_prefix}sitemap.xml",
            feed_href=f"{base_prefix}feeds/price-changes.xml",
            api_json_href=f"{base_prefix}api/models_live.json",
            badge_svg_href=f"{base_prefix}badges/coding-plan-status.svg",
            html_lang=route.get("html_lang", "zh-CN"),
            page_kind=page_kind,
            custom_main_html=custom_main_html,
            extra_ssr_section_html=extra_ssr_section_html,
            extra_bottom_section_html=extra_bottom_section_html,
            base_prefix=base_prefix,
            faq_title_zh=(
                "Agent Guardian 多账号隔离、双模沙箱与离线雷达常见问题 (FAQ)"
                if is_product
                else "大模型 API 计费核对、专属端点与自建边界常见问题 (FAQ)"
            ),
            faq_title_en=(
                "Agent Guardian Multi-Account Isolation, Sandbox & Offline Radar FAQ"
                if is_product
                else "LLM Billing Verification, Dedicated Endpoints & Self-Host Break-Even FAQ"
            ),
            faq_desc_zh=(
                "围绕 Fail-Closed 502、XNU Seatbelt / Apple VZ、四大 CLI 隔离与 MCP 密钥保险箱的常见疑问解答。"
                if is_product
                else ""
            ),
            faq_desc_en=(
                "Answers covering Fail-Closed 502, XNU Seatbelt / Apple VZ, 4-CLI isolation, and MCP secrets vault."
                if is_product
                else ""
            ),
        )

        out_file = target_dist / "index.html" if is_root else (target_dist / slug.strip("/") / "index.html")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text("\n".join(line.rstrip() for line in html_output.splitlines()) + "\n", encoding="utf-8")

    # Static public JSON API snapshot inside dist/
    api_dir = target_dist / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    api_payload = {
        "total_models": len(models),
        "counts_by_region": {"cn_direct": cn_count, "global": global_count},
        "build_date": build_date,
        "updated_at": updated_date,
        "quote_verified_date": quote_verified_date,
        "last_live_verified_at": last_live_verified_at,
        "source": source_label,
        "fx_rate_usd_to_rmb": fx_rate,
        "official_rule_audit": official_rule_audit,
        "price_changes": price_changes,
        "coding_plans": coding_plans,
        "models": [{**model, "signup_url": model.get("affiliate_url", "")} for model in models],
    }
    api_json_str = json.dumps(api_payload, ensure_ascii=False, indent=2) + "\n"
    (api_dir / "models_live.json").write_text(api_json_str, encoding="utf-8")
    # Backward-compatible root JSON feed for published Coze.cn Bot (`get_live_ai_models_pricing` -> `/radar_data.json`)
    (target_dist / "radar_data.json").write_text(api_json_str, encoding="utf-8")
    coze_spec = PROJECT_ROOT / "engine_a_mcp_actor/publish_bundles/coze_cn_bundle/openapi_coze_live.json"
    (api_dir / "openapi.json").write_text(coze_spec.read_text(encoding="utf-8"), encoding="utf-8")

    # Standalone read-only local 8-client CLI scanner scripts (legacy + global alias, byte-identical)
    cli_scanner_src = PROJECT_ROOT / "engine_a_mcp_actor/audit_local_claude.py"
    cli_bytes = cli_scanner_src.read_bytes()
    (target_dist / "audit_local_claude.py").write_bytes(cli_bytes)
    (target_dist / "audit_ai_spend.py").write_bytes(cli_bytes)

    # Embeddable SVG status badge + Atom price-change feed
    badges_dir = target_dist / "badges"
    badges_dir.mkdir(parents=True, exist_ok=True)
    badge_path = badges_dir / "coding-plan-status.svg"
    badge_path.write_text(build_status_badge_svg(quote_verified_date, len(models)), encoding="utf-8")

    feeds_dir = target_dist / "feeds"
    feeds_dir.mkdir(parents=True, exist_ok=True)
    feed_path = feeds_dir / "price-changes.xml"
    feed_path.write_text(
        build_atom_feed_xml(
            resolved_site_url,
            build_date,
            quote_verified_date,
            len(models),
            price_changes=price_changes,
        ),
        encoding="utf-8",
    )

    sitemap_path = target_dist / "sitemap.xml"
    robots_path = target_dist / "robots.txt"
    sitemap_path.write_text(build_sitemap_xml(resolved_site_url, build_date), encoding="utf-8")
    robots_path.write_text(build_robots_txt(resolved_site_url), encoding="utf-8")

    return {
        "index_path": str(index_path),
        "sitemap_path": str(sitemap_path),
        "robots_path": str(robots_path),
        "badge_path": str(badge_path),
        "feed_path": str(feed_path),
        "seo_pages_count": len(SEO_ROUTES),
        "total_models": len(models),
        "cn_models": cn_count,
        "global_models": global_count,
        "quote_verified_date": quote_verified_date,
        "build_date": build_date,
        "source": source_label,
        "fx_rate": fx_rate,
        "index_bytes": index_path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Engine B static bilingual AI API & Coding Plan Cost Calculator site (with SSR tables)."
    )
    parser.add_argument(
        "--fallback-only",
        action="store_true",
        help="Ignore shared_data/models_live.json and compile using the built-in fallback dataset.",
    )
    parser.add_argument(
        "--site-url",
        default=None,
        help="Canonical public URL for sitemap.xml, robots.txt, Atom feed, and JSON-LD.",
    )
    args = parser.parse_args()

    summary = build_site(force_fallback=args.fallback_only, site_url=args.site_url)
    print(
        f"✅ Engine B v3.0 静态比价与 SSR 核验站编译成功！\n"
        f"   - 页面构建日: {summary['build_date']} | 报价核验日: {summary['quote_verified_date']}\n"
        f"   - 数据源: {summary['source']} (共 {summary['total_models']} 款模型: 国内直连 {summary['cn_models']} 款 / 海外 Global {summary['global_models']} 款)\n"
        f"   - 静态 SEO/SSR 页面数: {summary['seo_pages_count']} 页 (含免 JS 可读 <table>、SVG 徽章与 Atom 订阅)\n"
        f"   - 汇率基准: 1 USD = {summary['fx_rate']} RMB\n"
        f"   - 主页体积: {summary['index_path']} ({summary['index_bytes']:,} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
