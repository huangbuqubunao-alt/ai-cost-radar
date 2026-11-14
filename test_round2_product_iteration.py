#!/usr/bin/env python3
"""
TDD Acceptance Suite for Autonomous Iteration Round 2 (v3.2):
  - Batch 1:
      1. SSR Worked Example B & FALLBACK_MODELS exact price parity with live Qwen3-Coder-Next (¥1.2/M in, ¥4.8/M out -> ¥184.32/mo)
      2. Coze Cloud Plugin (coze_cloud_tool.py) full v3.2 parity: standalone execution, alias/api_model_id resolution,
         LITE_WEEKLY_CAP=9000, per-plan eligible_subscriptions, covers_selected_model & recommended_same_family_plan_id
      3. Cloudflare /api/budget (functions/api/budget.js) 3-vendor subscription coverage (including volcengine-coding-plan),
         first_month_saving_rmb + recommended_same_family_plan_id, and verify_release.py --remote /api/budget contract probe
      4. Self-contained apify_store_bundle sync (includes pricing_core.py and runs standalone in an isolated directory)
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT / "engine_b_affiliate_web"))

import build_site  # noqa: E402
import pricing_core  # noqa: E402


def _load_coze_from_path(py_path: Path):
    spec = importlib.util.spec_from_file_location(f"coze_tool_{py_path.stat().st_mtime_ns}", py_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Round2Batch1CrossSurfaceParityTests(unittest.TestCase):
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

    def test_01_ssr_worked_example_b_matches_live_qwen3_coder_next_price(self) -> None:
        fb_qwen = next(m for m in build_site.FALLBACK_MODELS if m["id"] == "aliyun-bailian/qwen3-coder-next")
        self.assertAlmostEqual(fb_qwen["input_rmb_per_1m"], 1.2, places=2)
        self.assertAlmostEqual(fb_qwen["output_rmb_per_1m"], 4.8, places=2)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dist = Path(tmp) / "dist"
            build_site.build_site(dist_dir=tmp_dist)
            cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        # 800 calls/day * 30d = 24,000 calls -> 96M input (50% hit @ 0.2x of ¥1.2 = ¥0.72/M -> ¥69.12)
        # + 24M output (@ ¥4.8/M -> ¥115.20) = ¥184.32/mo
        self.assertIn("¥184.32/月", cp_html)
        self.assertIn("¥144.42", cp_html)  # 184.32 - 39.90 first-month savings
        self.assertIn("¥15.68", cp_html)   # 200.00 - 184.32 renewal extra cost
        self.assertNotIn("¥153.60/月", cp_html)

    def test_02_coze_cloud_tool_v3_parity_coverage_and_alias_resolution(self) -> None:
        src_coze = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle" / "coze_cloud_tool.py"

        with tempfile.TemporaryDirectory() as tmp:
            # Copy to isolated directory so local parents[3]/shared_data doesn't mask standalone Coze IDE behavior
            isolated_coze = Path(tmp) / "coze_cloud_tool.py"
            shutil.copy2(src_coze, isolated_coze)
            coze_mod = _load_coze_from_path(isolated_coze)

            self.assertEqual(getattr(coze_mod, "LITE_WEEKLY_CAP", None), 9000)

            res_ali = coze_mod.run_router(
                {
                    "action": "calculate_api_budget",
                    "model_query": "aliyun/qwen3.5-plus",
                    "daily_requests": 2000,
                    "avg_input_tokens": 3000,
                    "avg_output_tokens": 1000,
                    "cache_hit_rate": 0.5,
                }
            )
            self.assertEqual(res_ali["matched_model"]["id"], "aliyun-bailian/qwen3.5-plus")
            ev_ali = res_ali["coding_plan_evaluation"]
            self.assertIn("eligible_subscriptions", ev_ali)
            self.assertEqual(ev_ali.get("recommended_same_family_plan_id"), "aliyun-coding-plan")
            by_id_ali = {p["plan_id"]: p for p in ev_ali["eligible_subscriptions"]}
            self.assertTrue(by_id_ali["aliyun-coding-plan"]["covers_selected_model"])
            self.assertFalse(by_id_ali["tencent-coding-plan"]["covers_selected_model"])

            res_hy = coze_mod.run_router(
                {
                    "action": "calculate_api_budget",
                    "model_query": "hunyuan-t1-latest",
                    "daily_requests": 500,
                    "avg_input_tokens": 3000,
                    "avg_output_tokens": 1000,
                }
            )
            self.assertEqual(res_hy["matched_model"]["id"], "tencent-cloud/hunyuan-t1")
            self.assertEqual(
                res_hy["coding_plan_evaluation"].get("recommended_same_family_plan_id"),
                "tencent-coding-plan",
            )

    def test_03_cloudflare_budget_api_includes_volcengine_and_promo_savings_and_remote_verifier(self) -> None:
        results = self._run_budget_js(
            [
                {
                    "model_id": "tencent-cloud/deepseek-v3",
                    "daily_requests": "1500",
                    "avg_input_tokens": "3000",
                    "avg_output_tokens": "1000",
                    "peak_5h_calls": "1000",
                },
                {
                    "model_id": "qwen3-coder-next",
                    "daily_requests": "1200",
                    "avg_input_tokens": "4000",
                    "avg_output_tokens": "1000",
                    "cache_hit_rate": "0.5",
                    "peak_5h_calls": "1200",
                },
            ]
        )
        ds_body = results[0]["body"]
        plan_ids = [p["id"] for p in ds_body["coding_plans"]]
        self.assertEqual(
            plan_ids,
            ["aliyun-coding-plan", "tencent-coding-plan", "volcengine-coding-plan"],
        )
        ds_plans = {p["id"]: p for p in ds_body["coding_plans"]}
        self.assertTrue(ds_plans["volcengine-coding-plan"]["covers_selected_model"])
        self.assertFalse(ds_plans["aliyun-coding-plan"]["covers_selected_model"])
        self.assertEqual(ds_body.get("recommended_same_family_plan_id"), "volcengine-coding-plan")

        qw_body = results[1]["body"]
        self.assertEqual(qw_body.get("recommended_same_family_plan_id"), "aliyun-coding-plan")
        ali_pro = next(t for t in qw_body["coding_plans"][0]["tiers"] if t["tier_id"] == "pro")
        # 1200 * 30 = 36,000 calls; 144M in * 0.6 * 1.2 = 103.68; 36M out * 4.8 = 172.80 -> total 276.48
        self.assertAlmostEqual(ali_pro["first_month_saving_rmb"], 236.58, places=2)
        self.assertAlmostEqual(ali_pro["renewal_saving_rmb"], 76.48, places=2)

        # Verify verify_release.py --remote probes /api/budget and fails if /api/budget is broken
        dist_dir = ROOT / "engine_b_affiliate_web" / "dist"

        class BrokenBudgetHandler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:  # noqa: ANN002
                return

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlsplit(self.path)
                if parsed.path == "/admin/stats":
                    self.send_response(401)
                    self.end_headers()
                    return
                if parsed.path == "/api/budget":
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error":"broken"}')
                    return
                rel = parsed.path.lstrip("/")
                target = dist_dir / rel
                if target.is_dir():
                    target = target / "index.html"
                if not rel:
                    target = dist_dir / "index.html"
                if target.is_file():
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(target.read_bytes())
                    return
                self.send_response(404)
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), BrokenBudgetHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            proc = subprocess.run(
                [sys.executable, "cloudflare/verify_release.py", "--remote", f"http://127.0.0.1:{port}"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(
                proc.returncode,
                0,
                "verify_release.py --remote must fail when /api/budget returns HTTP 500",
            )
        finally:
            server.shutdown()
            server.server_close()

    def test_04_apify_store_bundle_is_self_contained_and_up_to_date(self) -> None:
        bundle_src = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "apify_store_bundle"
        if not bundle_src.is_dir():
            # Public release checkout exports root engine_a_mcp_actor/ (the canonical Apify Actor root)
            bundle_src = ROOT / "engine_a_mcp_actor"
        with tempfile.TemporaryDirectory() as tmp:
            isolated_bundle = Path(tmp) / "apify_store_bundle"
            shutil.copytree(bundle_src, isolated_bundle)
            check_code = (
                "import pricing_core, fetch_and_enrich, mcp_server; "
                "r = mcp_server.calculate_api_budget(model_query='qwen3-coder-next', daily_requests=5000); "
                "assert '超出 Pro 月额度 6 万次' in r['coding_plan_evaluation']['headline_zh'], r"
            )
            proc = subprocess.run(
                [sys.executable, "-c", check_code],
                cwd=str(isolated_bundle),
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"Standalone apify_store_bundle failed: stdout={proc.stdout} stderr={proc.stderr}",
            )


class Round2Batch2UxI18nAndShareTests(unittest.TestCase):
    def test_05_interactive_prompt_customizer_set_baseline_verdict_summary_and_modal_focus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dist = Path(tmp) / "dist"
            build_site.build_site(dist_dir=tmp_dist)
            cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        # 1. Custom Prompt x Turns-per-Prompt converter inputs
        self.assertIn('id="promptCountInput"', cp_html)
        self.assertIn('id="turnsPerPromptInput"', cp_html)

        # 2. One-click Set-as-Baseline action on model cards
        self.assertIn("data-set-baseline", cp_html)

        # 3. One-click Copy Verdict Summary brief button & generator
        self.assertIn('id="copySummaryBtn"', cp_html)
        self.assertIn("function buildVerdictSummaryText(", cp_html)

        # 4. Accessible configModal focus management (focus on open & restore trigger on close)
        self.assertIn("lastModalTrigger", cp_html)
        self.assertIn('document.getElementById("cfgClientSelect").focus()', cp_html)

    def test_06_complete_english_i18n_coverage_across_controls_and_dynamic_renderers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dist = Path(tmp) / "dist"
            build_site.build_site(dist_dir=tmp_dist)
            cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        # Previously untranslated static/dynamic surfaces must now carry English i18n hooks & copy
        required_en_markers = [
            'data-i18n="outputIncReasonLabel"',
            'data-i18n="modelsSectionTitle"',
            'data-i18n="modelsSectionDesc"',
            "Quotes Verified",
            "Excluded for Automated Backend",
            "Self-Host Gateway / GPU vs Pay-As-You-Go",
            "Set as Baseline",
            "Copy Verdict Brief",
            "1. Select Coding Client Protocol",
            "2. Select Active Billing Mode",
        ]
        for marker in required_en_markers:
            self.assertIn(marker, cp_html, f"Missing English localization marker: {marker}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
