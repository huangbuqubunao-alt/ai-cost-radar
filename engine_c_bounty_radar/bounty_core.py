#!/usr/bin/env python3
"""Core utilities for Engine C: Bounty Radar, Mainland China Payout Classifier & Scorer.

Uses Python 3.14 standard library ONLY.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
ROOT_DIR = ENGINE_DIR.parent
CONFIG_PATH = ROOT_DIR / "config.json"
SHARED_DIR = ROOT_DIR / "shared_data"
LIVE_JSON_PATH = SHARED_DIR / "bounties_live.json"
TODAY_MD_PATH = SHARED_DIR / "bounties_today.md"
SANDBOX_ROOT = ENGINE_DIR / "sandbox"

USER_AGENT = "AI-Revenue-Engine-BountyRadar/1.0 (Python/3.14; StandardLib)"

TIER_CN_FRIENDLY = "🟢 国内友好直收"
TIER_NEED_HK_STRIPE = "🟡 需港卡/海外Stripe"
TIER_UNCONFIRMED = "🔵 通道待确认"


@dataclass
class GitHubResponse:
    ok: bool
    status_code: int
    data: Any = None
    error: str | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset: int | None = None
    rate_limited: bool = False


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load config.json with safe defaults if fields are missing."""
    default_cfg: dict[str, Any] = {
        "payout_readiness": {
            "has_alipay_wechat": True,
            "has_paypal_cn": False,
            "has_payoneer": False,
            "has_usdc_wallet": False,
            "has_hk_bank_or_stripe": False,
            "usdc_base_wallet_address": "",
        },
        "bounty_preferences": {
            "preferred_languages": [
                "python",
                "typescript",
                "javascript",
                "go",
                "rust",
                "markdown",
            ],
            "max_competing_comments": 8,
            "prioritize_cn_friendly_payouts": True,
        },
    }
    if not config_path.exists():
        return default_cfg
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            for k in ("payout_readiness", "bounty_preferences"):
                if isinstance(loaded.get(k), dict):
                    default_cfg[k].update(loaded[k])
            for k, v in loaded.items():
                if k not in ("payout_readiness", "bounty_preferences"):
                    default_cfg[k] = v
    except Exception as exc:
        default_cfg["_config_load_warning"] = str(exc)
    return default_cfg


def github_get_json(
    url: str,
    timeout: float = 15.0,
    max_wait_on_ratelimit: float = 18.0,
) -> GitHubResponse:
    """Perform a polite GET request to the GitHub REST API with rate-limit handling."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"

    for attempt in range(2):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                rem_hdr = resp.headers.get("X-RateLimit-Remaining")
                rst_hdr = resp.headers.get("X-RateLimit-Reset")
                rem = int(rem_hdr) if rem_hdr and rem_hdr.isdigit() else None
                rst = int(rst_hdr) if rst_hdr and rst_hdr.isdigit() else None
                return GitHubResponse(
                    ok=True,
                    status_code=resp.status,
                    data=json.loads(raw),
                    rate_limit_remaining=rem,
                    rate_limit_reset=rst,
                )
        except urllib.error.HTTPError as err:
            rem_hdr = err.headers.get("X-RateLimit-Remaining") if err.headers else None
            rst_hdr = err.headers.get("X-RateLimit-Reset") if err.headers else None
            retry_hdr = err.headers.get("Retry-After") if err.headers else None
            rem = int(rem_hdr) if rem_hdr and rem_hdr.isdigit() else None
            rst = int(rst_hdr) if rst_hdr and rst_hdr.isdigit() else None
            body_preview = ""
            try:
                body_preview = err.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass

            is_rl = err.code in (403, 429) and (
                rem == 0
                or "rate limit" in body_preview.lower()
                or retry_hdr is not None
            )
            if is_rl and attempt == 0:
                wait_sec: float | None = None
                if retry_hdr and retry_hdr.isdigit():
                    wait_sec = float(retry_hdr) + 1.0
                elif rst is not None:
                    wait_sec = max(1.0, float(rst - time.time()) + 1.0)
                if wait_sec is not None and wait_sec <= max_wait_on_ratelimit:
                    time.sleep(wait_sec)
                    continue

            return GitHubResponse(
                ok=False,
                status_code=err.code,
                error=f"HTTP {err.code}: {body_preview or err.reason}",
                rate_limit_remaining=rem,
                rate_limit_reset=rst,
                rate_limited=is_rl,
            )
        except Exception as exc:
            return GitHubResponse(
                ok=False,
                status_code=0,
                error=f"Network/Request error: {exc}",
            )

    return GitHubResponse(ok=False, status_code=429, error="Rate limit retry exhausted", rate_limited=True)


_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def strip_code_spans(text: str) -> str:
    """Remove fenced code blocks and inline code spans to prevent technical false positives."""
    if not text:
        return ""
    cleaned = _FENCED_CODE_RE.sub(" ", text)
    cleaned = _INLINE_CODE_RE.sub(" ", cleaned)
    return cleaned


def extract_repo_full_name(issue: dict[str, Any]) -> str:
    """Extract 'owner/repo' from a GitHub issue payload."""
    repo_url = issue.get("repository_url", "")
    if "/repos/" in repo_url:
        return repo_url.split("/repos/", 1)[1].strip("/")
    html_url = issue.get("html_url", "")
    parts = urllib.parse.urlparse(html_url).path.strip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return "unknown/unknown"


@dataclass
class RewardInfo:
    display: str
    usd_estimate: float | None = None
    currency: str | None = None
    source: str = "unconfirmed"


def _parse_num(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def extract_reward(
    title: str,
    body: str,
    labels: list[str],
    extra_comments_text: str = "",
) -> RewardInfo:
    """Extract estimated bounty reward from labels, title, body, and optional comments."""
    # 1. Check labels first (highest precision)
    for lbl in labels:
        # e.g. "$100", "💎 $250", "Bounty: $500", "$1,000", "$2k"
        m_usd = re.search(r"(?:USD\s*\$?|\$)\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d{1,2})?)([kK])?\b", lbl, re.I)
        if m_usd:
            val = _parse_num(m_usd.group(1))
            if val and m_usd.group(2):
                val *= 1000.0
            if val and 1 <= val <= 100_000:
                return RewardInfo(display=f"${int(val) if val.is_integer() else val:,}", usd_estimate=val, currency="USD", source="label")
        m_crypto = re.search(r"\b(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(USDC|USDT|DAI|USD)\b", lbl, re.I)
        if m_crypto:
            val = _parse_num(m_crypto.group(1))
            cur = m_crypto.group(2).upper()
            if val and 1 <= val <= 100_000:
                disp_num = f"{int(val):,}" if val.is_integer() else f"{val}"
                return RewardInfo(display=f"{disp_num} {cur}", usd_estimate=val, currency=cur, source="label")

    # 2. Check Title
    m_title_crypto = re.search(r"\b(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(USDC|USDT|DAI|USD)\b", title, re.I)
    if m_title_crypto:
        val = _parse_num(m_title_crypto.group(1))
        cur = m_title_crypto.group(2).upper()
        if val and 1 <= val <= 100_000:
            disp_num = f"{int(val):,}" if val.is_integer() else f"{val}"
            return RewardInfo(display=f"{disp_num} {cur}", usd_estimate=val, currency=cur, source="title")

    if "site credit" not in (title or "").lower():
        m_title_usd = re.search(r"\$\s*(\d{1,3}(?:,\d{3})+|\d{1,5}(?:\.\d{1,2})?)([kK])?\b", title)
        if m_title_usd:
            val = _parse_num(m_title_usd.group(1))
            if val and m_title_usd.group(2):
                val *= 1000.0
            if val and 5 <= val <= 100_000:
                return RewardInfo(display=f"${int(val):,}", usd_estimate=val, currency="USD", source="title")

    # 3. Check Body & Comments (with code spans stripped so `$1` or `$100` in tests aren't misread)
    prose = strip_code_spans(f"{body or ''}\n{extra_comments_text or ''}")

    # Explicit /bounty command or "bounty: $XX" / "reward: $XX"
    m_cmd = re.search(
        r"(?:/bounty|bounty(?:\s+amount|\s+reward)?|reward|prize)\s*[:=\-]?\s*\$\s*(\d{1,3}(?:,\d{3})+|\d{1,5})(?:\.\d{1,2})?\b",
        prose,
        re.I,
    )
    if m_cmd:
        val = _parse_num(m_cmd.group(1))
        if val and 5 <= val <= 100_000:
            return RewardInfo(display=f"${int(val):,}", usd_estimate=val, currency="USD", source="body_explicit")

    m_slash_num = re.search(r"(?:^|\s)/bounty\s+\$?(\d{1,3}(?:,\d{3})+|\d{1,5})\b", prose, re.I)
    if m_slash_num:
        val = _parse_num(m_slash_num.group(1))
        if val and 5 <= val <= 100_000:
            return RewardInfo(display=f"${int(val):,}", usd_estimate=val, currency="USD", source="slash_bounty")

    # Crypto amounts in prose (USDC / USDT / DAI)
    m_body_crypto = re.search(r"\b(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(USDC|USDT|DAI)\b", prose, re.I)
    if m_body_crypto:
        val = _parse_num(m_body_crypto.group(1))
        cur = m_body_crypto.group(2).upper()
        if val and 2 <= val <= 100_000:
            disp_num = f"{int(val):,}" if val.is_integer() else f"{val}"
            return RewardInfo(display=f"{disp_num} {cur}", usd_estimate=val, currency=cur, source="body_crypto")

    # SOL / ETH amounts near bounty/reward context
    m_l1 = re.search(r"\b(\d+(?:\.\d+)?)\s*(SOL|ETH)\b", prose)
    if m_l1:
        amt = _parse_num(m_l1.group(1))
        cur = m_l1.group(2).upper()
        if amt and 0.005 <= amt <= 500:
            return RewardInfo(display=f"{m_l1.group(1)} {cur}", usd_estimate=None, currency=cur, source="body_crypto")

    # Standalone $XX in prose (require >= $10 and <= $25,000 to avoid noise, and exclude site/API credit)
    if not _NON_CASH_CREDIT_RE.search(prose):
        m_prose_usd = re.search(r"(?<![A-Za-z0-9_])\$\s*(\d{1,3}(?:,\d{3})+|\d{2,5})(?:\.\d{1,2})?\b", prose)
        if m_prose_usd:
            val = _parse_num(m_prose_usd.group(1))
            if val and 10 <= val <= 25_000:
                return RewardInfo(display=f"${int(val):,}", usd_estimate=val, currency="USD", source="body_usd")

    return RewardInfo(display="待确认 (未标金额)", usd_estimate=None, currency=None, source="unconfirmed")


@dataclass
class PayoutClassification:
    tier: str
    rails: list[str] = field(default_factory=list)
    is_algora_stripe_only: bool = False
    note: str = ""


# Carefully bounded patterns to avoid coding false positives ("base class", "node:crypto", "method", "otherwise")
_CN_RAIL_PATTERNS: list[tuple[str, re.Pattern[str], bool]] = [
    # (Rail label, regex, use_stripped_prose)
    ("USDC", re.compile(r"\busdc\b", re.I), True),
    ("USDT", re.compile(r"\busdt\b", re.I), True),
    ("Solana", re.compile(r"\bsolana\b|\b\d+(?:\.\d+)?\s*SOL\b", re.I), True),
    (
        "Base Chain",
        re.compile(
            r"\b(?:usdc\s+on\s+base|base\s+usdc|base\s+(?:mainnet|network|chain|l2|wallet)|on\s+base\s+(?:chain|network|l2))\b",
            re.I,
        ),
        True,
    ),
    (
        "L2 EVM (Arbitrum/Optimism/Polygon)",
        re.compile(
            r"\b(?:arbitrum|optimism|polygon)\s+(?:usdc|usdt|wallet|network|chain|mainnet)\b"
            r"|\b(?:usdc|usdt)\s+on\s+(?:arbitrum|optimism|polygon)\b",
            re.I,
        ),
        True,
    ),
    (
        "ETH",
        re.compile(
            r"\bethereum\b|\b\d+(?:\.\d+)?\s*ETH\b|\beth\s+(?:wallet|address|payout|mainnet)\b",
            re.I,
        ),
        True,
    ),
    (
        "Crypto",
        re.compile(
            r"\bcrypto(?:currency)?\s+(?:payout|payment|bounty|bounties|reward|rewards|wallet|transfer)\b"
            r"|\b(?:pay|paid|payout|paying|reward)\s+(?:in|via|with|through)\s+crypto(?:currency)?\b",
            re.I,
        ),
        True,
    ),
    ("PayPal", re.compile(r"\bpaypal\b", re.I), False),
    (
        "Wise",
        re.compile(
            r"\btransferwise\b|\bwise\.com\b|\b(?:via|through|paypal\s*/\s*|or\s+)wise\b"
            r"|\bwise\s+(?:transfer|payout|payment|account)\b",
            re.I,
        ),
        True,
    ),
    ("Payoneer", re.compile(r"\bpayoneer\b", re.I), False),
    ("Open Collective", re.compile(r"\bopen\s*collective\b", re.I), False),
    ("Opire", re.compile(r"\bopire(?:\.dev)?\b|@opire", re.I), False),
    ("Gitcoin", re.compile(r"\bgitcoin\b", re.I), False),
    ("Superteam", re.compile(r"\bsuperteam\b", re.I), False),
    ("UbiquityOS Crypto (pay.ubq.fi)", re.compile(r"\bpay\.ubq\.fi\b|\bubiquity-os\b|\bwxdai\b", re.I), False),
]

_ALGORA_RE = re.compile(r"algora\.io|@algora-pbc|\balgora-pbc\b|console\.algora\.io", re.I)
_ALGORA_DIAMOND_LABEL_RE = re.compile(r"💎\s*bounty", re.I)
_NON_CASH_CREDIT_RE = re.compile(
    r"\b(?:site\s+credits?|platform\s+credits?|api\s+credits?|store\s+credits?|free\s+mcp\s+(?:dev\s+)?keys?)\b",
    re.I,
)


def is_non_cash_reward_text(title: str, body: str) -> bool:
    prose = f"{title or ''}\n{strip_code_spans(body or '')}"
    return bool(_NON_CASH_CREDIT_RE.search(prose))


def classify_cn_payout(
    title: str,
    body: str,
    labels: list[str],
    payout_readiness: dict[str, Any],
    extra_comments_text: str = "",
    repo_full_name: str = "",
) -> PayoutClassification:
    """Classify issue payout friendliness for a developer in Mainland China."""
    raw_full = "\n".join(
        [repo_full_name or "", title or "", " ".join(labels), body or "", extra_comments_text or ""]
    )
    prose_only = "\n".join(
        [
            title or "",
            " ".join(labels),
            strip_code_spans(body or ""),
            strip_code_spans(extra_comments_text or ""),
        ]
    )

    matched_rails: list[str] = []
    for rail_name, pat, use_prose in _CN_RAIL_PATTERNS:
        haystack = prose_only if use_prose else raw_full
        if pat.search(haystack):
            matched_rails.append(rail_name)

    # UbiquityOS / DevPool Price labels pay via crypto wallet (WXDAI/USDC)
    if any(re.match(r"^Price:\s*\d+\s*USD$", l, re.I) for l in labels):
        if "UbiquityOS Crypto (pay.ubq.fi)" not in matched_rails:
            matched_rails.append("UbiquityOS Crypto (USDC/WXDAI)")

    is_algora = (
        bool(_ALGORA_RE.search(raw_full))
        or any("algora" in l.lower() or _ALGORA_DIAMOND_LABEL_RE.search(l) for l in labels)
    )
    has_hk_stripe = bool(payout_readiness.get("has_hk_bank_or_stripe", False))

    if is_algora and not matched_rails:
        if not has_hk_stripe:
            return PayoutClassification(
                tier=TIER_NEED_HK_STRIPE,
                rails=["Algora (Stripe Connect)"],
                is_algora_stripe_only=True,
                note="绑定 Algora Stripe-only 通道；当前 config.json 中 has_hk_bank_or_stripe=false，请勿盲目消耗算力（除非仓库另支持加密货币/PayPal）。",
            )
        return PayoutClassification(
            tier=TIER_CN_FRIENDLY,
            rails=["Algora (Stripe Unlocked)"],
            is_algora_stripe_only=False,
            note="Algora 悬赏（已在 config.json 启用港卡/海外 Stripe）。",
        )

    if is_non_cash_reward_text(title, body) and not matched_rails:
        return PayoutClassification(
            tier=TIER_UNCONFIRMED,
            rails=[],
            is_algora_stripe_only=False,
            note="奖励描述含 site credit / API credit / dev key（非可提现现金或加密货币），归入待核验队列，不计入可立即变现榜。",
        )

    if matched_rails:
        readiness_hints: list[str] = []
        crypto_set = {
            "USDC",
            "USDT",
            "Solana",
            "Base Chain",
            "L2 EVM (Arbitrum/Optimism/Polygon)",
            "ETH",
            "Crypto",
            "Gitcoin",
            "Superteam",
            "UbiquityOS Crypto (pay.ubq.fi)",
            "UbiquityOS Crypto (USDC/WXDAI)",
        }
        has_crypto_rail = bool(crypto_set.intersection(matched_rails))
        has_ready_fiat_rail = (
            ("PayPal" in matched_rails and bool(payout_readiness.get("has_paypal_cn")))
            or ("Payoneer" in matched_rails and bool(payout_readiness.get("has_payoneer")))
            or (
                bool({"Wise", "Open Collective", "Opire"}.intersection(matched_rails))
                and any(
                    bool(payout_readiness.get(k))
                    for k in ("has_hk_bank_or_stripe", "has_paypal_cn", "has_payoneer")
                )
            )
        )
        if not has_crypto_rail and not has_ready_fiat_rail:
            return PayoutClassification(
                tier=TIER_UNCONFIRMED,
                rails=matched_rails,
                is_algora_stripe_only=False,
                note=(
                    f"仅识别到 {', '.join(matched_rails)} 平台/法币信号"
                    "（当前 config.json 未启用对应 PayPal/Payoneer/Stripe 通道，且未见明确加密货币直付声明）；"
                    "动工前请先确认是否支持 USDC/USDT 打款。"
                ),
            )

        if has_crypto_rail:
            if payout_readiness.get("has_usdc_wallet"):
                readiness_hints.append("USDC钱包已就绪")
            else:
                readiness_hints.append("建议配置免KYC钱包地址即可直收加密货币")
        if "PayPal" in matched_rails and bool(payout_readiness.get("has_paypal_cn")):
            readiness_hints.append("国区PayPal已就绪")
        if ("Opire" in matched_rails or "Open Collective" in matched_rails) and not readiness_hints:
            readiness_hints.append("支持国际开源打款平台(PayPal/Wise/Payoneer/Crypto)")

        suffix = f"（{'；'.join(readiness_hints)}）" if readiness_hints else ""
        algora_note = " [注: 同时含Algora标记，建议确认支持非Stripe收款]" if is_algora else ""
        return PayoutClassification(
            tier=TIER_CN_FRIENDLY,
            rails=matched_rails,
            is_algora_stripe_only=False,
            note=f"识别到国内友好收款信号: {', '.join(matched_rails)}{suffix}{algora_note}",
        )

    return PayoutClassification(
        tier=TIER_UNCONFIRMED,
        rails=[],
        is_algora_stripe_only=False,
        note="通用 Bounty 标签或指令，尚未写明打款通道；动工前请先查阅仓库 README 或评论确认是否支持 USDC / PayPal / Open Collective。",
    )


_LANG_DETECT_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"\b(?:python|pytest|pydantic|fastapi|django|flask|pip|pyproject\.toml)\b|\.py\b", re.I),
    "typescript": re.compile(r"\b(?:typescript|tsx|nextjs|next\.js|nestjs|vitest|tsconfig)\b|\.tsx?\b", re.I),
    "javascript": re.compile(r"\b(?:javascript|nodejs|node\.js|react|vue|npm|pnpm|webpack|eslint)\b|\.m?jsx?\b", re.I),
    "go": re.compile(r"\b(?:golang|go\.mod|goroutine)\b|\.go\b", re.I),
    "rust": re.compile(r"\b(?:rust|cargo|crate|tokio|serde)\b|\.rs\b", re.I),
    "markdown": re.compile(r"\b(?:markdown|docs|documentation|readme|mdx|docusaurus)\b|\.mdx?\b", re.I),
}

_WIP_LABELS_RE = re.compile(r"\b(?:claimed|in[\s\-_]?progress|wip|assigned|taken)\b", re.I)
_CLEAR_SPEC_RE = re.compile(
    r"\b(?:reproduce|expected|acceptance\s+criteria|steps|requirements|specification|proposed\s+solution|deliverables|test\s+plan)\b|- \[[ x]\]",
    re.I,
)
_CODE_OR_PATH_RE = re.compile(r"```|(?:\b[\w./\-]+\.(?:py|ts|tsx|js|jsx|go|rs|md|json|yaml|yml|toml)\b)")
_AI_GOOD_TASK_RE = re.compile(
    r"\b(?:bug|fix|documentation|docs|test|tests|cli|sdk|api|plugin|parser|refactor|good\s+first\s+issue|help\s+wanted)\b",
    re.I,
)
_HEAVY_ENV_BLOCKER_RE = re.compile(
    r"\b(?:ios\s+simulator|xcode|kernel\s+driver|fpga|vr\s+headset|unreal\s+engine|cuda\s+kernel)\b",
    re.I,
)


def detect_languages(repo_full_name: str, title: str, body: str, labels: list[str]) -> list[str]:
    """Infer relevant languages/tech stacks from repo name, labels, title, and body."""
    combined = "\n".join([repo_full_name, " ".join(labels), title or "", (body or "")[:6000]])
    found: list[str] = []
    # Exact label checks for "go" (avoid matching English verb "go")
    for lbl in labels:
        l_clean = lbl.strip().lower()
        if l_clean in ("go", "golang") and "go" not in found:
            found.append("go")
    for lang, pat in _LANG_DETECT_PATTERNS.items():
        if pat.search(combined) and lang not in found:
            found.append(lang)
    return found


@dataclass
class SolvabilityResult:
    score: int
    matched_languages: list[str]
    factors: list[str]


def compute_ai_solvability_score(
    issue: dict[str, Any],
    repo_full_name: str,
    preferences: dict[str, Any],
) -> SolvabilityResult:
    """Compute a 0-100 AI Solvability Score based on competition, assignment, spec clarity & stack."""
    max_comments = int(preferences.get("max_competing_comments", 8))
    pref_langs = {str(x).lower() for x in preferences.get("preferred_languages", [])}

    title = issue.get("title") or ""
    body = issue.get("body") or ""
    comments = int(issue.get("comments") or 0)
    labels = [str(l.get("name", "")) for l in (issue.get("labels") or []) if isinstance(l, dict)]
    unassigned = (issue.get("assignee") is None) and (len(issue.get("assignees") or []) == 0)

    score = 0
    factors: list[str] = []

    # 1. Assignment & status (up to +25, heavy penalty if assigned or WIP)
    if unassigned:
        score += 25
        factors.append("未分配(+25)")
    else:
        score -= 30
        factors.append("已被分配(-30)")

    if any(_WIP_LABELS_RE.search(lbl) for lbl in labels):
        score -= 20
        factors.append("含进行中/已认领标签(-20)")

    # 2. Competition / Comment count (up to +25, penalty >10)
    if comments == 0:
        score += 25
        factors.append("0评论零竞争(+25)")
    elif comments <= max(1, max_comments // 2):
        score += 22
        factors.append(f"极低竞争:{comments}评论(+22)")
    elif comments <= max_comments:
        score += 15
        factors.append(f"竞争可控:{comments}<={max_comments}评论(+15)")
    elif comments <= 10:
        score += 5
        factors.append(f"接近竞争上限:{comments}评论(+5)")
    elif comments <= 20:
        score -= 15
        factors.append(f"评论拥挤:{comments}>10(-15)")
    else:
        score -= 25
        factors.append(f"高度拥挤:{comments}评论(-25)")

    # 3. Spec clarity & reproducibility (up to +25)
    body_len = len(body.strip())
    if body_len >= 500:
        score += 12
        factors.append("需求详尽(+12)")
    elif body_len >= 200:
        score += 8
        factors.append("需求清晰(+8)")
    elif body_len >= 80:
        score += 4
        factors.append("需求简短(+4)")
    else:
        score -= 5
        factors.append("描述过短(-5)")

    if _CODE_OR_PATH_RE.search(body):
        score += 7
        factors.append("含代码块/文件路径(+7)")

    if _CLEAR_SPEC_RE.search(body):
        score += 6
        factors.append("含复现或验收标准(+6)")

    # 4. Language & AI task fit (up to +25)
    detected_langs = detect_languages(repo_full_name, title, body, labels)
    matched_pref = [l for l in detected_langs if l in pref_langs]
    if matched_pref:
        score += 18
        factors.append(f"匹配技术栈:{'/'.join(matched_pref)}(+18)")
    elif not detected_langs:
        score += 8
        factors.append("通用技术栈(+8)")
    else:
        score += 2
        factors.append("非首选语言(+2)")

    combined_meta = f"{title} {' '.join(labels)}"
    if _AI_GOOD_TASK_RE.search(combined_meta):
        score += 7
        factors.append("适合AI闭环任务(+7)")

    if _HEAVY_ENV_BLOCKER_RE.search(f"{title}\n{body[:2000]}"):
        score -= 10
        factors.append("重硬件/特定系统依赖(-10)")

    clamped = max(0, min(100, score))
    return SolvabilityResult(score=clamped, matched_languages=detected_langs, factors=factors)


_BOUNTY_LABEL_RE = re.compile(
    r"(?:\bbounty\b|^price:\s*\d+\s*usd$|\breward\b|\bprize\b|\bcash\b|\$\s*\d+|\busdc\b|\busdt\b|💎|💰)",
    re.I,
)
_EXPLICIT_TITLE_BOUNTY_RE = re.compile(
    r"(?:\[\s*(?:qa\s+|bug\s+)?bounty[^\]]*\]"
    r"|\[\s*\$\s*\d{1,5}(?:[kK]|\.\d{1,2})?\s*\]"
    r"|^bounty\s*[:\-–—]"
    r"|\bbounty\s*[:=\-]\s*(?:\$|\d)"
    r"|(?:bounty|reward|prize)[^\n]{0,28}\$\s*\d+"
    r"|\$\s*\d+[kK]?[^\n]{0,28}(?:bounty|reward|prize)"
    r"|\b\d+\s*(?:USDC|USDT|SOL|ETH)\b)",
    re.I,
)
_EXPLICIT_PROSE_PLATFORM_RE = re.compile(
    r"(?:(?:^|\s)/bounty\b|opire\.dev|@opire|algora\.io|@algora-pbc|pay\.ubq\.fi"
    r"|(?:open\s*collective|gitcoin|superteam)[^\n.]{0,40}\b(?:bounty|reward|prize|grant|payout)\b"
    r"|\b(?:bounty|reward|prize|grant|payout)\b[^\n.]{0,40}(?:open\s*collective|gitcoin|superteam)"
    r"|(?:bounty|reward)\s*(?:amount|pool|of|is|:)\s*(?:\$\s*\d+|\d+\s*(?:USDC|USDT|USD|SOL|ETH)))",
    re.I,
)

_HONEYPOT_OR_MIRROR_RE = re.compile(
    r"(?:bot-trap|honeypot|oss-hunter-livefire|bot-tier-\d|bot-score:|prompt-injected|confirmed-ai"
    r"|manual pull requests from human engineers are not reviewed on this mirror"
    r"|sepolia\s+test\s+eth|testnet\s+eth)",
    re.I,
)
_MIRROR_REPO_OR_RADAR_TITLE_RE = re.compile(
    r"^(?:🎯\s*)?(?:\[radar\]|\[hydra\]|ai coms health:|bounty alert:|daily bounty)",
    re.I,
)
_VULN_SELF_REPORT_TITLE_RE = re.compile(
    r"^(?:\[bug\s+bounty\]|\[bounty\]\s*(?:low|medium|high|critical)\s*:)",
    re.I,
)


def is_honeypot_or_mirror(
    repo_full_name: str,
    title: str,
    body: str,
    labels: list[str],
) -> tuple[bool, str]:
    """Detect 2026 AI bot-trap honeypots, scraper mirrors, closed/claimed labels, and vuln self-reports."""
    lbl_joined = " | ".join(labels)
    combined_check = f"{repo_full_name}\n{title}\n{lbl_joined}\n{(body or '')[:2500]}"

    if _HONEYPOT_OR_MIRROR_RE.search(combined_check):
        return True, "honeypot_or_bot_trap"

    for lbl in labels:
        l_low = lbl.strip().lower()
        if l_low in ("reward:unfunded", "unfunded", "delivered", "claimed"):
            return True, f"non_actionable_label:{l_low}"

    repo_low = repo_full_name.lower()
    if (
        "bounty-plaza" in repo_low
        or "bountyscout" in repo_low
        or repo_low == "devpool-directory/devpool-directory"
        or "agent-bounty-experiment" in repo_low
    ):
        return True, "aggregator_mirror_or_experiment"

    if re.search(
        r"原始链接\s*/\s*Source URL\s*https://github\.com/|###\s*Active Bounty Scan Results",
        body or "",
        re.I,
    ):
        return True, "reposted_mirror_issue"

    # Directory issue whose entire body is just another GitHub issue URL
    body_stripped = (body or "").strip()
    if re.fullmatch(r"https?://github\.com/[\w.\-]+/[\w.\-]+/issues/\d+\s*", body_stripped):
        return True, "bare_pointer_issue"

    if _MIRROR_REPO_OR_RADAR_TITLE_RE.search((title or "").strip()):
        return True, "radar_watchlist_issue"

    # Security researcher submitting their own vulnerability finding for a bug bounty (not an open dev task)
    if _VULN_SELF_REPORT_TITLE_RE.search((title or "").strip()):
        if not any(l.lower() in ("help wanted", "good first issue", "bounty") for l in labels):
            return True, "researcher_vuln_disclosure"

    # Zero-bounty ($0 credit-only repos like MisakaNet) & customer support payment tickets
    if (
        re.search(
            r"zero-bounty|this\s+project\s+pays\s+no\s+money|pays\s+nothing\s+and\s+promises\s+nothing"
            r"|\[\s*\$\s*0(?:\.0+)?\s*\]|\bbounty\s*[:=\-]\s*\$\s*0\b|/reward\s+\$?\s*0\b",
            combined_check,
            re.I,
        )
        or repo_low == "ikalus1988/misakanet"
    ):
        return True, "zero_dollar_credit_only"

    # Parody / troll mega-bounties (e.g. `[bounty: 74000 ETH]`, `offering trillions in bounties`)
    if re.search(
        r"\boffering\s+trillions\s+in\s+bounties\b"
        r"|\[\s*bounty\s*[:=\-]?\s*(?:[1-9]\d{2,}\s*eth|[5-9]\d{3,}\s*sol|\$\s*[1-9]\d{5,})\s*\]",
        combined_check,
        re.I,
    ):
        return True, "parody_mega_bounty"

    # SaaS customer-discovery / design-partner recruitment & autonomous AI agent outreach posts
    if re.search(
        r"\bseeking\s+\d+\s+design\s+partners\b"
        r"|^data\s+exchange\s*:"
        r"|\bi['’]?m\s+[^.\n]{1,60}\ban\s+autonomous\s+ai\s+agent\b",
        f"{(title or '').strip()}\n{(body or '')[:1200]}",
        re.I | re.M,
    ):
        return True, "outreach_or_feedback_post"

    if re.search(r"funding\s+(?:payment\s+)?not\s+credited|still\s+shows\s+payment\s+due", combined_check, re.I):
        return True, "support_ticket_not_bounty"

    return False, ""


def has_genuine_bounty_signal(title: str, body: str, labels: list[str], reward: RewardInfo) -> bool:
    """Ensure the issue itself offers a bounty (avoiding codebases whose domain words include 'BountyCard')."""
    if any(_BOUNTY_LABEL_RE.search(l) for l in labels):
        return True
    if _EXPLICIT_TITLE_BOUNTY_RE.search(title or ""):
        return True
    prose = strip_code_spans(f"{title or ''}\n{(body or '')[:4000]}")
    if _EXPLICIT_PROSE_PLATFORM_RE.search(prose):
        return True
    return False
