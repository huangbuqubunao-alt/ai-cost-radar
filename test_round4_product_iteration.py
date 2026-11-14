#!/usr/bin/env python3
"""
Round 4 (v3.4) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. Over-cap (>90,000 calls/mo) "1 Pro Base (90k) + PayG Overflow" hybrid billing math parity
       across `pricing_core.py`, `functions/api/budget.js`, and `coze_cloud_tool.py` (including
       break-even safeguard when pure PayG is cheaper on renewal).
    2. Fallback catalog price parity (`volcengine/doubao-seed-2.0-pro` in `build_site.py` &
       `coze_cloud_tool.py`) and `openapi_coze_live.json` (`/api/openapi.json`) v3.4 schema parity.
    3. Automated official Coding Plan rule fingerprint audit (`audit_official_coding_plan_docs` in
       `fetch_and_enrich.py`) with drift -> `price_changes` -> Atom XML alert pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle"))
sys.path.insert(0, str(ROOT / "engine_b_affiliate_web"))
sys.path.insert(0, str(ROOT / "cloudflare"))

import build_site  # noqa: E402
import coze_cloud_tool  # noqa: E402
import fetch_and_enrich  # noqa: E402
import mcp_server  # noqa: E402
import pricing_core  # noqa: E402


class Round4Batch1OverflowMathRuleAuditAndSyncTests(unittest.TestCase):
    def _run_cloudflare_budget_js(self, query_string: str) -> dict:
        node_script = f"""
import fs from "node:fs";
import {{ calculateBudget }} from "./functions/api/budget.js";

const catalog = JSON.parse(fs.readFileSync("./shared_data/models_live.json", "utf-8"));
const params = new URLSearchParams({json.dumps(query_string)});
console.log(JSON.stringify(calculateBudget(catalog, params)));
"""
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", node_script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(proc.stdout.strip())

    def test_01_over_cap_pro_base_plus_payg_overflow_parity_across_python_js_and_coze(self) -> None:
        # Case A: Flagship default scenario (`5,000` calls/day = `150,000`/mo on `qwen3-coder-next`,
        # 4k in / 1k out, 50% cache hit -> Pure PayG = ¥1,152.00/mo).
        # 1 Aliyun Pro covers first 90,000 calls (¥39.90 1st mo / ¥200.00 renewal);
        # remaining 60,000 calls (40%) on PayG = ¥460.80 -> Combined ¥500.70 / ¥660.80,
        # saving ¥651.30 (1st mo) and ¥491.20/mo on renewal!
        mcp_res = mcp_server.calculate_api_budget(
            model_query="aliyun-bailian/qwen3-coder-next",
            daily_requests=5000,
            avg_input_tokens=4000,
            avg_output_tokens=1000,
            cache_hit_rate=0.5,
            usage_mode="interactive_ide",
        )
        py_eval = mcp_res["coding_plan_evaluation"]
        self.assertIsNone(py_eval["recommended_same_family_plan_id"])
        self.assertEqual(py_eval.get("recommended_overflow_hybrid_plan_id"), "aliyun-coding-plan")

        py_aliyun = next(p for p in py_eval["eligible_subscriptions"] if p["plan_id"] == "aliyun-coding-plan")
        self.assertEqual(py_aliyun["status"], "exceeds_monthly_cap")
        hyb = py_aliyun.get("overflow_hybrid")
        self.assertIsInstance(hyb, dict)
        self.assertEqual(hyb["covered_calls"], 90000)
        self.assertEqual(hyb["overflow_calls"], 60000)
        self.assertAlmostEqual(hyb["overflow_payg_rmb"], 460.80, places=2)
        self.assertAlmostEqual(hyb["first_month_total_rmb"], 500.70, places=2)
        self.assertAlmostEqual(hyb["renewal_total_rmb"], 660.80, places=2)
        self.assertAlmostEqual(hyb["first_month_saving_rmb"], 651.30, places=2)
        self.assertAlmostEqual(hyb["renewal_saving_rmb"], 491.20, places=2)
        self.assertTrue(hyb["saves_on_renewal"])
        self.assertIn("超出 Pro 月额度 6 万次", py_eval["headline_zh"])
        self.assertIn("660.80", py_eval["headline_zh"])

        # Cloudflare Pages Function `/api/budget` parity
        js_res = self._run_cloudflare_budget_js(
            "model_id=aliyun-bailian/qwen3-coder-next&daily_requests=5000"
            "&avg_input_tokens=4000&avg_output_tokens=1000&cache_hit_rate=0.5&usage_mode=interactive_ide"
        )
        self.assertAlmostEqual(js_res["monthly_rmb"], 1152.00, places=2)
        self.assertIsNone(js_res["recommended_same_family_plan_id"])
        self.assertEqual(js_res.get("recommended_overflow_hybrid_plan_id"), "aliyun-coding-plan")
        js_aliyun = next(p for p in js_res["coding_plans"] if p["id"] == "aliyun-coding-plan")
        js_pro = next(t for t in js_aliyun["tiers"] if t["tier_id"] == "pro")
        self.assertFalse(js_pro["eligible_by_provided_usage"])
        js_hyb = js_aliyun.get("overflow_hybrid")
        self.assertIsInstance(js_hyb, dict)
        self.assertEqual(js_hyb["covered_calls"], 90000)
        self.assertEqual(js_hyb["overflow_calls"], 60000)
        self.assertAlmostEqual(js_hyb["overflow_payg_rmb"], 460.80, places=2)
        self.assertAlmostEqual(js_hyb["first_month_total_rmb"], 500.70, places=2)
        self.assertAlmostEqual(js_hyb["renewal_total_rmb"], 660.80, places=2)
        self.assertAlmostEqual(js_hyb["renewal_saving_rmb"], 491.20, places=2)
        self.assertTrue(js_hyb["saves_on_renewal"])
        self.assertIn("60000", js_res["summary_cn"])

        # Coze cloud tool parity
        coze_res = coze_cloud_tool.handler(
            {
                "action": "budget",
                "model_query": "aliyun-bailian/qwen3-coder-next",
                "daily_requests": 5000,
                "avg_input_tokens": 4000,
                "avg_output_tokens": 1000,
                "cache_hit_rate": 0.5,
                "usage_mode": "interactive_ide",
            }
        )
        coze_eval = coze_res["data"]["coding_plan_evaluation"]
        self.assertEqual(coze_eval.get("recommended_overflow_hybrid_plan_id"), "aliyun-coding-plan")
        coze_aliyun = next(p for p in coze_eval["eligible_subscriptions"] if p["plan_id"] == "aliyun-coding-plan")
        self.assertAlmostEqual(coze_aliyun["overflow_hybrid"]["renewal_total_rmb"], 660.80, places=2)
        self.assertAlmostEqual(coze_aliyun["overflow_hybrid"]["renewal_saving_rmb"], 491.20, places=2)

        # Case B: Break-even safeguard (`aliyun-bailian/qwen-turbo` at 5,000 calls/day = ¥198.00/mo PayG).
        # First 90k calls only cost ¥118.80 on PayG (< ¥200 Pro renewal), so hybrid renewal costs
        # ¥200 + ¥79.20 = ¥279.20 (¥81.20 MORE expensive than pure PayG!). Must NOT recommend hybrid!
        turbo_mcp = mcp_server.calculate_api_budget(
            model_query="aliyun-bailian/qwen-turbo",
            daily_requests=5000,
            avg_input_tokens=4000,
            avg_output_tokens=1000,
            cache_hit_rate=0.5,
            usage_mode="interactive_ide",
        )
        turbo_eval = turbo_mcp["coding_plan_evaluation"]
        self.assertIsNone(turbo_eval.get("recommended_overflow_hybrid_plan_id"))
        turbo_aliyun = next(p for p in turbo_eval["eligible_subscriptions"] if p["plan_id"] == "aliyun-coding-plan")
        self.assertAlmostEqual(turbo_aliyun["overflow_hybrid"]["renewal_total_rmb"], 279.20, places=2)
        self.assertAlmostEqual(turbo_aliyun["overflow_hybrid"]["renewal_saving_rmb"], -81.20, places=2)
        self.assertFalse(turbo_aliyun["overflow_hybrid"]["saves_on_renewal"])

        turbo_js = self._run_cloudflare_budget_js(
            "model_id=aliyun-bailian/qwen-turbo&daily_requests=5000"
            "&avg_input_tokens=4000&avg_output_tokens=1000&cache_hit_rate=0.5&usage_mode=interactive_ide"
        )
        self.assertIsNone(turbo_js.get("recommended_overflow_hybrid_plan_id"))

    def test_02_fallback_models_doubao_parity_and_coze_openapi_live_schema(self) -> None:
        live_doubao = next(
            m for m in fetch_and_enrich.DOMESTIC_CN_PROVIDERS if m["id"] == "volcengine/doubao-seed-2.0-pro"
        )
        site_doubao = next(
            (m for m in build_site.FALLBACK_MODELS if m["id"] == "volcengine/doubao-seed-2.0-pro"),
            None,
        )
        self.assertIsNotNone(site_doubao)
        self.assertAlmostEqual(site_doubao["input_rmb_per_1m"], live_doubao["input_rmb_per_1m"], places=4)
        self.assertAlmostEqual(site_doubao["output_rmb_per_1m"], live_doubao["output_rmb_per_1m"], places=4)
        self.assertEqual(site_doubao.get("api_model_id"), live_doubao["api_model_id"])

        coze_doubao = next(
            (m for m in coze_cloud_tool.FALLBACK_CATALOG["models"] if m["id"] == "volcengine/doubao-seed-2.0-pro"),
            None,
        )
        self.assertIsNotNone(coze_doubao)
        self.assertAlmostEqual(coze_doubao["input_rmb_per_1m"], live_doubao["input_rmb_per_1m"], places=4)
        self.assertAlmostEqual(coze_doubao["output_rmb_per_1m"], live_doubao["output_rmb_per_1m"], places=4)
        self.assertEqual(coze_doubao.get("api_model_id"), live_doubao["api_model_id"])

        # Public `/api/openapi.json` (`openapi_coze_live.json`) schema parity
        spec_path = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle" / "openapi_coze_live.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        live_props = (
            spec["paths"]["/api/models_live.json"]["get"]["responses"]["200"]["content"]["application/json"]["schema"][
                "properties"
            ]
        )
        self.assertIn("price_changes", live_props)
        self.assertIn("official_rule_audit", live_props)

        budget_resp_props = (
            spec["paths"]["/api/budget"]["get"]["responses"]["200"]["content"]["application/json"]["schema"][
                "properties"
            ]
        )
        for field in (
            "cache_hit_rate",
            "effective_reasoning_multiplier",
            "recommended_same_family_plan_id",
            "recommended_overflow_hybrid_plan_id",
            "coding_plans",
            "last_live_verified_at",
        ):
            self.assertIn(field, budget_resp_props, msg=f"Missing {field} in openapi_coze_live.json /api/budget")

    def test_03_official_coding_plan_doc_fingerprint_audit_and_drift_atom_alert(self) -> None:
        # 1. Healthy Aliyun SSR HTML + Tencent CSR shell -> verified_markers + csr_shell_manual_check, 0 warnings
        healthy_aliyun_html = (
            "<html><body><h1>阿里云百炼 Coding Plan 套餐规则</h1>"
            "<p>" + ("套餐说明与计费细则。" * 45) + "</p>"
            "<table><tr><td>Lite 基础版（已停新购）</td><td>40</td></tr>"
            "<tr><td>Pro 高级版</td><td>新客首月 39.9 元，续费 200 元/月，每月上限 90,000 次调用</td></tr></table>"
            "</body></html>"
        )
        csr_tencent_html = "<html><head><title>腾讯云文档</title></head><body><div id='app'></div></body></html>"

        def mock_healthy_fetch(url: str) -> str:
            if "aliyun.com" in url:
                return healthy_aliyun_html
            return csr_tencent_html

        audit_ok = fetch_and_enrich.audit_official_coding_plan_docs(
            checked_at="2026-11-15T04:00:00Z",
            fetcher=mock_healthy_fetch,
        )
        self.assertEqual(audit_ok["checked_at"], "2026-11-15T04:00:00Z")
        self.assertEqual(audit_ok["drift_warnings"], [])
        by_id_ok = {v["plan_id"]: v for v in audit_ok["vendors"]}
        self.assertEqual(by_id_ok["aliyun-coding-plan"]["status"], "verified_markers")
        self.assertEqual(by_id_ok["tencent-coding-plan"]["status"], "csr_shell_manual_check")

        # 2. Mutated Aliyun SSR HTML (monthly cap changed from 90,000 -> 60,000 and 39.9 promo removed)
        #    -> marker_drift_detected + automatic `plan_rule_drift_warning` in `models_live.json` & Atom feed!
        drifted_aliyun_html = (
            "<html><body><h1>阿里云百炼 Coding Plan 套餐规则</h1>"
            "<p>" + ("套餐说明与计费细则。" * 45) + "</p>"
            "<table><tr><td>Pro 高级版</td><td>目录价 200 元/月，每月上限 60,000 次调用</td></tr></table>"
            "</body></html>"
        )

        def mock_drifted_fetch(url: str) -> str:
            if "aliyun.com" in url:
                return drifted_aliyun_html
            return csr_tencent_html

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_models = tmp_root / "models_live.json"
            tmp_dist = tmp_root / "dist"
            seed = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
            tmp_models.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

            with (
                mock.patch.object(
                    fetch_and_enrich,
                    "fetch_openrouter_raw",
                    return_value=(fetch_and_enrich.FALLBACK_OPENROUTER_RAW, "fallback_snapshot+curated_cn_2026"),
                ),
                mock.patch.object(
                    fetch_and_enrich,
                    "_fetch_doc_html_for_audit",
                    side_effect=mock_drifted_fetch,
                ),
            ):
                refreshed = fetch_and_enrich.refresh_models_live(output_path=tmp_models)

            self.assertIn("official_rule_audit", refreshed)
            aliyun_audit = next(
                v for v in refreshed["official_rule_audit"]["vendors"] if v["plan_id"] == "aliyun-coding-plan"
            )
            self.assertEqual(aliyun_audit["status"], "marker_drift_detected")
            drift_deltas = [
                c for c in refreshed["price_changes"] if c.get("change_type") == "plan_rule_drift_warning"
            ]
            self.assertEqual(len(drift_deltas), 1)
            self.assertEqual(drift_deltas[0]["id"], "aliyun-coding-plan")

            build_site.build_site(output_dir=tmp_dist, models_path=tmp_models)
            dist_catalog = json.loads((tmp_dist / "api" / "models_live.json").read_text(encoding="utf-8"))
            self.assertIn("official_rule_audit", dist_catalog)

            atom_xml = (tmp_dist / "feeds" / "price-changes.xml").read_text(encoding="utf-8")
            root = ET.fromstring(atom_xml)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            titles = [el.text or "" for el in root.findall("atom:entry/atom:title", ns)]
            self.assertTrue(
                any("规则巡检预警" in t and "aliyun-coding-plan" in t for t in titles),
                msg=f"Expected drift alert entry in Atom feed, got titles: {titles}",
            )


class Round4Batch2WebOverflowCompareAndRelTests(unittest.TestCase):
    def test_04_ssr_and_client_honest_rel_sponsored_qualification(self) -> None:
        from html.parser import HTMLParser

        class LinkCollector(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.links: list[dict[str, str]] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag == "a":
                    self.links.append({k: (v or "") for k, v in attrs})

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dist = Path(tmpdir)
            build_site.build_site(output_dir=tmp_dist)
            html_doc = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        parser = LinkCollector()
        parser.feed(html_doc)

        # Uncompensated direct vendor links in SSR tables must NEVER carry `sponsored`
        uncompensated_ssr = [
            a
            for a in parser.links
            if any(host in a.get("href", "") for host in ("volcengine.com", "openrouter.ai", "runpod.io"))
            and "?" not in a.get("href", "")
        ]
        self.assertGreaterEqual(len(uncompensated_ssr), 5)
        for a in uncompensated_ssr:
            self.assertNotIn(
                "sponsored",
                a.get("rel", "").split(),
                msg=f"Uncompensated link falsely marked sponsored in SSR HTML: {a}",
            )

        # Compensated partner links in SSR tables MUST carry `sponsored`
        compensated_ssr = [
            a
            for a in parser.links
            if any(tok in a.get("href", "") for tok in ("userCode=", "curl.qcloud.com", "siliconflow.cn/i/"))
        ]
        self.assertGreaterEqual(len(compensated_ssr), 5)
        for a in compensated_ssr:
            self.assertIn(
                "sponsored",
                a.get("rel", "").split(),
                msg=f"Affiliate link missing rel=sponsored in SSR HTML: {a}",
            )

        # Client JS template must use `relAttr(` helper instead of hardcoding `rel="noopener sponsored"` on plan/model cards
        self.assertIn("function isSponsoredUrl(", html_doc)
        self.assertIn("function relAttr(", html_doc)

    def test_05_web_over_cap_hybrid_verdict_and_model_compare_tray(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dist = Path(tmpdir)
            build_site.build_site(output_dir=tmp_dist)
            html_doc = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        # 1. Over-cap hybrid recommendation in client evaluator & primary recommendation card
        self.assertIn("overflowHybridWins", html_doc)
        self.assertIn("savesOnRenewal", html_doc)

        # 2. Interactive 3-model side-by-side compare tray + `?cmp=` URL state serialization/restoration
        self.assertIn('id="compareTray"', html_doc)
        self.assertIn("data-toggle-compare", html_doc)
        self.assertIn('id="clearCompareBtn"', html_doc)
        self.assertIn('params.set("cmp"', html_doc)
        self.assertIn('params.has("cmp")', html_doc)
        self.assertIn("Side-by-Side Workload Comparison", html_doc)

        # 3. Release pipeline & CI registration for Round 4 test suite
        prep_src = (ROOT / "cloudflare" / "prepare_release.py").read_text(encoding="utf-8")
        ci_src = (ROOT / "cloudflare" / "daily_refresh.yml").read_text(encoding="utf-8")
        self.assertIn("test_round4_product_iteration.py", prep_src)
        self.assertIn("test_round4_product_iteration", ci_src)
        sync_path = ROOT / "sync_config_to_cloud.sh"
        if sync_path.exists():
            self.assertIn("test_round4_product_iteration", sync_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
