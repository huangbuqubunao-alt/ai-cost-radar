#!/usr/bin/env python3
"""
Round 7 (v3.7) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. Multi-model CSV / TSV bill parsing (`parse_usage_log_snippet` -> `csv_multimodel_bill`) across
       OpenRouter Activity CSV (per-row & summary rows, USD spend, subset cached tokens, reasoning guard)
       and Mainland China cloud console CSV/TSV (scaled units, multi-day extrapolation), plus deterministic
       portfolio audit & slim-down recommendations (`pricing_core.audit_csv_bill`).
    2. Cross-surface CSV bill audit parity (`bill_audit`) & `auto` primary-model resolution across
       `mcp_server.py`, Cloudflare `functions/api/budget.js` (incl. HTTP 400 validation), and `coze_cloud_tool.py`.
    3. Claude Code persistent `~/.claude/settings.json` generation, `unset ANTHROPIC_API_KEY` conflict guard,
       Coding Plan covered-model auto-remapping (`qwen-max-latest` -> `qwen3.5-plus`, `doubao-seed-2-0-pro-250415`
       -> `doubao-seed-2.0-pro`), and 1-token connectivity `smoke_test_cmd`.
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
sys.path.insert(0, str(ROOT / "cloudflare"))

import build_site  # noqa: E402
import coze_cloud_tool  # noqa: E402
import mcp_server  # noqa: E402
import pricing_core  # noqa: E402


SAMPLE_OPENROUTER_CSV = """model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage
anthropic/claude-sonnet-4,15000,60000000,12000000,30000000,0,$315.00
deepseek/deepseek-r1,10000,40000000,10000000,20000000,6000000,$42.00
qwen3-coder-next,20000,80000000,16000000,40000000,0,$21.33
"""


class Round7Batch1CsvAuditAndClaudeSettingsTests(unittest.TestCase):
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

    def test_01_parse_and_audit_multimodel_csv_across_openrouter_and_cn_console(self) -> None:
        # 1. OpenRouter multi-model aggregated CSV (3 models, USD spend, subset cache, reasoning tokens)
        parsed = pricing_core.parse_usage_log_snippet(SAMPLE_OPENROUTER_CSV, days_observed=30.0)
        self.assertEqual(parsed["detected_format"], "csv_multimodel_bill")
        self.assertEqual(parsed["distinct_models_count"], 3)
        self.assertEqual(parsed["total_requests"], 45000)
        self.assertEqual(parsed["daily_requests"], 1500)
        self.assertEqual(parsed["total_input_tokens"], 180_000_000)
        self.assertEqual(parsed["cached_input_tokens"], 90_000_000)
        self.assertEqual(parsed["total_output_tokens"], 38_000_000)
        self.assertAlmostEqual(parsed["cache_hit_rate"], 0.50, places=4)
        self.assertTrue(parsed["output_includes_reasoning"])
        self.assertFalse(parsed["calls_estimated"])
        self.assertAlmostEqual(parsed["monthly_reported_cost_rmb"], round(378.33 * 7.20, 2), places=2)
        self.assertEqual(len(parsed["model_breakdown"]), 3)
        self.assertEqual(parsed["model_breakdown"][0]["model"], "anthropic/claude-sonnet-4")

        # 2. Per-generation OpenRouter CSV without a `requests` column (each row = 1 API call)
        per_gen_csv = (
            "generation_id,created_at,model_permaslug,native_tokens_prompt,native_tokens_completion,native_tokens_cached,usage\n"
            "gen-1,2026-11-14T01:00:00Z,anthropic/claude-sonnet-4,4000,1000,2000,0.024\n"
            "gen-2,2026-11-14T01:05:00Z,anthropic/claude-sonnet-4,6000,1000,3000,0.030\n"
            "gen-3,2026-11-14T01:10:00Z,deepseek/deepseek-chat,5000,1000,2500,0.002\n"
        )
        parsed_gen = pricing_core.parse_usage_log_snippet(per_gen_csv, days_observed=1.0)
        self.assertEqual(parsed_gen["detected_format"], "csv_multimodel_bill")
        self.assertEqual(parsed_gen["total_requests"], 3)
        self.assertEqual(parsed_gen["daily_requests"], 3)
        self.assertFalse(parsed_gen["calls_estimated"])
        self.assertEqual(parsed_gen["distinct_models_count"], 2)

        # 3. Chinese 7-day console billing CSV with scaled units & RMB currency prefix
        cn_csv = (
            "模型名称,调用次数,输入Token,缓存命中Token,输出Token,应付金额\n"
            "qwen-max,3500,14M,7M,3.5M,¥126.00\n"
            "qwen3-coder-next,7000,28M,14M,7M,¥54.88\n"
        )
        parsed_cn = pricing_core.parse_usage_log_snippet(cn_csv, days_observed=7.0)
        self.assertEqual(parsed_cn["detected_format"], "csv_multimodel_bill")
        self.assertEqual(parsed_cn["total_requests"], 10500)
        self.assertEqual(parsed_cn["daily_requests"], 1500)
        self.assertAlmostEqual(parsed_cn["monthly_input_m"], 180.0, places=3)
        self.assertAlmostEqual(parsed_cn["monthly_output_m"], 45.0, places=3)
        self.assertAlmostEqual(parsed_cn["monthly_reported_cost_rmb"], round(180.88 * (30.0 / 7.0), 2), places=2)

        # 4. Portfolio slim-down audit (`audit_csv_bill`)
        catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        audit = pricing_core.audit_csv_bill(
            models=catalog["models"],
            raw_text=SAMPLE_OPENROUTER_CSV,
            days_observed=30.0,
            usage_mode="interactive_ide",
            team_size=2,
            offers=catalog.get("coding_plans"),
        )
        self.assertEqual(len(audit["line_items"]), 3)
        self.assertEqual(audit["totals"]["monthly_requests"], 45000)
        self.assertAlmostEqual(audit["totals"]["baseline_monthly_rmb"], 2723.98, places=2)
        self.assertLess(audit["totals"]["optimized_payg_monthly_rmb"], 600.0)
        self.assertGreater(audit["totals"]["payg_savings_rmb"], 2100.0)
        self.assertTrue(audit["totals"]["has_global_closed_models"])
        for item in audit["line_items"]:
            self.assertGreaterEqual(item["savings_rmb"], 0.0)
            self.assertLessEqual(item["optimized_payg_rmb"], item["baseline_monthly_rmb"] + 0.01)
        self.assertIsNotNone(audit["coding_plan_option"])
        self.assertTrue(audit["coding_plan_option"]["has_cross_model_caveat"])

    def test_02_cross_surface_csv_bill_parity_across_mcp_cloudflare_and_coze(self) -> None:
        mcp_res = mcp_server.calculate_api_budget(
            model_query="auto",
            usage_snippet=SAMPLE_OPENROUTER_CSV,
            days_observed=30.0,
            team_size=2,
        )
        self.assertEqual(mcp_res["parsed_usage_summary"]["detected_format"], "csv_multimodel_bill")
        self.assertIn("bill_audit", mcp_res)
        mcp_opt_rmb = mcp_res["bill_audit"]["totals"]["optimized_payg_monthly_rmb"]
        mcp_base_rmb = mcp_res["bill_audit"]["totals"]["baseline_monthly_rmb"]

        # Cloudflare `/api/budget` parity + HTTP 400 on zero-token CSV
        cf_cases = self._run_cloudflare_budget_cases(
            [
                {
                    "model_id": "auto",
                    "usage_snippet": SAMPLE_OPENROUTER_CSV,
                    "days_observed": "30",
                    "team_size": "2",
                },
                {
                    "model_id": "qwen3.5-plus",
                    "usage_snippet": "model,prompt_tokens,completion_tokens\nfoo,0,0\n",
                },
            ]
        )
        self.assertEqual(cf_cases[0]["status"], 200)
        cf_body = cf_cases[0]["body"]
        self.assertEqual(cf_body["parsed_usage_summary"]["detected_format"], "csv_multimodel_bill")
        self.assertIn("bill_audit", cf_body)
        self.assertEqual(cf_body["bill_audit"]["totals"]["monthly_requests"], 45000)
        self.assertAlmostEqual(cf_body["bill_audit"]["totals"]["baseline_monthly_rmb"], mcp_base_rmb, delta=0.05)
        self.assertAlmostEqual(cf_body["bill_audit"]["totals"]["optimized_payg_monthly_rmb"], mcp_opt_rmb, delta=0.05)
        self.assertEqual(cf_cases[1]["status"], 400)

        # Standalone Coze cloud tool parity
        coze_res = coze_cloud_tool.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "auto",
                "usage_snippet": SAMPLE_OPENROUTER_CSV,
                "days_observed": 30,
                "team_size": 2,
            }
        )
        self.assertEqual(coze_res["parsed_usage_summary"]["detected_format"], "csv_multimodel_bill")
        self.assertIn("bill_audit", coze_res)
        self.assertAlmostEqual(coze_res["bill_audit"]["totals"]["optimized_payg_monthly_rmb"], mcp_opt_rmb, delta=0.05)

    def test_03_claude_code_settings_json_unset_conflict_covered_model_guard_and_smoke_curl(self) -> None:
        # 1. Aliyun Coding Plan + Claude Code + covered model `qwen3-coder-next`
        ali_cc = pricing_core.get_client_endpoint_config(
            vendor_or_plan="aliyun-coding-plan",
            client_type="claude_code",
            billing_mode="coding_plan",
            model_id="aliyun-bailian/qwen3-coder-next",
        )
        self.assertTrue(ali_cc["verified"])
        self.assertFalse(ali_cc["model_remapped"])
        self.assertEqual(ali_cc["effective_model_id"], "qwen3-coder-next")
        self.assertIn("unset ANTHROPIC_API_KEY", ali_cc["env_snippet"])
        settings_obj = json.loads(ali_cc["claude_settings_json"])
        self.assertEqual(
            settings_obj["env"]["ANTHROPIC_BASE_URL"],
            "https://coding.dashscope.aliyuncs.com/apps/anthropic",
        )
        self.assertTrue(settings_obj["env"]["ANTHROPIC_AUTH_TOKEN"].startswith("sk-sp-"))
        self.assertEqual(settings_obj["env"]["ANTHROPIC_MODEL"], "qwen3-coder-next")
        self.assertEqual(settings_obj["env"]["ANTHROPIC_SMALL_FAST_MODEL"], "qwen3-coder-next")
        self.assertIn("https://coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages", ali_cc["smoke_test_cmd"])
        self.assertIn('"max_tokens":1', ali_cc["smoke_test_cmd"])

        # 2. Non-covered model (`qwen-max-latest`) on Aliyun Coding Plan -> safely remaps to `qwen3.5-plus`
        ali_remap = pricing_core.get_client_endpoint_config(
            vendor_or_plan="aliyun-coding-plan",
            client_type="claude_code",
            billing_mode="coding_plan",
            model_id="qwen-max-latest",
        )
        self.assertTrue(ali_remap["model_remapped"])
        self.assertEqual(ali_remap["effective_model_id"], "qwen3.5-plus")
        self.assertIn('ANTHROPIC_MODEL="qwen3.5-plus"', ali_remap["env_snippet"])
        self.assertIn("qwen3.5-plus", ali_remap["warning_zh"])

        # 3. Volcengine date-suffixed model ID (`doubao-seed-2-0-pro-250415`) -> normalizes to `doubao-seed-2.0-pro`
        volc_cc = pricing_core.get_client_endpoint_config(
            vendor_or_plan="volcengine-coding-plan",
            client_type="claude_code",
            billing_mode="coding_plan",
            model_id="doubao-seed-2-0-pro-250415",
        )
        self.assertEqual(volc_cc["effective_model_id"], "doubao-seed-2.0-pro")
        volc_settings = json.loads(volc_cc["claude_settings_json"])
        self.assertEqual(volc_settings["env"]["ANTHROPIC_BASE_URL"], "https://ark.cn-beijing.volces.com/api/coding")
        self.assertEqual(volc_settings["env"]["ANTHROPIC_MODEL"], "doubao-seed-2.0-pro")

        # 4. OpenAI-compatible mode (`cursor`) -> `claude_settings_json` is None, `smoke_test_cmd` uses `/chat/completions`
        ali_oai = pricing_core.get_client_endpoint_config(
            vendor_or_plan="aliyun-coding-plan",
            client_type="cursor",
            billing_mode="coding_plan",
            model_id="qwen3.5-plus",
        )
        self.assertIsNone(ali_oai["claude_settings_json"])
        self.assertIn("https://coding.dashscope.aliyuncs.com/v1/chat/completions", ali_oai["smoke_test_cmd"])
        self.assertIn("Authorization: Bearer sk-sp-", ali_oai["smoke_test_cmd"])


class Round7Batch2WebUiAndPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dist_dir = Path(cls._tmp.name) / "dist"
        build_site.build_site(dist_dir=cls.dist_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_04_web_multimodel_csv_bill_upload_breakdown_and_gfm_export(self) -> None:
        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="usageFileInput"', index_html)
        self.assertIn('accept=".csv,.tsv,.json,.txt,.log"', index_html)
        self.assertIn('id="fillSampleCsvBtn"', index_html)
        self.assertIn('data-i18n="usagePrivacyNote"', index_html)
        self.assertIn('id="usageBillBreakdown"', index_html)
        self.assertIn("copyBillAuditMdBtn", index_html)
        self.assertIn("tryParseCsvBill", index_html)
        self.assertIn("auditCsvBillWeb", index_html)
        self.assertIn("buildBillAuditMarkdown", index_html)
        self.assertIn("FileReader", index_html)
        for i18n_key in ("usageFileBtn", "fillSampleCsvBtn", "usagePrivacyNote"):
            self.assertIn(f"{i18n_key}:", index_html, f"Missing {i18n_key} in I18N_EN")
        self.assertIn("min-width: 0;", index_html)

    def test_05_web_claude_code_settings_json_download_smoke_curl_and_route_smart_default(self) -> None:
        cc_html = (self.dist_dir / "claude-code-domestic" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="downloadSettingsJsonBtn"', cc_html)
        self.assertIn('id="cfgVerifyWrap"', cc_html)
        self.assertIn('id="cfgVerifyHeadingEl"', cc_html)
        self.assertIn('id="cfgVerifySnippet"', cc_html)
        self.assertIn('id="copyVerifyCmdBtn"', cc_html)
        self.assertIn("unset ANTHROPIC_API_KEY", cc_html)
        self.assertIn("ANTHROPIC_SMALL_FAST_MODEL", cc_html)
        self.assertIn("/v1/messages", cc_html)
        self.assertIn("/chat/completions", cc_html)
        self.assertIn('ROUTE_PATH.includes("claude-code-domestic")', cc_html)
        self.assertIn("settings.json", cc_html)

    def test_06_web_selfhost_interactive_controls_dify_compare_presets_and_pipeline_registration(self) -> None:
        dify_html = (self.dist_dir / "dify-openclaw-cloud-server" / "index.html").read_text(encoding="utf-8")
        self.assertIn("semanticCacheRateSelect", dify_html)
        self.assertIn("gpuMonthlyHoursSelect", dify_html)
        self.assertIn('params.set("scache"', dify_html)
        self.assertIn('params.set("gpuh"', dify_html)
        self.assertIn('params.has("scache")', dify_html)
        self.assertIn('params.has("gpuh")', dify_html)

        dify_route = next(r for r in build_site.SEO_ROUTES if r["slug"] == "dify-openclaw-cloud-server/")
        self.assertEqual(
            dify_route["preset"].get("compareIds"),
            [
                "siliconflow/deepseek-ai/DeepSeek-V3",
                "aliyun-bailian/qwen3.5-plus",
                "volcengine/doubao-seed-2.0-pro",
            ],
        )
        hunyuan_fb = next(m for m in build_site.FALLBACK_MODELS if m["id"] == "tencent-cloud/hunyuan-t1")
        self.assertEqual(hunyuan_fb.get("api_model_id"), "hunyuan-t1-latest")

        prep_src = (ROOT / "cloudflare" / "prepare_release.py").read_text(encoding="utf-8")
        ci_src = (ROOT / "cloudflare" / "daily_refresh.yml").read_text(encoding="utf-8")
        verify_src = (ROOT / "cloudflare" / "verify_release.py").read_text(encoding="utf-8")
        article_src = (ROOT / "marketing_pack" / "01_juejin_zhihu_article.md").read_text(encoding="utf-8")

        self.assertIn("test_round7_product_iteration.py", prep_src)
        self.assertIn("test_round7_product_iteration", ci_src)
        self.assertIn("bill_audit", verify_src)
        self.assertIn("settings.json", article_src)
        self.assertIn("unset ANTHROPIC_API_KEY", article_src)

        if (ROOT / "sync_config_to_cloud.sh").exists():
            sync_src = (ROOT / "sync_config_to_cloud.sh").read_text(encoding="utf-8")
            readme_src = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertIn("test_round7_product_iteration", sync_src)
            self.assertRegex(readme_src, r"\bv3\.(?:[7-9]|\d{2,})\b")


if __name__ == "__main__":
    unittest.main()
