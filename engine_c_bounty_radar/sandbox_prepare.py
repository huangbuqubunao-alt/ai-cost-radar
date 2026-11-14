#!/usr/bin/env python3
"""Engine C — Bounty Sandbox Pre-Solver & Pre-Flight Guard (`sandbox_prepare.py`).

Usage:
  python3 sandbox_prepare.py <github_issue_url>               # Fetch issue+comments+PR check, write TASK_BRIEF.md
  python3 sandbox_prepare.py --dry-run <github_issue_url>     # Live API pre-flight check & preview only (no disk write)
  python3 sandbox_prepare.py --clone <github_issue_url>       # Shallow-clone (depth=1) repo + write TASK_BRIEF.md

Uses Python 3.14 standard library ONLY.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

# Ensure sibling imports work from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bounty_core import (  # noqa: E402
    CONFIG_PATH,
    SANDBOX_ROOT,
    TIER_CN_FRIENDLY,
    TIER_NEED_HK_STRIPE,
    TIER_UNCONFIRMED,
    classify_cn_payout,
    compute_ai_solvability_score,
    extract_reward,
    github_get_json,
    is_non_cash_reward_text,
    load_config,
)

_ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.\-]+)/(?P<repo>[A-Za-z0-9_.\-]+)/issues/(?P<number>\d+)",
    re.I,
)

_CLAIM_COMMENT_RE = re.compile(
    r"(?:^|\s)(?:/attempt\b|/claim\b|/assign\b)|"
    r"\b(?:i(?:'d|\s+would)?\s+like\s+to\s+work\s+on\s+this|working\s+on\s+this|opened\s+a?\s*pr|submitted\s+a?\s*pr)\b",
    re.I,
)

_PR_REF_IN_TEXT_RE = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+/pull/(\d+)",
    re.I,
)


def parse_issue_url(url: str) -> tuple[str, str, int]:
    """Parse 'https://github.com/owner/repo/issues/123' into (owner, repo, number)."""
    m = _ISSUE_URL_RE.match(url.strip())
    if not m:
        raise ValueError(
            f"Invalid GitHub Issue URL: {url!r}. Expected https://github.com/<owner>/<repo>/issues/<number>"
        )
    return m.group("owner"), m.group("repo"), int(m.group("number"))


def inspect_linked_prs_and_claims(
    owner: str,
    repo: str,
    issue_number: int,
    comments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check timeline cross-references and comments for competing PRs or active claimants."""
    timeline_url = (
        f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/timeline?per_page=100"
    )
    tl_resp = github_get_json(timeline_url, timeout=15.0)

    linked_prs_by_url: dict[str, dict[str, Any]] = {}
    if tl_resp.ok and isinstance(tl_resp.data, list):
        for ev in tl_resp.data:
            if not isinstance(ev, dict):
                continue
            ev_type = ev.get("event")
            if ev_type == "cross-referenced":
                src_issue = (ev.get("source") or {}).get("issue") or {}
                if "pull_request" in src_issue:
                    pr_html = src_issue.get("html_url") or ""
                    pr_meta = src_issue.get("pull_request") or {}
                    if pr_html:
                        linked_prs_by_url[pr_html] = {
                            "number": src_issue.get("number"),
                            "title": src_issue.get("title") or "",
                            "state": src_issue.get("state") or "unknown",
                            "merged_at": pr_meta.get("merged_at"),
                            "author": (src_issue.get("user") or {}).get("login", "unknown"),
                            "url": pr_html,
                            "source": "timeline_cross_reference",
                        }

    # Also scan comments for explicit PR links and /attempt or /claim declarations
    claimants: list[dict[str, str]] = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        author = (c.get("user") or {}).get("login", "unknown")
        user_type = (c.get("user") or {}).get("type", "User")
        c_body = c.get("body") or ""
        c_date = (c.get("created_at") or "")[:10]

        for pr_match in _PR_REF_IN_TEXT_RE.finditer(c_body):
            pr_url = pr_match.group(0)
            pr_num = int(pr_match.group(1))
            if pr_url not in linked_prs_by_url:
                linked_prs_by_url[pr_url] = {
                    "number": pr_num,
                    "title": f"Referenced in comment by @{author}",
                    "state": "unknown (mentioned in comment)",
                    "merged_at": None,
                    "author": author,
                    "url": pr_url,
                    "source": "comment_mention",
                }

        if user_type != "Bot" and _CLAIM_COMMENT_RE.search(c_body):
            snippet = re.sub(r"\s+", " ", c_body).strip()[:120]
            claimants.append({"author": author, "date": c_date, "snippet": snippet})

    linked_prs = list(linked_prs_by_url.values())
    open_prs = [p for p in linked_prs if p["state"] in ("open", "unknown (mentioned in comment)")]
    merged_prs = [p for p in linked_prs if p.get("merged_at")]

    return {
        "timeline_checked": tl_resp.ok,
        "linked_prs": linked_prs,
        "open_or_active_prs": open_prs,
        "merged_prs": merged_prs,
        "claimants": claimants,
    }


def suggest_test_commands(primary_lang: str | None, repo_dir: Path | None) -> list[str]:
    """Generate practical build/test commands for TASK_BRIEF.md based on language or repo files."""
    cmds: list[str] = []
    if repo_dir and repo_dir.exists():
        if (repo_dir / "pyproject.toml").exists() or (repo_dir / "pytest.ini").exists():
            cmds.append("pytest -q")
        if (repo_dir / "package.json").exists():
            if (repo_dir / "pnpm-lock.yaml").exists():
                cmds.append("pnpm install && pnpm test")
            elif (repo_dir / "yarn.lock").exists():
                cmds.append("yarn install && yarn test")
            else:
                cmds.append("npm install && npm test")
        if (repo_dir / "Cargo.toml").exists():
            cmds.append("cargo test")
        if (repo_dir / "go.mod").exists():
            cmds.append("go test ./...")

    if not cmds:
        lang = (primary_lang or "").lower()
        if lang == "python":
            cmds = ["python3 -m pytest", "python3 -m unittest discover"]
        elif lang in ("typescript", "javascript"):
            cmds = ["npm test  # or pnpm test / vitest / jest"]
        elif lang == "rust":
            cmds = ["cargo check && cargo test"]
        elif lang == "go":
            cmds = ["go test ./..."]
        else:
            cmds = ["# Check README.md / Makefile / .github/workflows for project test suite"]
    return cmds


def determine_verdict(
    issue_state: str,
    unassigned: bool,
    pr_report: dict[str, Any],
    payout_tier: str,
    has_verified_cash_amount: bool = True,
) -> tuple[str, str]:
    """Compute pre-flight safety verdict before an AI coding agent invests compute."""
    if issue_state != "open":
        return ("🛑 STOP (CLOSED)", "该 Issue 已关闭，请勿投入开发。")
    if pr_report["merged_prs"]:
        return ("🛑 STOP (MERGED PR EXISTS)", "检测到已合并的关联 PR，悬赏极大概率已结案。")
    if not unassigned:
        return ("🛑 STOP (ALREADY ASSIGNED)", "该 Issue 已分配给其他开发者，建议换下一个目标。")
    if pr_report["open_or_active_prs"]:
        cnt = len(pr_report["open_or_active_prs"])
        return (
            f"⚠️ HIGH COMPETITION ({cnt} OPEN/REFERENCED PR)",
            f"已有 {cnt} 个关联/提及的 PR 正在竞争，动工前请先评估对方 PR 是否完整或已被放弃。",
        )
    if payout_tier == TIER_NEED_HK_STRIPE:
        return (
            "🟡 HOLD (PAYOUT RAIL LOCKED)",
            "技术上无竞争 PR，但收款绑定 Algora Stripe-only 且当前未配置港卡/海外 Stripe。",
        )
    if payout_tier == TIER_UNCONFIRMED or not has_verified_cash_amount:
        return (
            "🔵 VERIFY PAYOUT & RULES FIRST",
            "收款通道或现金/加密货币赏金尚未确认（可能为积分额度或未写明打款规则），请先人工核实后再决定是否投入算力。",
        )
    if pr_report["claimants"]:
        return (
            f"🟢 GO WITH SPEED ({len(pr_report['claimants'])} 评论认领但尚无PR)",
            "已确认国内友好收款与赏金，有人在评论区表达意向但尚无关联 PR 提交——可评估快速响应。",
        )
    return ("✅ CLEAR TO SOLVE", "Issue 开放未分配、无竞争 PR，且已确认国内友好收款通道与赏金金额！")


def build_task_brief_markdown(
    owner: str,
    repo: str,
    issue: dict[str, Any],
    repo_meta: dict[str, Any],
    comments: list[dict[str, Any]],
    pr_report: dict[str, Any],
    reward_display: str,
    payout_cls: Any,
    solvability: Any,
    verdict_badge: str,
    verdict_reason: str,
    sandbox_dir: Path,
    cloned: bool,
) -> str:
    """Format a comprehensive TASK_BRIEF.md for an autonomous AI coding agent."""
    number = issue.get("number")
    title = issue.get("title") or ""
    html_url = issue.get("html_url") or f"https://github.com/{owner}/{repo}/issues/{number}"
    state = issue.get("state") or "unknown"
    unassigned = (issue.get("assignee") is None) and (len(issue.get("assignees") or []) == 0)
    labels = [str(l.get("name", "")) for l in (issue.get("labels") or []) if isinstance(l, dict)]
    primary_lang = repo_meta.get("language") or (
        solvability.matched_languages[0] if solvability.matched_languages else "Unknown"
    )
    default_branch = repo_meta.get("default_branch") or "main"
    stars = repo_meta.get("stargazers_count", "N/A")
    now_utc = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append(f"# 🛠️ AI Bounty Task Brief: {owner}/{repo}#{number}")
    lines.append("")
    lines.append(f"> **Pre-Flight Verdict**: **{verdict_badge}** — {verdict_reason}")
    lines.append("")
    lines.append("## 1. Metadata & Payout Intelligence")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **Issue URL** | {html_url} |")
    lines.append(f"| **Title** | {title.replace('|', '\\|')} |")
    lines.append(f"| **Repository** | `{owner}/{repo}` (⭐ {stars}, default branch: `{default_branch}`) |")
    lines.append(f"| **Primary Language** | `{primary_lang}` |")
    lines.append(f"| **State / Assignment** | `{state}` / `{'Unassigned' if unassigned else 'Assigned'}` |")
    lines.append(f"| **Labels** | `{', '.join(labels) if labels else 'None'}` |")
    lines.append(f"| **Estimated Reward** | **{reward_display}** |")
    lines.append(f"| **CN Payout Tier** | **{payout_cls.tier}** |")
    lines.append(f"| **Payout Notes** | {payout_cls.note} |")
    lines.append(f"| **AI Solvability Score** | **{solvability.score}/100** (`{' | '.join(solvability.factors)}`) |")
    lines.append(f"| **Sandbox Path** | `{sandbox_dir}` (`{'cloned' if cloned else 'brief-only'}`) |")
    lines.append(f"| **Generated At** | `{now_utc}` |")
    lines.append("")

    # Competition & Linked PR Check
    lines.append("## 2. Linked PR & Competition Check")
    lines.append("")
    if pr_report["linked_prs"]:
        lines.append("⚠️ **Detected Linked / Referenced Pull Requests:**")
        for pr in pr_report["linked_prs"]:
            merged_tag = " (MERGED)" if pr.get("merged_at") else ""
            lines.append(
                f"- [PR #{pr['number']}]({pr['url']}) — `{pr['state']}{merged_tag}` by `@{pr['author']}`: {pr['title']}"
            )
    else:
        lines.append("- ✅ **0 linked PRs found** in issue timeline or comments.")

    if pr_report["claimants"]:
        lines.append("- **Comment Claimants / `/attempt` Mentions:**")
        for cl in pr_report["claimants"][:8]:
            lines.append(f"  - `@{cl['author']}` ({cl['date']}): \"{cl['snippet']}\"")
    else:
        lines.append("- ✅ **0 `/attempt` or `/claim` comments** from human contributors.")
    lines.append("")

    # Original Issue Spec
    lines.append("## 3. Original Issue Specification")
    lines.append("")
    body = (issue.get("body") or "_No issue body provided._").strip()
    lines.append(body)
    lines.append("")

    # Relevant Comments Digest
    lines.append("## 4. Issue Comments Digest")
    lines.append("")
    if not comments:
        lines.append("_No comments on this issue yet._")
    else:
        for idx, c in enumerate(comments[:12], start=1):
            author = (c.get("user") or {}).get("login", "unknown")
            utype = (c.get("user") or {}).get("type", "User")
            created = (c.get("created_at") or "")[:16].replace("T", " ")
            c_body = (c.get("body") or "").strip()
            if len(c_body) > 900:
                c_body = c_body[:900] + "\n...(truncated)..."
            bot_tag = " [BOT]" if utype == "Bot" else ""
            lines.append(f"### Comment #{idx} — `@{author}`{bot_tag} ({created})")
            lines.append(c_body)
            lines.append("")
        if len(comments) > 12:
            lines.append(f"_({len(comments) - 12} older/additional comments omitted; see {html_url})_")
    lines.append("")

    # Execution Plan for AI Coding Agent
    test_cmds = suggest_test_commands(primary_lang, sandbox_dir if cloned else None)
    lines.append("## 5. Autonomous Solver Execution Checklist")
    lines.append("")
    if not cloned:
        lines.append("0. **Clone Repository into Sandbox** (not cloned yet):")
        lines.append(
            f"   ```bash\n   python3 engine_c_bounty_radar/sandbox_prepare.py --clone {html_url}\n   ```"
        )
    lines.append("1. **Inspect CI & Contribution Rules**: Read `.github/workflows/`, `CONTRIBUTING.md`, and `README.md` before writing code.")
    lines.append("2. **Reproduce / Write Failing Test First**: Add or update a targeted unit/integration test proving the bug or new feature behavior.")
    lines.append("3. **Implement Minimal Focused Fix**: Keep diff tight, adhere strictly to repository formatting/lint conventions, and do not touch unrelated files.")
    lines.append("4. **Run Verification Suite**:")
    lines.append("   ```bash")
    for cmd in test_cmds:
        lines.append(f"   {cmd}")
    lines.append("   ```")
    lines.append(
        f"5. **PR & Payout Claim**: Reference `Fixes #{number}` in your PR description. "
        f"Current payout classification is **{payout_cls.tier}** — verify claim instructions (e.g. Opire `/claim #{number}`, USDC wallet note, or Open Collective invoice)."
    )
    lines.append("")
    return "\n".join(lines)


def resolve_sandbox_repo_dir(owner: str, repo: str) -> Path:
    """Resolve `engine_c_bounty_radar/sandbox/<repo_name>`, guarding against cross-owner collisions."""
    candidate = SANDBOX_ROOT / repo
    git_dir = candidate / ".git"
    if git_dir.exists():
        try:
            res = subprocess.run(
                ["git", "-C", str(candidate), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            remote = res.stdout.strip().lower()
            if remote and f"{owner}/{repo}".lower() not in remote:
                return SANDBOX_ROOT / f"{owner}__{repo}"
        except Exception:
            pass
    return candidate


def perform_shallow_clone(clone_url: str, target_dir: Path) -> tuple[bool, str]:
    """Run `git clone --depth 1 <clone_url> <target_dir>` safely."""
    if (target_dir / ".git").exists():
        return True, f"Repository already cloned at {target_dir}"

    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    # If target_dir exists with only TASK_BRIEF.md from a prior non-clone run, clean it so git clone succeeds
    if target_dir.exists():
        existing_entries = [p.name for p in target_dir.iterdir()]
        if existing_entries == ["TASK_BRIEF.md"] or not existing_entries:
            shutil.rmtree(target_dir)
        else:
            return False, f"Target directory {target_dir} already exists and is non-empty (no .git)."

    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(target_dir)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode == 0:
            return True, f"Shallow clone (--depth 1) succeeded -> {target_dir}"
        return False, f"git clone exited with {proc.returncode}: {proc.stderr.strip()}"
    except Exception as exc:
        return False, f"git clone failed: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a GitHub bounty sandbox: inspect issue, comments, linked PRs, and generate TASK_BRIEF.md."
    )
    parser.add_argument("issue_url", help="Full GitHub issue URL (https://github.com/owner/repo/issues/123)")
    parser.add_argument(
        "--clone",
        action="store_true",
        help="Explicitly shallow-clone (`git clone --depth 1`) the target repo into sandbox/<repo_name>",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch live API data, check linked PRs, and print report/preview without writing files or cloning",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Path to config.json",
    )
    args = parser.parse_args()

    try:
        owner, repo, number = parse_issue_url(args.issue_url)
    except ValueError as err:
        print(f"[Error] {err}", file=sys.stderr)
        return 2

    config = load_config(args.config)
    repo_full = f"{owner}/{repo}"
    print(f"[Sandbox Pre-Solver] Inspecting {repo_full}#{number} via GitHub API...")

    issue_api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    issue_resp = github_get_json(issue_api_url)
    if not issue_resp.ok or not isinstance(issue_resp.data, dict):
        print(f"[Error] Could not fetch issue {issue_api_url}: {issue_resp.error}", file=sys.stderr)
        return 1
    issue_data = issue_resp.data

    comments_api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments?per_page=100"
    comments_resp = github_get_json(comments_api_url)
    comments_data = comments_resp.data if (comments_resp.ok and isinstance(comments_resp.data, list)) else []

    repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
    repo_resp = github_get_json(repo_api_url)
    repo_meta = repo_resp.data if (repo_resp.ok and isinstance(repo_resp.data, dict)) else {}

    pr_report = inspect_linked_prs_and_claims(owner, repo, number, comments_data)

    title = issue_data.get("title") or ""
    body = issue_data.get("body") or ""
    labels = [
        str(l.get("name", ""))
        for l in (issue_data.get("labels") or [])
        if isinstance(l, dict) and l.get("name")
    ]
    all_comments_text = "\n".join((c.get("body") or "") for c in comments_data if isinstance(c, dict))

    reward = extract_reward(title=title, body=body, labels=labels, extra_comments_text=all_comments_text)
    payout_cls = classify_cn_payout(
        title=title,
        body=body,
        labels=labels,
        payout_readiness=config.get("payout_readiness", {}),
        extra_comments_text=all_comments_text,
        repo_full_name=repo_full,
    )
    solvability = compute_ai_solvability_score(
        issue=issue_data,
        repo_full_name=repo_full,
        preferences=config.get("bounty_preferences", {}),
    )
    # Incorporate exact GitHub repo primary language if not already in matched_languages
    gh_lang = (repo_meta.get("language") or "").lower()
    if gh_lang and gh_lang not in solvability.matched_languages:
        solvability.matched_languages.insert(0, gh_lang)

    unassigned = (issue_data.get("assignee") is None) and (len(issue_data.get("assignees") or []) == 0)
    has_cash = (
        (reward.usd_estimate is not None and reward.usd_estimate > 0)
        or (reward.currency in ("SOL", "ETH"))
    ) and not is_non_cash_reward_text(title, body)
    verdict_badge, verdict_reason = determine_verdict(
        issue_state=str(issue_data.get("state") or "unknown"),
        unassigned=unassigned,
        pr_report=pr_report,
        payout_tier=payout_cls.tier,
        has_verified_cash_amount=has_cash,
    )

    sandbox_dir = resolve_sandbox_repo_dir(owner, repo)
    cloned_ok = False

    print("=" * 74)
    print(f"Issue:             {repo_full}#{number} — {title}")
    print(f"State / Assigned:  {issue_data.get('state')} / {'Unassigned' if unassigned else 'Assigned'}")
    print(f"Estimated Reward:  {reward.display}")
    print(f"CN Payout Tier:    {payout_cls.tier}")
    print(f"Payout Details:    {payout_cls.note}")
    print(f"AI Solvability:    {solvability.score}/100 ({', '.join(solvability.factors)})")
    print(
        f"Linked PRs Check:  {len(pr_report['open_or_active_prs'])} open/referenced PR(s), "
        f"{len(pr_report['merged_prs'])} merged PR(s), {len(pr_report['claimants'])} comment claimant(s)"
    )
    print(f"Verdict:           {verdict_badge} — {verdict_reason}")
    print("=" * 74)

    if args.dry_run:
        brief_preview = build_task_brief_markdown(
            owner=owner,
            repo=repo,
            issue=issue_data,
            repo_meta=repo_meta,
            comments=comments_data,
            pr_report=pr_report,
            reward_display=reward.display,
            payout_cls=payout_cls,
            solvability=solvability,
            verdict_badge=verdict_badge,
            verdict_reason=verdict_reason,
            sandbox_dir=sandbox_dir,
            cloned=False,
        )
        print("[Dry-Run] Skipping disk write and git clone. TASK_BRIEF.md preview (first 35 lines):")
        for line in brief_preview.splitlines()[:35]:
            print(f"  {line}")
        print(f"  ... ({len(brief_preview.splitlines())} total lines ready to write to {sandbox_dir / 'TASK_BRIEF.md'})")
        return 0

    if args.clone:
        clone_url = repo_meta.get("clone_url") or f"https://github.com/{owner}/{repo}.git"
        print(f"[Sandbox Pre-Solver] Cloning {clone_url} (--depth 1) into {sandbox_dir} ...")
        cloned_ok, clone_msg = perform_shallow_clone(clone_url, sandbox_dir)
        print(f"[Sandbox Pre-Solver] {clone_msg}")
        if not cloned_ok:
            return 1
    else:
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        cloned_ok = (sandbox_dir / ".git").exists()

    brief_md = build_task_brief_markdown(
        owner=owner,
        repo=repo,
        issue=issue_data,
        repo_meta=repo_meta,
        comments=comments_data,
        pr_report=pr_report,
        reward_display=reward.display,
        payout_cls=payout_cls,
        solvability=solvability,
        verdict_badge=verdict_badge,
        verdict_reason=verdict_reason,
        sandbox_dir=sandbox_dir,
        cloned=cloned_ok,
    )
    brief_path = sandbox_dir / "TASK_BRIEF.md"
    brief_path.write_text(brief_md, encoding="utf-8")
    print(f"[Sandbox Pre-Solver] Wrote agent task brief to: {brief_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
