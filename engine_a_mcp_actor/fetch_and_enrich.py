#!/usr/bin/env python3
"""
Engine A — Live AI Model Price Fetcher & Domestic/Global Channel Enricher.

Uses Python 3.14 standard library ONLY (zero pip dependencies).
Fetches real-time model metadata & token pricing from OpenRouter API, merges curated
2026 Mainland China low-latency RMB API channels mapped to ../config.json affiliate
keys, computes value_score & capability tags, and writes ../shared_data/models_live.json.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import math
import ssl
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from typing import Any

FX_USD_TO_RMB: float = 7.20
OPENROUTER_API_URL: str = "https://openrouter.ai/api/v1/models"
HTTP_TIMEOUT_SECONDS: int = 15
TARGET_OPENROUTER_COUNT: int = 66  # + 14 curated Mainland China models = ~80 models

ENGINE_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = ENGINE_DIR.parent
CONFIG_PATH: Path = PROJECT_ROOT / "config.json"
OUTPUT_PATH: Path = PROJECT_ROOT / "shared_data" / "models_live.json"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import pricing_core  # noqa: E402

PRIORITY_VENDORS: tuple[str, ...] = (
    "openai/",
    "anthropic/",
    "google/",
    "deepseek/",
    "qwen/",
    "x-ai/",
    "meta-llama/",
    "mistralai/",
    "moonshotai/",
    "minimax/",
    "z-ai/",
    "thudm/",
    "cohere/",
    "amazon/",
    "microsoft/",
    "nvidia/",
    "perplexity/",
)

CODING_HINTS: tuple[str, ...] = (
    "coder",
    "codex",
    "codestral",
    "devstral",
    "code",
    "sonnet",
    "opus",
    "haiku",
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "gpt-6",
    "o3",
    "o4-mini",
    "deepseek-chat",
    "deepseek-v3",
    "deepseek-v4",
    "qwen3",
    "qwen4",
    "qwen-max",
    "gemini-2.5",
    "gemini-2.0-flash",
    "gemini-3",
    "grok-3",
    "grok-4",
    "kimi",
    "glm",
    "minimax",
)

REASONING_HINTS: tuple[str, ...] = (
    "deepseek-r1",
    "/r1",
    "-r1",
    "qwq",
    "o1",
    "o3",
    "o4",
    "thinking",
    "reasoner",
    "reasoning",
    "qwen3",
    "claude-3.7",
    "claude-3-7",
    "sonnet-4",
    "opus-4",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3",
    "grok-3",
    "grok-4",
    "kimi-k2",
)

# Curated 2026.11 Mainland China direct API channels (RMB native pricing per 1M tokens)
DOMESTIC_CN_PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "aliyun-bailian/qwen3-coder-next",
        "name": "阿里云百炼: Qwen3-Coder-Next (极速编程王 · 147 TPS)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_model_id": "qwen3-coder-next",
        "cache_hit_factor": 0.2,
        "perf_note": "百炼 Coding Plan 支持 · 256K 代码重构",
        "input_rmb_per_1m": 1.2,
        "output_rmb_per_1m": 4.8,
        "context_length": 262144,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "cheap"],
    },
    {
        "id": "aliyun-bailian/qwen3.5-plus",
        "name": "阿里云百炼: Qwen3.5-Plus (百万长文本全能旗舰)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_model_id": "qwen3.5-plus",
        "cache_hit_factor": 0.2,
        "perf_note": "1M 上下文 · 显式/隐式缓存命中 2 折",
        "input_rmb_per_1m": 0.8,
        "output_rmb_per_1m": 2.0,
        "context_length": 1000000,
        "supports_tools": True,
        "modality": "text+image->text",
        "extra_tags": ["coding", "reasoning", "cheap"],
    },
    {
        "id": "aliyun-bailian/qwen3-235b-a22b",
        "name": "阿里云百炼: Qwen3-235B-A22B (旗舰混合推理)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_model_id": "qwen3-235b-a22b",
        "cache_hit_factor": 0.2,
        "perf_note": "🧠 235B MoE 复杂架构推理",
        "input_rmb_per_1m": 2.0,
        "output_rmb_per_1m": 8.0,
        "context_length": 131072,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "reasoning"],
    },
    {
        "id": "aliyun-bailian/qwen-max",
        "name": "阿里云百炼: Qwen-Max (通义千问商业旗舰)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_model_id": "qwen-max-latest",
        "cache_hit_factor": 0.2,
        "perf_note": "🏢 企业专票合规旗舰",
        "input_rmb_per_1m": 2.4,
        "output_rmb_per_1m": 9.6,
        "context_length": 131072,
        "supports_tools": True,
        "modality": "text+image->text",
        "extra_tags": ["coding", "reasoning"],
    },
    {
        "id": "aliyun-bailian/qwen3-coder-plus",
        "name": "阿里云百炼: Qwen-Coder-Plus (代码Agent专精)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_model_id": "qwen-coder-plus-latest",
        "cache_hit_factor": 0.2,
        "perf_note": "💻 Claude Code / Cline 稳态平替",
        "input_rmb_per_1m": 1.5,
        "output_rmb_per_1m": 6.0,
        "context_length": 131072,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "cheap"],
    },
    {
        "id": "aliyun-bailian/qwen-turbo",
        "name": "阿里云百炼: Qwen-Turbo (百万上下文超低价)",
        "provider": "阿里云百炼 (Aliyun Bailian)",
        "provider_config_key": "aliyun_bailian_url",
        "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_model_id": "qwen-turbo-latest",
        "cache_hit_factor": 0.2,
        "perf_note": "📚 1M 超长文档批处理神卡",
        "input_rmb_per_1m": 0.3,
        "output_rmb_per_1m": 0.6,
        "context_length": 1000000,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["cheap"],
    },
    {
        "id": "tencent-cloud/hunyuan-t1",
        "name": "腾讯云: 混元 Hunyuan-T1 (256K 深度推理)",
        "provider": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "api_model_id": "hunyuan-t1-latest",
        "cache_hit_factor": 0.2,
        "perf_note": "腾讯 Coding Plan 支持 · 256K 深度思考",
        "input_rmb_per_1m": 1.0,
        "output_rmb_per_1m": 4.0,
        "context_length": 256000,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "reasoning", "cheap"],
    },
    {
        "id": "tencent-cloud/deepseek-v3",
        "name": "腾讯云: DeepSeek-V3.2 满血专线版",
        "provider": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "api_model_id": "deepseek-v3",
        "cache_hit_factor": 0.2,
        "perf_note": "🛡️ 腾讯BGP高防专线零丢包",
        "input_rmb_per_1m": 2.0,
        "output_rmb_per_1m": 8.0,
        "context_length": 131072,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "cheap"],
    },
    {
        "id": "tencent-cloud/deepseek-r1",
        "name": "腾讯云: DeepSeek-R1 深度推理满血版",
        "provider": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "api_model_id": "deepseek-r1",
        "cache_hit_factor": 0.2,
        "perf_note": "🧠 671B 满血思维链专线",
        "input_rmb_per_1m": 4.0,
        "output_rmb_per_1m": 16.0,
        "context_length": 65536,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["reasoning", "coding"],
    },
    {
        "id": "tencent-cloud/hunyuan-turbos",
        "name": "腾讯云: 混元 Hunyuan-TurboS 旗舰快思考",
        "provider": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "api_model_id": "hunyuan-turbos-latest",
        "cache_hit_factor": 0.2,
        "perf_note": "💨 高频客服与 Agent 路由首选",
        "input_rmb_per_1m": 0.8,
        "output_rmb_per_1m": 2.0,
        "context_length": 256000,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["cheap"],
    },
    {
        "id": "tencent-cloud/hunyuan-lite",
        "name": "腾讯云: 混元 Hunyuan-Lite (永久免费API)",
        "provider": "腾讯云 (Tencent Cloud)",
        "provider_config_key": "tencent_cps_url",
        "api_base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "api_model_id": "hunyuan-lite",
        "cache_hit_factor": 1.0,
        "perf_note": "🆓 256K上下文永久 ¥0 免费",
        "input_rmb_per_1m": 0.0,
        "output_rmb_per_1m": 0.0,
        "context_length": 256000,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["free", "cheap"],
    },
    {
        "id": "siliconflow/moonshotai/Kimi-K2.5",
        "name": "硅基流动: Kimi-K2.5 (256K 多轮工具编程旗舰)",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "api_base_url": "https://api.siliconflow.cn/v1",
        "api_model_id": "moonshotai/Kimi-K2.5",
        "cache_hit_factor": 0.25,
        "perf_note": "256K 长上下文 · 原生多步工具调用",
        "input_rmb_per_1m": 2.0,
        "output_rmb_per_1m": 8.0,
        "context_length": 262144,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "reasoning"],
    },
    {
        "id": "siliconflow/THUDM/GLM-5",
        "name": "硅基流动: 智谱 GLM-5 (代码重构与工具调用)",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "api_base_url": "https://api.siliconflow.cn/v1",
        "api_model_id": "THUDM/GLM-5",
        "cache_hit_factor": 0.25,
        "perf_note": "200K 上下文 · Claude Code 开源平替",
        "input_rmb_per_1m": 1.5,
        "output_rmb_per_1m": 6.0,
        "context_length": 200000,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "reasoning", "cheap"],
    },
    {
        "id": "siliconflow/MiniMaxAI/MiniMax-M2.5",
        "name": "硅基流动: MiniMax-M2.5 (1M 超长上下文代码模型)",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "api_base_url": "https://api.siliconflow.cn/v1",
        "api_model_id": "MiniMaxAI/MiniMax-M2.5",
        "cache_hit_factor": 0.25,
        "perf_note": "1M 上下文 · 低单价多文件检索",
        "input_rmb_per_1m": 1.0,
        "output_rmb_per_1m": 4.0,
        "context_length": 1000000,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "cheap"],
    },
    {
        "id": "siliconflow/deepseek-ai/DeepSeek-V3",
        "name": "硅基流动 SiliconFlow: DeepSeek-V3 满血按量",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "api_base_url": "https://api.siliconflow.cn/v1",
        "api_model_id": "deepseek-ai/DeepSeek-V3",
        "cache_hit_factor": 0.25,
        "perf_note": "128K 上下文 · OpenAI 协议兼容",
        "input_rmb_per_1m": 2.0,
        "output_rmb_per_1m": 8.0,
        "context_length": 131072,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "cheap"],
    },
    {
        "id": "siliconflow/deepseek-ai/DeepSeek-R1",
        "name": "硅基流动 SiliconFlow: DeepSeek-R1 满血推理",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "api_base_url": "https://api.siliconflow.cn/v1",
        "api_model_id": "deepseek-ai/DeepSeek-R1",
        "cache_hit_factor": 0.25,
        "perf_note": "🧠 注册送 ¥16 算力额度直接抵扣",
        "input_rmb_per_1m": 4.0,
        "output_rmb_per_1m": 16.0,
        "context_length": 65536,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["reasoning", "coding"],
    },
    {
        "id": "siliconflow/Qwen/Qwen3-32B",
        "name": "硅基流动 SiliconFlow: Qwen3-32B 高性价比编程/推理",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "api_base_url": "https://api.siliconflow.cn/v1",
        "api_model_id": "Qwen/Qwen3-32B",
        "cache_hit_factor": 0.25,
        "perf_note": "💎 中等体量高智商性价比王",
        "input_rmb_per_1m": 1.26,
        "output_rmb_per_1m": 5.04,
        "context_length": 131072,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["coding", "reasoning", "cheap"],
    },
    {
        "id": "siliconflow/Qwen/Qwen2.5-7B-Instruct",
        "name": "硅基流动 SiliconFlow: Qwen2.5-7B-Instruct (免费API)",
        "provider": "硅基流动 (SiliconFlow)",
        "provider_config_key": "siliconflow_invite_url",
        "api_base_url": "https://api.siliconflow.cn/v1",
        "api_model_id": "Qwen/Qwen2.5-7B-Instruct",
        "cache_hit_factor": 1.0,
        "perf_note": "🆓 永久 ¥0 免费轻量清洗/分类模型",
        "input_rmb_per_1m": 0.0,
        "output_rmb_per_1m": 0.0,
        "context_length": 32768,
        "supports_tools": True,
        "modality": "text->text",
        "extra_tags": ["free", "cheap", "coding"],
    },
    {
        "id": "volcengine/doubao-seed-2.0-pro",
        "name": "火山引擎方舟: 豆包 Doubao-Seed-2.0-Pro (旗舰高并发)",
        "provider": "火山引擎 (Volcengine Ark)",
        "provider_config_key": "volcengine_ark_url",
        "api_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_model_id": "doubao-seed-2-0-pro-250415",
        "cache_hit_factor": 0.2,
        "perf_note": "🔥 火山 Coding Plan 主力 · 百万TPM不限流",
        "input_rmb_per_1m": 0.8,
        "output_rmb_per_1m": 2.0,
        "context_length": 256000,
        "supports_tools": True,
        "modality": "text+image->text",
        "extra_tags": ["coding", "cheap"],
    },
    {
        "id": "volcengine/doubao-seed-thinking-pro",
        "name": "火山引擎方舟: 豆包 Doubao-2.0 深度思考版 (256K)",
        "provider": "火山引擎 (Volcengine Ark)",
        "provider_config_key": "volcengine_ark_url",
        "api_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_model_id": "doubao-seed-2-0-thinking-pro",
        "cache_hit_factor": 0.2,
        "perf_note": "🧠 256K 图文混合深度推理",
        "input_rmb_per_1m": 4.0,
        "output_rmb_per_1m": 16.0,
        "context_length": 256000,
        "supports_tools": True,
        "modality": "text+image->text",
        "extra_tags": ["reasoning", "coding"],
    },
]

# 2026.11 Verified Offers Catalog (Subscriptions vs Pay-As-You-Go Pools vs Cloud Hosts vs Gateways)
CODING_PLANS_2026: list[dict[str, Any]] = pricing_core.get_offers_catalog()

# Offline graceful fallback snapshot in case OpenRouter API has a network hiccup
FALLBACK_OPENROUTER_RAW: list[dict[str, Any]] = [
    {
        "id": "openai/gpt-4.1",
        "name": "OpenAI: GPT-4.1",
        "created": 1744675200,
        "context_length": 1047576,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.000002", "completion": "0.000008"},
        "supported_parameters": ["tools", "tool_choice"],
    },
    {
        "id": "openai/gpt-4.1-mini",
        "name": "OpenAI: GPT-4.1 Mini",
        "created": 1744675200,
        "context_length": 1047576,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.0000004", "completion": "0.0000016"},
        "supported_parameters": ["tools", "tool_choice"],
    },
    {
        "id": "openai/gpt-4.1-nano",
        "name": "OpenAI: GPT-4.1 Nano",
        "created": 1744675200,
        "context_length": 1047576,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
        "supported_parameters": ["tools", "tool_choice"],
    },
    {
        "id": "openai/o4-mini",
        "name": "OpenAI: o4 Mini",
        "created": 1744848000,
        "context_length": 200000,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.0000011", "completion": "0.0000044"},
        "supported_parameters": ["tools", "reasoning"],
    },
    {
        "id": "anthropic/claude-sonnet-4",
        "name": "Anthropic: Claude Sonnet 4",
        "created": 1747872000,
        "context_length": 200000,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.000003", "completion": "0.000015"},
        "supported_parameters": ["tools", "reasoning"],
    },
    {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Anthropic: Claude 3.5 Haiku",
        "created": 1730678400,
        "context_length": 200000,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.0000008", "completion": "0.000004"},
        "supported_parameters": ["tools"],
    },
    {
        "id": "google/gemini-2.5-pro",
        "name": "Google: Gemini 2.5 Pro",
        "created": 1749081600,
        "context_length": 1048576,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.00000125", "completion": "0.00001"},
        "supported_parameters": ["tools", "reasoning"],
    },
    {
        "id": "google/gemini-2.5-flash",
        "name": "Google: Gemini 2.5 Flash",
        "created": 1749081600,
        "context_length": 1048576,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.0000003", "completion": "0.0000025"},
        "supported_parameters": ["tools", "reasoning"],
    },
    {
        "id": "google/gemini-2.0-flash-001",
        "name": "Google: Gemini 2.0 Flash",
        "created": 1738713600,
        "context_length": 1048576,
        "architecture": {"modality": "text+image->text"},
        "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
        "supported_parameters": ["tools"],
    },
    {
        "id": "deepseek/deepseek-chat-v3-0324",
        "name": "DeepSeek: DeepSeek V3 0324",
        "created": 1742774400,
        "context_length": 131072,
        "architecture": {"modality": "text->text"},
        "pricing": {"prompt": "0.00000027", "completion": "0.0000011"},
        "supported_parameters": ["tools"],
    },
    {
        "id": "deepseek/deepseek-chat-v3-0324:free",
        "name": "DeepSeek: DeepSeek V3 0324 (free)",
        "created": 1742774400,
        "context_length": 131072,
        "architecture": {"modality": "text->text"},
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["tools"],
    },
    {
        "id": "deepseek/deepseek-r1-0528",
        "name": "DeepSeek: R1 0528",
        "created": 1748390400,
        "context_length": 131072,
        "architecture": {"modality": "text->text"},
        "pricing": {"prompt": "0.0000005", "completion": "0.00000218"},
        "supported_parameters": ["tools", "reasoning"],
    },
    {
        "id": "deepseek/deepseek-r1-0528:free",
        "name": "DeepSeek: R1 0528 (free)",
        "created": 1748390400,
        "context_length": 131072,
        "architecture": {"modality": "text->text"},
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["reasoning"],
    },
    {
        "id": "qwen/qwen3-235b-a22b",
        "name": "Qwen: Qwen3 235B A22B",
        "created": 1745884800,
        "context_length": 131072,
        "architecture": {"modality": "text->text"},
        "pricing": {"prompt": "0.0000002", "completion": "0.0000006"},
        "supported_parameters": ["tools", "reasoning"],
    },
    {
        "id": "qwen/qwen3-coder",
        "name": "Qwen: Qwen3 Coder",
        "created": 1753228800,
        "context_length": 262144,
        "architecture": {"modality": "text->text"},
        "pricing": {"prompt": "0.0000003", "completion": "0.0000012"},
        "supported_parameters": ["tools"],
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Meta: Llama 3.3 70B Instruct (free)",
        "created": 1733443200,
        "context_length": 131072,
        "architecture": {"modality": "text->text"},
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["tools"],
    },
]


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load ../config.json safely, returning empty dict if absent."""
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _clean_url(raw_url: Any, fallback: str) -> str:
    s = str(raw_url or "").strip()
    if not s or "YOUR_" in s.upper() or not s.startswith(("http://", "https://")):
        return fallback
    return s


def resolve_affiliate_map(config: dict[str, Any]) -> dict[str, str]:
    """Extract affiliate/channel URLs from config.json with clean placeholder-free fallbacks."""
    cn = config.get("domestic_affiliates_rmb") or {}
    gl = config.get("global_affiliates_usd") or {}
    return {
        "aliyun_ambassador_url": _clean_url(
            cn.get("aliyun_ambassador_url") or config.get("aliyun_ambassador_url"),
            "https://www.aliyun.com/minisite/goods",
        ),
        "aliyun_bailian_url": _clean_url(
            cn.get("aliyun_bailian_url") or config.get("aliyun_bailian_url"),
            "https://bailian.console.aliyun.com/",
        ),
        "tencent_cps_url": _clean_url(
            cn.get("tencent_cps_url") or config.get("tencent_cps_url"),
            "https://cloud.tencent.com/product/lkeap",
        ),
        "siliconflow_invite_url": _clean_url(
            cn.get("siliconflow_invite_url") or config.get("siliconflow_invite_url"),
            "https://cloud.siliconflow.cn/",
        ),
        "volcengine_ark_url": _clean_url(
            cn.get("volcengine_ark_url") or config.get("volcengine_ark_url"),
            "https://console.volcengine.com/ark",
        ),
        "openrouter_url": _clean_url(
            gl.get("openrouter_url") or config.get("openrouter_url"),
            "https://openrouter.ai",
        ),
    }


def _build_ssl_context() -> ssl.SSLContext:
    """Create a standard TLS context checking macOS/Linux CA bundle paths if needed."""
    ctx = ssl.create_default_context()
    for candidate in ("/etc/ssl/cert.pem", "/opt/homebrew/etc/openssl@3/cert.pem"):
        if Path(candidate).exists():
            try:
                ctx.load_verify_locations(cafile=candidate)
                break
            except ssl.SSLError:
                continue
    return ctx


def fetch_openrouter_raw(timeout: int = HTTP_TIMEOUT_SECONDS) -> tuple[list[dict[str, Any]], str]:
    """Fetch live model catalog from OpenRouter API with graceful fallback."""
    req = urllib.request.Request(
        OPENROUTER_API_URL,
        headers={
            "User-Agent": "AI-Revenue-Engine-ModelRouter/1.0 (Python-Stdlib)",
            "Accept": "application/json",
        },
    )
    try:
        ctx = _build_ssl_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            data = payload.get("data")
            if isinstance(data, list) and len(data) > 0:
                return data, "openrouter_live+curated_cn_2026"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[fetch_and_enrich] Network warning ({exc}); using fallback snapshot.", file=sys.stderr)

    return FALLBACK_OPENROUTER_RAW, "fallback_snapshot+curated_cn_2026"


def compute_tags_and_score(
    model_id: str,
    name: str,
    input_usd: float,
    output_usd: float,
    context_length: int,
    supports_tools: bool,
    modality: str,
    region: str,
    supported_params: list[str] | None = None,
    extra_tags: list[str] | None = None,
) -> tuple[list[str], float]:
    """Compute standardized tags and a 0-100 value_score."""
    haystack = f"{model_id} {name}".lower()
    params = set(supported_params or [])
    tags_set: set[str] = set(extra_tags or [])

    tags_set.add("cn_direct" if region == "cn_direct" else "global")

    is_free = input_usd == 0.0 and output_usd == 0.0
    blended_usd = 0.75 * input_usd + 0.25 * output_usd

    if is_free:
        tags_set.add("free")
        tags_set.add("cheap")
    elif blended_usd <= 0.65:
        tags_set.add("cheap")

    if any(hint in haystack for hint in CODING_HINTS):
        tags_set.add("coding")

    if "reasoning" in params or "include_reasoning" in params or any(
        hint in haystack for hint in REASONING_HINTS
    ):
        tags_set.add("reasoning")

    # Compute value_score (0..100): balances capability signals & cost efficiency
    capability = 18.0
    if "coding" in tags_set:
        capability += 8.5
    if "reasoning" in tags_set:
        capability += 8.5
    if supports_tools:
        capability += 5.5
    if "image" in modality or "audio" in modality or "video" in modality:
        capability += 3.0
    if context_length > 0:
        # e.g. 32k -> ~4.6, 128k -> ~6.9, 1M -> ~10.3
        capability += min(11.0, max(0.0, (math.log2(max(4096, context_length)) - 12.0) * 1.3))

    if any(
        model_id.startswith(v)
        for v in (
            "openai/",
            "anthropic/",
            "google/",
            "deepseek/",
            "qwen/",
            "aliyun-",
            "tencent-",
            "siliconflow/",
            "volcengine/",
        )
    ):
        capability += 4.0

    if is_free:
        # Free models are fantastic value, slightly tempered for rate limits vs cheap paid
        cost_efficiency = 33.0
    else:
        # Smooth logarithmic curve without ceiling collisions
        cost_efficiency = max(4.0, 39.5 - 14.5 * math.log10(1.0 + blended_usd * 5.0))

    value_score = round(min(98.5, max(15.0, capability + cost_efficiency)), 1)

    ordered_tag_vocab = ("coding", "reasoning", "cheap", "free", "cn_direct", "global")
    tags = [t for t in ordered_tag_vocab if t in tags_set]
    return tags, value_score


def normalize_openrouter_models(
    raw_models: list[dict[str, Any]],
    affiliate_map: dict[str, str],
    limit: int = TARGET_OPENROUTER_COUNT,
) -> list[dict[str, Any]]:
    """Parse, filter, rank, and normalize top paid + free OpenRouter models."""
    paid_candidates: list[tuple[float, dict[str, Any]]] = []
    free_candidates: list[tuple[float, dict[str, Any]]] = []

    openrouter_base_url = affiliate_map["openrouter_url"].rstrip("/")

    for item in raw_models:
        model_id = str(item.get("id") or "").strip()
        if (
            not model_id
            or model_id.startswith("openrouter/")
            or model_id.endswith((":batch", ":extended"))
        ):
            continue

        pricing = item.get("pricing") or {}
        try:
            prompt_per_tok = float(pricing.get("prompt", -1))
            completion_per_tok = float(pricing.get("completion", -1))
        except (TypeError, ValueError):
            continue

        # Must have valid non-negative pricing and non-absurd placeholder pricing
        if prompt_per_tok < 0 or completion_per_tok < 0:
            continue
        if prompt_per_tok > 0.0003 or completion_per_tok > 0.0006:
            continue

        ctx_len = int(item.get("context_length") or (item.get("top_provider") or {}).get("context_length") or 0)
        if ctx_len < 4096:
            continue

        input_usd = round(prompt_per_tok * 1_000_000, 4)
        output_usd = round(completion_per_tok * 1_000_000, 4)
        input_rmb = round(input_usd * FX_USD_TO_RMB, 4)
        output_rmb = round(output_usd * FX_USD_TO_RMB, 4)
        blended_usd = round(0.75 * input_usd + 0.25 * output_usd, 4)
        blended_rmb = round(blended_usd * FX_USD_TO_RMB, 4)

        supported_params = item.get("supported_parameters") or []
        supports_tools = "tools" in supported_params or "tool_choice" in supported_params
        arch = item.get("architecture") or {}
        modality = str(arch.get("modality") or "text->text")
        name = str(item.get("name") or model_id).strip()

        tags, value_score = compute_tags_and_score(
            model_id=model_id,
            name=name,
            input_usd=input_usd,
            output_usd=output_usd,
            context_length=ctx_len,
            supports_tools=supports_tools,
            modality=modality,
            region="global",
            supported_params=supported_params,
        )

        # Selection priority score so we retain flagship & popular active models
        vendor_bonus = 0.0
        for idx, prefix in enumerate(PRIORITY_VENDORS):
            if model_id.startswith(prefix):
                vendor_bonus = 40.0 - idx * 1.8
                break
        created_ts = float(item.get("created") or 0)
        recency_bonus = min(20.0, max(0.0, (created_ts - 1700000000.0) / 5_000_000.0))
        rank_score = vendor_bonus + recency_bonus + (value_score * 0.35)

        record = {
            "id": model_id,
            "name": name,
            "provider": "OpenRouter (Global)",
            "provider_config_key": "openrouter_url",
            "api_base_url": "https://openrouter.ai/api/v1",
            "api_model_id": model_id,
            "cache_hit_factor": 0.5 if input_usd > 0 else 1.0,
            "perf_note": "",
            "signup_url": openrouter_base_url,
            "affiliate_url": openrouter_base_url,
            "model_page_url": f"https://openrouter.ai/{model_id}",
            "region": "global",
            "input_usd_per_1m": input_usd,
            "output_usd_per_1m": output_usd,
            "input_rmb_per_1m": input_rmb,
            "output_rmb_per_1m": output_rmb,
            "blended_usd_per_1m": blended_usd,
            "blended_rmb_per_1m": blended_rmb,
            "context_length": ctx_len,
            "supports_tools": supports_tools,
            "modality": modality,
            "is_free": "free" in tags,
            "value_score": value_score,
            "tags": tags,
        }

        if record["is_free"]:
            free_candidates.append((rank_score, record))
        else:
            paid_candidates.append((rank_score, record))

    free_candidates.sort(key=lambda pair: pair[0], reverse=True)
    paid_candidates.sort(key=lambda pair: pair[0], reverse=True)

    free_quota = min(14, len(free_candidates))
    paid_quota = max(0, limit - free_quota)

    selected = [r for _, r in paid_candidates[:paid_quota]] + [
        r for _, r in free_candidates[:free_quota]
    ]
    return selected


def build_domestic_cn_models(affiliate_map: dict[str, str]) -> list[dict[str, Any]]:
    """Normalize curated 2026 Mainland China API models mapped to config.json keys."""
    enriched: list[dict[str, Any]] = []
    for item in DOMESTIC_CN_PROVIDERS:
        cfg_key = item["provider_config_key"]
        channel_url = affiliate_map.get(cfg_key, "")
        in_rmb = round(float(item["input_rmb_per_1m"]), 4)
        out_rmb = round(float(item["output_rmb_per_1m"]), 4)
        in_usd = round(in_rmb / FX_USD_TO_RMB, 4)
        out_usd = round(out_rmb / FX_USD_TO_RMB, 4)
        blended_usd = round(0.75 * in_usd + 0.25 * out_usd, 4)
        blended_rmb = round(0.75 * in_rmb + 0.25 * out_rmb, 4)

        tags, value_score = compute_tags_and_score(
            model_id=item["id"],
            name=item["name"],
            input_usd=in_usd,
            output_usd=out_usd,
            context_length=int(item["context_length"]),
            supports_tools=bool(item["supports_tools"]),
            modality=str(item["modality"]),
            region="cn_direct",
            extra_tags=list(item.get("extra_tags") or []),
        )

        enriched.append(
            {
                "id": item["id"],
                "name": item["name"],
                "provider": item["provider"],
                "provider_config_key": cfg_key,
                "api_base_url": str(item.get("api_base_url") or "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                "api_model_id": str(item.get("api_model_id") or item["id"].split("/", 1)[-1]),
                "cache_hit_factor": float(item.get("cache_hit_factor", 0.25)),
                "perf_note": str(item.get("perf_note") or ""),
                "signup_url": channel_url,
                "affiliate_url": channel_url,
                "model_page_url": channel_url,
                "region": "cn_direct",
                "input_usd_per_1m": in_usd,
                "output_usd_per_1m": out_usd,
                "input_rmb_per_1m": in_rmb,
                "output_rmb_per_1m": out_rmb,
                "blended_usd_per_1m": blended_usd,
                "blended_rmb_per_1m": blended_rmb,
                "context_length": int(item["context_length"]),
                "supports_tools": bool(item["supports_tools"]),
                "modality": str(item["modality"]),
                "is_free": "free" in tags,
                "value_score": value_score,
                "tags": tags,
            }
        )
    return enriched


def build_coding_plans(affiliate_map: dict[str, str]) -> list[dict[str, Any]]:
    """Enrich 2026 offers catalog (subscriptions, payg pools, cloud hosts, gateways) with affiliate URLs."""
    plans: list[dict[str, Any]] = []
    for item in pricing_core.get_offers_catalog():
        cfg_key = item["provider_config_key"]
        url = affiliate_map.get(cfg_key) or "https://bailian.console.aliyun.com/"
        plans.append(
            {
                **item,
                "url": url,
                "monthly_usd": round(float(item["monthly_rmb"]) / FX_USD_TO_RMB, 2),
                "pro_monthly_usd": round(float(item["pro_monthly_rmb"]) / FX_USD_TO_RMB, 2),
            }
        )
    return plans


def compute_price_changes(
    prev_models: list[dict[str, Any]],
    new_models: list[dict[str, Any]],
    prev_plans: list[dict[str, Any]],
    new_plans: list[dict[str, Any]],
    detected_at: str,
    prior_changes: list[dict[str, Any]] | None = None,
    max_entries: int = 15,
) -> list[dict[str, Any]]:
    """
    Compare previous `models_live.json` snapshot against refreshed models & Coding Plan tiers.
    Records structured price deltas and carries forward recent history up to `max_entries`.
    """
    deltas: list[dict[str, Any]] = []
    prev_by_id = {str(m.get("id")): m for m in prev_models if isinstance(m, dict) and m.get("id")}

    if prev_by_id:
        for m in new_models:
            mid = str(m.get("id") or "")
            if not mid:
                continue
            old = prev_by_id.get(mid)
            if old is None:
                continue
            is_cn = m.get("region") == "cn_direct"
            if is_cn:
                old_in = round(float(old.get("input_rmb_per_1m") or 0.0), 4)
                new_in = round(float(m.get("input_rmb_per_1m") or 0.0), 4)
                old_out = round(float(old.get("output_rmb_per_1m") or 0.0), 4)
                new_out = round(float(m.get("output_rmb_per_1m") or 0.0), 4)
                unit = "¥"
            else:
                old_in = round(float(old.get("input_usd_per_1m") or 0.0), 4)
                new_in = round(float(m.get("input_usd_per_1m") or 0.0), 4)
                old_out = round(float(old.get("output_usd_per_1m") or 0.0), 4)
                new_out = round(float(m.get("output_usd_per_1m") or 0.0), 4)
                unit = "$"

            if abs(old_in - new_in) >= 0.0005 or abs(old_out - new_out) >= 0.0005:
                deltas.append(
                    {
                        "detected_at": detected_at,
                        "entity_type": "model",
                        "id": mid,
                        "name": str(m.get("name") or mid),
                        "change_type": "price_update",
                        "summary_zh": (
                            f"输入单价 {unit}{old_in:g} -> {unit}{new_in:g} / 1M，"
                            f"输出单价 {unit}{old_out:g} -> {unit}{new_out:g} / 1M"
                        ),
                    }
                )

    prev_plan_by_id = {str(p.get("id")): p for p in prev_plans if isinstance(p, dict) and p.get("id")}
    if prev_plan_by_id:
        for p in new_plans:
            pid = str(p.get("id") or "")
            old_p = prev_plan_by_id.get(pid)
            if not pid or old_p is None:
                continue
            old_m = round(float(old_p.get("monthly_rmb") or 0.0), 2)
            new_m = round(float(p.get("monthly_rmb") or 0.0), 2)
            old_pro = round(float(old_p.get("pro_monthly_rmb") or 0.0), 2)
            new_pro = round(float(p.get("pro_monthly_rmb") or 0.0), 2)
            if abs(old_m - new_m) >= 0.01 or abs(old_pro - new_pro) >= 0.01:
                deltas.append(
                    {
                        "detected_at": detected_at,
                        "entity_type": "coding_plan",
                        "id": pid,
                        "name": str(p.get("name") or pid),
                        "change_type": "plan_price_update",
                        "summary_zh": f"套餐报价调整：入门/首月 ¥{old_m:g} -> ¥{new_m:g}，Pro ¥{old_pro:g} -> ¥{new_pro:g}",
                    }
                )

    combined: list[dict[str, Any]] = list(deltas)
    seen_keys = {(c.get("id"), c.get("summary_zh")) for c in combined}
    for item in prior_changes or []:
        if not isinstance(item, dict):
            continue
        key = (item.get("id"), item.get("summary_zh"))
        if key not in seen_keys:
            seen_keys.add(key)
            combined.append(item)
        if len(combined) >= max_entries:
            break
    return combined[:max_entries]


OFFICIAL_DOC_AUDIT_SPECS: list[dict[str, Any]] = [
    {
        "plan_id": "aliyun-coding-plan",
        "name": "阿里云百炼 Coding Plan 编程套餐",
        "url": "https://help.aliyun.com/zh/model-studio/coding-plan",
        "marker_groups": {
            "pro_monthly_cap_90k": ("90,000", "90000", "9万"),
            "pro_renewal_200": ("200",),
            "pro_promo_39_9": ("39.9", "39.90"),
        },
    },
    {
        "plan_id": "tencent-coding-plan",
        "name": "腾讯云 LKEAP Coding Plan 编程套餐",
        "url": "https://cloud.tencent.com/document/product/1823/130092",
        "marker_groups": {
            "lite_monthly_cap_18k": ("18,000", "18000", "1.8万"),
            "lite_renewal_40": ("40",),
            "pro_monthly_cap_90k": ("90,000", "90000", "9万"),
            "pro_renewal_200": ("200",),
        },
    },
    {
        "plan_id": "volcengine-coding-plan",
        "name": "火山方舟 Coding Plan 编程套餐",
        "url": "https://www.volcengine.com/docs/82379/1925114",
        "marker_groups": {
            "tiers_lite_pro": ("Lite 套餐", "Pro 套餐"),
            "quota_window_5h": ("每5小时限额", "每 5 小时"),
            "dedicated_coding_endpoint": ("api/coding/v3", "api/coding"),
            "interactive_ide_only": ("不可用于 API 调用", "不能用于 API 调用"),
        },
    },
]


def _fetch_doc_html_for_audit(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AI-Cost-Radar-RuleAudit/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    ctx = _build_ssl_context()
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
                headers = getattr(resp, "headers", None) or {}
                enc = str(headers.get("Content-Encoding", "") or "").lower()
                if "gzip" in enc or raw[:2] == b"\x1f\x8b":
                    try:
                        raw = gzip.decompress(raw)
                    except OSError:
                        pass
                elif "deflate" in enc:
                    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
                        try:
                            raw = zlib.decompress(raw, wbits)
                            break
                        except zlib.error:
                            continue
                return raw.decode("utf-8", errors="ignore")
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise
    if last_exc is not None:
        raise last_exc
    return ""


def _strip_html_visible_text(raw_html: str) -> str:
    import re

    without_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html or "", flags=re.IGNORECASE | re.DOTALL)
    plain = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", plain).strip()


def audit_official_coding_plan_docs(
    *,
    checked_at: str | None = None,
    fetcher: Any | None = None,
    timeout: int = 8,
) -> dict[str, Any]:
    """
    Lightweight, non-blocking SSR rule fingerprint audit against official Coding Plan docs.
    Distinguishes verified SSR markers vs CSR shells (no false alarms) vs true marker drift.
    """
    ts = checked_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fetch_fn = (
        fetcher
        if callable(fetcher)
        else ((lambda u: _fetch_doc_html_for_audit(u)) if timeout == 8 else (lambda u: _fetch_doc_html_for_audit(u, timeout)))
    )

    vendor_reports: list[dict[str, Any]] = []
    drift_warnings: list[dict[str, Any]] = []

    for spec in OFFICIAL_DOC_AUDIT_SPECS:
        plan_id = spec["plan_id"]
        plan_name = spec["name"]
        url = spec["url"]
        marker_groups: dict[str, tuple[str, ...]] = spec["marker_groups"]
        try:
            raw_html = str(fetch_fn(url) or "")
        except Exception as exc:  # noqa: BLE001
            vendor_reports.append(
                {
                    "plan_id": plan_id,
                    "url": url,
                    "status": "unreachable",
                    "matched_groups": [],
                    "missing_groups": [],
                    "note": str(exc)[:160],
                }
            )
            continue

        visible_text = _strip_html_visible_text(raw_html)
        lower_text = visible_text.lower()
        has_doc_body = (
            len(visible_text) >= 400
            and "coding plan" in lower_text
            and "pro" in lower_text
            and any(k in visible_text for k in ("上限", "月限", "每5小时限额", "每 5 小时", "请求次数", "调用次数"))
        )
        if not has_doc_body:
            vendor_reports.append(
                {
                    "plan_id": plan_id,
                    "url": url,
                    "status": "csr_shell_manual_check",
                    "matched_groups": [],
                    "missing_groups": [],
                }
            )
            continue

        matched: list[str] = []
        missing: list[str] = []
        for group_key, variants in marker_groups.items():
            if any(v in visible_text for v in variants):
                matched.append(group_key)
            else:
                missing.append(group_key)

        if missing:
            vendor_reports.append(
                {
                    "plan_id": plan_id,
                    "url": url,
                    "status": "marker_drift_detected",
                    "matched_groups": matched,
                    "missing_groups": missing,
                }
            )
            drift_warnings.append(
                {
                    "detected_at": ts,
                    "entity_type": "coding_plan",
                    "id": plan_id,
                    "name": plan_name,
                    "change_type": "plan_rule_drift_warning",
                    "summary_zh": (
                        f"官方规则页指纹异动（未命中指标：{', '.join(missing)}），"
                        f"请核对最新月上限、首购特惠与续费原价：{url}"
                    ),
                }
            )
        else:
            vendor_reports.append(
                {
                    "plan_id": plan_id,
                    "url": url,
                    "status": "verified_markers",
                    "matched_groups": matched,
                    "missing_groups": [],
                }
            )

    return {
        "checked_at": ts,
        "vendors": vendor_reports,
        "drift_warnings": drift_warnings,
    }


def refresh_models_live(output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    """Fetch, enrich, merge global + Mainland China models + Offers Catalog, and save models_live.json."""
    config = load_config()
    affiliate_map = resolve_affiliate_map(config)

    prev_live_verified_at: str | None = None
    prev_all_models: list[dict[str, Any]] = []
    prev_global_models: list[dict[str, Any]] = []
    prev_plans: list[dict[str, Any]] = []
    prior_changes: list[dict[str, Any]] = []
    if output_path.exists():
        try:
            prev_obj = json.loads(output_path.read_text(encoding="utf-8"))
            prev_live_verified_at = prev_obj.get("last_live_verified_at") or prev_obj.get("updated_at")
            prev_all_models = [dict(m) for m in (prev_obj.get("models") or []) if isinstance(m, dict)]
            prev_plans = [dict(p) for p in (prev_obj.get("coding_plans") or []) if isinstance(p, dict)]
            prior_changes = [dict(c) for c in (prev_obj.get("price_changes") or []) if isinstance(c, dict)]
            prev_source = str(prev_obj.get("source") or "")
            if "openrouter_live" in prev_source or "openrouter_cached" in prev_source:
                prev_global_models = [
                    dict(m)
                    for m in prev_all_models
                    if m.get("region") == "global"
                ]
        except (OSError, json.JSONDecodeError):
            prev_live_verified_at = None
            prev_all_models = []
            prev_global_models = []
            prev_plans = []
            prior_changes = []

    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_openrouter, source_label = fetch_openrouter_raw()
    if "openrouter_live" in source_label:
        last_live_verified_at = now_iso
        global_models = normalize_openrouter_models(raw_openrouter, affiliate_map, limit=TARGET_OPENROUTER_COUNT)
    elif len(prev_global_models) >= 20:
        last_live_verified_at = prev_live_verified_at or f"{pricing_core.QUOTE_VERIFIED_DATE}T00:00:00Z"
        source_label = "openrouter_cached+curated_cn_2026"
        or_url = affiliate_map.get("openrouter_url") or "https://openrouter.ai"
        global_models = [
            {
                **m,
                "signup_url": or_url,
                "affiliate_url": or_url,
            }
            for m in prev_global_models
        ]
    else:
        last_live_verified_at = prev_live_verified_at or f"{pricing_core.QUOTE_VERIFIED_DATE}T00:00:00Z"
        global_models = normalize_openrouter_models(raw_openrouter, affiliate_map, limit=TARGET_OPENROUTER_COUNT)

    cn_models = build_domestic_cn_models(affiliate_map)
    coding_plans = build_coding_plans(affiliate_map)

    merged = cn_models + global_models
    merged.sort(key=lambda m: (-m["value_score"], m["blended_usd_per_1m"]))
    rule_audit = audit_official_coding_plan_docs(checked_at=now_iso)
    non_drift_prior = [c for c in prior_changes if c.get("change_type") != "plan_rule_drift_warning"]
    base_changes = compute_price_changes(
        prev_models=prev_all_models,
        new_models=merged,
        prev_plans=prev_plans,
        new_plans=coding_plans,
        detected_at=now_iso,
        prior_changes=non_drift_prior,
    )
    drift_warnings = rule_audit.get("drift_warnings") or []
    seen_change_keys = {(c.get("id"), c.get("summary_zh")) for c in drift_warnings}
    price_changes = list(drift_warnings) + [
        c for c in base_changes if (c.get("id"), c.get("summary_zh")) not in seen_change_keys
    ]
    price_changes = price_changes[:25]

    payload = {
        "updated_at": now_iso,
        "last_live_verified_at": last_live_verified_at,
        "quote_verified_date": pricing_core.QUOTE_VERIFIED_DATE,
        "source": source_label,
        "fx_rate_usd_to_rmb": FX_USD_TO_RMB,
        "total_models": len(merged),
        "counts_by_region": {
            "cn_direct": len(cn_models),
            "global": len(global_models),
        },
        "official_rule_audit": {
            "checked_at": rule_audit["checked_at"],
            "vendors": rule_audit["vendors"],
        },
        "price_changes": price_changes,
        "coding_plans": coding_plans,
        "models": merged,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = refresh_models_live()
    free_count = sum(1 for m in payload["models"] if m["is_free"])
    cn_count = payload["counts_by_region"]["cn_direct"]
    gl_count = payload["counts_by_region"]["global"]
    print(
        f"[OK] Saved {payload['total_models']} models "
        f"(global={gl_count}, cn_direct={cn_count}, free={free_count}, source={payload['source']}) "
        f"-> {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
