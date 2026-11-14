#!/usr/bin/env python3
"""
TDD Test Suite for 2026.11 Market Research & Product Upgrade Roadmap:
  1. Zero placeholder affiliate URLs (`YOUR_...` sanitizer + clean config.json)
  2. Engine A: 2026.11 domestic models (`qwen3-coder-next`, `doubao-seed-2.0-pro`, `hunyuan-t1`, `Kimi-K2.5`, `GLM-5`),
     `coding_plans` catalog, `api_base_url` / `api_model_id` / `cache_hit_factor` fields
  3. Engine B: Programmatic SEO multi-page static compilation (5 routes in `dist/` + `sitemap.xml`),
     Coding Plan vs Pay-As-You-Go breakeven section, Reasoning Token toggle, and 1-Click Claude Code / Cursor config copy
  4. Engine C: Expanded multi-chain bounty radar queries (>=7) + Arbitrum/Optimism/Solana payout recognition
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT_DIR / "engine_b_affiliate_web"))
sys.path.insert(0, str(ROOT_DIR / "engine_c_bounty_radar"))

import bounty_core  # noqa: E402
import build_site  # noqa: E402
import fetch_and_enrich  # noqa: E402
import scan_bounties  # noqa: E402


class Roadmap2026UpgradeTests(unittest.TestCase):
    def test_01_no_placeholder_affiliate_urls_anywhere(self) -> None:
        raw_cfg = json.loads((ROOT_DIR / "config.json").read_text(encoding="utf-8"))
        cfg_dump = json.dumps(raw_cfg)
        self.assertNotIn("YOUR_", cfg_dump, "config.json must not contain YOUR_... placeholders")

        affiliates = build_site.load_affiliates(ROOT_DIR / "config.json")
        for key, url in affiliates.items():
            self.assertTrue(url.startswith("https://"), f"{key} must be an https URL, got {url}")
            self.assertNotIn("YOUR_", url, f"{key} leaked placeholder URL: {url}")

        # Even if a broken config has YOUR_DO_REF, load_affiliates must sanitize it to official clean URL
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(
                {
                    "global_affiliates_usd": {
                        "digitalocean_affiliate_url": "https://m.do.co/c/YOUR_DO_REF",
                        "runpod_affiliate_url": "https://runpod.io?ref=YOUR_RUNPOD_REF",
                    }
                },
                tmp,
            )
            tmp_path = Path(tmp.name)
        try:
            sanitized = build_site.load_affiliates(tmp_path)
            self.assertNotIn("YOUR_", sanitized["digitalocean_affiliate_url"])
            self.assertNotIn("YOUR_", sanitized["runpod_affiliate_url"])
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_02_engine_a_2026_models_coding_plans_and_client_configs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = Path(tmpdir) / "models_live.json"
            payload = fetch_and_enrich.refresh_models_live(output_path=out_json)

            self.assertIn("coding_plans", payload, "models_live.json must include 2026 coding_plans catalog")
            self.assertGreaterEqual(len(payload["coding_plans"]), 6)

            plan_ids = {p["id"] for p in payload["coding_plans"]}
            self.assertIn("aliyun-coding-plan", plan_ids)
            self.assertIn("tencent-coding-plan", plan_ids)

            model_ids = {m["id"] for m in payload["models"]}
            for expected_2026_model in (
                "aliyun-bailian/qwen3-coder-next",
                "aliyun-bailian/qwen3.5-plus",
                "volcengine/doubao-seed-2.0-pro",
                "tencent-cloud/hunyuan-t1",
                "siliconflow/moonshotai/Kimi-K2.5",
                "siliconflow/THUDM/GLM-5",
            ):
                self.assertIn(expected_2026_model, model_ids, f"Missing 2026 model {expected_2026_model}")

            for m in payload["models"]:
                self.assertIn("api_base_url", m)
                self.assertIn("api_model_id", m)
                self.assertIn("cache_hit_factor", m)
                self.assertTrue(str(m["api_base_url"]).startswith("https://"))

    def test_03_engine_b_programmatic_seo_pages_and_conversion_hooks(self) -> None:
        summary = build_site.build_site(site_url="https://huangbuqubunao-alt.github.io/ai-cost-radar/")
        dist_dir = ROOT_DIR / "engine_b_affiliate_web" / "dist"

        expected_routes = [
            dist_dir / "index.html",
            dist_dir / "claude-code-domestic" / "index.html",
            dist_dir / "coding-plan-2026" / "index.html",
            dist_dir / "deepseek-vs-qwen" / "index.html",
            dist_dir / "dify-openclaw-cloud-server" / "index.html",
        ]
        for route_file in expected_routes:
            self.assertTrue(route_file.exists(), f"Missing programmatic SEO page: {route_file}")
            html_text = route_file.read_text(encoding="utf-8")
            self.assertNotIn("YOUR_DO_REF", html_text)
            self.assertNotIn("YOUR_RUNPOD_REF", html_text)
            self.assertNotIn("YOUR_RAILWAY_CODE", html_text)

        index_html = (dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn("codingPlanSection", index_html, "Must render Coding Plan PK section")
        self.assertIn("reasoningToggle", index_html, "Must render Reasoning Token overhead toggle")
        self.assertIn("configModal", index_html, "Must render 1-Click Claude Code / Cursor config modal")
        self.assertIn("vlxk7knp", index_html)
        self.assertIn("EGH3k1cs", index_html)

        sitemap_xml = (dist_dir / "sitemap.xml").read_text(encoding="utf-8")
        for slug in (
            "claude-code-domestic/",
            "coding-plan-2026/",
            "deepseek-vs-qwen/",
            "dify-openclaw-cloud-server/",
        ):
            self.assertIn(slug, sitemap_xml, f"sitemap.xml missing SEO route {slug}")
        self.assertGreaterEqual(summary.get("seo_pages_count", 0), 5)

    def test_04_engine_c_multichain_bounty_queries_and_l2_solana_classifier(self) -> None:
        self.assertGreaterEqual(
            len(scan_bounties.TARGETED_QUERIES),
            7,
            "Engine C should scan >=7 diversified crypto/CN-friendly GitHub bounty queries",
        )
        cls_arb = bounty_core.classify_cn_payout(
            title="[Bounty $200] Fix SDK streaming parser",
            body="Reward paid in USDC on Arbitrum or Optimism upon PR merge.",
            labels=["bounty"],
            payout_readiness={"has_usdc_wallet": True, "has_hk_bank_or_stripe": False},
        )
        self.assertEqual(cls_arb.tier, bounty_core.TIER_CN_FRIENDLY)

        cls_sol = bounty_core.classify_cn_payout(
            title="Add Rust anchor client examples",
            body="150 USDC payout on Solana SPL wallet.",
            labels=["bounty"],
            payout_readiness={"has_usdc_wallet": True, "has_hk_bank_or_stripe": False},
        )
        self.assertEqual(cls_sol.tier, bounty_core.TIER_CN_FRIENDLY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
