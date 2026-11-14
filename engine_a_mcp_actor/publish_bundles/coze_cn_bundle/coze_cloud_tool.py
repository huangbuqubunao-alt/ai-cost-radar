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
LITE_5H_CAP = 1_200
DEFAULT_FX_USD_TO_RMB = 7.20

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


def _evaluate_coding_plan_verdict(daily_calls: int, payg_rmb: float, usage_mode: str, peak: int | None = None) -> dict[str, Any]:
    monthly_calls = daily_calls * 30
    is_backend = str(usage_mode or "").strip().lower() in (
        "automated_backend",
        "backend",
        "api_service",
        "batch",
        "non_interactive",
    )
    if is_backend:
        return {
            "usage_mode": "automated_backend",
            "monthly_calls_30d": monthly_calls,
            "headline_zh": (
                "当前为非交互式后端/API服务场景：已排除阿里云百炼、腾讯云与火山方舟个人 Coding Plan"
                "（官方规则仅限 Claude Code / Cursor / Cline 等交互式编程工具），请直接使用按量 API。"
            ),
            "window_note_zh": "非交互式后端不可使用个人编程套餐。",
        }

    if monthly_calls > PRO_MONTHLY_CAP:
        over = monthly_calls - PRO_MONTHLY_CAP
        headline = (
            f"按 30 天预计 {_fmt_wan(monthly_calls)}（{monthly_calls:,} 次模型调用），"
            f"超出 Pro 月额度 {_fmt_wan(over)}（百炼/腾讯/火山 Pro 月上限均为 {PRO_MONTHLY_CAP:,} 次）——"
            "¥200 包月套餐不够用，超出部分需走按量 API 或多账号/企业方案！"
        )
        window_note = f"Pro 另有每 5 小时 {PRO_5H_CAP:,} 次、每周 {PRO_WEEKLY_CAP:,} 次硬上限。"
    else:
        window_note = (
            f"月额度足够，5 小时窗口待确认（Pro 每 5h 限 {PRO_5H_CAP:,} 次 / 腾讯与火山 Lite 每 5h 限 {LITE_5H_CAP:,} 次；"
            "注意单位为模型调用次数，一次提问可能触发 5～30 次调用）。"
        )
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
    if peak is not None and monthly_calls <= PRO_MONTHLY_CAP:
        if peak > PRO_5H_CAP:
            window_note = f"5 小时峰值 {peak:,} 次，超过 Pro 窗口上限 {PRO_5H_CAP:,} 次。"
        elif peak > LITE_5H_CAP:
            window_note = "5 小时峰值超过 Lite 上限，处于 Pro 窗口额度内。"
        else:
            window_note = "5 小时峰值处于 Lite 和 Pro 窗口额度内。"
    return {
        "usage_mode": "interactive_ide",
        "monthly_calls_30d": monthly_calls,
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

    best_match = models[0]
    best_rank = -1.0
    q_tokens = [tok for tok in q.replace("/", " ").replace("-", " ").split() if tok]
    for m in models:
        mid = m["id"].lower()
        mname = m["name"].lower()
        hay = f"{mid} {mname} {m['provider'].lower()}"
        score = 0.0
        if mid == q:
            score = 1000.0
        elif mid.endswith("/" + q):
            score = 900.0
        elif q in mid:
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

    monthly_in_m = (reqs * in_tok * 30.0) / 1_000_000.0
    monthly_out_m = (reqs * out_tok * 30.0) / 1_000_000.0
    model_hit_factor = float(
        best_match.get("cache_hit_factor")
        if best_match.get("cache_hit_factor") is not None
        else (0.2 if best_match.get("region") == "cn_direct" else 0.5)
    )
    is_reasoning = "reasoning" in (best_match.get("tags") or [])
    effective_r_mult = r_mult if is_reasoning else 1.0

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
    coding_eval = _evaluate_coding_plan_verdict(int(round(reqs)), monthly_rmb, usage_mode, peak)

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
    return (
        summary,
        {
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
        },
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
    action = str(_get_param(params, "action", "recommend_cheapest_model")).strip()
    catalog = _fetch_live_catalog(logger=logger)

    if action == "calculate_api_budget":
        summary_cn, data, deep_url = _run_budget(catalog, params)
    elif action == "list_free_and_ultra_cheap_models":
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
