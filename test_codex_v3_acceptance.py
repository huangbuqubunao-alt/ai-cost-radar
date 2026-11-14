#!/usr/bin/env python3
"""
TDD Acceptance Suite for AI Cost Radar v3.0 (Codex Audit & Option A Spec):
  1. Official Coding Plan prices, quotas (Aliyun Lite stopped, Pro ¥39.90 first / ¥200 renewal 6k/45k/90k;
     Tencent Lite ¥40 1.2k/9k/18k, Pro ¥200 6k/45k/90k), offer_type separation, automated_backend exclusion,
     and exact 5,000 calls/day ("按 30 天预计 15 万次，超出 Pro 月额度 6 万次") verdict in Web & Coze/MCP.
  2. Cross-engine math parity (Web/SSR, MCP, Coze) on 3 fixed cases:
     - Case A: 1M input tokens, ¥1.0 regular, ¥0.2 hit price, 50% hit rate -> ¥0.60 input cost.
     - Case B: Reasoning multiplier (2.5x) vs output_includes_reasoning=True (no double multiplication).
     - Case C: 800 calls/day interactive IDE -> 24,000 calls/mo (exceeds Tencent Lite 18k, fits Pro 90k with
       "月额度足够，5 小时窗口待确认", and separates first-month vs ¥200 renewal verdict).
  3. Dedicated protocol endpoints (Claude Code Anthropic sk-sp- vs OpenAI-compat sk-sp- vs Pay-As-You-Go sk-)
     and Self-Host / Dify Cache total cost (advising Pay-As-You-Go when self-host exceeds current API bill).
  4. Build-time SSR HTML tables (<table>, <tr>, official citations, dual dates) readable with JS/CSS stripped
     via HTMLParser, clean canonical URL, and URLSearchParams share/restore support.
  5. First-party /events attribution validation, viewport impression & CTR deduplication (unique clickers /
     unique viewers), "估算日 UV" wording, updated marketing_pack (no false "不收集任何数据" or "¥29 封顶").
  6. Engine C strict actionable gate ("通道待确认" or non-cash site credit never enters actionable_now or CLEAR TO SOLVE).
"""

from __future__ import annotations

from html.parser import HTMLParser
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT_DIR / "engine_b_affiliate_web"))
sys.path.insert(0, str(ROOT_DIR / "engine_c_bounty_radar"))
sys.path.insert(0, str(ROOT_DIR / "cloudflare"))


def _load_coze_module():
    coze_path = (
        ROOT_DIR
        / "engine_a_mcp_actor"
        / "publish_bundles"
        / "coze_cn_bundle"
        / "coze_cloud_tool.py"
    )
    spec = importlib.util.spec_from_file_location("coze_cloud_tool_v3", coze_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _NoScriptHTMLInspector(HTMLParser):
    """Extracts visible text, table/row counts, links, and canonical href with <script>/<style> stripped."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.table_count = 0
        self.tr_count = 0
        self.caption_count = 0
        self.hrefs: list[str] = []
        self.canonical_href: str | None = None
        self.ids: set[str] = set()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if "id" in attr_map and attr_map["id"]:
            self.ids.add(attr_map["id"])
        if t == "link" and "canonical" in attr_map.get("rel", "").lower():
            self.canonical_href = attr_map.get("href")
        if t in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth == 0:
            if t == "table":
                self.table_count += 1
            elif t == "tr":
                self.tr_count += 1
            elif t == "caption":
                self.caption_count += 1
            elif t == "a" and attr_map.get("href"):
                self.hrefs.append(attr_map["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._chunks.append(stripped)

    @property
    def visible_text(self) -> str:
        return "\n".join(self._chunks)


class CodexV3AcceptanceTests(unittest.TestCase):
    def test_01_official_coding_plan_quotas_prices_and_5000_calls_verdict(self) -> None:
        import fetch_and_enrich
        import mcp_server
        import pricing_core

        coze_mod = _load_coze_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = Path(tmpdir) / "models_live.json"
            payload = fetch_and_enrich.refresh_models_live(output_path=out_json)

        self.assertIn("quote_verified_date", payload)
        plans_by_id = {p["id"]: p for p in payload["coding_plans"]}

        # Offer type separation: non-subscriptions must NOT be labeled "subscription"
        self.assertEqual(plans_by_id["aliyun-coding-plan"]["offer_type"], "subscription")
        self.assertEqual(plans_by_id["tencent-coding-plan"]["offer_type"], "subscription")
        self.assertEqual(plans_by_id["siliconflow-coding-pack"]["offer_type"], "payg_pool")
        self.assertEqual(plans_by_id["aliyun-ecs-agent-host"]["offer_type"], "cloud_host")
        self.assertEqual(plans_by_id["openrouter-global-coding"]["offer_type"], "gateway_example")

        # Aliyun official rules: Lite stopped for new purchase, Pro ¥39.90 first month / ¥200 renewal, 6k/45k/90k
        ali = plans_by_id["aliyun-coding-plan"]
        self.assertEqual(ali["official_source_url"], "https://help.aliyun.com/zh/model-studio/coding-plan")
        ali_tiers = {t["tier_id"]: t for t in ali["tiers"]}
        self.assertFalse(ali_tiers["lite"]["purchasable"])
        self.assertTrue(ali_tiers["pro"]["purchasable"])
        self.assertAlmostEqual(ali_tiers["pro"]["first_month_rmb"], 39.90, places=2)
        self.assertAlmostEqual(ali_tiers["pro"]["renewal_rmb"], 200.0, places=2)
        self.assertEqual(
            (ali_tiers["pro"]["quota_5h"], ali_tiers["pro"]["quota_weekly"], ali_tiers["pro"]["quota_monthly"]),
            (6000, 45000, 90000),
        )

        # Tencent official rules: Lite ¥40 (1,200 / 9,000 / 18,000), Pro ¥200 (6,000 / 45,000 / 90,000)
        tx = plans_by_id["tencent-coding-plan"]
        self.assertEqual(tx["official_source_url"], "https://cloud.tencent.com/document/product/1823/130092")
        tx_tiers = {t["tier_id"]: t for t in tx["tiers"]}
        self.assertTrue(tx_tiers["lite"]["purchasable"])
        self.assertAlmostEqual(tx_tiers["lite"]["renewal_rmb"], 40.0, places=2)
        self.assertEqual(
            (tx_tiers["lite"]["quota_5h"], tx_tiers["lite"]["quota_weekly"], tx_tiers["lite"]["quota_monthly"]),
            (1200, 9000, 18000),
        )
        self.assertAlmostEqual(tx_tiers["pro"]["renewal_rmb"], 200.0, places=2)
        self.assertEqual(
            (tx_tiers["pro"]["quota_5h"], tx_tiers["pro"]["quota_weekly"], tx_tiers["pro"]["quota_monthly"]),
            (6000, 45000, 90000),
        )

        # 5,000 calls/day -> 150,000 calls/month -> exceeds Pro 90,000 by 60,000 in Core, MCP, AND Coze
        eval_5k = pricing_core.evaluate_coding_plans(
            daily_calls=5000,
            payg_monthly_rmb=900.0,
            usage_mode="interactive_ide",
        )
        self.assertIn("按 30 天预计 15 万次", eval_5k["headline_zh"])
        self.assertIn("超出 Pro 月额度 6 万次", eval_5k["headline_zh"])

        mcp_5k = mcp_server.calculate_api_budget(
            model_query="qwen3.5-plus",
            daily_requests=5000,
            avg_input_tokens=2000,
            avg_output_tokens=800,
        )
        self.assertIn("coding_plan_evaluation", mcp_5k)
        self.assertIn("按 30 天预计 15 万次", mcp_5k["coding_plan_evaluation"]["headline_zh"])
        self.assertIn("超出 Pro 月额度 6 万次", mcp_5k["coding_plan_evaluation"]["headline_zh"])

        coze_5k = coze_mod.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "qwen3.5-plus",
                "daily_requests": 5000,
                "avg_input_tokens": 2000,
                "avg_output_tokens": 800,
            }
        )
        coze_dump = json.dumps(coze_5k, ensure_ascii=False)
        self.assertIn("按 30 天预计 15 万次", coze_dump)
        self.assertIn("超出 Pro 月额度 6 万次", coze_dump)

        # Non-interactive automated backend MUST exclude Aliyun & Tencent personal Coding Plans
        eval_backend = pricing_core.evaluate_coding_plans(
            daily_calls=1000,
            payg_monthly_rmb=500.0,
            usage_mode="automated_backend",
        )
        eligible_ids = [item["plan_id"] for item in eval_backend["eligible_subscriptions"]]
        self.assertEqual(eligible_ids, [])
        self.assertGreaterEqual(len(eval_backend["excluded_subscriptions"]), 2)

    def test_02_consistent_token_cache_and_reasoning_math_across_web_coze_mcp(self) -> None:
        import mcp_server
        import pricing_core

        coze_mod = _load_coze_module()

        # Case 1 (Codex exact spec): 1M input tokens, 0 output, regular ¥1.0, hit ¥0.2 (factor 0.2), hit_rate 50% -> ¥0.60
        c1 = pricing_core.calculate_token_bill(
            monthly_input_m=1.0,
            monthly_output_m=0.0,
            input_price_per_1m=1.0,
            output_price_per_1m=4.0,
            cache_hit_rate=0.5,
            cache_hit_factor=0.2,
            reasoning_multiplier=1.0,
            output_includes_reasoning=False,
        )
        self.assertAlmostEqual(c1["input_cost"], 0.60, places=4)
        self.assertAlmostEqual(c1["total_cost"], 0.60, places=4)

        # Case 2: Reasoning 2.5x vs output_includes_reasoning=True (no double multiplication)
        c2_mult = pricing_core.calculate_token_bill(
            monthly_input_m=1.0,
            monthly_output_m=1.0,
            input_price_per_1m=2.0,
            output_price_per_1m=8.0,
            cache_hit_rate=0.0,
            cache_hit_factor=0.2,
            reasoning_multiplier=2.5,
            output_includes_reasoning=False,
        )
        c2_included = pricing_core.calculate_token_bill(
            monthly_input_m=1.0,
            monthly_output_m=1.0,
            input_price_per_1m=2.0,
            output_price_per_1m=8.0,
            cache_hit_rate=0.0,
            cache_hit_factor=0.2,
            reasoning_multiplier=2.5,
            output_includes_reasoning=True,
        )
        self.assertAlmostEqual(c2_mult["output_cost"], 20.0, places=4)
        self.assertAlmostEqual(c2_included["output_cost"], 8.0, places=4)

        # Case 3: Cross-check MCP and Coze on identical model & cache/reasoning parameters
        mcp_res = mcp_server.calculate_api_budget(
            model_query="aliyun-bailian/qwen3-coder-next",
            daily_requests=800,
            avg_input_tokens=4000,
            avg_output_tokens=1000,
            cache_hit_rate=0.5,
            reasoning_multiplier=1.0,
            usage_mode="interactive_ide",
        )
        coze_res = coze_mod.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "aliyun-bailian/qwen3-coder-next",
                "daily_requests": 800,
                "avg_input_tokens": 4000,
                "avg_output_tokens": 1000,
                "cache_hit_rate": 0.5,
                "reasoning_multiplier": 1.0,
                "usage_mode": "interactive_ide",
            }
        )
        self.assertAlmostEqual(
            mcp_res["budget_estimate"]["monthly_rmb"],
            coze_res["budget_estimate"]["monthly_rmb"],
            places=2,
        )
        # 800/day * 30 = 24,000 calls/mo -> fits Pro 90k, exceeds Lite 18k, and flags 5h peak window unconfirmed
        self.assertIn("5 小时窗口待确认", mcp_res["coding_plan_evaluation"]["window_note_zh"])

    def test_03_dedicated_endpoints_and_self_host_total_cost(self) -> None:
        import pricing_core

        # Tencent Coding Plan + Claude Code MUST use Anthropic native endpoint, distinct from Tencent Pay-As-You-Go
        tx_cc = pricing_core.get_client_endpoint_config(
            vendor_or_plan="tencent-coding-plan",
            client_type="claude_code",
            billing_mode="coding_plan",
            model_id="hunyuan-t1",
        )
        tx_payg = pricing_core.get_client_endpoint_config(
            vendor_or_plan="tencent_cps_url",
            client_type="openai_compat",
            billing_mode="payg",
            model_id="deepseek-r1",
        )
        self.assertEqual(tx_cc["base_url"], "https://api.lkeap.cloud.tencent.com/coding/anthropic")
        self.assertIn("ANTHROPIC_BASE_URL", tx_cc["env_snippet"])
        self.assertIn("sk-sp-", tx_cc["env_snippet"])
        self.assertEqual(tx_payg["base_url"], "https://api.lkeap.cloud.tencent.com/v1")
        self.assertIn("OPENAI_BASE_URL", tx_payg["env_snippet"])
        self.assertNotEqual(tx_cc["base_url"], tx_payg["base_url"])

        # Aliyun Coding Plan + Claude Code vs OpenAI-compatible
        ali_cc = pricing_core.get_client_endpoint_config(
            vendor_or_plan="aliyun-coding-plan",
            client_type="claude_code",
            billing_mode="coding_plan",
            model_id="qwen3.5-plus",
        )
        ali_oai = pricing_core.get_client_endpoint_config(
            vendor_or_plan="aliyun-coding-plan",
            client_type="cursor",
            billing_mode="coding_plan",
            model_id="qwen3.5-plus",
        )
        self.assertEqual(ali_cc["base_url"], "https://coding.dashscope.aliyuncs.com/apps/anthropic")
        self.assertEqual(ali_oai["base_url"], "https://coding.dashscope.aliyuncs.com/v1")

        # Self-host / Dify cache: when total self-host cost > current API bill, MUST advise staying on Pay-As-You-Go
        sh_low = pricing_core.evaluate_self_host_vs_payg(
            current_payg_rmb=45.0,
            semantic_cache_hit_rate=0.35,
            gateway_host_rmb=68.0,
            storage_egress_rmb=15.0,
        )
        self.assertFalse(sh_low["gateway_saves_money"])
        self.assertIn("继续按量", sh_low["recommendation_zh"])

    def test_shared_budget_peak_and_config(self) -> None:
        import pricing_core
        from urllib.parse import parse_qs, urlsplit

        coze = _load_coze_module()
        result = coze.run_router({
            "action": "calculate_api_budget", "model_query": "qwen3.5-plus",
            "daily_requests": 800, "peak_5h_calls": 6500, "output_includes_reasoning": True,
        })
        query = parse_qs(urlsplit(result["web_calculator_url"]).query)
        self.assertEqual(query["inc_cot"], ["1"])
        self.assertEqual(query["peak5h"], ["6500"])
        self.assertIn("6,500", result["summary_cn"])
        evaluation = pricing_core.evaluate_coding_plans(
            daily_calls=800, payg_monthly_rmb=260, peak_5h_calls=6500,
        )
        self.assertIn("exceeds_5h_cap", str(evaluation))
        config = pricing_core.get_client_endpoint_config(vendor_or_plan="tencent-coding-plan", billing_mode="coding_plan")
        self.assertIn('ANTHROPIC_MODEL="tc-code-latest"', config["env_snippet"])

    def test_04_ssr_no_js_htmlparser_and_shareable_url_params(self) -> None:
        import build_site

        build_site.build_site(site_url="https://huangbuqubunao-alt.github.io/ai-cost-radar/")
        dist_dir = ROOT_DIR / "engine_b_affiliate_web" / "dist"

        for rel_path in ("index.html", "coding-plan-2026/index.html", "deepseek-vs-qwen/index.html"):
            raw_html = (dist_dir / rel_path).read_text(encoding="utf-8")
            inspector = _NoScriptHTMLInspector()
            inspector.feed(raw_html)
            self.assertGreater(inspector.table_count, 0, f"{rel_path} must contain SSR <table> outside <script>")
            self.assertGreater(inspector.tr_count, 2, f"{rel_path} must contain SSR <tr> rows outside <script>")
            self.assertGreater(inspector.caption_count, 0, f"{rel_path} must contain <caption>")

        cp_raw = (dist_dir / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")
        cp = _NoScriptHTMLInspector()
        cp.feed(cp_raw)
        vis = cp.visible_text

        # Core prices, quotas, dual dates, worked example, and official sources visible WITHOUT JS
        self.assertIn("39.9", vis)
        self.assertIn("200", vis)
        self.assertIn("90,000", vis)
        self.assertIn("18,000", vis)
        self.assertIn("按 30 天预计 15 万次", vis)
        self.assertIn("超出 Pro 月额度 6 万次", vis)
        self.assertIn("页面构建日", vis)
        self.assertIn("报价核验日", vis)
        self.assertIn("估算日 UV", vis)
        self.assertTrue(
            any("help.aliyun.com/zh/model-studio/coding-plan" in h for h in cp.hrefs),
            "SSR page must link directly to Aliyun Coding Plan official documentation",
        )
        self.assertTrue(
            any("cloud.tencent.com/document/product/1823/130092" in h for h in cp.hrefs),
            "SSR page must link directly to Tencent Coding Plan official documentation",
        )
        self.assertEqual(
            cp.canonical_href,
            "https://huangbuqubunao-alt.github.io/ai-cost-radar/coding-plan-2026/",
        )

        # Shareable URLSearchParams + sendBeacon(/events) + IntersectionObserver in client script
        self.assertIn("URLSearchParams", cp_raw)
        self.assertIn("sendBeacon", cp_raw)
        self.assertIn("IntersectionObserver", cp_raw)

        # Static SVG badge & Atom feed generated
        self.assertTrue((dist_dir / "badges" / "coding-plan-status.svg").exists())
        self.assertTrue((dist_dir / "feeds" / "price-changes.xml").exists())

    def test_05_events_attribution_reconcile_and_honest_marketing_pack(self) -> None:
        import events_reconcile

        events = [
            {"event_name": "page_view", "day_bucket": "2026-11-13", "browser_day_id": "b1", "route": "/coding-plan-2026/"},
            {"event_name": "page_view", "day_bucket": "2026-11-13", "browser_day_id": "b1", "route": "/coding-plan-2026/"},
            {"event_name": "page_view", "day_bucket": "2026-11-13", "browser_day_id": "b2", "route": "/coding-plan-2026/"},
            {"event_name": "result_view", "day_bucket": "2026-11-13", "browser_day_id": "b1", "route": "/coding-plan-2026/"},
            {"event_name": "offer_impression", "day_bucket": "2026-11-13", "browser_day_id": "b1", "offer_id": "aliyun-ecs-agent-host"},
            {"event_name": "offer_impression", "day_bucket": "2026-11-13", "browser_day_id": "b2", "offer_id": "aliyun-ecs-agent-host"},
            {"event_name": "offer_impression", "day_bucket": "2026-11-13", "browser_day_id": "b2", "offer_id": "aliyun-ecs-agent-host"},
            {"event_name": "affiliate_click", "day_bucket": "2026-11-13", "browser_day_id": "b1", "offer_id": "aliyun-ecs-agent-host"},
            {"event_name": "evil_event", "day_bucket": "2026-11-13", "browser_day_id": "b9"},
        ]
        valid = [e for e in events if events_reconcile.validate_event_payload(e)[0]]
        self.assertEqual(len(valid), 8)  # evil_event rejected

        report = events_reconcile.summarize_daily_reconciliation(valid, day="2026-11-13")
        self.assertEqual(report["estimated_daily_uv"], 2)
        self.assertEqual(report["calculations_completed_uv"], 1)
        card = report["offers"]["aliyun-ecs-agent-host"]
        self.assertEqual(card["unique_viewers"], 2)
        self.assertEqual(card["unique_clickers"], 1)
        self.assertAlmostEqual(card["ctr_pct"], 50.0, places=1)
        self.assertIn("settled_commission_rmb", report)

        # Cloudflare Pages Function + D1 schema exist
        self.assertTrue((ROOT_DIR / "functions" / "events.js").exists())
        self.assertTrue((ROOT_DIR / "cloudflare" / "d1_schema.sql").exists())

        # Marketing pack must NOT claim "不收集任何数据" or false "¥29 封顶", and MUST lead with the 5,000 calls article
        for md_file in (ROOT_DIR / "marketing_pack").glob("*"):
            if md_file.is_file():
                txt = md_file.read_text(encoding="utf-8")
                self.assertNotIn("不收集任何数据", txt, f"{md_file.name} still claims zero data collection")
                self.assertNotIn("¥29 封顶", txt, f"{md_file.name} still claims outdated ¥29 cap")
        article_txt = (ROOT_DIR / "marketing_pack" / "01_juejin_zhihu_article.md").read_text(encoding="utf-8")
        self.assertIn("每天 5,000 次调用，为什么 ¥200 包月仍然不够用", article_txt)

    def test_06_engine_c_strict_actionable_gate(self) -> None:
        import bounty_core
        import sandbox_prepare
        import scan_bounties

        # Non-cash site credit / MCP dev key or TIER_UNCONFIRMED must NEVER be actionable_now or CLEAR TO SOLVE
        cls_credit = bounty_core.classify_cn_payout(
            title="[Bounty] Build sample integration — $2 site credit reward",
            body="Contributors receive $2 platform site credit and a free MCP dev key.",
            labels=["bounty"],
            payout_readiness={"has_usdc_wallet": True, "has_hk_bank_or_stripe": False},
        )
        self.assertNotEqual(cls_credit.tier, bounty_core.TIER_CN_FRIENDLY)

        verdict_badge, _ = sandbox_prepare.determine_verdict(
            issue_state="open",
            unassigned=True,
            pr_report={"merged_prs": [], "open_or_active_prs": [], "claimants": []},
            payout_tier=bounty_core.TIER_UNCONFIRMED,
            has_verified_cash_amount=False,
        )
        self.assertNotIn("CLEAR TO SOLVE", verdict_badge)
        self.assertIn("VERIFY", verdict_badge.upper())

        # Verify scan_bounties helper strictly filters actionable_now to verified CN-friendly cash/crypto bounties
        sample_candidate = {
            "payout_tier": bounty_core.TIER_UNCONFIRMED,
            "reward_amount_usd": None,
            "unassigned": True,
            "is_non_cash_credit": True,
        }
        self.assertFalse(scan_bounties.is_strictly_actionable_bounty(sample_candidate))

        verified_candidate = {
            "payout_tier": bounty_core.TIER_CN_FRIENDLY,
            "reward_amount_usd": 150.0,
            "unassigned": True,
            "is_non_cash_credit": False,
        }
        self.assertTrue(scan_bounties.is_strictly_actionable_bounty(verified_candidate))


if __name__ == "__main__":
    unittest.main(verbosity=2)
