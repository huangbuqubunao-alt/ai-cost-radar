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
    "runpod_affiliate_url": "https://www.runpod.io",
    "digitalocean_affiliate_url": "https://www.digitalocean.com",
    "railway_affiliate_url": "https://railway.com",
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
    if config_key in ("aliyun_bailian_url", "aliyun_ambassador_url", "tencent_cps_url", "siliconflow_invite_url") and "?" in raw_url:
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
        "openrouter_url": "https://openrouter.ai/api/v1",
    }
    api_base_url = str(raw.get("api_base_url") or default_base_map.get(config_key, "https://openrouter.ai/api/v1"))
    api_model_id = str(
        raw.get("api_model_id")
        or (
            model_id.split("/", 1)[-1]
            if region == "cn_direct" and not model_id.startswith("siliconflow/")
            else model_id.removeprefix("siliconflow/")
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
) -> tuple[str, str]:
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
        "claude-code-domestic/": "navTopicClaudeCode",
        "dify-openclaw-cloud-server/": "navTopicDifyHost",
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

        app_payload = {
            "build_date": build_date,
            "updated_at": updated_date,
            "quote_verified_date": quote_verified_date,
            "last_live_verified_at": last_live_verified_at,
            "source": source_label,
            "fx_rate_usd_to_rmb": fx_rate,
            "route_path": route_key,
            "affiliates": affiliates,
            "coding_plans": coding_plans,
            "page_preset": route["preset"],
            "models": models,
        }
        embedded_json = safe_json_for_html_script(app_payload)
        json_ld_webapp, json_ld_faq = build_json_ld(
            route_canonical,
            build_date,
            quote_verified_date,
            len(models),
            route["title"],
            route["description"],
        )
        seo_nav_html = build_seo_nav_html(base_prefix, slug)
        ssr_models_table_html = build_ssr_models_table_html(
            models=models,
            quote_verified_date=quote_verified_date,
            open_by_default=(slug == "deepseek-vs-qwen/"),
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
            faq_html_items=faq_html,
            ssr_coding_plan_tables_html=ssr_coding_plan_tables_html,
            ssr_models_table_html=ssr_models_table_html,
            hero_title_main=html.escape(route["hero_main"]),
            hero_title_accent=html.escape(route["hero_accent"]),
            hero_subtitle=html.escape(route["hero_sub"]),
            seo_nav_html=seo_nav_html,
            sitemap_href=f"{base_prefix}sitemap.xml",
            feed_href=f"{base_prefix}feeds/price-changes.xml",
            api_json_href=f"{base_prefix}api/models_live.json",
            badge_svg_href=f"{base_prefix}badges/coding-plan-status.svg",
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

    # Standalone read-only local ~/.claude/projects CLI scanner script
    cli_scanner_src = PROJECT_ROOT / "engine_a_mcp_actor/audit_local_claude.py"
    cli_scanner_dst = target_dist / "audit_local_claude.py"
    cli_scanner_dst.write_bytes(cli_scanner_src.read_bytes())

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
