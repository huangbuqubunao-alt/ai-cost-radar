#!/usr/bin/env python3
"""
AI Cost Radar — Zero-Dependency Local Multi-Client AI Coding Session Scanner (v3.11).

100% local, read-only CLI auditor for:
  - Claude Code (`~/.claude/projects/**/*.jsonl`)
  - OpenAI Codex CLI (`~/.codex/sessions/**/*.jsonl`)
  - VS Code / Cursor Cline & Roo Code (`globalStorage/{saoudrizwan.claude-dev,rooveterinaryinc.roo-cline}/tasks/*/ui_messages.json`)

Zero raw prompts, zero OS usernames, and zero session contents are ever uploaded anywhere.

Quick one-liner usage (auto-scans Claude Code + Codex CLI + Cline):
  curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py | python3 - --days 30

Local options:
  python3 audit_local_claude.py --client all --days 30 --seats 1
  python3 audit_local_claude.py --client codex --days 14 --offline --json
  python3 audit_local_claude.py --dir ~/.claude/projects --days 30 --export-csv coding_30d_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

SUPPORTED_CLIENTS: tuple[str, ...] = (
    "all",
    "claude",
    "codex",
    "antigravity",
    "opencode",
    "grok",
    "workbuddy",
    "qwen",
    "cline",
)

LIVE_CATALOG_URL: str = "https://ai-cost-radar-nlu.pages.dev/api/models_live.json"
WEB_CALCULATOR_BASE: str = "https://ai-cost-radar-nlu.pages.dev/"
DEFAULT_FX_USD_TO_RMB: float = 7.20
PRO_MONTHLY_CAP: int = 90_000
LITE_MONTHLY_CAP: int = 18_000

EMBEDDED_FALLBACK_MODELS: list[dict[str, Any]] = [
    {
        "id": "anthropic/claude-opus-5.5",
        "api_model_id": "anthropic/claude-opus-5.5",
        "name": "Anthropic: Claude Opus 5.5",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 28.80,
        "output_rmb_per_1m": 144.00,
        "cache_hit_factor": 0.50,
        "context_length": 1_000_000,
        "is_free": False,
        "value_score": 82.0,
        "tags": ["coding", "reasoning", "global"],
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
        "context_length": 1_000_000,
        "is_free": False,
        "value_score": 88.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "anthropic/claude-haiku-5.5",
        "api_model_id": "anthropic/claude-haiku-5.5",
        "name": "Anthropic: Claude Haiku 5.5",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 0.72,
        "output_rmb_per_1m": 3.60,
        "cache_hit_factor": 0.50,
        "context_length": 1_000_000,
        "is_free": False,
        "value_score": 91.0,
        "tags": ["coding", "reasoning", "cheap", "global"],
    },
    {
        "id": "openai/gpt-6-astra",
        "api_model_id": "openai/gpt-6-astra",
        "name": "OpenAI: GPT-6 Astra",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 72.00,
        "output_rmb_per_1m": 360.00,
        "cache_hit_factor": 0.50,
        "context_length": 1_050_000,
        "is_free": False,
        "value_score": 80.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "openai/gpt-5.4",
        "api_model_id": "openai/gpt-5.4",
        "name": "OpenAI: GPT-5.4",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 18.00,
        "output_rmb_per_1m": 108.00,
        "cache_hit_factor": 0.50,
        "context_length": 1_050_000,
        "is_free": False,
        "value_score": 85.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "openai/gpt-5.3-codex",
        "api_model_id": "openai/gpt-5.3-codex",
        "name": "OpenAI: GPT-5.3 Codex",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 12.60,
        "output_rmb_per_1m": 100.80,
        "cache_hit_factor": 0.50,
        "context_length": 400_000,
        "is_free": False,
        "value_score": 87.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "openai/gpt-5.1-codex-mini",
        "api_model_id": "openai/gpt-5.1-codex-mini",
        "name": "OpenAI: GPT-5.1 Codex Mini",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 1.80,
        "output_rmb_per_1m": 14.40,
        "cache_hit_factor": 0.50,
        "context_length": 400_000,
        "is_free": False,
        "value_score": 90.0,
        "tags": ["coding", "reasoning", "cheap", "global"],
    },
    {
        "id": "openai/gpt-5.4-mini",
        "api_model_id": "openai/gpt-5.4-mini",
        "name": "OpenAI: GPT-5.4 Mini",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 5.40,
        "output_rmb_per_1m": 32.40,
        "cache_hit_factor": 0.50,
        "context_length": 400_000,
        "is_free": False,
        "value_score": 89.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "x-ai/grok-4",
        "api_model_id": "x-ai/grok-4",
        "name": "xAI: Grok 4",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 21.60,
        "output_rmb_per_1m": 108.00,
        "cache_hit_factor": 0.25,
        "context_length": 256_000,
        "is_free": False,
        "value_score": 86.0,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "x-ai/grok-code-fast-1",
        "api_model_id": "x-ai/grok-code-fast-1",
        "name": "xAI: Grok Code Fast 1",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 1.44,
        "output_rmb_per_1m": 10.80,
        "cache_hit_factor": 0.25,
        "context_length": 256_000,
        "is_free": False,
        "value_score": 92.0,
        "tags": ["coding", "reasoning", "cheap", "global"],
    },
    {
        "id": "google/gemini-4-hydrogen",
        "api_model_id": "google/gemini-4-hydrogen",
        "name": "Google: Gemini 4 Hydrogen",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 10.80,
        "output_rmb_per_1m": 54.00,
        "cache_hit_factor": 0.50,
        "context_length": 1_048_576,
        "is_free": False,
        "value_score": 89.5,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "google/gemini-3.8-flash",
        "api_model_id": "google/gemini-3.8-flash",
        "name": "Google: Gemini 3.8 Flash",
        "provider": "OpenRouter",
        "region": "global",
        "input_rmb_per_1m": 5.94,
        "output_rmb_per_1m": 29.70,
        "cache_hit_factor": 0.50,
        "context_length": 1_048_576,
        "is_free": False,
        "value_score": 91.5,
        "tags": ["coding", "reasoning", "global"],
    },
    {
        "id": "aliyun-bailian/qwen3.5-plus",
        "api_model_id": "qwen3.5-plus",
        "name": "阿里云百炼 · Qwen3.5-Plus",
        "provider": "阿里云百炼",
        "region": "cn_direct",
        "input_rmb_per_1m": 0.80,
        "output_rmb_per_1m": 2.00,
        "cache_hit_factor": 0.20,
        "context_length": 1_000_000,
        "is_free": False,
        "value_score": 98.0,
        "tags": ["coding", "reasoning", "cheap", "cn_direct"],
    },
    {
        "id": "aliyun-bailian/qwen3-coder-next",
        "api_model_id": "qwen3-coder-next",
        "name": "阿里云百炼 · Qwen3-Coder-Next",
        "provider": "阿里云百炼",
        "region": "cn_direct",
        "input_rmb_per_1m": 1.20,
        "output_rmb_per_1m": 4.80,
        "cache_hit_factor": 0.20,
        "context_length": 262_144,
        "is_free": False,
        "value_score": 96.0,
        "tags": ["coding", "reasoning", "cheap", "cn_direct"],
    },
    {
        "id": "tencent-cloud/hunyuan-t1",
        "api_model_id": "hunyuan-t1-latest",
        "name": "腾讯云 · 混元 T1",
        "provider": "腾讯云",
        "region": "cn_direct",
        "input_rmb_per_1m": 1.00,
        "output_rmb_per_1m": 4.00,
        "cache_hit_factor": 0.20,
        "context_length": 256_000,
        "is_free": False,
        "value_score": 95.0,
        "tags": ["coding", "reasoning", "cheap", "cn_direct"],
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
        "context_length": 131_072,
        "is_free": False,
        "value_score": 94.0,
        "tags": ["coding", "cheap", "cn_direct"],
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
        "context_length": 65_536,
        "is_free": False,
        "value_score": 93.0,
        "tags": ["coding", "reasoning", "cn_direct"],
    },
    {
        "id": "siliconflow/THUDM/GLM-5",
        "api_model_id": "THUDM/GLM-5",
        "name": "硅基流动 · GLM-5",
        "provider": "SiliconFlow",
        "region": "cn_direct",
        "input_rmb_per_1m": 1.50,
        "output_rmb_per_1m": 6.00,
        "cache_hit_factor": 0.25,
        "context_length": 200_000,
        "is_free": False,
        "value_score": 94.5,
        "tags": ["coding", "reasoning", "cheap", "cn_direct"],
    },
    {
        "id": "siliconflow/moonshotai/Kimi-K2.5",
        "api_model_id": "moonshotai/Kimi-K2.5",
        "name": "硅基流动 · Kimi-K2.5",
        "provider": "SiliconFlow",
        "region": "cn_direct",
        "input_rmb_per_1m": 2.00,
        "output_rmb_per_1m": 8.00,
        "cache_hit_factor": 0.25,
        "context_length": 262_144,
        "is_free": False,
        "value_score": 93.5,
        "tags": ["coding", "reasoning", "cheap", "cn_direct"],
    },
    {
        "id": "volcengine/doubao-seed-2.0-pro",
        "api_model_id": "doubao-seed-2-0-pro-250415",
        "name": "火山引擎 · 豆包 Seed 2.0 Pro",
        "provider": "火山引擎",
        "region": "cn_direct",
        "input_rmb_per_1m": 0.80,
        "output_rmb_per_1m": 2.00,
        "cache_hit_factor": 0.20,
        "context_length": 256_000,
        "is_free": False,
        "value_score": 95.5,
        "tags": ["coding", "cheap", "cn_direct"],
    },
]


def _safe_float(val: Any) -> float:
    if val is None or isinstance(val, (dict, list, bool)):
        return 0.0
    if isinstance(val, (int, float)):
        return max(0.0, float(val))
    s = str(val).strip().replace(",", "").replace("_", "")
    if not s:
        return 0.0
    try:
        return max(0.0, float(s))
    except ValueError:
        return 0.0


def _first_scalar(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None and not isinstance(v, (dict, list, bool)):
            return v
    return None


def _parse_currency_rmb(raw_val: Any, is_usd: bool, fx_rate: float = DEFAULT_FX_USD_TO_RMB) -> float:
    s = str(raw_val or "").strip()
    if not s or s.lower() in ("-", "n/a", "na", "null", "none"):
        return 0.0
    low = s.lower()
    explicit_rmb = ("¥" in s) or ("￥" in s) or ("rmb" in low) or ("cny" in low)
    explicit_usd = ("$" in s) or ("usd" in low)
    cleaned = re.sub(r"(?:rmb|cny|usd|元|美元|[¥￥$])", "", s, flags=re.IGNORECASE).strip()
    num = _safe_float(cleaned)
    if explicit_rmb:
        return num
    if explicit_usd or is_usd:
        return num * fx_rate
    return num


def _load_catalog(*, offline: bool = False) -> dict[str, Any]:
    local_candidates: list[Path] = []
    if "__file__" in globals():
        here = Path(__file__).resolve().parent
        local_candidates.extend(
            [
                here.parent / "shared_data" / "models_live.json",
                here / "models_live.json",
            ]
        )

    if not offline:
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                LIVE_CATALOG_URL,
                headers={"User-Agent": "ai-cost-radar-local-cli/3.11", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and isinstance(data.get("models"), list) and data["models"]:
                    return data
        except (OSError, urllib.error.URLError, ValueError):
            pass

    for cand in local_candidates:
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("models"), list) and data["models"]:
                    return data
            except (OSError, ValueError):
                continue

    return {
        "quote_verified_date": "2026-11-13",
        "fx_rate_usd_to_rmb": DEFAULT_FX_USD_TO_RMB,
        "models": EMBEDDED_FALLBACK_MODELS,
    }


def resolve_catalog_model(models: list[dict[str, Any]], raw_query: str) -> dict[str, Any]:
    if not models:
        return EMBEDDED_FALLBACK_MODELS[1]
    raw = str(raw_query or "claude-sonnet-4").strip()
    q_low = raw.lower()
    norm_id = q_low
    if norm_id.startswith("aliyun/"):
        norm_id = "aliyun-bailian/" + norm_id[len("aliyun/") :]
    elif norm_id.startswith("tencent/"):
        norm_id = "tencent-cloud/" + norm_id[len("tencent/") :]

    for m in models:
        mid = str(m.get("id") or "")
        if mid == raw or mid.lower() == norm_id:
            return m

    suffix_hits = [
        m
        for m in models
        if str(m.get("api_model_id") or "").lower() == q_low
        or str(m.get("id") or "").lower().endswith("/" + q_low)
    ]
    if suffix_hits:
        suffix_hits.sort(
            key=lambda item: (
                1 if item.get("region") == "cn_direct" else 0,
                0 if item.get("is_free") else 1,
                float(item.get("value_score") or 0.0),
            ),
            reverse=True,
        )
        return suffix_hits[0]

    stripped_q = re.sub(r"-(?:20\d{2}-\d{2}-\d{2}|20\d{6}|\d{4})$", "", q_low)
    slug_base = stripped_q.split("/")[-1]
    alias_cands: list[str] = []
    if stripped_q != q_low:
        alias_cands.extend([stripped_q, slug_base])
    if slug_base in ("deepseek-reasoner", "r1"):
        alias_cands.append("deepseek-r1")
    elif slug_base in ("deepseek-chat", "v3"):
        alias_cands.append("deepseek-v3")
    elif "codex" in slug_base and ("mini" in slug_base or "nano" in slug_base):
        alias_cands.extend(["openai/gpt-5.1-codex-mini", "openai/gpt-5.4-mini", "openai/gpt-5-mini"])
    elif "codex" in slug_base:
        alias_cands.extend(["openai/gpt-5.3-codex", "openai/gpt-5.2-codex", "openai/gpt-5.4"])
    elif slug_base in ("gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano", "o1-mini", "o3-mini", "o4-mini") or (
        slug_base.startswith(("gpt-6", "gpt-5", "gpt-4")) and ("mini" in slug_base or "nano" in slug_base)
    ):
        alias_cands.extend(["openai/gpt-5.4-mini", "openai/gpt-5-mini"])
    elif slug_base.startswith(("gpt-6", "gpt-5", "gpt-4", "chatgpt-4o")) or slug_base in ("o1", "o3", "o3-pro"):
        alias_cands.extend(["openai/gpt-5.4", "openai/gpt-5.5"])
    elif "claude" in slug_base and "sonnet" in slug_base:
        alias_cands.extend(["anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5"])
    elif "claude" in slug_base and "opus" in slug_base:
        alias_cands.extend(["anthropic/claude-opus-5.5", "anthropic/claude-opus-5"])
    elif "claude" in slug_base and "haiku" in slug_base:
        alias_cands.append("anthropic/claude-haiku-5.5")
    elif "grok" in slug_base and ("fast" in slug_base or "code" in slug_base or "mini" in slug_base):
        alias_cands.extend(["x-ai/grok-code-fast-1", "x-ai/grok-4"])
    elif "grok" in slug_base:
        alias_cands.extend(["x-ai/grok-4", "x-ai/grok-code-fast-1"])
    elif "gemini" in slug_base and ("flash" in slug_base or "lite" in slug_base):
        alias_cands.extend(["google/gemini-3.8-flash", "google/gemini-3.7-flash", "google/gemini-2.5-flash"])
    elif "gemini" in slug_base or slug_base in ("antigravity", "antigravity-pro"):
        alias_cands.extend(["google/gemini-4-hydrogen", "google/gemini-2.5-pro", "google/gemini-3.8-flash"])

    for ca in alias_cands:
        ca_low = ca.lower()
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
            return ca_hits[0]

    q_tokens = [tok for tok in norm_id.replace("/", " ").replace("-", " ").split() if tok]
    best = models[0]
    best_rank = -1.0
    for m in models:
        mid = str(m.get("id") or "").lower()
        api_mid = str(m.get("api_model_id") or "").lower()
        mname = str(m.get("name") or "").lower()
        hay = f"{mid} {api_mid} {mname} {str(m.get('provider') or '').lower()}"
        score = 0.0
        if norm_id in mid or (api_mid and q_low in api_mid):
            score = 700.0
        elif q_low in mname:
            score = 600.0
        elif q_tokens and all(tok in hay for tok in q_tokens):
            score = 500.0
        elif q_tokens:
            overlap = sum(1 for tok in q_tokens if tok in hay)
            if overlap > 0:
                score = overlap * 120.0
        if score > 0:
            if not m.get("is_free"):
                score += float(m.get("value_score") or 0.0) * 0.1
            else:
                score -= 50.0
            if score > best_rank:
                best_rank = score
                best = m
    return best


def _calc_monthly_rmb(
    monthly_in_m: float,
    monthly_out_m: float,
    model: dict[str, Any],
    cache_hit_rate: float,
) -> float:
    hit = min(1.0, max(0.0, float(cache_hit_rate or 0.0)))
    factor = float(
        model.get("cache_hit_factor")
        if model.get("cache_hit_factor") is not None
        else (0.20 if model.get("region") == "cn_direct" else 0.50)
    )
    eff_in = (1.0 - hit) + (hit * factor)
    in_cost = max(0.0, monthly_in_m) * eff_in * float(model.get("input_rmb_per_1m") or 0.0)
    out_cost = max(0.0, monthly_out_m) * float(model.get("output_rmb_per_1m") or 0.0)
    return round(in_cost + out_cost, 4)


def _safe_rel_session_label(file_path: Path, root_dir: Path, client_prefix: str | None = None) -> str:
    try:
        rel = file_path.resolve().relative_to(root_dir.resolve()).as_posix()
    except ValueError:
        rel = file_path.name
    parts = [p for p in rel.split("/") if p and p not in (".", "..")]
    if client_prefix == "codex":
        return f"codex/{parts[-1] if parts else file_path.name}"
    if client_prefix == "antigravity" or ".system_generated" in parts:
        conv_id = parts[0] if parts else "conv"
        return f"antigravity/{conv_id}/{file_path.name}"
    if client_prefix == "grok":
        sess_id = parts[-2] if len(parts) >= 2 else "session"
        return f"grok/{sess_id}/{file_path.name}"
    if client_prefix == "opencode":
        sess_id = parts[-2] if len(parts) >= 2 else (parts[-1] if parts else file_path.name)
        return f"opencode/{sess_id}"
    if client_prefix == "workbuddy":
        tail = "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else file_path.name)
        return f"workbuddy/{tail}"
    if client_prefix == "qwen":
        tail = "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else file_path.name)
        return f"qwen/{tail}"
    if client_prefix == "cline":
        tail = "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else file_path.name)
        return f"cline/{tail}"
    if len(parts) > 2:
        parts = parts[-2:]
    base = "/".join(parts) if parts else file_path.name
    if client_prefix == "claude":
        return f"claude/{base}"
    return base


def discover_client_roots(
    client: str = "all",
    *,
    home_dir: str | Path | None = None,
) -> list[tuple[str, Path]]:
    """
    Auto-discover existing local log directories across all 8 exact-telemetry coding/agent clients
    without reading any file contents yet.
    """
    norm_client = str(client or "all").strip().lower()
    if norm_client not in SUPPORTED_CLIENTS:
        raise ValueError(f"Unsupported client '{client}' (must be one of {', '.join(SUPPORTED_CLIENTS)})")

    base_home = Path(home_dir).expanduser() if home_dir is not None else Path.home()
    candidates: list[tuple[str, Path]] = []

    if norm_client in ("all", "claude"):
        candidates.append(("claude", base_home / ".claude" / "projects"))
    if norm_client in ("all", "codex"):
        candidates.append(("codex", base_home / ".codex" / "sessions"))
        candidates.append(("codex", base_home / ".codex" / "archived_sessions"))
    if norm_client in ("all", "antigravity"):
        candidates.append(("antigravity", base_home / ".gemini" / "antigravity" / "brain"))
        candidates.append(("antigravity", base_home / "Library" / "Application Support" / "Antigravity" / "brain"))
    if norm_client in ("all", "opencode"):
        if home_dir is None and os.environ.get("OPENCODE_DATA_DIR"):
            candidates.append(("opencode", Path(os.environ["OPENCODE_DATA_DIR"]).expanduser()))
        candidates.append(("opencode", base_home / ".local" / "share" / "opencode"))
        candidates.append(("opencode", base_home / "AppData" / "Local" / "opencode"))
    if norm_client in ("all", "grok"):
        if home_dir is None and os.environ.get("GROK_HOME"):
            candidates.append(("grok", Path(os.environ["GROK_HOME"]).expanduser() / "sessions"))
        candidates.append(("grok", base_home / ".grok" / "sessions"))
    if norm_client in ("all", "workbuddy"):
        candidates.append(("workbuddy", base_home / ".workbuddy"))
        candidates.append(("workbuddy", base_home / ".codebuddy"))
    if norm_client in ("all", "qwen"):
        candidates.append(("qwen", base_home / ".qwen"))
        candidates.append(("qwen", base_home / ".qoder"))
    if norm_client in ("all", "cline"):
        for ide_dir in ("Code", "Cursor"):
            for ext_id in ("saoudrizwan.claude-dev", "rooveterinaryinc.roo-cline"):
                candidates.append(
                    ("cline", base_home / "Library" / "Application Support" / ide_dir / "User" / "globalStorage" / ext_id / "tasks")
                )
                candidates.append(
                    ("cline", base_home / ".config" / ide_dir / "User" / "globalStorage" / ext_id / "tasks")
                )
                candidates.append(
                    ("cline", base_home / "AppData" / "Roaming" / ide_dir / "User" / "globalStorage" / ext_id / "tasks")
                )
                if home_dir is None and os.environ.get("APPDATA"):
                    candidates.append(
                        ("cline", Path(os.environ["APPDATA"]) / ide_dir / "User" / "globalStorage" / ext_id / "tasks")
                    )

    discovered: list[tuple[str, Path]] = []
    seen_resolved: set[Path] = set()
    for c_name, c_path in candidates:
        try:
            if c_path.is_dir():
                resolved = c_path.resolve()
                if resolved not in seen_resolved:
                    seen_resolved.add(resolved)
                    discovered.append((c_name, c_path))
        except OSError:
            continue
    return discovered


def _decompress_zst_bytes(fpath: Path) -> str:
    """Decode a `.jsonl.zst` file strictly in memory (zero temp files, zero third-party deps)."""
    try:
        from compression import zstd as _stdlib_zstd  # type: ignore[attr-defined]

        return _stdlib_zstd.decompress(fpath.read_bytes()).decode("utf-8", errors="replace")
    except Exception:
        pass
    zstd_bin = shutil.which("zstd")
    if zstd_bin:
        try:
            proc = subprocess.run(
                [zstd_bin, "-dc", str(fpath)],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError):
            pass
    return ""


def _load_records_from_session_file(fpath: Path) -> list[dict[str, Any]]:
    fname_low = fpath.name.lower()
    if fname_low in ("settings.json", "auth.json", "config.json", "summary.json", "mcp.json"):
        return []
    if fname_low == "ui_messages.json" or (fname_low.endswith(".json") and not fname_low.endswith(".jsonl")):
        raw_txt = fpath.read_text(encoding="utf-8", errors="replace").strip()
        if not raw_txt:
            return []
        try:
            parsed = json.loads(raw_txt)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            return [parsed]
        return []

    if fname_low.endswith(".jsonl.zst"):
        raw_zst_text = _decompress_zst_bytes(fpath)
        if not raw_zst_text:
            return []
        out_zst: list[dict[str, Any]] = []
        for raw_line in raw_zst_text.splitlines():
            ln = raw_line.strip()
            if not ln or not ln.startswith("{"):
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                out_zst.append(rec)
        return out_zst

    out: list[dict[str, Any]] = []
    is_agy_transcript = fname_low == "transcript.jsonl"
    with fpath.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            if is_agy_transcript and "PLANNER_RESPONSE" not in raw_line and "planner_response" not in raw_line:
                continue
            ln = raw_line.strip()
            if not ln or not ln.startswith("{"):
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def _normalize_epoch_seconds(raw_ts: Any) -> float | None:
    if raw_ts is None or isinstance(raw_ts, bool):
        return None
    if isinstance(raw_ts, (int, float)):
        val = float(raw_ts)
        if not math.isfinite(val) or val <= 0:
            return None
        if val > 1e14:
            return val / 1_000_000.0
        if val > 1e11:
            return val / 1_000.0
        return val
    s = str(raw_ts).strip()
    if not s:
        return None
    try:
        num = float(s)
        return _normalize_epoch_seconds(num)
    except ValueError:
        pass
    try:
        iso = s.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


def _read_sqlite_agent_entries(
    db_path: Path,
    client_tag: str,
    cutoff_ts: float,
    fx_rate: float,
) -> list[tuple[dict[str, Any], str | None]]:
    """Read OpenCode (`opencode.db`) or WorkBuddy (`workbuddy.db`) strictly in read-only SQLite mode."""
    results: list[tuple[dict[str, Any], str | None]] = []
    conn: sqlite3.Connection | None = None
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        tables = {
            str(r[0])
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if r and r[0]
        }
        msg_table = (
            "message"
            if "message" in tables
            else ("session_message" if "session_message" in tables else None)
        )
        if msg_table is not None:
            cols = {
                str(r[1])
                for r in conn.execute(f"PRAGMA table_info({msg_table})").fetchall()
                if len(r) > 1
            }
            id_col = "id" if "id" in cols else "rowid"
            sess_col = "session_id" if "session_id" in cols else ("sessionID" if "sessionID" in cols else "''")
            ts_col = (
                "time_created"
                if "time_created" in cols
                else ("created_at" if "created_at" in cols else ("timestamp" if "timestamp" in cols else "NULL"))
            )
            data_col = "data" if "data" in cols else None
            if data_col is not None:
                rows = conn.execute(
                    f"SELECT {id_col}, {sess_col}, {ts_col}, {data_col} FROM {msg_table}"
                ).fetchall()
                for msg_id, sess_id, raw_ts, raw_data in rows:
                    if not isinstance(raw_data, str) or not raw_data.strip().startswith("{"):
                        continue
                    try:
                        data = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    ts_sec = _normalize_epoch_seconds(raw_ts)
                    if ts_sec is None:
                        time_obj = data.get("time") if isinstance(data.get("time"), dict) else {}
                        ts_sec = _normalize_epoch_seconds(
                            time_obj.get("created") or data.get("time_created") or data.get("created_at")
                        )
                    if ts_sec is not None and ts_sec < cutoff_ts:
                        continue
                    role_low = str(data.get("role") or "").strip().lower()
                    if role_low and role_low != "assistant":
                        continue
                    toks = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
                    if not toks:
                        continue
                    cache_obj = toks.get("cache") if isinstance(toks.get("cache"), dict) else {}
                    t_in = _safe_float(toks.get("input"))
                    c_read = _safe_float(cache_obj.get("read"))
                    c_write = _safe_float(cache_obj.get("write"))
                    row_in = t_in + c_read + c_write
                    row_cached = c_read
                    out_val = _safe_float(toks.get("output"))
                    reason_val = _safe_float(toks.get("reasoning"))
                    if row_in <= 0 and out_val <= 0:
                        continue
                    m_id = str(
                        _first_scalar(data, ("modelID", "model_id", "model")) or "anthropic/claude-sonnet-5.5"
                    ).strip()
                    prov_id = str(data.get("providerID") or "").strip()
                    if prov_id and "/" not in m_id and prov_id.lower() in ("x-ai", "openai", "anthropic", "google", "deepseek", "qwen"):
                        model_label = f"{prov_id}/{m_id}"
                    else:
                        model_label = m_id or "anthropic/claude-sonnet-5.5"
                    cost_usd = _first_scalar(data, ("cost", "cost_usd"))
                    cost_rmb = _parse_currency_rmb(cost_usd, is_usd=True, fx_rate=fx_rate) if cost_usd is not None else 0.0
                    clean_sess = str(sess_id or data.get("sessionID") or "session").strip() or "session"
                    rel_lbl = f"{client_tag}/{clean_sess}"
                    dedupe = f"{client_tag}_msg:{msg_id}" if msg_id else None
                    results.append(
                        (
                            {
                                "client": client_tag,
                                "model": model_label,
                                "requests": 1.0,
                                "input_tokens": row_in,
                                "cached_input_tokens": row_cached,
                                "output_tokens": out_val,
                                "reasoning_tokens": reason_val,
                                "reported_cost_rmb": cost_rmb,
                                "session_relpath": rel_lbl,
                                "project_name": client_tag,
                            },
                            dedupe,
                        )
                    )
                return results

        if "session" in tables:
            cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(session)").fetchall() if len(r) > 1}
            if "tokens_input" in cols and "tokens_output" in cols:
                ts_col = "time_updated" if "time_updated" in cols else ("time_created" if "time_created" in cols else "NULL")
                c_read_col = "tokens_cache_read" if "tokens_cache_read" in cols else "0"
                c_write_col = "tokens_cache_write" if "tokens_cache_write" in cols else "0"
                r_col = "tokens_reasoning" if "tokens_reasoning" in cols else "0"
                cost_col = "cost" if "cost" in cols else "0"
                m_col = "model" if "model" in cols else "NULL"
                rows = conn.execute(
                    f"SELECT id, {ts_col}, tokens_input, {c_read_col}, {c_write_col}, tokens_output, {r_col}, {cost_col}, {m_col} FROM session"
                ).fetchall()
                for s_id, raw_ts, t_in, c_read, c_write, t_out, t_r, c_usd, raw_m in rows:
                    ts_sec = _normalize_epoch_seconds(raw_ts)
                    if ts_sec is not None and ts_sec < cutoff_ts:
                        continue
                    row_in = _safe_float(t_in) + _safe_float(c_read) + _safe_float(c_write)
                    out_val = _safe_float(t_out)
                    if row_in <= 0 and out_val <= 0:
                        continue
                    m_label = "anthropic/claude-sonnet-5.5"
                    if isinstance(raw_m, str) and raw_m.strip():
                        if raw_m.strip().startswith("{"):
                            try:
                                m_obj = json.loads(raw_m)
                                m_label = str(m_obj.get("id") or m_obj.get("modelID") or m_label)
                            except json.JSONDecodeError:
                                pass
                        else:
                            m_label = raw_m.strip()
                    results.append(
                        (
                            {
                                "client": client_tag,
                                "model": m_label,
                                "requests": 1.0,
                                "input_tokens": row_in,
                                "cached_input_tokens": _safe_float(c_read),
                                "output_tokens": out_val,
                                "reasoning_tokens": _safe_float(t_r),
                                "reported_cost_rmb": _parse_currency_rmb(c_usd, is_usd=True, fx_rate=fx_rate) if c_usd else 0.0,
                                "session_relpath": f"{client_tag}/{s_id or 'session'}",
                                "project_name": client_tag,
                            },
                            f"{client_tag}_sess:{s_id}" if s_id else None,
                        )
                    )
    except (sqlite3.Error, OSError):
        return results
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
    return results


def _scan_roots_internal(
    roots: list[tuple[str | None, Path]],
    *,
    days: float = 30.0,
    seats: int = 1,
    offline: bool = False,
    catalog: dict[str, Any] | None = None,
    lang: str = "auto",
    region: str = "auto",
    currency: str = "auto",
) -> dict[str, Any]:
    obs_days = float(days if days is not None else 30.0)
    if not math.isfinite(obs_days) or obs_days <= 0 or obs_days > 365:
        raise ValueError("days must be between 0.1 and 365")
    team_seats = max(1, min(50, int(round(float(seats or 1)))))

    norm_lang = str(lang or "auto").strip().lower()
    norm_region = str(region or "auto").strip().lower()
    norm_currency = str(currency or "auto").strip().lower()
    use_global = norm_region == "global" or norm_currency == "usd"
    use_en = norm_lang == "en" or (norm_lang == "auto" and use_global)
    use_usd = norm_currency == "usd" or (norm_currency == "auto" and use_global)

    cat = catalog if isinstance(catalog, dict) else _load_catalog(offline=offline)
    models = cat.get("models") if isinstance(cat.get("models"), list) and cat.get("models") else EMBEDDED_FALLBACK_MODELS
    fx_rate = float(cat.get("fx_rate_usd_to_rmb") or DEFAULT_FX_USD_TO_RMB)
    quote_date = str(cat.get("quote_verified_date") or "2026-11-13")

    cutoff_ts = time.time() - (obs_days * 86400.0)
    candidate_files: list[tuple[str | None, Path, Path]] = []
    sqlite_targets: list[tuple[str, Path]] = []
    seen_files: set[Path] = set()

    for client_prefix, root in roots:
        if client_prefix == "cline":
            patterns: tuple[str, ...] = ("ui_messages.json",)
        elif client_prefix == "antigravity":
            patterns = ("transcript.jsonl",)
        elif client_prefix == "grok":
            patterns = ("updates.jsonl",)
        elif client_prefix == "codex":
            patterns = ("*.jsonl", "*.jsonl.zst")
        elif client_prefix == "opencode":
            db_cand = root / "opencode.db"
            if db_cand.is_file():
                sqlite_targets.append(("opencode", db_cand))
            msg_root = root / "storage" / "message"
            if msg_root.is_dir():
                for p in sorted(msg_root.rglob("*.json")):
                    if not p.is_file():
                        continue
                    try:
                        rp = p.resolve()
                        if rp not in seen_files and p.stat().st_mtime >= cutoff_ts:
                            seen_files.add(rp)
                            candidate_files.append(("opencode", msg_root, p))
                    except OSError:
                        continue
            continue
        elif client_prefix in ("workbuddy", "qwen"):
            if client_prefix == "workbuddy":
                wb_db = root / "workbuddy.db"
                if wb_db.is_file():
                    sqlite_targets.append(("workbuddy", wb_db))
            patterns = ("projects/**/*.jsonl", "sessions/**/*.jsonl", "usage-data/**/*.json", "*.jsonl")
        else:
            patterns = ("*.jsonl", "*.jsonl.zst", "ui_messages.json")

        for pat in patterns:
            for p in sorted(root.rglob(pat)):
                if not p.is_file():
                    continue
                parts_low = {pt.lower() for pt in p.parts}
                if p.name.lower() == "transcript_full.jsonl":
                    continue
                if ".system_generated" in parts_low and "chunks" in parts_low:
                    continue
                try:
                    rp = p.resolve()
                    if rp in seen_files:
                        continue
                    if p.stat().st_mtime >= cutoff_ts:
                        seen_files.add(rp)
                        candidate_files.append((client_prefix, root, p))
                except OSError:
                    continue

    skip_types = {
        "user",
        "user_input",
        "summary",
        "system",
        "file-history-snapshot",
        "queue-operation",
        "session_meta",
        "response_item",
        "compacted",
    }
    summary_labels = {"total", "totals", "sum", "summary", "合计", "总计", "汇总", "小计"}
    deduped_entries: dict[str, dict[str, Any]] = {}
    anon_entries: list[dict[str, Any]] = []
    deduplicated_chunks = 0

    def _push_entry(entry: dict[str, Any], dedupe_id: str | None) -> None:
        nonlocal deduplicated_chunks
        if dedupe_id is not None:
            if dedupe_id in deduped_entries:
                deduplicated_chunks += 1
                prev = deduped_entries[dedupe_id]
                for nk in ("requests", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "reported_cost_rmb"):
                    prev[nk] = max(prev[nk], entry[nk])
                if prev["model"] == "unknown" and entry["model"] != "unknown":
                    prev["model"] = entry["model"]
            else:
                deduped_entries[dedupe_id] = entry
        else:
            anon_entries.append(entry)

    for sq_client, sq_db in sqlite_targets:
        for sq_entry, sq_dedupe in _read_sqlite_agent_entries(sq_db, sq_client, cutoff_ts, fx_rate):
            _push_entry(sq_entry, sq_dedupe)

    for client_prefix, root, fpath in candidate_files:
        rel_label = _safe_rel_session_label(fpath, root, client_prefix=client_prefix)
        proj_name = rel_label.split("/")[0] if "/" in rel_label else root.name
        try:
            records = _load_records_from_session_file(fpath)
        except OSError:
            continue
        if not records:
            continue

        grok_summary_model: str | None = None
        if client_prefix == "grok" or fpath.name.lower() == "updates.jsonl":
            sum_file = fpath.parent / "summary.json"
            if sum_file.is_file():
                try:
                    sum_obj = json.loads(sum_file.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(sum_obj, dict):
                        sm = _first_scalar(sum_obj, ("current_model_id", "model_id", "model"))
                        if sm:
                            grok_summary_model = str(sm).strip()
                except (OSError, json.JSONDecodeError):
                    pass

        has_codex_tur = any(str(r.get("type") or "").strip().lower() == "token_usage_record" for r in records)
        sticky_codex_model: str | None = None
        last_codex_cum_total: float | None = None

        for rec in records:
            rec_type_low = str(rec.get("type") or "").strip().lower()
            if rec_type_low in skip_types:
                continue

            # Google Antigravity transcript.jsonl (`PLANNER_RESPONSE` with additive input + cache_read_tokens)
            if rec_type_low == "planner_response" or (
                (client_prefix == "antigravity" or fpath.name.lower() == "transcript.jsonl")
                and "cache_read_tokens" in rec
            ):
                if rec_type_low and rec_type_low != "planner_response":
                    continue
                uncached_agy = _safe_float(rec.get("input_tokens"))
                cread_agy = _safe_float(rec.get("cache_read_tokens"))
                cwrite_agy = _safe_float(rec.get("cache_creation_tokens"))
                row_in = uncached_agy + cread_agy + cwrite_agy
                row_cached = cread_agy
                out_val = _safe_float(rec.get("output_tokens"))
                reason_val = _safe_float(rec.get("thinking_tokens"))
                if row_in <= 0 and out_val <= 0:
                    continue
                m_agy = str(
                    _first_scalar(rec, ("model", "model_id", "model_name")) or "google/gemini-4-hydrogen"
                ).strip() or "google/gemini-4-hydrogen"
                step_idx = rec.get("step_index")
                _push_entry(
                    {
                        "client": client_prefix or "antigravity",
                        "model": m_agy,
                        "requests": 1.0,
                        "input_tokens": row_in,
                        "cached_input_tokens": row_cached,
                        "output_tokens": out_val,
                        "reasoning_tokens": reason_val,
                        "reported_cost_rmb": 0.0,
                        "session_relpath": rel_label,
                        "project_name": proj_name,
                    },
                    f"agy:{rel_label}:{step_idx}" if step_idx is not None else None,
                )
                continue

            # xAI Grok CLI updates.jsonl (`sessionUpdate == "turn_completed"`, inclusive inputTokens)
            if "sessionUpdate" in rec or client_prefix == "grok" or fpath.name.lower() == "updates.jsonl":
                su_val = str(rec.get("sessionUpdate") or "").strip()
                if su_val and su_val != "turn_completed":
                    continue
                u_grok = rec.get("usage") if isinstance(rec.get("usage"), dict) else rec
                in_g = _safe_float(_first_scalar(u_grok, ("inputTokens", "prompt_tokens", "input_tokens")))
                cread_g = _safe_float(_first_scalar(u_grok, ("cachedReadTokens", "cached_tokens", "cached_input_tokens")))
                cwrite_g = _safe_float(_first_scalar(u_grok, ("cacheCreationTokens", "cache_creation_input_tokens")))
                row_in = max(in_g, cread_g) + cwrite_g
                row_cached = min(row_in, cread_g)
                out_val = _safe_float(_first_scalar(u_grok, ("outputTokens", "completion_tokens", "output_tokens")))
                reason_val = _safe_float(_first_scalar(u_grok, ("reasoningTokens", "reasoning_tokens")))
                if row_in <= 0 and out_val <= 0:
                    continue
                m_grok = str(
                    _first_scalar(rec, ("model", "modelId", "model_id"))
                    or _first_scalar(u_grok, ("model", "modelId"))
                    or grok_summary_model
                    or "x-ai/grok-4"
                ).strip() or "x-ai/grok-4"
                c_usd = _first_scalar(u_grok, ("costUsd", "cost", "cost_usd")) or _first_scalar(rec, ("costUsd", "cost"))
                cost_rmb = _parse_currency_rmb(c_usd, is_usd=True, fx_rate=fx_rate) if c_usd is not None else 0.0
                t_id = _first_scalar(rec, ("turnId", "turn_id", "id"))
                _push_entry(
                    {
                        "client": client_prefix or "grok",
                        "model": m_grok,
                        "requests": 1.0,
                        "input_tokens": row_in,
                        "cached_input_tokens": row_cached,
                        "output_tokens": out_val,
                        "reasoning_tokens": reason_val,
                        "reported_cost_rmb": cost_rmb,
                        "session_relpath": rel_label,
                        "project_name": proj_name,
                    },
                    f"grok:{rel_label}:{t_id}" if t_id is not None else None,
                )
                continue

            # OpenCode legacy JSON message (`tokens: {input, output, reasoning, cache: {read, write}}`)
            if isinstance(rec.get("tokens"), dict) and (client_prefix == "opencode" or "modelID" in rec or "sessionID" in rec):
                role_oc = str(rec.get("role") or "").strip().lower()
                if role_oc and role_oc != "assistant":
                    continue
                toks_oc = rec["tokens"]
                cache_oc = toks_oc.get("cache") if isinstance(toks_oc.get("cache"), dict) else {}
                t_in = _safe_float(toks_oc.get("input"))
                c_read = _safe_float(cache_oc.get("read"))
                c_write = _safe_float(cache_oc.get("write"))
                row_in = t_in + c_read + c_write
                row_cached = c_read
                out_val = _safe_float(toks_oc.get("output"))
                reason_val = _safe_float(toks_oc.get("reasoning"))
                if row_in <= 0 and out_val <= 0:
                    continue
                m_oc = str(
                    _first_scalar(rec, ("modelID", "model_id", "model")) or "anthropic/claude-sonnet-5.5"
                ).strip() or "anthropic/claude-sonnet-5.5"
                c_usd = _first_scalar(rec, ("cost", "cost_usd"))
                cost_rmb = _parse_currency_rmb(c_usd, is_usd=True, fx_rate=fx_rate) if c_usd is not None else 0.0
                oc_id = _first_scalar(rec, ("id", "messageID"))
                oc_sess = str(_first_scalar(rec, ("sessionID", "session_id")) or "").strip()
                oc_rel = f"opencode/{oc_sess}" if oc_sess else rel_label
                _push_entry(
                    {
                        "client": client_prefix or "opencode",
                        "model": m_oc,
                        "requests": 1.0,
                        "input_tokens": row_in,
                        "cached_input_tokens": row_cached,
                        "output_tokens": out_val,
                        "reasoning_tokens": reason_val,
                        "reported_cost_rmb": cost_rmb,
                        "session_relpath": oc_rel,
                        "project_name": "opencode",
                    },
                    f"opencode_msg:{oc_id}" if oc_id else None,
                )
                continue

            if rec_type_low == "turn_context":
                payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
                tc_model = _first_scalar(payload, ("model", "model_id", "model_name")) or _first_scalar(rec, ("model",))
                if tc_model:
                    sticky_codex_model = str(tc_model).strip()
                continue

            if rec_type_low == "token_usage_record":
                payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
                u_nested = (
                    payload.get("usage")
                    if isinstance(payload.get("usage"), dict)
                    else (rec.get("usage") if isinstance(rec.get("usage"), dict) else {})
                )
                u_codex = {**rec, **payload, **u_nested}
                m_codex = str(_first_scalar(u_codex, ("model", "model_id")) or sticky_codex_model or "gpt-5-codex").strip() or "gpt-5-codex"
                in_v = _safe_float(u_codex.get("input_tokens"))
                c_v = _safe_float(u_codex.get("cached_input_tokens"))
                row_in = max(in_v, c_v)
                row_cached = min(row_in, c_v)
                out_val = _safe_float(u_codex.get("output_tokens"))
                reason_val = _safe_float(_first_scalar(u_codex, ("reasoning_output_tokens", "reasoning_tokens")))
                if row_in <= 0 and out_val <= 0:
                    continue
                resp_id = _first_scalar(u_codex, ("response_id", "id"))
                _push_entry(
                    {
                        "client": client_prefix or "codex",
                        "model": m_codex,
                        "requests": 1.0,
                        "input_tokens": row_in,
                        "cached_input_tokens": row_cached,
                        "output_tokens": out_val,
                        "reasoning_tokens": reason_val,
                        "reported_cost_rmb": 0.0,
                        "session_relpath": rel_label,
                        "project_name": proj_name,
                    },
                    f"codex_resp:{resp_id}" if resp_id else None,
                )
                continue

            if rec_type_low == "event_msg":
                if has_codex_tur:
                    continue
                payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
                if str(payload.get("type") or "").strip().lower() != "token_count":
                    continue
                info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
                last_u = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else None
                tot_u = info.get("total_token_usage") if isinstance(info.get("total_token_usage"), dict) else {}
                if not isinstance(last_u, dict):
                    continue
                cum_tot = _safe_float(tot_u.get("total_tokens"))
                if cum_tot > 0:
                    if last_codex_cum_total == cum_tot:
                        deduplicated_chunks += 1
                        continue
                    last_codex_cum_total = cum_tot
                m_codex = str(
                    _first_scalar(info, ("model", "model_id"))
                    or _first_scalar(payload, ("model",))
                    or sticky_codex_model
                    or "gpt-5-codex"
                ).strip() or "gpt-5-codex"
                in_v = _safe_float(last_u.get("input_tokens"))
                c_v = _safe_float(last_u.get("cached_input_tokens"))
                row_in = max(in_v, c_v)
                row_cached = min(row_in, c_v)
                out_val = _safe_float(last_u.get("output_tokens"))
                reason_val = _safe_float(_first_scalar(last_u, ("reasoning_output_tokens", "reasoning_tokens")))
                if row_in <= 0 and out_val <= 0:
                    continue
                _push_entry(
                    {
                        "client": client_prefix or "codex",
                        "model": m_codex,
                        "requests": 1.0,
                        "input_tokens": row_in,
                        "cached_input_tokens": row_cached,
                        "output_tokens": out_val,
                        "reasoning_tokens": reason_val,
                        "reported_cost_rmb": 0.0,
                        "session_relpath": rel_label,
                        "project_name": proj_name,
                    },
                    None,
                )
                continue

            if str(rec.get("say") or "").strip() == "api_req_started" and isinstance(rec.get("text"), str):
                try:
                    c_info = json.loads(rec["text"])
                except json.JSONDecodeError:
                    continue
                if not isinstance(c_info, dict):
                    continue
                t_in = _safe_float(c_info.get("tokensIn"))
                t_out = _safe_float(c_info.get("tokensOut"))
                c_reads = _safe_float(c_info.get("cacheReads"))
                c_writes = _safe_float(c_info.get("cacheWrites"))
                row_in = t_in + c_reads + c_writes
                row_cached = c_reads
                out_val = t_out
                reason_val = _safe_float(_first_scalar(c_info, ("reasoningTokens", "thinkingTokens")))
                if row_in <= 0 and out_val <= 0:
                    continue
                m_cline = str(
                    _first_scalar(c_info, ("model", "modelId", "apiModelId"))
                    or _first_scalar(rec, ("model", "modelId"))
                    or "anthropic/claude-sonnet-5.5"
                ).strip() or "anthropic/claude-sonnet-5.5"
                cost_usd = _first_scalar(c_info, ("cost", "totalCost"))
                row_cost_rmb = _parse_currency_rmb(cost_usd, is_usd=True, fx_rate=fx_rate) if cost_usd is not None else 0.0
                ts_val = _first_scalar(rec, ("ts", "id"))
                _push_entry(
                    {
                        "client": client_prefix or "cline",
                        "model": m_cline,
                        "requests": 1.0,
                        "input_tokens": row_in,
                        "cached_input_tokens": row_cached,
                        "output_tokens": out_val,
                        "reasoning_tokens": reason_val,
                        "reported_cost_rmb": row_cost_rmb,
                        "session_relpath": rel_label,
                        "project_name": proj_name,
                    },
                    f"cline:{rel_label}:{ts_val}" if ts_val is not None else None,
                )
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

            model_raw = (
                _first_scalar(rec, ("model_permaslug", "model", "model_id", "model_name", "api_model_id"))
                or _first_scalar(msg, ("model", "model_id"))
                or _first_scalar(body, ("model", "model_id"))
                or "unknown"
            )
            model_label = str(model_raw).strip() or "unknown"
            if model_label.lower() in summary_labels:
                continue

            merged: dict[str, Any] = {**rec, **body, **msg, **u}
            if "cache_read_input_tokens" in merged or "cache_creation_input_tokens" in merged:
                uncached = _safe_float(merged.get("input_tokens"))
                c_read = _safe_float(merged.get("cache_read_input_tokens"))
                c_write = _safe_float(merged.get("cache_creation_input_tokens"))
                row_in = uncached + c_read + c_write
                row_cached = c_read
            else:
                p_det = merged.get("prompt_tokens_details") if isinstance(merged.get("prompt_tokens_details"), dict) else {}
                in_det = merged.get("input_tokens_details") if isinstance(merged.get("input_tokens_details"), dict) else {}
                in_val = _safe_float(
                    _first_scalar(merged, ("prompt_tokens", "native_tokens_prompt", "tokens_prompt", "input_tokens", "total_input_tokens"))
                )
                c_raw = (
                    p_det.get("cached_tokens")
                    if p_det.get("cached_tokens") is not None
                    else (
                        in_det.get("cached_tokens")
                        if in_det.get("cached_tokens") is not None
                        else _first_scalar(merged, ("native_tokens_cached", "cached_tokens", "cached_input_tokens", "cache_hit_tokens"))
                    )
                )
                c_val = _safe_float(c_raw)
                row_in = max(in_val, c_val)
                row_cached = min(row_in, c_val)

            out_val = _safe_float(
                _first_scalar(merged, ("completion_tokens", "native_tokens_completion", "tokens_completion", "output_tokens", "total_output_tokens"))
            )
            c_det = merged.get("completion_tokens_details") if isinstance(merged.get("completion_tokens_details"), dict) else {}
            o_det = merged.get("output_tokens_details") if isinstance(merged.get("output_tokens_details"), dict) else {}
            r_raw = (
                c_det.get("reasoning_tokens")
                if c_det.get("reasoning_tokens") is not None
                else (
                    o_det.get("reasoning_tokens")
                    if o_det.get("reasoning_tokens") is not None
                    else _first_scalar(merged, ("native_tokens_reasoning", "reasoning_tokens", "reasoning_output_tokens", "thinking_tokens"))
                )
            )
            reason_val = _safe_float(r_raw)
            if row_in <= 0 and out_val <= 0:
                continue

            req_raw = _first_scalar(rec, ("requests", "total_requests", "calls", "api_calls", "num_requests", "request_count"))
            row_reqs = max(1.0, _safe_float(req_raw)) if req_raw is not None else 1.0

            rmb_raw = _first_scalar(rec, ("cost_rmb", "spend_rmb", "cost_cny", "应付金额", "账单金额"))
            usd_raw = _first_scalar(rec, ("spend", "response_cost", "cost_usd", "costUSD", "total_cost", "cost"))
            if usd_raw is None and rec.get("usage") is not None and not isinstance(rec.get("usage"), (dict, list, bool)):
                usd_raw = rec.get("usage")
            if rmb_raw is not None:
                row_cost_rmb = _parse_currency_rmb(rmb_raw, is_usd=False, fx_rate=fx_rate)
            elif usd_raw is not None:
                row_cost_rmb = _parse_currency_rmb(usd_raw, is_usd=True, fx_rate=fx_rate)
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

            _push_entry(
                {
                    "client": client_prefix or "claude",
                    "model": model_label,
                    "requests": row_reqs,
                    "input_tokens": row_in,
                    "cached_input_tokens": row_cached,
                    "output_tokens": out_val,
                    "reasoning_tokens": reason_val,
                    "reported_cost_rmb": row_cost_rmb,
                    "session_relpath": rel_label,
                    "project_name": proj_name,
                },
                dedupe_id,
            )

    all_entries = list(deduped_entries.values()) + anon_entries
    scale_30d = 30.0 / obs_days

    if use_global:
        workhorses = [
            m
            for m in models
            if m.get("region") == "global"
            and not m.get("is_free")
            and int(m.get("context_length") or 0) >= 64_000
            and (
                "grok-code-fast" in str(m.get("id") or "").lower()
                or not any(tok in str(m.get("id") or "").lower() for tok in ("7b", "8b", "lite", "turbo", "nano", "flash"))
            )
        ]
    else:
        workhorses = [
            m
            for m in models
            if m.get("region") == "cn_direct"
            and not m.get("is_free")
            and int(m.get("context_length") or 0) >= 64_000
            and not any(tok in str(m.get("id") or "").lower() for tok in ("7b", "8b", "lite", "turbo", "mini", "flash"))
        ]

    model_groups: dict[str, dict[str, Any]] = {}
    session_groups: dict[str, dict[str, Any]] = {}
    client_groups: dict[str, dict[str, Any]] = {}

    for ent in all_entries:
        mk = str(ent["model"]).lower()
        if mk not in model_groups:
            model_groups[mk] = {
                "model": str(ent["model"]),
                "requests": 0.0,
                "input_tokens": 0.0,
                "cached_input_tokens": 0.0,
                "output_tokens": 0.0,
                "reasoning_tokens": 0.0,
                "reported_cost_rmb": 0.0,
            }
        mg = model_groups[mk]
        mg["requests"] += float(ent["requests"])
        mg["input_tokens"] += float(ent["input_tokens"])
        mg["cached_input_tokens"] += float(ent["cached_input_tokens"])
        mg["output_tokens"] += float(ent["output_tokens"])
        mg["reasoning_tokens"] += float(ent["reasoning_tokens"])
        mg["reported_cost_rmb"] += float(ent["reported_cost_rmb"])

        sk = str(ent["session_relpath"])
        c_tag = str(ent.get("client") or "claude")
        if sk not in session_groups:
            session_groups[sk] = {
                "client": c_tag,
                "session_relpath": sk,
                "project_name": str(ent["project_name"]),
                "requests": 0.0,
                "input_tokens": 0.0,
                "cached_input_tokens": 0.0,
                "output_tokens": 0.0,
                "reasoning_tokens": 0.0,
                "reported_cost_rmb": 0.0,
                "by_model": {},
            }
        sg = session_groups[sk]
        sg["requests"] += float(ent["requests"])
        sg["input_tokens"] += float(ent["input_tokens"])
        sg["cached_input_tokens"] += float(ent["cached_input_tokens"])
        sg["output_tokens"] += float(ent["output_tokens"])
        sg["reasoning_tokens"] += float(ent["reasoning_tokens"])
        sg["reported_cost_rmb"] += float(ent["reported_cost_rmb"])
        if mk not in sg["by_model"]:
            sg["by_model"][mk] = {
                "model": str(ent["model"]),
                "input_tokens": 0.0,
                "cached_input_tokens": 0.0,
                "output_tokens": 0.0,
                "reported_cost_rmb": 0.0,
            }
        sbm = sg["by_model"][mk]
        sbm["input_tokens"] += float(ent["input_tokens"])
        sbm["cached_input_tokens"] += float(ent["cached_input_tokens"])
        sbm["output_tokens"] += float(ent["output_tokens"])
        sbm["reported_cost_rmb"] += float(ent["reported_cost_rmb"])

        if c_tag not in client_groups:
            client_groups[c_tag] = {
                "client": c_tag,
                "sessions": set(),
                "requests": 0.0,
                "input_tokens": 0.0,
                "cached_input_tokens": 0.0,
                "output_tokens": 0.0,
                "estimated_monthly_rmb": 0.0,
            }
        cg = client_groups[c_tag]
        cg["sessions"].add(sk)
        cg["requests"] += float(ent["requests"])
        cg["input_tokens"] += float(ent["input_tokens"])
        cg["cached_input_tokens"] += float(ent["cached_input_tokens"])
        cg["output_tokens"] += float(ent["output_tokens"])

    model_breakdown: list[dict[str, Any]] = []
    total_reqs = total_in = total_cached = total_out = total_reason = 0.0
    total_base_monthly_rmb = total_opt_monthly_rmb = 0.0

    for mg in model_groups.values():
        g_in = mg["input_tokens"]
        g_cached = min(g_in, max(0.0, mg["cached_input_tokens"]))
        g_out = mg["output_tokens"]
        hit_rate = round(g_cached / g_in, 4) if g_in > 0 else 0.0
        matched = resolve_catalog_model(models, mg["model"])

        m_in_m = (g_in * scale_30d) / 1_000_000.0
        m_out_m = (g_out * scale_30d) / 1_000_000.0
        cat_monthly_rmb = round(_calc_monthly_rmb(m_in_m, m_out_m, matched, hit_rate), 2)
        rep_monthly_rmb = round(mg["reported_cost_rmb"] * scale_30d, 2)
        base_monthly_rmb = rep_monthly_rmb if rep_monthly_rmb > 0 else cat_monthly_rmb
        obs_cost_rmb = round(base_monthly_rmb / scale_30d, 4)

        raw_low = mg["model"].lower()
        needs_reasoning = bool(
            mg["reasoning_tokens"] > 0
            or any(k in raw_low for k in ("-r1", "/r1", "deepseek-r1", "o1", "o3", "o4", "qwq", "hunyuan-t1", "thinking", "reasoner"))
        )
        req_tag = "reasoning" if needs_reasoning else "coding"
        pool = [c for c in workhorses if req_tag in (c.get("tags") or [])] or workhorses

        best_cand = matched
        best_rmb = base_monthly_rmb
        best_score = -1.0
        for cand in pool:
            c_rmb = round(_calc_monthly_rmb(m_in_m, m_out_m, cand, hit_rate), 2)
            c_score = float(cand.get("value_score") or 0.0)
            if c_rmb < best_rmb - 0.005 or (abs(c_rmb - best_rmb) <= 0.005 and c_score > best_score and best_cand is not matched):
                best_cand = cand
                best_rmb = c_rmb
                best_score = c_score

        opt_rmb = round(best_rmb, 2) if best_rmb < base_monthly_rmb - 0.005 else round(base_monthly_rmb, 2)
        rec_model = best_cand if best_rmb < base_monthly_rmb - 0.005 else matched

        total_reqs += mg["requests"]
        total_in += g_in
        total_cached += g_cached
        total_out += g_out
        total_reason += mg["reasoning_tokens"]
        total_base_monthly_rmb += base_monthly_rmb
        total_opt_monthly_rmb += opt_rmb

        model_breakdown.append(
            {
                "model": mg["model"],
                "matched_model_id": matched["id"],
                "requests": int(round(mg["requests"])),
                "input_tokens": int(round(g_in)),
                "cached_input_tokens": int(round(g_cached)),
                "output_tokens": int(round(g_out)),
                "reasoning_tokens": int(round(mg["reasoning_tokens"])),
                "cache_hit_rate": hit_rate,
                "observed_cost_rmb": obs_cost_rmb,
                "baseline_monthly_rmb": round(base_monthly_rmb, 2),
                "recommended_model_id": rec_model["id"],
                "recommended_model_name": rec_model["name"],
                "optimized_payg_rmb": opt_rmb,
                "savings_rmb": round(max(0.0, base_monthly_rmb - opt_rmb), 2),
            }
        )

    model_breakdown.sort(key=lambda x: (x["baseline_monthly_rmb"], x["input_tokens"] + x["output_tokens"]), reverse=True)

    session_breakdown: list[dict[str, Any]] = []
    for sg in session_groups.values():
        s_in = sg["input_tokens"]
        s_cached = min(s_in, max(0.0, sg["cached_input_tokens"]))
        s_out = sg["output_tokens"]
        s_hit = round(s_cached / s_in, 4) if s_in > 0 else 0.0

        est_monthly = 0.0
        top_model = "-"
        top_model_weight = (-1.0, -1.0)
        for sub in sg["by_model"].values():
            sub_in = sub["input_tokens"]
            sub_cached = min(sub_in, max(0.0, sub["cached_input_tokens"]))
            sub_hit = (sub_cached / sub_in) if sub_in > 0 else 0.0
            if sub["reported_cost_rmb"] > 0:
                sub_m_rmb = sub["reported_cost_rmb"] * scale_30d
            else:
                m_obj = resolve_catalog_model(models, sub["model"])
                sub_m_rmb = _calc_monthly_rmb(
                    (sub_in * scale_30d) / 1_000_000.0,
                    (sub["output_tokens"] * scale_30d) / 1_000_000.0,
                    m_obj,
                    sub_hit,
                )
            est_monthly += sub_m_rmb
            w = (sub_m_rmb, sub_in + sub["output_tokens"])
            if w > top_model_weight:
                top_model_weight = w
                top_model = sub["model"]

        est_monthly_rounded = round(est_monthly, 2)
        c_tag = sg["client"]
        if c_tag in client_groups:
            client_groups[c_tag]["estimated_monthly_rmb"] += est_monthly

        session_breakdown.append(
            {
                "client": c_tag,
                "session_relpath": sg["session_relpath"],
                "project_name": sg["project_name"],
                "requests": int(round(sg["requests"])),
                "input_tokens": int(round(s_in)),
                "cached_input_tokens": int(round(s_cached)),
                "output_tokens": int(round(s_out)),
                "cache_hit_rate": s_hit,
                "top_model": top_model,
                "observed_cost_rmb": round(est_monthly / scale_30d, 4),
                "estimated_monthly_rmb": est_monthly_rounded,
            }
        )

    session_breakdown.sort(
        key=lambda x: (x["estimated_monthly_rmb"], x["input_tokens"] + x["output_tokens"]),
        reverse=True,
    )

    client_breakdown: list[dict[str, Any]] = []
    for cg in client_groups.values():
        c_in = cg["input_tokens"]
        c_cached = min(c_in, max(0.0, cg["cached_input_tokens"]))
        client_breakdown.append(
            {
                "client": cg["client"],
                "sessions_count": len(cg["sessions"]),
                "requests": int(round(cg["requests"])),
                "input_tokens": int(round(c_in)),
                "cached_input_tokens": int(round(c_cached)),
                "output_tokens": int(round(cg["output_tokens"])),
                "cache_hit_rate": round(c_cached / c_in, 4) if c_in > 0 else 0.0,
                "estimated_monthly_rmb": round(cg["estimated_monthly_rmb"], 2),
            }
        )
    client_breakdown.sort(
        key=lambda x: (x["estimated_monthly_rmb"], x["input_tokens"] + x["output_tokens"]),
        reverse=True,
    )

    total_reqs_int = int(round(total_reqs))
    daily_calls = max(1, int(round(total_reqs / obs_days))) if total_reqs > 0 else 1
    monthly_calls = max(1, int(round((total_reqs / obs_days) * 30.0))) if total_reqs > 0 else 0
    avg_in = max(1, int(round(total_in / max(1.0, total_reqs)))) if total_in > 0 else 1500
    avg_out = max(1, int(round(total_out / max(1.0, total_reqs)))) if total_out > 0 else 500
    overall_hit = round(total_cached / total_in, 4) if total_in > 0 else 0.0
    inc_cot = bool(total_reason > 0)

    base_rmb = round(total_base_monthly_rmb, 2)
    opt_rmb = round(total_opt_monthly_rmb, 2)
    sav_rmb = round(max(0.0, base_rmb - opt_rmb), 2)
    sav_pct = round((sav_rmb / base_rmb) * 100.0, 1) if base_rmb > 0 else 0.0

    obs_usd = round((base_rmb / scale_30d) / fx_rate, 2)
    base_usd = round(base_rmb / fx_rate, 2)
    opt_usd = round(opt_rmb / fx_rate, 2)
    sav_usd = round(max(0.0, base_usd - opt_usd), 2)

    # Global infrastructure break-even math: Railway LiteLLM proxy (~$5/mo + 30% semantic cache savings) vs RunPod 24GB GPU (~$120/mo active coding window)
    railway_gw_usd = round(5.0 + opt_usd * 0.75 + 2.0, 2)
    runpod_gpu_usd = 124.0
    if base_usd >= runpod_gpu_usd + 15.0:
        self_host_verdict = (
            f"Monthly spend (${base_usd:,.2f}) exceeds self-hosted GPU break-even (~${runpod_gpu_usd:.0f}/mo on RunPod RTX 4090/A100 Serverless or Pod) "
            f"and Railway LiteLLM cache gateway (~${railway_gw_usd:,.2f}/mo)."
            if use_en
            else f"月账单已达弹性 GPU 回本线（RunPod 按秒 GPU 约 ${runpod_gpu_usd:.0f}/月；Railway 托管 LiteLLM 缓存网关约 ${railway_gw_usd:,.2f}/月）。"
        )
    elif base_usd >= 25.0:
        self_host_verdict = (
            f"Below dedicated GPU break-even (~${runpod_gpu_usd:.0f}/mo on RunPod), but a $5/mo Railway LiteLLM cache gateway (~${railway_gw_usd:,.2f}/mo total) "
            "or routing coding subtasks to Grok Code Fast / Gemini Flash cuts spend immediately."
            if use_en
            else f"暂未达独立 GPU 回本线（RunPod 约 ${runpod_gpu_usd:.0f}/月），但可用 Railway 轻量缓存网关（总约 ${railway_gw_usd:,.2f}/月）或高性价比按量模型降本。"
        )
    else:
        self_host_verdict = (
            f"Spend (${base_usd:,.2f}/mo) is well below RunPod GPU (~${runpod_gpu_usd:.0f}/mo) break-even; stay on Pay-As-You-Go APIs (no dedicated GPU needed yet)."
            if use_en
            else f"当前月耗（约 ${base_usd:,.2f}/月）低于独立 GPU 回本线（RunPod 约 ${runpod_gpu_usd:.0f}/月），直接保持按量 API 最划算。"
        )

    if use_en:
        if monthly_calls == 0:
            plan_verdict = "No active model API calls detected within the selected window."
        else:
            plan_verdict = (
                f"Projected ~{monthly_calls:,} model calls/mo ({team_seats} seat{'s' if team_seats > 1 else ''}); "
                f"{self_host_verdict}"
            )
    elif monthly_calls == 0:
        plan_verdict = "未检出近窗口有效模型调用记录。"
    elif monthly_calls <= LITE_MONTHLY_CAP * team_seats:
        plan_verdict = (
            f"月预计 {monthly_calls:,} 次调用（{team_seats} 席），处于腾讯/火山 Lite（¥{40 * team_seats}/月，上限 {LITE_MONTHLY_CAP * team_seats:,} 次）"
            f"与百炼/腾讯/火山 Pro（续费 ¥{200 * team_seats}/月）额度内。"
        )
    elif monthly_calls <= PRO_MONTHLY_CAP * team_seats:
        plan_verdict = (
            f"月预计 {monthly_calls:,} 次调用（{team_seats} 席），处于 Pro 档上限 {PRO_MONTHLY_CAP * team_seats:,} 次/月内"
            f"（百炼新客首月 ¥{39.9 * team_seats:.2f} / 续费 ¥{200 * team_seats}/月；注意仅覆盖国产编程模型）。"
        )
    else:
        plan_verdict = (
            f"月预计 {monthly_calls:,} 次调用，超出 {team_seats} 席 Pro 合计月上限 {PRO_MONTHLY_CAP * team_seats:,} 次；"
            "建议走国内直连按量 API 或「Pro 打底 + 溢出按量」混合方案。"
        )

    for row in model_breakdown:
        row["observed_cost_usd"] = round(float(row["observed_cost_rmb"]) / fx_rate, 4)
        row["baseline_monthly_usd"] = round(float(row["baseline_monthly_rmb"]) / fx_rate, 2)
        row["optimized_payg_usd"] = round(float(row["optimized_payg_rmb"]) / fx_rate, 2)
        row["savings_usd"] = round(float(row["savings_rmb"]) / fx_rate, 2)
    for srow in session_breakdown:
        srow["estimated_monthly_usd"] = round(float(srow["estimated_monthly_rmb"]) / fx_rate, 2)
    for crow in client_breakdown:
        crow["estimated_monthly_usd"] = round(float(crow["estimated_monthly_rmb"]) / fx_rate, 2)

    baseline_id = model_breakdown[0]["matched_model_id"] if model_breakdown else "anthropic/claude-sonnet-5.5"
    qs_params: dict[str, Any] = {
        "calls": daily_calls,
        "in": avg_in,
        "out": avg_out,
        "cache": overall_hit,
        "inc_cot": 1 if inc_cot else 0,
        "mode": "interactive_ide",
        "baseline": baseline_id,
        "src": "local_cli",
        "qv": quote_date,
    }
    if team_seats > 1:
        qs_params["seats"] = team_seats
    if use_en:
        qs_params["lang"] = "en"
    if use_global:
        qs_params["region"] = "global"
    base_web_url = f"{WEB_CALCULATOR_BASE}ai-coding-spend-auditor/" if (use_en and use_global) else WEB_CALCULATOR_BASE
    web_deep_link = f"{base_web_url}?{urllib.parse.urlencode(qs_params)}"

    return {
        "scanned_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days_observed": obs_days,
        "team_size": team_seats,
        "lang": "en" if use_en else "zh",
        "region": "global" if use_global else "cn",
        "currency": "usd" if use_usd else "rmb",
        "scanned_files_count": len(candidate_files) + len(sqlite_targets),
        "active_files_count": len(session_breakdown),
        "deduplicated_chunks": deduplicated_chunks,
        "total_requests": total_reqs_int,
        "monthly_requests": monthly_calls,
        "total_input_tokens": int(round(total_in)),
        "cached_input_tokens": int(round(total_cached)),
        "total_output_tokens": int(round(total_out)),
        "cache_hit_rate": overall_hit,
        "output_includes_reasoning": inc_cot,
        "totals": {
            "observed_baseline_rmb": round(base_rmb / scale_30d, 2),
            "baseline_monthly_rmb": base_rmb,
            "optimized_payg_monthly_rmb": opt_rmb,
            "payg_savings_rmb": sav_rmb,
            "observed_baseline_usd": obs_usd,
            "baseline_monthly_usd": base_usd,
            "optimized_payg_monthly_usd": opt_usd,
            "payg_savings_usd": sav_usd,
            "payg_savings_pct": sav_pct,
            "coding_plan_verdict": plan_verdict,
            "self_host_verdict": self_host_verdict,
        },
        "client_breakdown": client_breakdown,
        "model_breakdown": model_breakdown,
        "session_breakdown": session_breakdown,
        "web_deep_link": web_deep_link,
    }


def scan_claude_projects_dir(
    root_dir: str | Path = "~/.claude/projects",
    *,
    days: float = 30.0,
    seats: int = 1,
    offline: bool = False,
    catalog: dict[str, Any] | None = None,
    lang: str = "auto",
    region: str = "auto",
    currency: str = "auto",
) -> dict[str, Any]:
    """
    Scan a specific local session directory modified within the last `days` days (100% read-only).
    """
    root = Path(root_dir).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {root}")
    return _scan_roots_internal(
        [(None, root)],
        days=days,
        seats=seats,
        offline=offline,
        catalog=catalog,
        lang=lang,
        region=region,
        currency=currency,
    )


def scan_local_coding_logs(
    *,
    client: str = "all",
    explicit_dir: str | Path | None = None,
    home_dir: str | Path | None = None,
    days: float = 30.0,
    seats: int = 1,
    offline: bool = False,
    catalog: dict[str, Any] | None = None,
    lang: str = "auto",
    region: str = "auto",
    currency: str = "auto",
) -> dict[str, Any]:
    """
    Auto-discover and scan local Claude Code, OpenAI Codex, Google Antigravity, OpenCode,
    xAI Grok CLI, Tencent WorkBuddy/CodeBuddy, Qwen Code/Qoder, and VS Code/Cursor Cline
    session transcripts in a single unified, read-only pass.
    """
    if explicit_dir is not None:
        return scan_claude_projects_dir(
            explicit_dir,
            days=days,
            seats=seats,
            offline=offline,
            catalog=catalog,
            lang=lang,
            region=region,
            currency=currency,
        )
    discovered = discover_client_roots(client, home_dir=home_dir)
    roots: list[tuple[str | None, Path]] = [(c_name, c_path) for c_name, c_path in discovered]
    return _scan_roots_internal(
        roots,
        days=days,
        seats=seats,
        offline=offline,
        catalog=catalog,
        lang=lang,
        region=region,
        currency=currency,
    )


def export_privacy_safe_csv(report: dict[str, Any], out_path: str | Path) -> Path:
    """
    Export aggregated per-model token totals & observed RMB cost ONLY (zero prompts, zero file paths).
    Directly importable into AI Cost Radar Web UI or `pricing_core.parse_usage_log_snippet`.
    """
    dst = Path(out_path).expanduser()
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "model_permaslug",
                "requests",
                "tokens_prompt",
                "tokens_completion",
                "native_tokens_cached",
                "native_tokens_reasoning",
                "cost_rmb",
            ]
        )
        for row in report.get("model_breakdown", []):
            writer.writerow(
                [
                    row["model"],
                    row["requests"],
                    row["input_tokens"],
                    row["output_tokens"],
                    row["cached_input_tokens"],
                    row["reasoning_tokens"],
                    f"{float(row['observed_cost_rmb']):.4f}",
                ]
            )
    return dst


def _format_human_report(report: dict[str, Any], csv_exported: Path | None = None) -> str:
    totals = report["totals"]
    is_en = report.get("lang") == "en"
    is_usd = report.get("currency") == "usd"

    if is_en:
        sym = "$" if is_usd else "¥"
        b_mo = totals["baseline_monthly_usd"] if is_usd else totals["baseline_monthly_rmb"]
        b_obs = totals["observed_baseline_usd"] if is_usd else totals["observed_baseline_rmb"]
        o_mo = totals["optimized_payg_monthly_usd"] if is_usd else totals["optimized_payg_monthly_rmb"]
        s_mo = totals["payg_savings_usd"] if is_usd else totals["payg_savings_rmb"]
        lines_en = [
            "========================================================================",
            f" AI Cost Radar · Read-Only Local AI Coding & Agent Spend Report (Last {report['days_observed']:g}d)",
            " Privacy Guarantee: 100% Local Scan · Zero Prompts Uploaded · Zero Paths Sent",
            "========================================================================",
            (
                f" Scanned Sources : {report['active_files_count']} active sessions / {report['scanned_files_count']} sources"
                f" ({report['deduplicated_chunks']} duplicate stream chunks merged)"
            ),
            (
                f" API Model Calls : {report['total_requests']:,} calls (~{report['monthly_requests']:,} calls/30d · {report['team_size']} seat{'s' if report['team_size'] > 1 else ''})"
            ),
            (
                f" Token Footprint : {report['total_input_tokens']:,} input ({report['cache_hit_rate'] * 100:.1f}% cached)"
                f" · {report['total_output_tokens']:,} output"
            ),
            "------------------------------------------------------------------------",
            f" Baseline 30d Spend    : {sym}{b_mo:,.2f} / mo ({sym}{b_obs:,.2f} observed over {report['days_observed']:g}d)",
            f" Optimized PayG Spend  : {sym}{o_mo:,.2f} / mo (est. savings {sym}{s_mo:,.2f}/mo · -{totals['payg_savings_pct']:.1f}%)",
            f" Infra & GPU Verdict   : {totals.get('self_host_verdict') or totals['coding_plan_verdict']}",
        ]
        cb = report.get("client_breakdown") or []
        if cb:
            cb_parts = [
                f"{c['client']} ({c['sessions_count']} sess / {c['requests']:,} calls / {sym}{(c['estimated_monthly_usd'] if is_usd else c['estimated_monthly_rmb']):,.2f}/mo)"
                for c in cb
            ]
            lines_en.append(f" Spend by Agent Client : {' · '.join(cb_parts)}")

        mb = report.get("model_breakdown") or []
        if mb:
            lines_en.append("------------------------------------------------------------------------")
            lines_en.append(" Model Breakdown (30-Day Normalized):")
            for idx, item in enumerate(mb[:6], start=1):
                m_base = item["baseline_monthly_usd"] if is_usd else item["baseline_monthly_rmb"]
                m_opt = item["optimized_payg_usd"] if is_usd else item["optimized_payg_rmb"]
                lines_en.append(
                    f"  {idx}. {item['model']} | {item['requests']:,} calls | {item['cache_hit_rate'] * 100:.0f}% cached | "
                    f"~{sym}{m_base:,.2f}/mo -> Try {item['recommended_model_name']} ({sym}{m_opt:,.2f}/mo)"
                )

        sb = report.get("session_breakdown") or []
        if sb:
            lines_en.append("------------------------------------------------------------------------")
            lines_en.append(" Top Spend Sessions (Local Terminal Only):")
            for idx, s in enumerate(sb[:5], start=1):
                s_est = s["estimated_monthly_usd"] if is_usd else s["estimated_monthly_rmb"]
                lines_en.append(
                    f"  {idx}. {s['session_relpath']} | {s['requests']:,} calls | {s['top_model']} | ~{sym}{s_est:,.2f}/mo"
                )

        if csv_exported is not None:
            lines_en.append("------------------------------------------------------------------------")
            lines_en.append(f" Privacy-safe CSV exported (drop into Web UI to generate LiteLLM config.yaml): {csv_exported}")

        lines_en.extend(
            [
                "------------------------------------------------------------------------",
                " Interactive Calculator & GPU Break-Even Link (zero paths or prompts):",
                f" {report['web_deep_link']}",
                "========================================================================",
            ]
        )
        return "\n".join(lines_en)

    lines = [
        "========================================================================",
        f" AI Cost Radar · 本地 AI 编程与 Agent 会话只读体检报告（近 {report['days_observed']:g} 天 · 8 大客户端）",
        " 隐私承诺：100% 本地扫描 · 零对话内容上传 · 零本地路径外发",
        "========================================================================",
        (
            f" 扫描会话文件：{report['active_files_count']} 个有效 / {report['scanned_files_count']} 个候选"
            f"（流式分片去重 {report['deduplicated_chunks']} 条）"
        ),
        (
            f" 累计有效请求：{report['total_requests']:,} 次（折算 30 天约 {report['monthly_requests']:,} 次 · {report['team_size']} 席）"
        ),
        (
            f" 累计 Token  ：输入 {report['total_input_tokens']:,}（缓存命中 {report['cache_hit_rate'] * 100:.1f}%）"
            f" · 输出 {report['total_output_tokens']:,}"
        ),
        "------------------------------------------------------------------------",
        f" 当前原路径折算月账单 ：¥{totals['baseline_monthly_rmb']:,.2f} / 月（近 {report['days_observed']:g} 天实耗约 ¥{totals['observed_baseline_rmb']:,.2f}）",
        f" 国内直连按量平替月费 ：¥{totals['optimized_payg_monthly_rmb']:,.2f} / 月（预计可省 ¥{totals['payg_savings_rmb']:,.2f}/月 · -{totals['payg_savings_pct']:.1f}%）",
        f" 包月套餐配额核验     ：{totals['coding_plan_verdict']}",
    ]

    cb = report.get("client_breakdown") or []
    if cb:
        cb_parts = [
            f"{c['client']} ({c['sessions_count']} 会话 / {c['requests']:,} 次 / ¥{c['estimated_monthly_rmb']:,.2f}/月)"
            for c in cb
        ]
        lines.append(f" 按客户端消耗分布     ：{' · '.join(cb_parts)}")

    mb = report.get("model_breakdown") or []
    if mb:
        lines.append("------------------------------------------------------------------------")
        lines.append(" 按模型消耗明细（30 天折算）：")
        for idx, item in enumerate(mb[:6], start=1):
            lines.append(
                f"  {idx}. {item['model']} | {item['requests']:,} 次 | 缓存 {item['cache_hit_rate'] * 100:.0f}% | "
                f"原约 ¥{item['baseline_monthly_rmb']:,.2f}/月 -> 建议 {item['recommended_model_name']} (¥{item['optimized_payg_rmb']:,.2f}/月)"
            )

    sb = report.get("session_breakdown") or []
    if sb:
        lines.append("------------------------------------------------------------------------")
        lines.append(" 高消耗项目 / 会话文件 Top 排行（仅本地终端可见）：")
        for idx, s in enumerate(sb[:5], start=1):
            lines.append(
                f"  {idx}. {s['session_relpath']} | {s['requests']:,} 次 | 主力 {s['top_model']} | "
                f"折算约 ¥{s['estimated_monthly_rmb']:,.2f}/月"
            )

    if csv_exported is not None:
        lines.append("------------------------------------------------------------------------")
        lines.append(f" 已导出脱敏汇总 CSV（仅含模型与 Token 总量，可直接拖入网页版生成 LiteLLM 迁移配置）：{csv_exported}")

    lines.extend(
        [
            "------------------------------------------------------------------------",
            " 一键打开脱敏交互式选型台（不含任何路径或对话文本）：",
            f" {report['web_deep_link']}",
            "========================================================================",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="100% local read-only AI Coding & Agent Spend Auditor (Claude Code, Codex, Antigravity, OpenCode, Grok, WorkBuddy, Qwen, Cline)."
    )
    parser.add_argument(
        "--client",
        choices=SUPPORTED_CLIENTS,
        default="all",
        help="Auto-discover logs for 'all' (default) or a specific client family.",
    )
    parser.add_argument(
        "--dir",
        default=None,
        help="Explicit directory override to scan instead of auto-discovering client directories.",
    )
    parser.add_argument(
        "--days",
        type=float,
        default=30.0,
        help="Scan session files/rows within the last N days (default: 30).",
    )
    parser.add_argument(
        "--seats",
        type=int,
        default=1,
        help="Interactive IDE developer seats 1..50 (default: 1).",
    )
    parser.add_argument(
        "--lang",
        choices=("auto", "zh", "en"),
        default="auto",
        help="Output language: 'zh' (default for CN), 'en' (default when --region global / --currency usd), or 'auto'.",
    )
    parser.add_argument(
        "--region",
        choices=("auto", "cn", "global"),
        default="auto",
        help="Recommendation market: 'cn' (domestic RMB channels) or 'global' (USD APIs + RunPod/Railway self-host).",
    )
    parser.add_argument(
        "--currency",
        choices=("auto", "rmb", "usd"),
        default="auto",
        help="Display currency: 'rmb' (¥) or 'usd' ($).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Disable live catalog HTTP lookup and use built-in verified 2026 rates.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON report to stdout.",
    )
    parser.add_argument(
        "--export-csv",
        default=None,
        metavar="FILE",
        help="Write a privacy-safe aggregated per-model CSV (zero prompts, zero file paths).",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the privacy-safe interactive calculator deep link in your browser.",
    )
    args = parser.parse_args(argv)
    is_en_cli = args.lang == "en" or (args.lang == "auto" and (args.region == "global" or args.currency == "usd"))

    if args.dir is not None:
        target_dir = Path(args.dir).expanduser()
        if not target_dir.exists():
            msg = (
                f"Directory not found: {target_dir} (check --dir <path>)."
                if is_en_cli
                else f"未找到目录 {target_dir}（若你的日志在其他路径，请检查 --dir <路径>）。"
            )
            if args.json:
                print(json.dumps({"error": msg, "active_files_count": 0}, ensure_ascii=False, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 1
        report = scan_claude_projects_dir(
            target_dir,
            days=args.days,
            seats=args.seats,
            offline=args.offline,
            lang=args.lang,
            region=args.region,
            currency=args.currency,
        )
    else:
        discovered = discover_client_roots(args.client)
        if not discovered:
            msg = (
                f"No local {args.client} session logs found under standard paths (~/.claude, ~/.codex, ~/.gemini/antigravity, ~/.local/share/opencode, ~/.grok, ~/.workbuddy, ~/.qwen, Cline). Pass --dir <path> if customized."
                if is_en_cli
                else (
                    f"未检出本地 {args.client} 会话目录（默认自动扫描 Claude Code、Codex、Antigravity、OpenCode、Grok、WorkBuddy/CodeBuddy、Qwen 与 Cline；"
                    "若你的日志在其他路径，请使用 --dir <路径> 指定）。"
                )
            )
            if args.json:
                print(json.dumps({"error": msg, "active_files_count": 0}, ensure_ascii=False, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 1
        report = scan_local_coding_logs(
            client=args.client,
            days=args.days,
            seats=args.seats,
            offline=args.offline,
            lang=args.lang,
            region=args.region,
            currency=args.currency,
        )

    exported_path: Path | None = None
    if args.export_csv:
        exported_path = export_privacy_safe_csv(report, args.export_csv)

    if args.json:
        out_obj = dict(report)
        if exported_path is not None:
            out_obj["exported_csv"] = str(exported_path)
        print(json.dumps(out_obj, ensure_ascii=False, indent=2))
    else:
        print(_format_human_report(report, csv_exported=exported_path))

    if args.open and report.get("active_files_count", 0) > 0:
        webbrowser.open(report["web_deep_link"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
