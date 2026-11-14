#!/usr/bin/env python3
"""
Round 5 (v3.5) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. Gzip/deflate decompression in `_fetch_doc_html_for_audit` (unlocking Tencent Cloud SSR rule
       verification) + Volcengine sidebar-only CSR guard + expanded Tencent Lite/Pro marker audit.
    2. Multi-developer Team Seat (`team_size = 1..50`) procurement math & multi-seat overflow hybrid
       parity across `pricing_core.py`, `mcp_server.py` (Python + HTTP), `functions/api/budget.js`,
       and `coze_cloud_tool.py`, including over-subscription safeguard and HTTP 400 validation.
    3. Schema & bundle parity across `MCP_TOOLS_SPEC`, `openapi_coze.json`, `openapi_coze_live.json`,
       `.actor/input_schema.json`, `apify_store_bundle`, and 6th bilingual FAQ entry.
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tempfile
import unittest
from unittest import mock
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle"))
sys.path.insert(0, str(ROOT / "engine_b_affiliate_web"))
sys.path.insert(0, str(ROOT / "cloudflare"))

import build_site  # noqa: E402
import coze_cloud_tool  # noqa: E402
import fetch_and_enrich  # noqa: E402
import mcp_server  # noqa: E402


class Round5Batch1GzipAuditTeamSeatsAndSchemaTests(unittest.TestCase):
    def _run_cloudflare_budget_cases(self, cases: list[dict[str, str]]) -> list[dict]:
        runner = """
import fs from "node:fs";
const source = fs.readFileSync("functions/api/budget.js", "utf8");
const {onRequestGet} = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const {catalog, cases} = JSON.parse(fs.readFileSync(0, "utf8"));
const outputs = [];
for (const query of cases) {
  const request = new Request("https://example.test/api/budget?" + new URLSearchParams(query));
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

    def test_01_gzip_decompression_in_official_doc_audit_and_sidebar_csr_guard(self) -> None:
        tencent_ssr_html = (
            "<html><body><h1>腾讯云 Coding Plan 套餐说明</h1>"
            "<p>" + ("编程助手套餐计费与调用次数额度规则。" * 35) + "</p>"
            "<table>"
            "<tr><td>Lite</td><td>40 元/月，每 5 小时 1,200 次，每月上限 18,000 次请求次数</td></tr>"
            "<tr><td>Pro</td><td>200 元/月，每 5 小时 6,000 次，每月上限 90,000 次请求次数</td></tr>"
            "</table></body></html>"
        )
        gz_payload = gzip.compress(tencent_ssr_html.encode("utf-8"))

        class FakeGzipHTTPResponse(io.BytesIO):
            def __init__(self, raw_bytes: bytes, encoding_header: str = "gzip") -> None:
                super().__init__(raw_bytes)
                self.headers = {"Content-Encoding": encoding_header}

            def __enter__(self) -> "FakeGzipHTTPResponse":
                return self

            def __exit__(self, *args: object) -> None:
                self.close()

        with mock.patch("urllib.request.urlopen", return_value=FakeGzipHTTPResponse(gz_payload, "gzip")):
            decoded = fetch_and_enrich._fetch_doc_html_for_audit("https://cloud.tencent.com/document/product/1823/130092")
        self.assertIn("90,000", decoded)
        self.assertIn("18,000", decoded)

        # Also verify magic-header (\x1f\x8b) gzip detection even if Content-Encoding header is omitted
        with mock.patch("urllib.request.urlopen", return_value=FakeGzipHTTPResponse(gz_payload, "")):
            decoded_magic = fetch_and_enrich._fetch_doc_html_for_audit("https://cloud.tencent.com/document/product/1823/130092")
        self.assertIn("90,000", decoded_magic)

        healthy_aliyun_html = (
            "<html><body><h1>阿里云百炼 Coding Plan 套餐规则</h1>"
            "<p>" + ("套餐说明与计费细则。" * 45) + "</p>"
            "<table><tr><td>Lite 基础版（已停新购）</td><td>40</td></tr>"
            "<tr><td>Pro 高级版</td><td>新客首月 39.9 元，续费 200 元/月，每月上限 90,000 次调用</td></tr></table>"
            "</body></html>"
        )
        healthy_volc_ssr_html = (
            "<html><body><h1>火山方舟 Coding Plan 个人版 套餐概览</h1>"
            "<p>" + ("方舟 Coding Plan 为开发者量身定制订阅服务，提供 Lite 套餐 与 Pro 套餐。" * 25) + "</p>"
            "<p>每5小时限额：根据首次请求发生时间定时刷新。周限额与月限额自动重置。套餐额度不可用于 API 调用。</p>"
            "<p>务必使用 Base URL：https://ark.cn-beijing.volces.com/api/coding/v3 或 https://ark.cn-beijing.volces.com/api/coding</p>"
            "</body></html>"
        )
        # Pure sidebar CSR shell (no 5h/weekly/monthly cap or coding endpoint body) must NOT trigger false drift
        pure_csr_shell_html = (
            "<html><body><nav>"
            + ("Coding Plan Doubao-Seed-2.0-Pro 免费额度 模型调用 计费说明 火山方舟文档导航目录 " * 25)
            + "</nav><div id='root'></div></body></html>"
        )

        def mock_three_vendors(url: str) -> str:
            if "aliyun.com" in url:
                return healthy_aliyun_html
            if "cloud.tencent.com" in url:
                return tencent_ssr_html
            return healthy_volc_ssr_html

        audit = fetch_and_enrich.audit_official_coding_plan_docs(
            checked_at="2026-11-15T05:00:00Z",
            fetcher=mock_three_vendors,
        )
        self.assertEqual(audit["drift_warnings"], [])
        by_id = {v["plan_id"]: v for v in audit["vendors"]}
        self.assertEqual(by_id["aliyun-coding-plan"]["status"], "verified_markers")
        self.assertEqual(by_id["tencent-coding-plan"]["status"], "verified_markers")
        self.assertIn("lite_monthly_cap_18k", by_id["tencent-coding-plan"]["matched_groups"])
        self.assertIn("lite_renewal_40", by_id["tencent-coding-plan"]["matched_groups"])
        self.assertEqual(by_id["volcengine-coding-plan"]["status"], "verified_markers")
        self.assertIn("dedicated_coding_endpoint", by_id["volcengine-coding-plan"]["matched_groups"])

        # Verify pure CSR shell without rule body returns csr_shell_manual_check (0 false alarms)
        audit_csr = fetch_and_enrich.audit_official_coding_plan_docs(
            checked_at="2026-11-15T05:02:00Z",
            fetcher=lambda _u: pure_csr_shell_html,
        )
        self.assertEqual(audit_csr["drift_warnings"], [])
        self.assertTrue(all(v["status"] == "csr_shell_manual_check" for v in audit_csr["vendors"]))

        # Verify Volcengine OpenAI-compatible dedicated Coding Plan endpoint (/api/coding/v3) from official doc
        import pricing_core

        volc_oai = pricing_core.get_client_endpoint_config(
            vendor_or_plan="volcengine-coding-plan",
            client_type="openai_compat",
            billing_mode="coding_plan",
        )
        self.assertTrue(volc_oai["verified"])
        self.assertEqual(volc_oai["base_url"], "https://ark.cn-beijing.volces.com/api/coding/v3")

        # Verify Tencent Lite cap drift is caught when 18,000 changes to 12,000
        drifted_tencent_html = tencent_ssr_html.replace("18,000", "12,000")
        audit_drift = fetch_and_enrich.audit_official_coding_plan_docs(
            checked_at="2026-11-15T05:05:00Z",
            fetcher=lambda u: drifted_tencent_html if "cloud.tencent.com" in u else pure_csr_shell_html,
        )
        by_id_drift = {v["plan_id"]: v for v in audit_drift["vendors"]}
        self.assertEqual(by_id_drift["tencent-coding-plan"]["status"], "marker_drift_detected")
        self.assertIn("lite_monthly_cap_18k", by_id_drift["tencent-coding-plan"]["missing_groups"])

    def test_02_team_multi_seat_math_parity_across_python_mcp_cloudflare_and_coze(self) -> None:
        # Case A: 5-developer team, 6,000 calls/day total = 180,000 calls/mo (36,000/mo per seat)
        # on `aliyun-bailian/qwen3-coder-next` (4k in / 1k out, 50% cache -> Team PayG = ¥1,382.40/mo).
        # 5 × Aliyun Pro covers 450,000 calls/mo; 1st mo = 5 × ¥39.90 = ¥199.50 (saves ¥1,182.90),
        # renewal = 5 × ¥200 = ¥1,000.00/mo (saves ¥382.40/mo vs PayG!).
        mcp_res = mcp_server.calculate_api_budget(
            model_query="aliyun-bailian/qwen3-coder-next",
            daily_requests=6000,
            avg_input_tokens=4000,
            avg_output_tokens=1000,
            cache_hit_rate=0.5,
            usage_mode="interactive_ide",
            team_size=5,
        )
        self.assertEqual(mcp_res["query"]["team_size"], 5)
        self.assertAlmostEqual(mcp_res["budget_estimate"]["monthly_rmb"], 1382.40, places=2)
        py_eval = mcp_res["coding_plan_evaluation"]
        self.assertEqual(py_eval["team_size"], 5)
        self.assertEqual(py_eval["per_seat_monthly_calls"], 36000)
        self.assertEqual(py_eval["recommended_same_family_plan_id"], "aliyun-coding-plan")
        py_ali = next(p for p in py_eval["eligible_subscriptions"] if p["plan_id"] == "aliyun-coding-plan")
        self.assertEqual(py_ali["status"], "recommended_even_on_renewal")
        self.assertEqual(py_ali["seats_count"], 5)
        self.assertAlmostEqual(py_ali["first_month_rmb"], 199.50, places=2)
        self.assertAlmostEqual(py_ali["renewal_rmb"], 1000.00, places=2)
        self.assertAlmostEqual(py_ali["first_month_savings_rmb"], 1182.90, places=2)
        self.assertAlmostEqual(py_ali["renewal_savings_rmb"], 382.40, places=2)

        # Verify MCP HTTP server GET /api/budget?team_size=5 passes team_size through
        mcp_server.ModelRouterHTTPHandler.enable_x402 = False
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), mcp_server.ModelRouterHTTPHandler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            url = (
                f"http://127.0.0.1:{port}/api/budget?"
                "model_id=aliyun-bailian/qwen3-coder-next&daily_requests=6000"
                "&avg_input_tokens=4000&avg_output_tokens=1000&cache_hit_rate=0.5&team_size=5"
            )
            with urllib.request.urlopen(url, timeout=5) as resp:
                http_budget = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(http_budget["coding_plan_evaluation"]["team_size"], 5)
            self.assertEqual(
                http_budget["coding_plan_evaluation"]["recommended_same_family_plan_id"],
                "aliyun-coding-plan",
            )
        finally:
            httpd.shutdown()
            httpd.server_close()

        # Coze cloud tool parity (Case A)
        coze_res = coze_cloud_tool.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "aliyun-bailian/qwen3-coder-next",
                "daily_requests": 6000,
                "avg_input_tokens": 4000,
                "avg_output_tokens": 1000,
                "cache_hit_rate": 0.5,
                "usage_mode": "interactive_ide",
                "team_size": 5,
            }
        )
        coze_eval = coze_res["coding_plan_evaluation"]
        self.assertEqual(coze_eval["team_size"], 5)
        self.assertEqual(coze_eval["recommended_same_family_plan_id"], "aliyun-coding-plan")
        coze_ali = next(p for p in coze_eval["eligible_subscriptions"] if p["plan_id"] == "aliyun-coding-plan")
        self.assertAlmostEqual(coze_ali["renewal_rmb"], 1000.00, places=2)
        self.assertAlmostEqual(coze_ali["renewal_savings_rmb"], 382.40, places=2)
        self.assertIn("seats=5", coze_res["web_calculator_url"])

        # Case B (low-volume safeguard: 2,000 calls/day across 5 devs -> PayG ¥460.80 < ¥1,000 renewal)
        # + Case C (multi-seat overflow hybrid: 2 devs, 8,000 calls/day = 240k/mo > 180k combined Pro cap)
        # + Case D (invalid team_size values -> HTTP 400)
        js_outputs = self._run_cloudflare_budget_cases(
            [
                {
                    "model_id": "aliyun-bailian/qwen3-coder-next",
                    "daily_requests": "6000",
                    "avg_input_tokens": "4000",
                    "avg_output_tokens": "1000",
                    "cache_hit_rate": "0.5",
                    "usage_mode": "interactive_ide",
                    "team_size": "5",
                },
                {
                    "model_id": "aliyun-bailian/qwen3-coder-next",
                    "daily_requests": "2000",
                    "avg_input_tokens": "4000",
                    "avg_output_tokens": "1000",
                    "cache_hit_rate": "0.5",
                    "usage_mode": "interactive_ide",
                    "team_size": "5",
                },
                {
                    "model_id": "aliyun-bailian/qwen3-coder-next",
                    "daily_requests": "8000",
                    "avg_input_tokens": "4000",
                    "avg_output_tokens": "1000",
                    "cache_hit_rate": "0.5",
                    "usage_mode": "interactive_ide",
                    "team_size": "2",
                },
                {"model_id": "aliyun-bailian/qwen3-coder-next", "team_size": "0"},
                {"model_id": "aliyun-bailian/qwen3-coder-next", "team_size": "51"},
                {"model_id": "aliyun-bailian/qwen3-coder-next", "team_size": "2.5"},
            ]
        )
        self.assertEqual([o["status"] for o in js_outputs], [200, 200, 200, 400, 400, 400])

        # Cloudflare Case A assertions
        js_a = js_outputs[0]["body"]
        self.assertEqual(js_a["team_size"], 5)
        self.assertEqual(js_a["per_seat_monthly_requests"], 36000)
        self.assertEqual(js_a["recommended_same_family_plan_id"], "aliyun-coding-plan")
        self.assertIn("seats=5", js_a["web_calculator_url"])
        js_a_ali_pro = next(
            t for t in next(p for p in js_a["coding_plans"] if p["id"] == "aliyun-coding-plan")["tiers"] if t["tier_id"] == "pro"
        )
        self.assertAlmostEqual(js_a_ali_pro["estimated_first_month_saving_rmb"], 1182.90, places=2)
        self.assertAlmostEqual(js_a_ali_pro["estimated_renewal_saving_rmb"], 382.40, places=2)

        # Case B assertions across Python, Coze, and Cloudflare (must NOT recommend 5x Pro on renewal!)
        mcp_b = mcp_server.calculate_api_budget(
            model_query="aliyun-bailian/qwen3-coder-next",
            daily_requests=2000,
            avg_input_tokens=4000,
            avg_output_tokens=1000,
            cache_hit_rate=0.5,
            team_size=5,
        )
        self.assertIsNone(mcp_b["coding_plan_evaluation"]["recommended_same_family_plan_id"])
        coze_b = coze_cloud_tool.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "aliyun-bailian/qwen3-coder-next",
                "daily_requests": 2000,
                "avg_input_tokens": 4000,
                "avg_output_tokens": 1000,
                "cache_hit_rate": 0.5,
                "team_size": 5,
            }
        )
        self.assertIsNone(coze_b["coding_plan_evaluation"]["recommended_same_family_plan_id"])
        self.assertIsNone(js_outputs[1]["body"]["recommended_same_family_plan_id"])

        # Case C assertions across Python, Coze, and Cloudflare (2x Pro covers 180k + 60k overflow PayG)
        mcp_c = mcp_server.calculate_api_budget(
            model_query="aliyun-bailian/qwen3-coder-next",
            daily_requests=8000,
            avg_input_tokens=4000,
            avg_output_tokens=1000,
            cache_hit_rate=0.5,
            team_size=2,
        )
        hyb_py = next(
            p for p in mcp_c["coding_plan_evaluation"]["eligible_subscriptions"] if p["plan_id"] == "aliyun-coding-plan"
        )["overflow_hybrid"]
        self.assertEqual(mcp_c["coding_plan_evaluation"]["recommended_overflow_hybrid_plan_id"], "aliyun-coding-plan")
        self.assertEqual(hyb_py["covered_calls"], 180000)
        self.assertEqual(hyb_py["overflow_calls"], 60000)
        self.assertAlmostEqual(hyb_py["first_month_plan_rmb"], 79.80, places=2)
        self.assertAlmostEqual(hyb_py["renewal_plan_rmb"], 400.00, places=2)
        self.assertAlmostEqual(hyb_py["overflow_payg_rmb"], 460.80, places=2)
        self.assertAlmostEqual(hyb_py["renewal_total_rmb"], 860.80, places=2)
        self.assertAlmostEqual(hyb_py["renewal_saving_rmb"], 982.40, places=2)

        js_c = js_outputs[2]["body"]
        self.assertEqual(js_c["recommended_overflow_hybrid_plan_id"], "aliyun-coding-plan")
        hyb_js = next(p for p in js_c["coding_plans"] if p["id"] == "aliyun-coding-plan")["overflow_hybrid"]
        self.assertEqual(hyb_js["covered_calls"], 180000)
        self.assertAlmostEqual(hyb_js["renewal_total_rmb"], 860.80, places=2)
        self.assertAlmostEqual(hyb_js["renewal_saving_rmb"], 982.40, places=2)

    def test_03_openapi_mcp_apify_and_faq_v35_parity(self) -> None:
        # 1. MCP tool inputSchema includes `team_size`
        budget_tool = next(t for t in mcp_server.MCP_TOOLS_SPEC if t["name"] == "calculate_api_budget")
        self.assertIn("team_size", budget_tool["inputSchema"]["properties"])

        # 2. Engine A `openapi_coze.json` includes `team_size` + `coding_plan_evaluation` & `self_host_evaluation`
        oa_engine_a = json.loads((ROOT / "engine_a_mcp_actor" / "openapi_coze.json").read_text(encoding="utf-8"))
        req_props = oa_engine_a["paths"]["/api/budget"]["post"]["requestBody"]["content"]["application/json"]["schema"][
            "properties"
        ]
        self.assertIn("team_size", req_props)
        resp_props = oa_engine_a["paths"]["/api/budget"]["post"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["properties"]
        self.assertIn("coding_plan_evaluation", resp_props)
        self.assertIn("self_host_evaluation", resp_props)

        # 3. Apify `.actor/input_schema.json` includes `team_size` & `cache_hit_rate`
        actor_schema = json.loads((ROOT / "engine_a_mcp_actor" / ".actor" / "input_schema.json").read_text(encoding="utf-8"))
        self.assertIn("team_size", actor_schema["properties"])
        self.assertIn("cache_hit_rate", actor_schema["properties"])

        # 4. Public `/api/openapi.json` (`openapi_coze_live.json`) includes `team_size` param & response field
        oa_live = json.loads(
            (ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle" / "openapi_coze_live.json").read_text(
                encoding="utf-8"
            )
        )
        live_param_names = [p["name"] for p in oa_live["paths"]["/api/budget"]["get"]["parameters"]]
        self.assertIn("team_size", live_param_names)
        live_resp_props = oa_live["paths"]["/api/budget"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["properties"]
        self.assertIn("team_size", live_resp_props)

        # 5. Standalone `apify_store_bundle` parity when present
        apify_bundle = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "apify_store_bundle"
        if apify_bundle.is_dir():
            with tempfile.TemporaryDirectory() as tmp:
                isolated = Path(tmp) / "apify_store_bundle"
                shutil.copytree(apify_bundle, isolated)
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import mcp_server; "
                            "r = mcp_server.calculate_api_budget("
                            "model_query='aliyun-bailian/qwen3-coder-next', daily_requests=6000, "
                            "avg_input_tokens=4000, avg_output_tokens=1000, cache_hit_rate=0.5, team_size=5); "
                            "assert r['coding_plan_evaluation']['recommended_same_family_plan_id'] == 'aliyun-coding-plan', r"
                        ),
                    ],
                    cwd=str(isolated),
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(proc.returncode, 0, msg=f"apify_store_bundle out of sync: {proc.stderr}")

        # 6. Bilingual FAQ expanded to >= 6 entries covering team seat / hybrid overflow procurement
        self.assertGreaterEqual(len(build_site.FAQ_ENTRIES), 6)
        for entry in build_site.FAQ_ENTRIES:
            for key in ("q", "a", "q_en", "a_en"):
                self.assertTrue(str(entry.get(key) or "").strip(), f"Empty FAQ field {key}")
        self.assertTrue(
            any("团队" in e["q"] or "多人" in e["q"] or "席位" in e["a"] for e in build_site.FAQ_ENTRIES),
            "Expected bilingual FAQ entry covering multi-developer team seat / hybrid procurement",
        )


class Round5Batch2WebTeamSeatsMarkdownAndPresetTests(unittest.TestCase):
    def test_04_web_team_size_control_seats_query_and_markdown_procurement_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dist = Path(tmpdir)
            build_site.build_site(output_dir=tmp_dist)
            html_doc = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        # 1. Team IDE seat count control (`#teamSizeInput`) + bilingual i18n
        self.assertIn('id="teamSizeInput"', html_doc)
        self.assertIn('data-i18n="labelTeamSize"', html_doc)
        self.assertIn("Developer Seats", html_doc)

        # 2. Shareable `?seats=` query param serialization & restoration
        self.assertIn("teamSize:", html_doc)
        self.assertIn('params.set("seats"', html_doc)
        self.assertIn('params.has("seats")', html_doc)

        # 3. 1-click GFM Markdown procurement table button & generator + telemetry
        self.assertIn('id="copyMarkdownBtn"', html_doc)
        self.assertIn("function buildMarkdownProcurementTable(", html_doc)
        self.assertIn('slot_id: "markdown_table"', html_doc)
        self.assertIn("Copy Markdown Table", html_doc)

    def test_05_deepseek_vs_qwen_preset_compare_ids_and_ci_registration(self) -> None:
        import re

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dist = Path(tmpdir)
            build_site.build_site(output_dir=tmp_dist)
            dq_html = (tmp_dist / "deepseek-vs-qwen" / "index.html").read_text(encoding="utf-8")
            cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        m_dq = re.search(r'<script id="app-data" type="application/json">(.*?)</script>', dq_html, re.DOTALL)
        self.assertIsNotNone(m_dq)
        dq_data = json.loads(m_dq.group(1))
        self.assertEqual(
            dq_data["page_preset"].get("compareIds"),
            [
                "tencent-cloud/deepseek-r1",
                "aliyun-bailian/qwen3.5-plus",
                "aliyun-bailian/qwen3-coder-next",
            ],
        )

        m_cp = re.search(r'<script id="app-data" type="application/json">(.*?)</script>', cp_html, re.DOTALL)
        self.assertIsNotNone(m_cp)
        cp_data = json.loads(m_cp.group(1))
        self.assertFalse(cp_data["page_preset"].get("compareIds"))

        self.assertIn("Array.isArray(PAGE_PRESET.compareIds)", dq_html)

        # Release pipeline, remote verifier & CI registration for Round 5
        prep_src = (ROOT / "cloudflare" / "prepare_release.py").read_text(encoding="utf-8")
        ci_src = (ROOT / "cloudflare" / "daily_refresh.yml").read_text(encoding="utf-8")
        ver_src = (ROOT / "cloudflare" / "verify_release.py").read_text(encoding="utf-8")
        self.assertIn("test_round5_product_iteration.py", prep_src)
        self.assertIn("test_round5_product_iteration", ci_src)
        self.assertIn("team_size=5", ver_src)
        sync_path = ROOT / "sync_config_to_cloud.sh"
        if sync_path.exists():
            self.assertIn("test_round5_product_iteration", sync_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
