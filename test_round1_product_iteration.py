#!/usr/bin/env python3
"""
TDD Acceptance Suite for Autonomous Iteration Round 1:
  - Batch 1: Build/test isolation, production default canonical URL, and anti-shrinkage live feed caching
  - Batch 2: /api/budget <-> Web deep-link cache parity, smart model alias resolution, and genuine EN/ZH i18n
  - Batch 3: Coding Plan model-coverage matching (same-family vs cross-model switch) & prompt-to-calls converter
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT / "engine_b_affiliate_web"))

import build_site  # noqa: E402
import fetch_and_enrich  # noqa: E402


class Round1Batch1PipelineTests(unittest.TestCase):
    def test_01_build_site_default_canonical_and_isolated_dist_dir(self) -> None:
        env_clean = {k: v for k, v in os.environ.items() if k != "SITE_BASE_URL"}
        with mock.patch.dict(os.environ, env_clean, clear=True):
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dist = Path(tmp) / "isolated_dist"
                summary = build_site.build_site(dist_dir=tmp_dist)
                self.assertEqual(summary["seo_pages_count"], 5)
                cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")
                self.assertIn(
                    '<link rel="canonical" href="https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/" />',
                    cp_html,
                )

        # Running legacy roadmap suite must NOT corrupt real dist/ canonicals
        subprocess.run(
            [sys.executable, "-W", "error", "-m", "unittest", "test_upgrade_2026_roadmap"],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        verify = subprocess.run(
            [sys.executable, "cloudflare/verify_release.py"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(verify.returncode, 0, f"verify_release.py failed after roadmap test: {verify.stderr}")

    def test_02_fetch_and_enrich_preserves_cached_global_models_on_transient_network_failure(self) -> None:
        live_seed = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(live_seed["counts_by_region"]["global"], 50)

        with tempfile.TemporaryDirectory() as tmp:
            seeded_path = Path(tmp) / "models_live.json"
            seeded_path.write_text(json.dumps(live_seed, ensure_ascii=False), encoding="utf-8")

            with mock.patch.object(
                fetch_and_enrich,
                "fetch_openrouter_raw",
                return_value=(fetch_and_enrich.FALLBACK_OPENROUTER_RAW, "fallback_snapshot+curated_cn_2026"),
            ):
                refreshed = fetch_and_enrich.refresh_models_live(output_path=seeded_path)

            self.assertEqual(refreshed["source"], "openrouter_cached+curated_cn_2026")
            self.assertEqual(refreshed["last_live_verified_at"], live_seed["last_live_verified_at"])
            self.assertGreaterEqual(
                refreshed["counts_by_region"]["global"],
                live_seed["counts_by_region"]["global"],
                "Transient OpenRouter SSL failure must not shrink cached global model catalog",
            )


class Round1Batch2ParityAndI18nTests(unittest.TestCase):
    def _run_budget_js(self, queries: list[dict[str, str]]) -> list[dict]:
        runner = """
import fs from 'node:fs';
const source = fs.readFileSync('functions/api/budget.js', 'utf8');
const {onRequestGet} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const {catalog, queries} = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = [];
for (const q of queries) {
  const req = new Request('https://example.test/api/budget?' + new URLSearchParams(q));
  const res = await onRequestGet({request: req, env: {ASSETS: {fetch: async () => Response.json(catalog)}}});
  out.push({status: res.status, body: await res.json()});
}
console.log(JSON.stringify(out));
"""
        catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", runner],
            cwd=str(ROOT),
            input=json.dumps({"catalog": catalog, "queries": queries}),
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(proc.stdout)

    def test_03_budget_api_deep_link_cache_parity_and_smart_model_resolution(self) -> None:
        from urllib.parse import parse_qs, urlsplit

        results = self._run_budget_js(
            [
                {"model_id": "qwen3-coder-next", "daily_requests": "1200", "cache_hit_rate": "0.5"},
                {"model_id": "siliconflow/thudm/glm-5", "daily_requests": "1000"},
                {"model_id": "aliyun/qwen3.5-plus", "daily_requests": "800"},
                {"model_id": "deepseek-v3", "daily_requests": "1000"},
                {"model_id": "unknown"},
            ]
        )
        self.assertEqual([r["status"] for r in results], [200, 200, 200, 200, 400])
        self.assertEqual(results[0]["body"]["model_id"], "aliyun-bailian/qwen3-coder-next")
        self.assertEqual(results[1]["body"]["model_id"], "siliconflow/THUDM/GLM-5")
        self.assertEqual(results[2]["body"]["model_id"], "aliyun-bailian/qwen3.5-plus")
        self.assertIn("deepseek-v3", results[3]["body"]["model_id"].lower())

        deep_url = results[0]["body"]["web_calculator_url"]
        parsed = urlsplit(deep_url)
        self.assertEqual(parsed.path, "/coding-plan-2026/")
        qs = parse_qs(parsed.query)
        self.assertEqual(qs["cache"], ["0.5"], "budget.js must emit 0..1 cache ratio matching Web restore logic")

    def test_04_bilingual_lang_toggle_and_legacy_cache_percent_restore_in_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dist = Path(tmp) / "dist"
            build_site.build_site(dist_dir=tmp_dist)
            cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

            # UI template must define real applyLang() i18n dictionary and support ?lang=en + legacy cache=50
            self.assertIn("function applyLang(", cp_html)
            self.assertIn("Workload & Billing Inputs", cp_html)
            self.assertIn('params.get("lang")', cp_html)
            self.assertIn("c > 1 && c <= 100", cp_html)


class Round1Batch3DecisionAccuracyAndUxTests(unittest.TestCase):
    def _run_budget_js(self, queries: list[dict[str, str]]) -> list[dict]:
        runner = """
import fs from 'node:fs';
const source = fs.readFileSync('functions/api/budget.js', 'utf8');
const {onRequestGet} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const {catalog, queries} = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = [];
for (const q of queries) {
  const req = new Request('https://example.test/api/budget?' + new URLSearchParams(q));
  const res = await onRequestGet({request: req, env: {ASSETS: {fetch: async () => Response.json(catalog)}}});
  out.push({status: res.status, body: await res.json()});
}
console.log(JSON.stringify(out));
"""
        catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", runner],
            cwd=str(ROOT),
            input=json.dumps({"catalog": catalog, "queries": queries}),
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(proc.stdout)

    def test_05_coding_plan_model_coverage_matching_across_python_and_budget_js(self) -> None:
        import pricing_core

        self.assertTrue(pricing_core.plan_covers_model("aliyun-coding-plan", "aliyun-bailian/qwen3-coder-next"))
        self.assertFalse(pricing_core.plan_covers_model("tencent-coding-plan", "aliyun-bailian/qwen3-coder-next"))

        self.assertTrue(pricing_core.plan_covers_model("tencent-coding-plan", "tencent-cloud/hunyuan-t1"))
        self.assertFalse(pricing_core.plan_covers_model("aliyun-coding-plan", "tencent-cloud/hunyuan-t1"))

        self.assertTrue(pricing_core.plan_covers_model("aliyun-coding-plan", "siliconflow/THUDM/GLM-5"))
        self.assertTrue(pricing_core.plan_covers_model("tencent-coding-plan", "siliconflow/THUDM/GLM-5"))

        self.assertTrue(pricing_core.plan_covers_model("volcengine-coding-plan", "tencent-cloud/deepseek-v3"))
        self.assertFalse(pricing_core.plan_covers_model("aliyun-coding-plan", "tencent-cloud/deepseek-v3"))

        self.assertFalse(pricing_core.plan_covers_model("aliyun-coding-plan", "anthropic/claude-sonnet-4"))
        self.assertFalse(pricing_core.plan_covers_model("tencent-coding-plan", "anthropic/claude-sonnet-4"))
        self.assertFalse(pricing_core.plan_covers_model("volcengine-coding-plan", "openai/gpt-4.1"))

        # Hunyuan-T1 at 500 calls/day (15,000/mo <= 18k Lite) and ¥105/mo PayG -> matches Tencent Lite ¥40 same-family!
        ev_hy = pricing_core.evaluate_coding_plans(
            daily_calls=500,
            payg_monthly_rmb=105.0,
            usage_mode="interactive_ide",
            model_id="tencent-cloud/hunyuan-t1",
        )
        self.assertEqual(ev_hy["recommended_same_family_plan_id"], "tencent-coding-plan")

        ev_claude = pricing_core.evaluate_coding_plans(
            daily_calls=2000,
            payg_monthly_rmb=3000.0,
            usage_mode="interactive_ide",
            model_id="anthropic/claude-sonnet-4",
        )
        self.assertIsNone(ev_claude["recommended_same_family_plan_id"])
        self.assertTrue(all(not p["covers_selected_model"] for p in ev_claude["eligible_subscriptions"]))

        # /api/budget JS parity for covers_selected_model
        js_res = self._run_budget_js(
            [
                {"model_id": "tencent-cloud/hunyuan-t1", "daily_requests": "500"},
                {"model_id": "aliyun-bailian/qwen3-coder-next", "daily_requests": "2000"},
            ]
        )
        hy_plans = {p["id"]: p for p in js_res[0]["body"]["coding_plans"]}
        self.assertTrue(hy_plans["tencent-coding-plan"]["covers_selected_model"])
        self.assertFalse(hy_plans["aliyun-coding-plan"]["covers_selected_model"])

        qw_plans = {p["id"]: p for p in js_res[1]["body"]["coding_plans"]}
        self.assertTrue(qw_plans["aliyun-coding-plan"]["covers_selected_model"])
        self.assertFalse(qw_plans["tencent-coding-plan"]["covers_selected_model"])

    def test_06_prompt_to_calls_quick_converter_and_coverage_ui_in_web(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dist = Path(tmp) / "dist"
            build_site.build_site(dist_dir=tmp_dist)
            cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

            self.assertIn('id="promptToCallsBar"', cp_html)
            self.assertIn('data-prompt-calls="480"', cp_html)
            self.assertIn('data-prompt-calls="2000"', cp_html)
            self.assertIn('data-prompt-calls="5000"', cp_html)
            self.assertIn("function planCoversModel(", cp_html)
            self.assertIn("套餐含同系模型", cp_html)
            self.assertIn("跨模型国产平替", cp_html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
