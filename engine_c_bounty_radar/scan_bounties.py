#!/usr/bin/env python3
"""Engine C — Autonomous GitHub Bounty Radar + Mainland China Payout Classifier.

Scans GitHub's public Search Issues API across targeted bounty queries, classifies
each bounty's Mainland China payout friendliness (`cn_payout_tier`), computes an
AI Solvability Score (0-100), and writes:
  - shared_data/bounties_live.json
  - shared_data/bounties_today.md

Uses Python 3.14 standard library ONLY.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

# Ensure local sibling imports work regardless of current working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bounty_core import (  # noqa: E402
    CONFIG_PATH,
    LIVE_JSON_PATH,
    SHARED_DIR,
    TIER_CN_FRIENDLY,
    TIER_NEED_HK_STRIPE,
    TIER_UNCONFIRMED,
    TODAY_MD_PATH,
    classify_cn_payout,
    compute_ai_solvability_score,
    extract_repo_full_name,
    extract_reward,
    github_get_json,
    has_genuine_bounty_signal,
    is_honeypot_or_mirror,
    is_non_cash_reward_text,
    load_config,
)

SEARCH_API_URL = "https://api.github.com/search/issues"

TARGETED_QUERIES: list[dict[str, Any]] = [
    {
        "id": "label_bounty_fresh",
        "description": "Fresh open unassigned issues with explicit label:bounty",
        "q": "is:issue is:open no:assignee label:bounty",
        "sort": "created",
        "order": "desc",
        "per_page": 40,
    },
    {
        "id": "usdc_crypto_bounty",
        "description": "Fresh open unassigned bounties mentioning USDC direct crypto payout",
        "q": "is:issue is:open no:assignee bounty USDC",
        "sort": "created",
        "order": "desc",
        "per_page": 40,
    },
    {
        "id": "solana_spl_bounty",
        "description": "Solana / Superteam / SPL USDC open GitHub bounties",
        "q": "is:issue is:open no:assignee bounty Solana",
        "sort": "updated",
        "order": "desc",
        "per_page": 30,
    },
    {
        "id": "l2_evm_usdt_bounty",
        "description": "EVM L2 (Base / Arbitrum / Optimism) & USDT crypto bounties",
        "q": "is:issue is:open no:assignee bounty USDT",
        "sort": "updated",
        "order": "desc",
        "per_page": 30,
    },
    {
        "id": "opire_slash_bounty",
        "description": "Opire open-source bounties (supports Crypto / PayPal / Wise)",
        "q": 'is:issue is:open no:assignee "@opire"',
        "sort": "updated",
        "order": "desc",
        "per_page": 30,
    },
    {
        "id": "ubiquity_crypto_bounty",
        "description": "UbiquityOS DevPool direct wallet crypto bounties (USDC / WXDAI)",
        "q": 'is:issue is:open no:assignee "pay.ubq.fi"',
        "sort": "updated",
        "order": "desc",
        "per_page": 30,
    },
    {
        "id": "rust_python_ts_bounty",
        "description": "High-win-rate Rust/Python/TypeScript open bounties with explicit USD reward",
        "q": 'is:issue is:open no:assignee label:bounty "$100" OR "$200" OR "$250" OR "$500"',
        "sort": "updated",
        "order": "desc",
        "per_page": 35,
    },
    {
        "id": "algora_diamond_bounty",
        "description": "Active open unassigned issues with Algora '💎 Bounty' label (for CN Stripe-gate check)",
        "q": 'is:issue is:open no:assignee label:"💎 Bounty"',
        "sort": "updated",
        "order": "desc",
        "per_page": 35,
    },
]

_SPAM_RE = re.compile(
    r"(?:whatsapp|telegram\s*@|recover\s+stolen\s+crypto|airdrop\s+claim|seed\s+phrase"
    r"|cloud\s+revenue\s+command\s+dashboard|\[\$\d+\s+site\s+credit\]|\[bounty\s+proposal\])",
    re.I,
)


def compute_action_priority(
    solvability_score: int,
    cn_tier: str,
    reward_usd: float | None,
    prioritize_cn: bool,
) -> float:
    """Composite priority score used to rank actionable bounties for Mainland China devs."""
    priority = float(solvability_score)
    if prioritize_cn:
        if cn_tier == TIER_CN_FRIENDLY:
            priority += 22.0
        elif cn_tier == TIER_UNCONFIRMED:
            priority += 6.0
        elif cn_tier == TIER_NEED_HK_STRIPE:
            priority -= 30.0

    if reward_usd is not None:
        if reward_usd >= 200:
            priority += 10.0
        elif reward_usd >= 50:
            priority += 6.0
        elif reward_usd >= 15:
            priority += 3.0

    return round(priority, 2)


def process_raw_issue(
    issue: dict[str, Any],
    source_query_id: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Normalize, filter, classify, and score a single GitHub Search issue item."""
    if "pull_request" in issue or issue.get("locked"):
        return None
    if issue.get("state") != "open":
        return None
    author_login = str((issue.get("user") or {}).get("login") or "").lower()
    if author_login in ("github-actions[bot]", "dependabot[bot]"):
        return None

    title = (issue.get("title") or "").strip()
    body = issue.get("body") or ""
    if _SPAM_RE.search(f"{title}\n{body[:1000]}"):
        return None

    labels = [
        str(lbl.get("name", "")).strip()
        for lbl in (issue.get("labels") or [])
        if isinstance(lbl, dict) and lbl.get("name")
    ]
    repo_full_name = extract_repo_full_name(issue)

    is_trap, _trap_reason = is_honeypot_or_mirror(
        repo_full_name=repo_full_name,
        title=title,
        body=body,
        labels=labels,
    )
    if is_trap:
        return None

    reward = extract_reward(title=title, body=body, labels=labels)
    if not has_genuine_bounty_signal(title=title, body=body, labels=labels, reward=reward):
        return None

    payout_cfg = config.get("payout_readiness", {})
    prefs_cfg = config.get("bounty_preferences", {})

    payout_cls = classify_cn_payout(
        title=title,
        body=body,
        labels=labels,
        payout_readiness=payout_cfg,
        repo_full_name=repo_full_name,
    )
    solvability = compute_ai_solvability_score(
        issue=issue,
        repo_full_name=repo_full_name,
        preferences=prefs_cfg,
    )
    action_priority = compute_action_priority(
        solvability_score=solvability.score,
        cn_tier=payout_cls.tier,
        reward_usd=reward.usd_estimate,
        prioritize_cn=bool(prefs_cfg.get("prioritize_cn_friendly_payouts", True)),
    )

    html_url = issue.get("html_url", "")
    unassigned = (issue.get("assignee") is None) and (len(issue.get("assignees") or []) == 0)

    # Extract concise clean snippet of the spec
    body_oneline = re.sub(r"\s+", " ", re.sub(r"<!--[\s\S]*?-->", " ", body)).strip()
    spec_excerpt = (body_oneline[:240] + "…") if len(body_oneline) > 240 else body_oneline

    return {
        "id": issue.get("id"),
        "repo": repo_full_name,
        "number": issue.get("number"),
        "title": title,
        "url": html_url,
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "comments": int(issue.get("comments") or 0),
        "unassigned": unassigned,
        "labels": labels,
        "estimated_reward": reward.display,
        "reward_usd_est": reward.usd_estimate,
        "reward_currency": reward.currency,
        "reward_source": reward.source,
        "is_non_cash_credit": is_non_cash_reward_text(title, body),
        "cn_payout_tier": payout_cls.tier,
        "cn_payout_rails": payout_cls.rails,
        "cn_payout_note": payout_cls.note,
        "is_algora_stripe_only": payout_cls.is_algora_stripe_only,
        "ai_solvability_score": solvability.score,
        "action_priority_score": action_priority,
        "matched_languages": solvability.matched_languages,
        "score_factors": solvability.factors,
        "source_queries": [source_query_id],
        "spec_excerpt": spec_excerpt,
        "sandbox_dry_run_cmd": f"python3 engine_c_bounty_radar/sandbox_prepare.py --dry-run {html_url}",
        "sandbox_clone_cmd": f"python3 engine_c_bounty_radar/sandbox_prepare.py --clone {html_url}",
    }


def load_cached_bounties_if_available() -> list[dict[str, Any]]:
    """Graceful fallback loader if GitHub API is completely rate-limited."""
    if not LIVE_JSON_PATH.exists():
        return []
    try:
        prev = json.loads(LIVE_JSON_PATH.read_text(encoding="utf-8"))
        items = prev.get("bounties", [])
        return items if isinstance(items, list) else []
    except Exception:
        return []


def recompute_cached_bounty_item(b: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    """Re-validate and re-classify a cached bounty item against current filters and payout readiness."""
    item = dict(b)
    title_txt = str(item.get("title") or "")
    excerpt_txt = str(item.get("spec_excerpt") or "")
    labels_list = [str(x) for x in (item.get("labels") or [])]
    repo_name = str(item.get("repo") or "")
    is_trap, _ = is_honeypot_or_mirror(
        repo_full_name=repo_name,
        title=title_txt,
        body=excerpt_txt,
        labels=labels_list,
    )
    if is_trap:
        return None
    rails_hint = " ".join(str(r) for r in (item.get("cn_payout_rails") or []))
    combined_body = f"{excerpt_txt}\n{rails_hint}".strip()
    reward_obj = extract_reward(title=title_txt, body=combined_body, labels=labels_list)
    if not has_genuine_bounty_signal(title=title_txt, body=combined_body, labels=labels_list, reward=reward_obj):
        return None
    payout_cfg = config.get("payout_readiness", {})
    prefs_cfg = config.get("bounty_preferences", {})
    payout_cls = classify_cn_payout(
        title=title_txt,
        body=combined_body,
        labels=labels_list,
        payout_readiness=payout_cfg,
        repo_full_name=repo_name,
    )
    item["cn_payout_tier"] = payout_cls.tier
    item["cn_payout_rails"] = payout_cls.rails
    item["cn_payout_note"] = payout_cls.note
    item["is_algora_stripe_only"] = payout_cls.is_algora_stripe_only
    if is_non_cash_reward_text(title_txt, f"{excerpt_txt}\n{item.get('cn_payout_note', '')}"):
        item["is_non_cash_credit"] = True
        if item.get("cn_payout_tier") == TIER_CN_FRIENDLY:
            item["cn_payout_tier"] = TIER_UNCONFIRMED
    item["action_priority_score"] = compute_action_priority(
        solvability_score=int(item.get("ai_solvability_score") or 0),
        cn_tier=item["cn_payout_tier"],
        reward_usd=item.get("reward_usd_est"),
        prioritize_cn=bool(prefs_cfg.get("prioritize_cn_friendly_payouts", True)),
    )
    return item


def scan_github_bounties(config: dict[str, Any], max_queries: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Execute targeted GitHub Search Issues queries and merge/deduplicate results."""
    cached_prior = load_cached_bounties_if_available()
    by_url: dict[str, dict[str, Any]] = {}
    query_stats: list[dict[str, Any]] = []
    any_success = False
    hit_rate_limit = False

    queries_to_run = TARGETED_QUERIES if max_queries is None else TARGETED_QUERIES[:max_queries]
    for idx, q_spec in enumerate(queries_to_run):
        if idx > 0:
            time.sleep(3.2)  # Polite spacing for GitHub Search API secondary rate-limit

        params = urllib.parse.urlencode(
            {
                "q": q_spec["q"],
                "sort": q_spec["sort"],
                "order": q_spec["order"],
                "per_page": q_spec["per_page"],
            }
        )
        full_url = f"{SEARCH_API_URL}?{params}"
        resp = github_get_json(full_url, timeout=15.0)
        if not resp.ok and resp.status_code == 403 and (resp.rate_limit_remaining or 0) > 0:
            # Secondary burst limit while primary quota remains: back off once and retry
            time.sleep(6.0)
            resp = github_get_json(full_url, timeout=15.0)

        if resp.ok and isinstance(resp.data, dict):
            any_success = True
            raw_items = resp.data.get("items") or []
            accepted = 0
            for raw_item in raw_items:
                processed = process_raw_issue(raw_item, q_spec["id"], config)
                if not processed:
                    continue
                accepted += 1
                url_key = processed["url"]
                if url_key in by_url:
                    existing_qs = by_url[url_key]["source_queries"]
                    if q_spec["id"] not in existing_qs:
                        existing_qs.append(q_spec["id"])
                else:
                    by_url[url_key] = processed

            query_stats.append(
                {
                    "id": q_spec["id"],
                    "query": q_spec["q"],
                    "status": "ok",
                    "http_status": resp.status_code,
                    "total_count_reported": resp.data.get("total_count", 0),
                    "fetched_items": len(raw_items),
                    "accepted_bounties": accepted,
                    "rate_limit_remaining": resp.rate_limit_remaining,
                }
            )
        else:
            if resp.rate_limited:
                hit_rate_limit = True
            query_stats.append(
                {
                    "id": q_spec["id"],
                    "query": q_spec["q"],
                    "status": "rate_limited" if resp.rate_limited else "error",
                    "http_status": resp.status_code,
                    "error": resp.error,
                    "rate_limit_remaining": resp.rate_limit_remaining,
                    "rate_limit_reset": resp.rate_limit_reset,
                }
            )
            if resp.rate_limited and (resp.rate_limit_remaining or 0) == 0:
                # Primary search bucket exhausted; stop firing further search queries
                break

    used_cache_fallback = False
    if (not any_success or hit_rate_limit) and cached_prior:
        if not any_success:
            used_cache_fallback = True
        for c_item in cached_prior:
            c_url = str(c_item.get("url") or "")
            if not c_url or c_url in by_url:
                continue
            sanitized = recompute_cached_bounty_item(c_item, config)
            if sanitized is not None:
                by_url[c_url] = sanitized

    preliminary_sorted = sorted(
        by_url.values(),
        key=lambda x: (
            x["action_priority_score"],
            x["ai_solvability_score"],
            x["reward_usd_est"] or 0.0,
            -x["comments"],
        ),
        reverse=True,
    )

    # Enforce per-repository diversity cap (at most 3 issues per repo) so no single repo floods the radar
    repo_counts: dict[str, int] = {}
    ranked: list[dict[str, Any]] = []
    for item in preliminary_sorted:
        repo_key = item["repo"]
        if repo_counts.get(repo_key, 0) >= 3:
            continue
        repo_counts[repo_key] = repo_counts.get(repo_key, 0) + 1
        ranked.append(item)

    for rank_idx, item in enumerate(ranked, start=1):
        item["rank"] = rank_idx

    return ranked, query_stats, used_cache_fallback


def is_strictly_actionable_bounty(item: dict[str, Any], max_actionable_comments: int = 40) -> bool:
    """
    Strict gate: a bounty enters 'actionable_now' ONLY when:
      1. Payout tier is confirmed CN-friendly (`TIER_CN_FRIENDLY`) — NEVER `TIER_UNCONFIRMED` or `TIER_NEED_HK_STRIPE`.
      2. Issue is unassigned.
      3. Comment count does not exceed `max_actionable_comments` (excludes heavily swarmed zombie issues).
      4. Has an explicit positive cash/crypto reward amount (not unconfirmed or non-cash site/API credits).
    """
    tier = item.get("cn_payout_tier") or item.get("payout_tier")
    if tier != TIER_CN_FRIENDLY:
        return False
    if not bool(item.get("unassigned", True)):
        return False
    if int(item.get("comments") or 0) > max_actionable_comments:
        return False
    if bool(item.get("is_non_cash_credit", False)):
        return False
    amt = item.get("reward_usd_est")
    if amt is None:
        amt = item.get("reward_amount_usd")
    if amt is not None and float(amt) > 0:
        return True
    return str(item.get("reward_currency") or "") in ("SOL", "ETH")


def _md_escape_table(text: str, max_len: int = 68) -> str:
    cleaned = (text or "").replace("|", "\\|").replace("\n", " ").strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def render_markdown_report(
    bounties: list[dict[str, Any]],
    query_stats: list[dict[str, Any]],
    config: dict[str, Any],
    generated_at_cn: str,
    used_cache_fallback: bool,
) -> str:
    """Render shared_data/bounties_today.md with actionable CN-friendly ranking."""
    payout_cfg = config.get("payout_readiness", {})
    prefs_cfg = config.get("bounty_preferences", {})

    cn_friendly = [b for b in bounties if b["cn_payout_tier"] == TIER_CN_FRIENDLY]
    unconfirmed = [b for b in bounties if b["cn_payout_tier"] == TIER_UNCONFIRMED]
    need_stripe = [b for b in bounties if b["cn_payout_tier"] == TIER_NEED_HK_STRIPE]
    actionable = [b for b in bounties if is_strictly_actionable_bounty(b)]
    verification_queue = [
        b for b in bounties if b["cn_payout_tier"] != TIER_NEED_HK_STRIPE and not is_strictly_actionable_bounty(b)
    ]

    lines: list[str] = []
    lines.append("# 🎯 Engine C — 全球开源悬赏实时雷达 (中国大陆收款友好版)")
    lines.append("")
    lines.append(f"- **扫描时间 (北京时间)**: `{generated_at_cn}`")
    lines.append(
        f"- **有效去重悬赏总数**: **{len(bounties)}** 个 "
        f"（{TIER_CN_FRIENDLY}: **{len(cn_friendly)}** | "
        f"{TIER_UNCONFIRMED}: **{len(unconfirmed)}** | "
        f"{TIER_NEED_HK_STRIPE}: **{len(need_stripe)}**）"
    )
    lines.append(
        f"- **收款就绪状态 (`config.json`)**: "
        f"支付宝/微信=`{payout_cfg.get('has_alipay_wechat')}` | "
        f"国区PayPal=`{payout_cfg.get('has_paypal_cn')}` | "
        f"Payoneer=`{payout_cfg.get('has_payoneer')}` | "
        f"USDC钱包=`{payout_cfg.get('has_usdc_wallet')}` | "
        f"港卡/海外Stripe=`{payout_cfg.get('has_hk_bank_or_stripe')}`"
    )
    lines.append(
        f"- **偏好语言栈**: `{', '.join(prefs_cfg.get('preferred_languages', []))}` "
        f"| **低竞争评论上限**: `<= {prefs_cfg.get('max_competing_comments', 8)} 条`"
    )

    if used_cache_fallback:
        lines.append("")
        lines.append("> ⚠️ **API 限流回退提示**: GitHub Search API 当前触发匿名速率限制，以下展示最近一次本地缓存快照。稍等 60 秒或设置环境变量 `GITHUB_TOKEN` 后重跑即可刷新。")

    if not bounties:
        lines.append("")
        lines.append("## ⚠️ 暂未拉取到悬赏数据")
        lines.append("当前 GitHub API 可能处于限流冷却期（匿名每分钟 10 次搜索配额）。请等待 60 秒后重新运行：")
        lines.append("```bash\npython3 engine_c_bounty_radar/scan_bounties.py\n```")
        return "\n".join(lines) + "\n"

    # Section 1: Top Strictly Verified Actionable Bounties Table
    lines.append("")
    lines.append("## 📌 已提交 PR 跟进台账（人工对账状态）")
    lines.append("")
    lines.append(
        "- `Scottcjn/rustchain-bounties` — PR `#4398` / `#4400` (`Go-Hybrid` 关联提交)："
        "**已提交待评选，奖金与资格未确认**（未计入已结算收入，待维护者合并与链上打款核实）。"
    )
    lines.append("")
    lines.append("## 🚀 Top 已核验可立即动工悬赏榜（国内直收通道已确认 + 明确现金/加密货币赏金）")
    lines.append("")
    if actionable:
        lines.append("| 排名 | 仓库 & Issue | 预估赏金 | 大陆收款分级 (`cn_payout_tier`) | AI可解度 | 评论数 | 技术栈 |")
        lines.append("| :---: | :--- | :---: | :--- | :---: | :---: | :--- |")
        for idx, b in enumerate(actionable[:15], start=1):
            issue_link = f"[{b['repo']}#{b['number']}]({b['url']}) — {_md_escape_table(b['title'], 46)}"
            langs = ", ".join(b["matched_languages"][:3]) if b["matched_languages"] else "通用"
            rails_str = f" ({'/'.join(b['cn_payout_rails'][:2])})" if b["cn_payout_rails"] else ""
            lines.append(
                f"| {idx} | {issue_link} | **{b['estimated_reward']}** | "
                f"{b['cn_payout_tier']}{rails_str} | **{b['ai_solvability_score']}/100** | "
                f"{b['comments']} | `{langs}` |"
            )
    else:
        lines.append("> 当前扫描批次暂无同时满足「国内直收通道已确认 + 明确现金/加密货币金额 + 未分配」的零障碍悬赏，请先核验下方待确认队列。")

    if verification_queue:
        lines.append("")
        lines.append("## 🔎 待人工核验队列（`🔵 通道待确认` / 金额待核实 / 疑似非现金积分 — 核实前勿盲目写代码）")
        lines.append("")
        lines.append("| 仓库 & Issue | 标称奖励 | 当前状态 | AI可解度 | 评论数 | 需人工确认事项 |")
        lines.append("| :--- | :---: | :--- | :---: | :---: | :--- |")
        for b in verification_queue[:12]:
            issue_link = f"[{b['repo']}#{b['number']}]({b['url']}) — {_md_escape_table(b['title'], 44)}"
            if b.get("is_non_cash_credit"):
                note_short = "疑似平台积分/代金券"
            elif int(b.get("comments") or 0) > 40:
                note_short = "竞争过热(评论>40)，需先核实是否仍开放"
            elif b.get("cn_payout_tier") == TIER_CN_FRIENDLY and b.get("reward_usd_est") is None:
                note_short = "通道已确认，需核实具体悬赏金额"
            elif b.get("cn_payout_tier") == TIER_UNCONFIRMED and b.get("cn_payout_rails"):
                note_short = "需确认是否支持USDC/加密货币直收"
            else:
                note_short = "需确认打款通道与真实金额"
            lines.append(
                f"| {issue_link} | **{b['estimated_reward']}** | {b['cn_payout_tier']} | "
                f"{b['ai_solvability_score']}/100 | {b['comments']} | {note_short} |"
            )

    top_table_items = actionable if actionable else verification_queue

    # Section 2: Top 5 Deep-Dive Action Cards
    lines.append("")
    lines.append("## 🔍 Top 5 精选悬赏作战卡（一键预检 & 沙盒克隆）")
    lines.append("")

    for idx, b in enumerate(top_table_items[:5], start=1):
        lines.append(f"### {idx}. [{b['repo']}#{b['number']} — {b['title']}]({b['url']})")
        lines.append(f"- **预估赏金**: `{b['estimated_reward']}` | **大陆收款分级**: **{b['cn_payout_tier']}**")
        lines.append(f"- **收款说明**: {b['cn_payout_note']}")
        lines.append(
            f"- **AI 可解度评分**: **{b['ai_solvability_score']}/100** "
            f"（综合优先分 `{b['action_priority_score']}`）— `{' | '.join(b['score_factors'])}`"
        )
        if b.get("spec_excerpt"):
            lines.append(f"- **需求摘要**: {b['spec_excerpt']}")
        lines.append("- **沙盒预检指令 (不克隆，秒查是否已有竞争 PR)**:")
        lines.append(f"  ```bash\n  {b['sandbox_dry_run_cmd']}\n  ```")
        lines.append("- **正式拉取沙盒并生成 `TASK_BRIEF.md`**:")
        lines.append(f"  ```bash\n  {b['sandbox_clone_cmd']}\n  ```")
        lines.append("")

    # Section 3: Stripe-gated Warning List (so compute isn't wasted)
    if need_stripe:
        lines.append("## 🛑 防踩坑拦截区：`🟡 需港卡/海外Stripe`（暂缓投入算力）")
        lines.append("")
        lines.append(
            "> 以下悬赏绑定 **Algora (`algora.io` / `@algora-pbc`)** Stripe Connect 提现，因 `config.json` 中 "
            "`has_hk_bank_or_stripe=false`，已被自动降权隔离，避免白白消耗 Token 与开发时间。未来开通港卡或海外 Stripe 后将其设为 `true` 即可解锁："
        )
        lines.append("")
        lines.append("| 仓库 & Issue | 预估赏金 | AI可解度 | 评论数 | 拦截原因 |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        for b in need_stripe[:10]:
            issue_link = f"[{b['repo']}#{b['number']}]({b['url']}) — {_md_escape_table(b['title'], 44)}"
            lines.append(
                f"| {issue_link} | **{b['estimated_reward']}** | {b['ai_solvability_score']}/100 | "
                f"{b['comments']} | Algora Stripe-only |"
            )
        lines.append("")

    # Section 4: Query Telemetry
    lines.append("## 📡 GitHub API 扫描诊断")
    lines.append("")
    for qs in query_stats:
        status_icon = "✅" if qs["status"] == "ok" else "⚠️"
        lines.append(
            f"- {status_icon} `{qs['id']}` (`{qs['query']}`): HTTP `{qs['http_status']}` | "
            f"入库 `{qs.get('accepted_bounties', 0)}/{qs.get('fetched_items', 0)}` 条 | "
            f"剩余搜索配额: `{qs.get('rate_limit_remaining', 'N/A')}`"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan GitHub for open unassigned bounties with Mainland China payout classification."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Path to config.json",
    )
    parser.add_argument(
        "--recompute-from-cache",
        action="store_true",
        help="Re-apply strict actionable gate and re-render shared_data/bounties_today.md from cached bounties_live.json without network calls.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    now_utc = dt.datetime.now(dt.timezone.utc)
    tz_cn = dt.timezone(dt.timedelta(hours=8))
    now_cn_str = now_utc.astimezone(tz_cn).strftime("%Y-%m-%d %H:%M:%S UTC+8")

    if args.recompute_from_cache and LIVE_JSON_PATH.exists():
        cached = json.loads(LIVE_JSON_PATH.read_text(encoding="utf-8"))
        raw_cached = cached.get("bounties", [])
        bounties = []
        for b in raw_cached:
            sanitized = recompute_cached_bounty_item(b, config)
            if sanitized is not None:
                bounties.append(sanitized)
        bounties.sort(
            key=lambda x: (
                float(x.get("action_priority_score") or 0.0),
                int(x.get("ai_solvability_score") or 0),
                float(x.get("reward_usd_est") or 0.0),
            ),
            reverse=True,
        )
        for rank_idx, item in enumerate(bounties, start=1):
            item["rank"] = rank_idx
        query_stats = cached.get("query_stats", [])
        used_cache_fallback = bool(cached.get("used_cache_fallback", False))
    else:
        print(f"[Engine C] Reading config from: {args.config}")
        print(f"[Engine C] Querying live GitHub Search Issues API across {len(TARGETED_QUERIES)} targeted queries...")
        bounties, query_stats, used_cache_fallback = scan_github_bounties(config=config)

    cn_friendly_cnt = sum(1 for b in bounties if b["cn_payout_tier"] == TIER_CN_FRIENDLY)
    unconfirmed_cnt = sum(1 for b in bounties if b["cn_payout_tier"] == TIER_UNCONFIRMED)
    need_stripe_cnt = sum(1 for b in bounties if b["cn_payout_tier"] == TIER_NEED_HK_STRIPE)
    known_rewards = [b["reward_usd_est"] for b in bounties if b.get("reward_usd_est") is not None]

    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    live_payload = {
        "engine": "engine_c_bounty_radar",
        "generated_at_utc": now_utc.isoformat(),
        "generated_at_cn": now_cn_str,
        "used_cache_fallback": used_cache_fallback,
        "config_snapshot": {
            "payout_readiness": config.get("payout_readiness", {}),
            "bounty_preferences": config.get("bounty_preferences", {}),
        },
        "summary": {
            "total_unique_bounties": len(bounties),
            "cn_friendly_direct_count": cn_friendly_cnt,
            "channel_unconfirmed_count": unconfirmed_cnt,
            "need_hk_stripe_count": need_stripe_cnt,
            "actionable_now_count": sum(1 for b in bounties if is_strictly_actionable_bounty(b)),
            "verification_queue_count": sum(
                1 for b in bounties if b["cn_payout_tier"] != TIER_NEED_HK_STRIPE and not is_strictly_actionable_bounty(b)
            ),
            "highest_usd_reward_seen": max(known_rewards) if known_rewards else None,
        },
        "query_stats": query_stats,
        "bounties": bounties,
    }

    LIVE_JSON_PATH.write_text(
        json.dumps(live_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md_report = render_markdown_report(
        bounties=bounties,
        query_stats=query_stats,
        config=config,
        generated_at_cn=now_cn_str,
        used_cache_fallback=used_cache_fallback,
    )
    TODAY_MD_PATH.write_text(md_report, encoding="utf-8")

    print(
        f"[Engine C] Done! Unique bounties: {len(bounties)} "
        f"(🟢={cn_friendly_cnt}, 🔵={unconfirmed_cnt}, 🟡={need_stripe_cnt})"
    )
    print(f"[Engine C] JSON written to:     {LIVE_JSON_PATH}")
    print(f"[Engine C] Markdown written to: {TODAY_MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
