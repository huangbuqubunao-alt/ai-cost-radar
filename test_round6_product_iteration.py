#!/usr/bin/env python3
"""
Round 6 (v3.6) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. `pricing_core.parse_usage_log_snippet` across Claude Code `/cost` (Anthropic additive cache_read),
       OpenAI/DeepSeek/Bailian `usage` JSON (subset cached_tokens + automatic `reasoning_tokens` double-count
       guard), and Chinese cloud console summaries (with `days_observed` extrapolation & call estimation).
    2. Monthly bill totals (`monthly_requests`, `monthly_input_m`, `monthly_output_m`, `cached_input_m`) and
       `usage_snippet` cross-surface math parity across `mcp_server.py` (Python + HTTP), Cloudflare
       `functions/api/budget.js` (incl. HTTP 400 validation), `coze_cloud_tool.py`, and OpenAPI/MCP/Apify schemas.
    3. `fetch_and_enrich.audit_official_coding_plan_docs(..., prior_audit=...)` `last_verified_at` &
       `last_verified_groups` preservation across overseas CSR shell / transient network degradation while
       still firing immediate `marker_drift_detected` warnings on real rule changes.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle"))
sys.path.insert(0, str(ROOT / "engine_b_affiliate_web"))
sys.path.insert(0, str(ROOT / "cloudflare"))

import build_site  # noqa: E402
import coze_cloud_tool  # noqa: E402
import events_reconcile  # noqa: E402
import fetch_and_enrich  # noqa: E402
import mcp_server  # noqa: E402
import prepare_release  # noqa: E402
import pricing_core  # noqa: E402


class Round6Batch1UsageImportAndAuditPersistenceTests(unittest.TestCase):
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

    def test_01_parse_usage_log_snippet_across_claude_cost_openai_json_and_cn_console(self) -> None:
        # 1. Claude Code `/cost` log: uncached Input + Cache read are additive!
        claude_cost_text = (
            "Total cost: $18.40\n"
            "Total duration (API): 42m 12s\n"
            "Input: 1.6M tokens\n"
            "Cache read: 2.4M tokens\n"
            "Output: 600k tokens\n"
            "Requests: 1,200\n"
        )
        parsed_cc = pricing_core.parse_usage_log_snippet(claude_cost_text, days_observed=30.0)
        self.assertEqual(parsed_cc["total_input_tokens"], 4_000_000)
        self.assertEqual(parsed_cc["cached_input_tokens"], 2_400_000)
        self.assertEqual(parsed_cc["total_output_tokens"], 600_000)
        self.assertEqual(parsed_cc["daily_requests"], 40)
        self.assertEqual(parsed_cc["avg_input_tokens"], 3333)
        self.assertEqual(parsed_cc["avg_output_tokens"], 500)
        self.assertAlmostEqual(parsed_cc["cache_hit_rate"], 0.60, places=4)
        self.assertFalse(parsed_cc["calls_estimated"])
        self.assertFalse(parsed_cc["output_includes_reasoning"])

        # 2. OpenAI / DeepSeek / Bailian JSON: `cached_tokens` is a subset of `prompt_tokens`,
        #    and `reasoning_tokens` inside `completion_tokens_details` triggers `output_includes_reasoning=True`!
        oai_json = json.dumps(
            {
                "requests": 90000,
                "prompt_tokens": 360_000_000,
                "prompt_tokens_details": {"cached_tokens": 180_000_000},
                "completion_tokens": 90_000_000,
                "completion_tokens_details": {"reasoning_tokens": 54_000_000},
            }
        )
        parsed_oai = pricing_core.parse_usage_log_snippet(oai_json, days_observed=30.0)
        self.assertEqual(parsed_oai["daily_requests"], 3000)
        self.assertEqual(parsed_oai["avg_input_tokens"], 4000)
        self.assertEqual(parsed_oai["avg_output_tokens"], 1000)
        self.assertAlmostEqual(parsed_oai["cache_hit_rate"], 0.50, places=4)
        self.assertTrue(parsed_oai["output_includes_reasoning"])
        self.assertFalse(parsed_oai["calls_estimated"])

        # 3. Chinese 7-day cloud console summary without explicit request count -> extrapolates to daily & estimates calls
        cn_7d = "近7天统计：输入 Token 28M（缓存命中 14M），输出 Token 7M"
        parsed_cn = pricing_core.parse_usage_log_snippet(cn_7d, days_observed=7.0)
        self.assertEqual(parsed_cn["daily_requests"], 1000)
        self.assertEqual(parsed_cn["avg_input_tokens"], 4000)
        self.assertEqual(parsed_cn["avg_output_tokens"], 1000)
        self.assertAlmostEqual(parsed_cn["cache_hit_rate"], 0.50, places=4)
        self.assertTrue(parsed_cn["calls_estimated"])

        # 4. Unparseable garbage raises ValueError
        with self.assertRaises(ValueError):
            pricing_core.parse_usage_log_snippet("hello world no token metrics here")

    def test_02_monthly_totals_and_usage_snippet_parity_across_mcp_cloudflare_and_coze(self) -> None:
        # Case A: Monthly bill totals (`90,000` calls/mo, `360M` input w/ `216M` cached = 60% hit, `90M` output)
        # on `aliyun-bailian/qwen3-coder-next` (in=1.2, out=4.8, factor=0.2):
        # Input = 360 * (0.4 * 1.2 + 0.6 * 0.24) = 360 * 0.624 = ¥224.64
        # Output = 90 * 4.8 = ¥432.00 -> Total = ¥656.64/mo
        mcp_tot = mcp_server.calculate_api_budget(
            model_query="aliyun-bailian/qwen3-coder-next",
            monthly_requests=90000,
            monthly_input_m=360.0,
            monthly_output_m=90.0,
            cached_input_m=216.0,
        )
        self.assertAlmostEqual(mcp_tot["budget_estimate"]["monthly_rmb"], 656.64, places=2)
        self.assertAlmostEqual(mcp_tot["query"]["cache_hit_rate"], 0.60, places=4)
        self.assertEqual(mcp_tot["query"]["daily_requests"], 3000)
        self.assertEqual(mcp_tot["query"]["avg_input_tokens"], 4000)
        self.assertEqual(mcp_tot["query"]["avg_output_tokens"], 1000)
        self.assertIn("parsed_usage_summary", mcp_tot)

        # Case B: `usage_snippet` with OpenAI `reasoning_tokens` on `tencent-cloud/deepseek-r1`
        # even when `reasoning_multiplier=2.5` is passed, `output_includes_reasoning` auto-guards to `1.0x`!
        snippet = json.dumps(
            {
                "requests": 30000,
                "prompt_tokens": 120_000_000,
                "prompt_tokens_details": {"cached_tokens": 60_000_000},
                "completion_tokens": 30_000_000,
                "completion_tokens_details": {"reasoning_tokens": 18_000_000},
            }
        )
        mcp_snip = mcp_server.calculate_api_budget(
            model_query="tencent-cloud/deepseek-r1",
            usage_snippet=snippet,
            reasoning_multiplier=2.5,
        )
        self.assertTrue(mcp_snip["query"]["output_includes_reasoning"])
        self.assertAlmostEqual(mcp_snip["query"]["reasoning_multiplier"], 1.0, places=4)

        # HTTP GET `/api/budget` on `mcp_server.ModelRouterHTTPHandler`
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), mcp_server.ModelRouterHTTPHandler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            qs = urllib.parse.urlencode(
                {
                    "model_id": "aliyun-bailian/qwen3-coder-next",
                    "monthly_requests": "90000",
                    "monthly_input_m": "360",
                    "monthly_output_m": "90",
                    "cached_input_m": "216",
                }
            )
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/budget?{qs}", timeout=5) as resp:
                http_res = json.loads(resp.read().decode("utf-8"))
            self.assertAlmostEqual(http_res["budget_estimate"]["monthly_rmb"], 656.64, places=2)
        finally:
            httpd.shutdown()
            httpd.server_close()

        # Cloudflare Pages Function `functions/api/budget.js` parity + HTTP 400 validation
        cf_cases = self._run_cloudflare_budget_cases(
            [
                {
                    "model_id": "aliyun-bailian/qwen3-coder-next",
                    "monthly_requests": "90000",
                    "monthly_input_m": "360",
                    "monthly_output_m": "90",
                    "cached_input_m": "216",
                },
                {
                    "model_id": "tencent-cloud/deepseek-r1",
                    "usage_snippet": snippet,
                    "reasoning_multiplier": "2.5",
                },
                {
                    "model_id": "aliyun-bailian/qwen3-coder-next",
                    "monthly_requests": "0",
                    "monthly_input_m": "100",
                    "monthly_output_m": "20",
                },
                {
                    "model_id": "aliyun-bailian/qwen3-coder-next",
                    "usage_snippet": "not a valid log",
                },
            ]
        )
        self.assertEqual(cf_cases[0]["status"], 200)
        self.assertAlmostEqual(cf_cases[0]["body"]["monthly_rmb"], 656.64, places=2)
        self.assertAlmostEqual(cf_cases[0]["body"]["cache_hit_rate"], 0.60, places=4)
        self.assertEqual(cf_cases[1]["status"], 200)
        self.assertAlmostEqual(
            cf_cases[1]["body"]["monthly_rmb"],
            mcp_snip["budget_estimate"]["monthly_rmb"],
            places=2,
        )
        self.assertAlmostEqual(cf_cases[1]["body"]["effective_reasoning_multiplier"], 1.0, places=4)
        self.assertEqual(cf_cases[2]["status"], 400)
        self.assertEqual(cf_cases[3]["status"], 400)

        # Coze Cloud Tool parity
        coze_tot = coze_cloud_tool.handler(
            {
                "action": "budget",
                "model_query": "aliyun-bailian/qwen3-coder-next",
                "monthly_requests": 90000,
                "monthly_input_m": 360.0,
                "monthly_output_m": 90.0,
                "cached_input_m": 216.0,
            }
        )
        self.assertAlmostEqual(coze_tot["data"]["budget_estimate"]["monthly_rmb"], 656.64, places=2)

        coze_snip = coze_cloud_tool.handler(
            {
                "action": "budget",
                "model_query": "tencent-cloud/deepseek-r1",
                "usage_snippet": snippet,
                "reasoning_multiplier": 2.5,
            }
        )
        self.assertAlmostEqual(
            coze_snip["data"]["budget_estimate"]["monthly_rmb"],
            mcp_snip["budget_estimate"]["monthly_rmb"],
            places=2,
        )

        # Schema parity across MCP_TOOLS_SPEC, openapi_coze.json, openapi_coze_live.json, .actor/input_schema.json
        calc_tool = next(t for t in mcp_server.MCP_TOOLS_SPEC if t["name"] == "calculate_api_budget")
        for key in ("monthly_requests", "monthly_input_m", "monthly_output_m", "cached_input_m", "usage_snippet", "days_observed"):
            self.assertIn(key, calc_tool["inputSchema"]["properties"], f"Missing {key} in MCP_TOOLS_SPEC")

        openapi_local = json.loads((ROOT / "engine_a_mcp_actor" / "openapi_coze.json").read_text(encoding="utf-8"))
        budget_post_props = (
            openapi_local["paths"]["/api/budget"]["post"]["requestBody"]["content"]["application/json"]["schema"][
                "properties"
            ]
        )
        for key in ("monthly_requests", "monthly_input_m", "monthly_output_m", "cached_input_m", "usage_snippet"):
            self.assertIn(key, budget_post_props, f"Missing {key} in openapi_coze.json")

        openapi_live = json.loads(
            (ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle" / "openapi_coze_live.json").read_text(
                encoding="utf-8"
            )
        )
        live_param_names = {p["name"] for p in openapi_live["paths"]["/api/budget"]["get"]["parameters"]}
        for key in ("monthly_requests", "monthly_input_m", "monthly_output_m", "cached_input_m", "usage_snippet"):
            self.assertIn(key, live_param_names, f"Missing {key} in openapi_coze_live.json")

        actor_schema = json.loads(
            (ROOT / "engine_a_mcp_actor" / ".actor" / "input_schema.json").read_text(encoding="utf-8")
        )
        for key in ("monthly_requests", "monthly_input_m", "monthly_output_m", "usage_snippet"):
            self.assertIn(key, actor_schema["properties"], f"Missing {key} in .actor/input_schema.json")

    def test_03_audit_preserves_last_verified_at_across_csr_degradation_and_clears_on_drift(self) -> None:
        healthy_aliyun = (
            "<html><body><h1>阿里云百炼 Coding Plan</h1><p>"
            + ("套餐计费规则说明。" * 45)
            + "</p><p>Pro 新客首月 39.9 元，续费 200 元/月，每月上限 90,000 次调用</p></body></html>"
        )
        healthy_tencent = (
            "<html><body><h1>腾讯云 Coding Plan</h1><p>"
            + ("编程助手套餐规则说明。" * 45)
            + "</p><p>Lite 40 元 每月上限 18,000 次；Pro 200 元 每月上限 90,000 次请求次数</p></body></html>"
        )
        healthy_volc = (
            "<html><body><h1>火山方舟 Coding Plan</h1><p>"
            + ("提供 Lite 套餐 与 Pro 套餐。" * 35)
            + "</p><p>每5小时限额自动重置，不可用于 API 调用，Base URL https://ark.cn-beijing.volces.com/api/coding/v3</p></body></html>"
        )
        csr_shell = "<html><body><div id='app'>Loading...</div></body></html>"

        def domestic_fetch(url: str) -> str:
            if "aliyun.com" in url:
                return healthy_aliyun
            if "cloud.tencent.com" in url:
                return healthy_tencent
            return healthy_volc

        audit_t1 = fetch_and_enrich.audit_official_coding_plan_docs(
            checked_at="2026-11-15T05:30:00Z",
            fetcher=domestic_fetch,
        )
        t1_by_id = {v["plan_id"]: v for v in audit_t1["vendors"]}
        self.assertEqual(t1_by_id["tencent-coding-plan"]["status"], "verified_markers")
        self.assertEqual(t1_by_id["tencent-coding-plan"]["last_verified_at"], "2026-11-15T05:30:00Z")

        # Overseas CI run 2 minutes later: Tencent returns CSR shell -> preserves `last_verified_at` & 0 drift!
        def overseas_ci_fetch(url: str) -> str:
            if "aliyun.com" in url:
                return healthy_aliyun
            if "cloud.tencent.com" in url:
                return csr_shell
            return healthy_volc

        audit_t2 = fetch_and_enrich.audit_official_coding_plan_docs(
            checked_at="2026-11-15T05:32:00Z",
            fetcher=overseas_ci_fetch,
            prior_audit=audit_t1,
        )
        self.assertEqual(audit_t2["drift_warnings"], [])
        t2_by_id = {v["plan_id"]: v for v in audit_t2["vendors"]}
        self.assertEqual(t2_by_id["tencent-coding-plan"]["status"], "csr_shell_manual_check")
        self.assertEqual(t2_by_id["tencent-coding-plan"]["last_verified_at"], "2026-11-15T05:30:00Z")
        self.assertIn("pro_monthly_cap_90k", t2_by_id["tencent-coding-plan"]["last_verified_groups"])

        # Real drift on Aliyun (90,000 -> 60,000) still immediately triggers marker_drift_detected!
        drifted_aliyun = healthy_aliyun.replace("90,000", "60,000")
        audit_t3 = fetch_and_enrich.audit_official_coding_plan_docs(
            checked_at="2026-11-15T06:00:00Z",
            fetcher=lambda u: drifted_aliyun if "aliyun.com" in u else csr_shell,
            prior_audit=audit_t2,
        )
        self.assertEqual(len(audit_t3["drift_warnings"]), 1)
        t3_by_id = {v["plan_id"]: v for v in audit_t3["vendors"]}
        self.assertEqual(t3_by_id["aliyun-coding-plan"]["status"], "marker_drift_detected")


class Round6Batch2WebImporterPresetsAndDocsTests(unittest.TestCase):
    def test_04_web_usage_import_drawer_i18n_and_telemetry_whitelist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp)
            build_site.build_site(dist_dir=dist_dir)
            root_html = (dist_dir / "index.html").read_text(encoding="utf-8")
            cp_html = (dist_dir / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        for html_doc in (root_html, cp_html):
            for required_id in (
                'id="usageImportDrawer"',
                'id="usageLogTextarea"',
                'id="usageDaysSelect"',
                'id="applyUsageLogBtn"',
                'id="fillSampleLogBtn"',
                'id="monthlyCallsQuick"',
                'id="monthlyInputMQuick"',
                'id="monthlyOutputMQuick"',
                'id="monthlyCachedMQuick"',
                'id="applyMonthlyTotalsBtn"',
                'id="usageImportStatus"',
            ):
                self.assertIn(required_id, html_doc, f"Missing {required_id} in built HTML")
            self.assertIn("function parseUsageSnippet(", html_doc)

        # Verify every new `data-i18n` inside `#usageImportDrawer` is mapped in `I18N_EN` with zero CJK characters
        drawer_start = cp_html.index('id="usageImportDrawer"')
        drawer_end = cp_html.index("</details>", drawer_start)
        drawer_fragment = cp_html[drawer_start:drawer_end]
        drawer_i18n_keys = re.findall(r'data-i18n="([^"]+)"', drawer_fragment)
        self.assertGreaterEqual(len(drawer_i18n_keys), 8)
        for key in drawer_i18n_keys:
            m = re.search(rf'\b{re.escape(key)}\s*:\s*"([^"]+)"', cp_html)
            self.assertIsNotNone(m, f"Missing I18N_EN entry for {key}")
            en_val = m.group(1)
            self.assertIsNone(
                re.search(r"[\u4e00-\u9fff]", en_val),
                f"CJK leak in I18N_EN[{key}]: {en_val}",
            )

        # Extract client JS `parseScaledNumber` + `parseUsageSnippet` and verify exact parity in Node.js
        m_fn = re.search(
            r"(function parseScaledNumber\([\s\S]*?function parseUsageSnippet\([\s\S]*?\n    \})",
            cp_html,
        )
        self.assertIsNotNone(m_fn, "Could not extract parseScaledNumber / parseUsageSnippet from inline script")
        js_fns = m_fn.group(1)
        node_probe = f"""
{js_fns}
const cases = [
  {{
    raw: "Total cost: $18.40\\nInput: 1.6M tokens\\nCache read: 2.4M tokens\\nOutput: 600k tokens\\nRequests: 1,200",
    days: 30
  }},
  {{
    raw: JSON.stringify({{
      requests: 90000,
      prompt_tokens: 360000000,
      prompt_tokens_details: {{ cached_tokens: 180000000 }},
      completion_tokens: 90000000,
      completion_tokens_details: {{ reasoning_tokens: 54000000 }}
    }}),
    days: 30
  }},
  {{
    raw: "近7天统计：输入 Token 28M（缓存命中 14M），输出 Token 7M",
    days: 7
  }}
];
console.log(JSON.stringify(cases.map(c => parseUsageSnippet(c.raw, c.days))));
"""
        proc = subprocess.run(
            ["node", "-e", node_probe],
            capture_output=True,
            text=True,
            check=True,
        )
        web_parsed = json.loads(proc.stdout.strip())
        self.assertEqual(web_parsed[0]["daily_requests"], 40)
        self.assertEqual(web_parsed[0]["avg_input_tokens"], 3333)
        self.assertEqual(web_parsed[0]["avg_output_tokens"], 500)
        self.assertAlmostEqual(web_parsed[0]["cache_hit_rate"], 0.60, places=4)
        self.assertFalse(web_parsed[0]["calls_estimated"])

        self.assertEqual(web_parsed[1]["daily_requests"], 3000)
        self.assertEqual(web_parsed[1]["avg_input_tokens"], 4000)
        self.assertEqual(web_parsed[1]["avg_output_tokens"], 1000)
        self.assertAlmostEqual(web_parsed[1]["cache_hit_rate"], 0.50, places=4)
        self.assertTrue(web_parsed[1]["output_includes_reasoning"])

        self.assertEqual(web_parsed[2]["daily_requests"], 1000)
        self.assertEqual(web_parsed[2]["avg_input_tokens"], 4000)
        self.assertEqual(web_parsed[2]["avg_output_tokens"], 1000)
        self.assertTrue(web_parsed[2]["calls_estimated"])

        # Verify `"usage_import"` telemetry whitelist across Python reconciler, `functions/events.js`, and `functions/admin/stats.js`
        ok, status, clean = events_reconcile.validate_event_payload(
            {
                "event_name": "usage_import",
                "day_bucket": "2026-11-15",
                "browser_day_id": "bday_r6_import_01",
                "route": "/coding-plan-2026/",
                "slot_id": "claude_code_cost",
            }
        )
        self.assertTrue(ok, f"events_reconcile rejected usage_import: {status}")
        self.assertEqual(clean["event_name"], "usage_import")
        rec = events_reconcile.summarize_daily_reconciliation(
            [
                {
                    "event_name": "usage_import",
                    "day_bucket": "2026-11-15",
                    "browser_day_id": "bday_r6_import_01",
                    "route": "/coding-plan-2026/",
                    "slot_id": "claude_code_cost",
                }
            ],
            day="2026-11-15",
        )
        self.assertEqual(rec["usage_imports_uv"], 1)

        ev_runner = """
import fs from "node:fs";
const evSrc = fs.readFileSync("functions/events.js", "utf8");
const {onRequestPost} = await import("data:text/javascript;base64," + Buffer.from(evSrc).toString("base64"));
const req = new Request("https://example.test/events", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    event_name: "usage_import",
    day_bucket: "2026-11-15",
    browser_day_id: "bday_r6_import_01",
    route: "/coding-plan-2026/",
    slot_id: "claude_code_cost"
  })
});
const res = await onRequestPost({request: req, env: {}});
console.log(JSON.stringify({status: res.status, body: await res.json()}));
"""
        ev_proc = subprocess.run(
            ["node", "--input-type=module", "-e", ev_runner],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        ev_out = json.loads(ev_proc.stdout.strip())
        self.assertEqual(ev_out["status"], 202)
        self.assertTrue(ev_out["body"]["ok"])

        stats_js = (ROOT / "functions" / "admin" / "stats.js").read_text(encoding="utf-8")
        self.assertIn("usage_imports_uv", stats_js)

    def test_05_claude_code_domestic_3vendor_preset_ssr_example_e_and_pipeline_sync(self) -> None:
        cc_route = next(r for r in build_site.SEO_ROUTES if r["slug"] == "claude-code-domestic/")
        self.assertEqual(
            cc_route["preset"].get("compareIds"),
            [
                "aliyun-bailian/qwen3-coder-next",
                "tencent-cloud/deepseek-v3",
                "volcengine/doubao-seed-2.0-pro",
            ],
        )
        self.assertIn("火山", cc_route["description"])

        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp)
            build_site.build_site(dist_dir=dist_dir)
            cp_html = (dist_dir / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        # SSR Worked Example E: 5-developer team (`team_size=5`, `daily_calls=6000` -> `180,000` calls/mo, `5 × Pro`)
        self.assertIn("案例 E", cp_html)
        self.assertIn("180,000", cp_html)
        self.assertIn("199.50", cp_html)
        self.assertIn("1,000", cp_html)

        # Pipeline & docs registration
        self.assertIn("test_round6_product_iteration.py", prepare_release.FILES)
        daily_yml = (ROOT / "cloudflare" / "daily_refresh.yml").read_text(encoding="utf-8")
        self.assertIn("test_round6_product_iteration", daily_yml)
        verify_py = (ROOT / "cloudflare" / "verify_release.py").read_text(encoding="utf-8")
        self.assertIn("monthly_requests=90000", verify_py)
        sync_sh_path = ROOT / "sync_config_to_cloud.sh"
        if sync_sh_path.exists():
            sync_sh = sync_sh_path.read_text(encoding="utf-8")
            self.assertIn("test_round6_product_iteration", sync_sh)
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertRegex(readme, r"\bv3\.(?:[6-9]|\d{2,})\b")
            self.assertIn("test_round6_product_iteration", readme)
        article = (ROOT / "marketing_pack" / "01_juejin_zhihu_article.md").read_text(encoding="utf-8")
        self.assertIn("ark.cn-beijing.volces.com/api/coding", article)


if __name__ == "__main__":
    unittest.main()
