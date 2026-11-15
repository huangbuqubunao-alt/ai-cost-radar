#!/usr/bin/env python3
"""
Round 9 (v3.9) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. Multi-file batch session & billing merger (`merge_usage_log_snippets`) + repeated CSV header skipping:
       - Merges multiple Claude Code `~/.claude/projects/*.jsonl` transcripts (with cross-file `message.id`
         streaming deduplication), OpenAI Batch `.jsonl`, OpenRouter/Cloud `.csv` bills, and `/cost` summaries
         into a unified 30-day multi-model portfolio (`detected_format="csv_multimodel_bill"`,
         `source_format="multifile_merged"`, `merged_files_count`).
       - Skips repeated CSV header rows when users concatenate weekly/monthly CSV exports (`cat w1.csv w2.csv`).
       - Strict `ValueError` / HTTP 400 when all merged files contain zero positive token records.
    2. Cross-surface parity (`pricing_core.py`, `mcp_server.py`, Cloudflare `functions/api/budget.js`,
       `coze_cloud_tool.py`, `openapi_coze.json`, `.actor/input_schema.json`, and `apify_store_bundle` byte-for-byte sync)
       for `usage_snippets` + repeated-header CSV + multi-session `.jsonl` batch auditing.
    3. Engine C Bounty Radar real-world data integrity hardening:
       - `classify_cn_payout` respects `payout_readiness`: non-crypto rails (`Opire`, `PayPal`, `Payoneer`, `Wise`,
         `Open Collective`) are NOT marked `TIER_CN_FRIENDLY` when their corresponding readiness flag is `False`
         and zero crypto rail is present (demoted to `TIER_UNCONFIRMED`).
       - Rejects SaaS pricing / design-partner feedback posts (`Seeking 10 design partners ... $59 Console Kit`),
         autonomous-agent data-exchange outreach essays (`Data exchange: first-hand agent sign-up/payout tests`),
         zero-dollar `[$0]` / `MisakaNet` credit-only issues, and parody mega-bounty troll issues (`[bounty: 74000 ETH]`).
       - `is_strictly_actionable_bounty` excludes heavily swarmed zombie issues (`comments > 40`, e.g. `2454` comments)
         from `actionable_now` into `verification_queue`.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle"))
sys.path.insert(0, str(ROOT / "engine_b_affiliate_web"))
sys.path.insert(0, str(ROOT / "engine_c_bounty_radar"))
sys.path.insert(0, str(ROOT / "cloudflare"))

import bounty_core  # noqa: E402
import build_site  # noqa: E402
import coze_cloud_tool  # noqa: E402
import mcp_server  # noqa: E402
import prepare_release  # noqa: E402
import pricing_core  # noqa: E402
import scan_bounties  # noqa: E402


SESSION_JSONL_1 = "\n".join(
    [
        json.dumps({"type": "user", "message": {"role": "user", "content": "input tokens 999999"}}),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_shared_dup_01",
                    "model": "claude-sonnet-4-20250514",
                    "usage": {
                        "input_tokens": 2000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 18000,
                        "output_tokens": 300,
                    },
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_sess1_only_02",
                    "model": "claude-sonnet-4-20250514",
                    "usage": {
                        "input_tokens": 4000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 6000,
                        "output_tokens": 1000,
                    },
                },
            }
        ),
    ]
)

SESSION_JSONL_2_WITH_OVERLAP = "\n".join(
    [
        # Overlapping export of `msg_shared_dup_01` (final chunk has 1000 output tokens) — must deduplicate across files!
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_shared_dup_01",
                    "model": "claude-sonnet-4-20250514",
                    "usage": {
                        "input_tokens": 2000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 18000,
                        "output_tokens": 1000,
                    },
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_sess2_opus_03",
                    "model": "claude-opus-4-20250514",
                    "usage": {
                        "input_tokens": 5000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 15000,
                        "output_tokens": 2000,
                    },
                },
            }
        ),
    ]
)

CSV_PART_WEEK1 = """model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage
deepseek/deepseek-r1,10,50000,10000,25000,6000,$0.08
"""

CSV_CONCATENATED_REPEATED_HEADER = """model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage
anthropic/claude-sonnet-4,5000,20000000,4000000,10000000,0,$105.00
model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage
deepseek/deepseek-r1,5000,20000000,5000000,10000000,3000000,$21.00
"""


class Round9Batch1MultiFileAndBountyGateTests(unittest.TestCase):
    def _run_cloudflare_budget_cases(self, cases: list[list[tuple[str, str]] | dict[str, str]]) -> list[dict]:
        runner = """
import fs from "node:fs";
const source = fs.readFileSync("functions/api/budget.js", "utf8");
const {onRequestGet} = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const {catalog, cases} = JSON.parse(fs.readFileSync(0, "utf8"));
const outputs = [];
for (const query of cases) {
  const qs = new URLSearchParams(query);
  const request = new Request("https://example.test/api/budget?" + qs.toString());
  const response = await onRequestGet({request, env: {ASSETS: {fetch: async () => Response.json(catalog)}}});
  outputs.push({status: response.status, body: await response.json()});
}
console.log(JSON.stringify(outputs));
"""
        catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", runner],
            cwd=ROOT,
            input=json.dumps({"catalog": catalog, "cases": cases}),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(proc.stdout.strip())

    def test_01_multi_file_session_and_csv_merge_with_cross_file_dedupe(self) -> None:
        # 1. Repeated CSV header rows in a concatenated CSV file must be skipped cleanly
        parsed_concat_csv = pricing_core.parse_usage_log_snippet(CSV_CONCATENATED_REPEATED_HEADER, days_observed=30.0)
        self.assertEqual(parsed_concat_csv["detected_format"], "csv_multimodel_bill")
        self.assertEqual(parsed_concat_csv["distinct_models_count"], 2)
        self.assertEqual(parsed_concat_csv["total_requests"], 10_000)
        self.assertEqual(parsed_concat_csv["total_input_tokens"], 40_000_000)
        self.assertEqual(parsed_concat_csv["total_output_tokens"], 9_000_000)

        # 2. Multi-file batch merge: 2 `.jsonl` Claude Code transcripts (sharing `msg_shared_dup_01`) + 1 `.csv` bill
        merged = pricing_core.merge_usage_log_snippets(
            [SESSION_JSONL_1, SESSION_JSONL_2_WITH_OVERLAP, CSV_PART_WEEK1],
            days_observed=1.0,
        )
        self.assertEqual(merged["detected_format"], "csv_multimodel_bill")
        self.assertEqual(merged["source_format"], "multifile_merged")
        self.assertEqual(merged["merged_files_count"], 3)
        self.assertGreaterEqual(merged["deduplicated_chunks"], 1)
        self.assertEqual(merged["distinct_models_count"], 3)
        # Requests: 2 sonnet (`msg_shared_dup_01` deduped once + `msg_sess1_only_02`) + 1 opus + 10 deepseek-r1 = 13
        self.assertEqual(merged["total_requests"], 13)
        # Input: sonnet (20k + 10k = 30k) + opus (20k) + deepseek-r1 (50k) = 100,000
        self.assertEqual(merged["total_input_tokens"], 100_000)
        # Cached: sonnet (18k + 6k = 24k) + opus (15k) + deepseek-r1 (25k) = 64,000
        self.assertEqual(merged["cached_input_tokens"], 64_000)
        # Output: sonnet (max(300,1000)=1000 + 1000 = 2000) + opus (2000) + deepseek-r1 (10000) = 14,000
        self.assertEqual(merged["total_output_tokens"], 14_000)
        self.assertTrue(merged["output_includes_reasoning"])

        # 3. Zero-token multi-file batch must raise ValueError
        with self.assertRaises(ValueError):
            pricing_core.merge_usage_log_snippets(
                [
                    json.dumps({"type": "user", "message": {"content": "input tokens 50000"}}),
                    json.dumps({"type": "summary", "summary": "done"}),
                ],
                days_observed=7.0,
            )

    def test_02_cross_surface_multifile_and_repeated_csv_header_parity(self) -> None:
        snippets = [SESSION_JSONL_1, SESSION_JSONL_2_WITH_OVERLAP, CSV_PART_WEEK1]
        mcp_res = mcp_server.calculate_api_budget(
            model_query="auto",
            usage_snippets=snippets,
            days_observed=3.0,
            team_size=2,
        )
        self.assertEqual(mcp_res["parsed_usage_summary"]["source_format"], "multifile_merged")
        self.assertEqual(mcp_res["parsed_usage_summary"]["merged_files_count"], 3)
        self.assertEqual(mcp_res["parsed_usage_summary"]["total_requests"], 13)

        cf_cases = self._run_cloudflare_budget_cases(
            [
                [
                    ("model_id", "auto"),
                    ("usage_snippet", SESSION_JSONL_1),
                    ("usage_snippet", SESSION_JSONL_2_WITH_OVERLAP),
                    ("usage_snippet", CSV_PART_WEEK1),
                    ("days_observed", "3"),
                    ("team_size", "2"),
                ],
                {
                    "model_id": "auto",
                    "usage_snippet": CSV_CONCATENATED_REPEATED_HEADER,
                    "days_observed": "30",
                    "team_size": "1",
                },
            ]
        )
        self.assertEqual(cf_cases[0]["status"], 200)
        cf_multi = cf_cases[0]["body"]
        self.assertEqual(cf_multi["parsed_usage_summary"]["source_format"], "multifile_merged")
        self.assertEqual(cf_multi["parsed_usage_summary"]["merged_files_count"], 3)
        self.assertEqual(cf_multi["parsed_usage_summary"]["total_requests"], 13)
        self.assertAlmostEqual(
            cf_multi["bill_audit"]["totals"]["optimized_payg_monthly_rmb"],
            mcp_res["bill_audit"]["totals"]["optimized_payg_monthly_rmb"],
            delta=0.05,
        )

        self.assertEqual(cf_cases[1]["status"], 200)
        self.assertEqual(cf_cases[1]["body"]["parsed_usage_summary"]["total_requests"], 10_000)

        coze_res = coze_cloud_tool.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "auto",
                "usage_snippets": snippets,
                "days_observed": 3,
                "team_size": 2,
            }
        )
        self.assertEqual(coze_res["parsed_usage_summary"]["source_format"], "multifile_merged")
        self.assertEqual(coze_res["parsed_usage_summary"]["total_requests"], 13)
        self.assertAlmostEqual(
            coze_res["bill_audit"]["totals"]["optimized_payg_monthly_rmb"],
            mcp_res["bill_audit"]["totals"]["optimized_payg_monthly_rmb"],
            delta=0.05,
        )

        # Keep MCP_TOOLS_SPEC at 3 tools & verify apify_store_bundle byte-for-byte sync
        self.assertEqual(len(mcp_server.MCP_TOOLS_SPEC), 3)
        budget_tool = next(t for t in mcp_server.MCP_TOOLS_SPEC if t["name"] == "calculate_api_budget")
        self.assertIn("usage_snippets", budget_tool["inputSchema"]["properties"])

        apify_dir = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "apify_store_bundle"
        if apify_dir.is_dir():
            for fname in ("pricing_core.py", "mcp_server.py", "fetch_and_enrich.py"):
                src = (ROOT / "engine_a_mcp_actor" / fname).read_bytes()
                dst = (apify_dir / fname).read_bytes()
                self.assertEqual(src, dst, f"apify_store_bundle/{fname} drifted from engine_a_mcp_actor/{fname}")

    def test_03_engine_c_payout_readiness_feedback_filter_and_crowd_gate(self) -> None:
        cn_crypto_only_cfg = {
            "has_alipay_wechat": True,
            "has_paypal_cn": False,
            "has_payoneer": False,
            "has_usdc_wallet": True,
            "has_hk_bank_or_stripe": False,
        }
        # 1. Opire-only / PayPal-only without crypto when fiat/Stripe flags are False -> TIER_UNCONFIRMED
        cls_opire_only = bounty_core.classify_cn_payout(
            title="[BOUNTY $50] SKILL: Generate a structured CHANGELOG",
            body="## Bounty: $50 — powered by Opire (https://opire.dev)",
            labels=["bounty"],
            payout_readiness=cn_crypto_only_cfg,
        )
        self.assertEqual(cls_opire_only.tier, bounty_core.TIER_UNCONFIRMED)

        cls_paypal_unready = bounty_core.classify_cn_payout(
            title="[Bounty $80] Fix CLI output table",
            body="Reward $80 paid via PayPal upon merge.",
            labels=["bounty"],
            payout_readiness=cn_crypto_only_cfg,
        )
        self.assertEqual(cls_paypal_unready.tier, bounty_core.TIER_UNCONFIRMED)

        # When PayPal is enabled OR USDC crypto is also offered, it IS TIER_CN_FRIENDLY
        cls_paypal_ready = bounty_core.classify_cn_payout(
            title="[Bounty $80] Fix CLI output table",
            body="Reward $80 paid via PayPal upon merge.",
            labels=["bounty"],
            payout_readiness={**cn_crypto_only_cfg, "has_paypal_cn": True},
        )
        self.assertEqual(cls_paypal_ready.tier, bounty_core.TIER_CN_FRIENDLY)

        cls_opire_with_usdc = bounty_core.classify_cn_payout(
            title="[BOUNTY $100] Add Rust parser",
            body="Powered by Opire — maintainer also pays direct USDC on Base wallet.",
            labels=["bounty"],
            payout_readiness=cn_crypto_only_cfg,
        )
        self.assertEqual(cls_opire_with_usdc.tier, bounty_core.TIER_CN_FRIENDLY)

        # 2. SaaS Console Kit / design-partner recruitment post (`dporkka/syntyr-css#3`) must NOT be accepted
        feedback_issue = {
            "id": 9001,
            "number": 3,
            "state": "open",
            "title": "Seeking 10 design partners: zero-JS SaaS dashboard screens and $59 Console Kit concept",
            "body": "I'm looking for 10 developers building SaaS dashboards to review two screens and give feedback.",
            "html_url": "https://github.com/dporkka/syntyr-css/issues/3",
            "repository_url": "https://api.github.com/repos/dporkka/syntyr-css",
            "labels": [{"name": "feedback"}],
            "comments": 1,
        }
        self.assertIsNone(
            scan_bounties.process_raw_issue(
                feedback_issue,
                "opire_slash_bounty",
                {"payout_readiness": cn_crypto_only_cfg, "bounty_preferences": {}},
            )
        )

        # 3. Autonomous AI agent data-exchange outreach post (`awesome-molt-ecosystem#46`) must NOT be accepted
        agent_outreach_issue = {
            "id": 9002,
            "number": 46,
            "state": "open",
            "title": "Data exchange: first-hand agent sign-up/payout tests (21 platforms), and may I cite your measured numbers?",
            "body": "Hi! I'm Agent Oprimus, an autonomous AI agent. I tested 21 platforms including Superteam (2 USDC).",
            "html_url": "https://github.com/eltociear/awesome-molt-ecosystem/issues/46",
            "repository_url": "https://api.github.com/repos/eltociear/awesome-molt-ecosystem",
            "labels": [],
            "comments": 0,
        }
        self.assertIsNone(
            scan_bounties.process_raw_issue(
                agent_outreach_issue,
                "usdc_crypto_bounty",
                {"payout_readiness": cn_crypto_only_cfg, "bounty_preferences": {}},
            )
        )

        # 4. Parody mega-bounty (`[bounty: 74000 ETH]`) & `[$0]` zero-dollar bounty must be rejected as traps
        is_troll, _ = bounty_core.is_honeypot_or_mirror(
            repo_full_name="dwebagents/AgentPipe",
            title="[bounty: 74000 ETH] start building company town for contributing agents",
            body="we are offering trillions in bounties - 3 ETH for first PR",
            labels=["bounty", "good first issue"],
        )
        self.assertTrue(is_troll)

        is_zero, _ = bounty_core.is_honeypot_or_mirror(
            repo_full_name="Ikalus1988/MisakaNet",
            title="[Bounty][$0][i18n] lessons/en 镜像：20 篇确认过期",
            body="/reward $0 internal corpus lesson",
            labels=["bounty"],
        )
        self.assertTrue(is_zero)

        # 5. Crowd/swarm gate: issues with >40 comments (e.g. 2454 comments) are NOT strictly actionable without verification
        swarmed_item = {
            "cn_payout_tier": bounty_core.TIER_CN_FRIENDLY,
            "reward_usd_est": 150.0,
            "unassigned": True,
            "is_non_cash_credit": False,
            "comments": 2454,
        }
        self.assertFalse(scan_bounties.is_strictly_actionable_bounty(swarmed_item))

        clean_item = {
            "cn_payout_tier": bounty_core.TIER_CN_FRIENDLY,
            "reward_usd_est": 150.0,
            "unassigned": True,
            "is_non_cash_credit": False,
            "comments": 6,
        }
        self.assertTrue(scan_bounties.is_strictly_actionable_bounty(clean_item))

        # 6. Partial rate-limit resilience: cached items from unqueried channels are preserved (and re-sanitized)
        cached_valid = {
            "id": 9101,
            "repo": "ubiquity/pay.ubq.fi",
            "number": 500,
            "title": "[Bounty 27 USD] Fix permit deletion scope",
            "url": "https://github.com/ubiquity/pay.ubq.fi/issues/500",
            "comments": 5,
            "unassigned": True,
            "labels": ["Price: 27 USD"],
            "estimated_reward": "27 USD",
            "reward_usd_est": 27.0,
            "reward_currency": "USD",
            "cn_payout_tier": bounty_core.TIER_CN_FRIENDLY,
            "cn_payout_rails": ["UbiquityOS Crypto (pay.ubq.fi)"],
            "cn_payout_note": "",
            "ai_solvability_score": 77,
            "action_priority_score": 102.0,
            "matched_languages": ["typescript"],
            "score_factors": ["未分配(+25)"],
            "source_queries": ["ubiquity_crypto_bounty"],
            "spec_excerpt": "Permit deletion scope fix on pay.ubq.fi",
        }
        cached_trap = {
            "id": 9102,
            "repo": "dporkka/syntyr-css",
            "number": 3,
            "title": "Seeking 10 design partners: zero-JS SaaS dashboard screens and $59 Console Kit concept",
            "url": "https://github.com/dporkka/syntyr-css/issues/3",
            "comments": 1,
            "unassigned": True,
            "labels": ["feedback"],
            "estimated_reward": "$59",
            "reward_usd_est": 59.0,
            "reward_currency": "USD",
            "cn_payout_tier": bounty_core.TIER_UNCONFIRMED,
            "cn_payout_rails": [],
            "cn_payout_note": "",
            "ai_solvability_score": 60,
            "action_priority_score": 60.0,
            "matched_languages": [],
            "score_factors": [],
            "source_queries": ["opire_slash_bounty"],
            "spec_excerpt": "Looking for 10 developers to review two screens.",
        }
        sanitized_valid = scan_bounties.recompute_cached_bounty_item(
            dict(cached_valid),
            {"payout_readiness": cn_crypto_only_cfg, "bounty_preferences": {}},
        )
        self.assertIsNotNone(sanitized_valid)
        self.assertEqual(sanitized_valid["cn_payout_tier"], bounty_core.TIER_CN_FRIENDLY)
        sanitized_trap = scan_bounties.recompute_cached_bounty_item(
            dict(cached_trap),
            {"payout_readiness": cn_crypto_only_cfg, "bounty_preferences": {}},
        )
        self.assertIsNone(sanitized_trap)


class Round9Batch2WebUiSnapshotAndPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dist_dir = Path(cls._tmp.name) / "dist"
        build_site.build_site(dist_dir=cls.dist_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_04_web_multifile_batch_upload_dragdrop_and_cross_file_merge(self) -> None:
        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        # Preserve Round 8 exact accept attribute while enabling multi-file batch selection
        self.assertIn('accept=".csv,.tsv,.json,.jsonl,.txt,.log" multiple', index_html)
        self.assertIn('id="usageDropZone"', index_html)
        self.assertIn("mergeUsageFilesWeb", index_html)
        self.assertIn("multifile_merged", index_html)
        self.assertIn("merged_files_count", index_html)
        self.assertIn("multifile_upload", index_html)
        self.assertIn("multifile_drop", index_html)
        for i18n_key in ("usageDropHint", "usageFileBtn"):
            self.assertIn(f"{i18n_key}:", index_html, f"Missing {i18n_key} in I18N_EN")

    def test_05_web_local_baseline_snapshot_diff_banner_markdown_and_print(self) -> None:
        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="saveBillSnapshotBtn"', index_html)
        self.assertIn('id="clearBillSnapshotBtn"', index_html)
        self.assertIn('id="billSnapshotDiffBanner"', index_html)
        self.assertIn("ai_cost_saved_baseline_v1", index_html)
        self.assertIn("pin_bill_snapshot", index_html)
        self.assertIn("renderBillSnapshotDiffBanner", index_html)
        for i18n_key in ("saveBillSnapshotBtn", "clearBillSnapshotBtn"):
            self.assertIn(f"{i18n_key}:", index_html, f"Missing {i18n_key} in I18N_EN")

    def test_06_pipeline_verifier_readme_and_marketing_v39_sync(self) -> None:
        self.assertIn("test_round9_product_iteration.py", prepare_release.FILES)
        workflow_yml = (ROOT / "cloudflare" / "daily_refresh.yml").read_text(encoding="utf-8")
        self.assertIn("test_round9_product_iteration.py", workflow_yml)
        self.assertIn("test_round9_product_iteration", workflow_yml)
        verifier_py = (ROOT / "cloudflare" / "verify_release.py").read_text(encoding="utf-8")
        self.assertIn("multifile_merged", verifier_py)
        article = (ROOT / "marketing_pack" / "01_juejin_zhihu_article.md").read_text(encoding="utf-8")
        self.assertIn("批量", article)
        self.assertIn("快照", article)
        if (ROOT / "sync_config_to_cloud.sh").exists():
            sync_sh = (ROOT / "sync_config_to_cloud.sh").read_text(encoding="utf-8")
            self.assertIn("test_round9_product_iteration", sync_sh)
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertRegex(readme, r"\bv3\.(?:9|\d{2,})\b")
            self.assertIn("test_round9_product_iteration", readme)


if __name__ == "__main__":
    unittest.main()
