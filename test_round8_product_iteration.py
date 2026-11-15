#!/usr/bin/env python3
"""
Round 8 (v3.8) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. Multi-record JSON Array (`[...]`, `{"data": [...]}`) & JSONL (`{...}\\n{...}`) bill parsing across
       Claude Code `~/.claude/projects/*.jsonl` transcripts (streaming `message.id` deduplication + additive
       Anthropic cache tokens + non-usage metadata filtering), OpenAI Batch `.jsonl` (`response.body`),
       LiteLLM/OpenRouter JSON logs, dated/alias model resolution (`gpt-4.1-2025-04-14`, `deepseek-reasoner`),
       and strict `ValueError` / HTTP 400 on zero-token JSONL files.
    2. Zero-code LiteLLM proxy migration config (`migration_litellm_config`), exact `raw_model` alias mapping,
       same-family Mainland China direct route calculation (`same_family_cn_model_id`), and cross-surface parity
       across `pricing_core.py`, `mcp_server.py`, Cloudflare `functions/api/budget.js`, and `coze_cloud_tool.py`.
    3. Full-funnel `feature_funnel` (`event_name` x `slot_id` deduplicated UV) in `cloudflare/events_reconcile.py`
       and Cloudflare `functions/admin/stats.js`.
    Batch 2:
    4. Web UI local JSON/JSONL multi-model upload (`.jsonl` accept, `#fillSampleJsonlBtn`, `tryParseJsonRecordsBill`,
       5MB local snippet support), interactive per-row route selector (`bill-route-select` / `billRowOverrides`),
       and zero-code LiteLLM migration modal (`#openBillMigrationBtn`, `#downloadConfigYamlBtn`,
       `buildBillMigrationLiteLlmConfig`) with full `I18N_EN` parity.
    5. Executive 1-page Print / Save-as-PDF procurement audit sheet (`#printAuditBtn`, `#printAuditStamp`,
       `@media print` clean white layout & unclipped tables, `.has-bill-audit` print visibility, and `print_pdf_audit` telemetry).
    6. Release pipeline (`cloudflare/prepare_release.py`, `cloudflare/daily_refresh.yml`, `sync_config_to_cloud.sh`),
       production remote verifier (`cloudflare/verify_release.py` JSONL + `migration_litellm_config`),
       `README.md`, and `marketing_pack/01_juejin_zhihu_article.md` synced to `v3.8`.
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
import events_reconcile  # noqa: E402
import mcp_server  # noqa: E402
import prepare_release  # noqa: E402
import pricing_core  # noqa: E402


SAMPLE_OPENROUTER_CSV = """model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage
anthropic/claude-sonnet-4,15000,60000000,12000000,30000000,0,$315.00
deepseek/deepseek-r1,10000,40000000,10000000,20000000,6000000,$42.00
qwen3-coder-next,20000,80000000,16000000,40000000,0,$21.33
"""

SAMPLE_MULTIMODEL_JSONL = "\n".join(
    [
        json.dumps(
            {
                "model": "anthropic/claude-sonnet-4",
                "requests": 15000,
                "prompt_tokens": 60_000_000,
                "completion_tokens": 12_000_000,
                "cached_tokens": 30_000_000,
                "spend": 315.00,
            }
        ),
        json.dumps(
            {
                "model": "deepseek/deepseek-r1",
                "requests": 10000,
                "prompt_tokens": 40_000_000,
                "completion_tokens": 10_000_000,
                "cached_tokens": 20_000_000,
                "reasoning_tokens": 6_000_000,
                "spend": 42.00,
            }
        ),
        json.dumps(
            {
                "model": "qwen3-coder-next",
                "requests": 20000,
                "prompt_tokens": 80_000_000,
                "completion_tokens": 16_000_000,
                "cached_tokens": 40_000_000,
                "spend": 21.33,
            }
        ),
    ]
)


class Round8Batch1JsonlMigrationAndFunnelTests(unittest.TestCase):
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

    def test_01_jsonl_and_json_array_multimodel_parsing_incl_claude_code_dedupe(self) -> None:
        # 1. Claude Code `~/.claude/projects/*.jsonl` transcript with streaming chunks + user/summary metadata lines
        claude_code_jsonl = "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "prompt tokens: 999999999"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "id": "msg_cc_stream_01",
                            "model": "claude-sonnet-4-20250514",
                            "usage": {
                                "input_tokens": 2000,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 18000,
                                "output_tokens": 55,
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "id": "msg_cc_stream_01",
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
                            "id": "msg_cc_stream_02",
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
                json.dumps({"type": "summary", "summary": "Completed refactoring"}),
            ]
        )
        parsed_cc = pricing_core.parse_usage_log_snippet(claude_code_jsonl, days_observed=1.0)
        self.assertEqual(parsed_cc["detected_format"], "csv_multimodel_bill")
        self.assertEqual(parsed_cc["source_format"], "jsonl_multimodel")
        self.assertGreaterEqual(parsed_cc["deduplicated_chunks"], 1)
        self.assertEqual(parsed_cc["distinct_models_count"], 2)
        self.assertEqual(parsed_cc["total_requests"], 2)
        self.assertEqual(parsed_cc["total_input_tokens"], 40_000)
        self.assertEqual(parsed_cc["cached_input_tokens"], 33_000)
        self.assertEqual(parsed_cc["total_output_tokens"], 3_000)
        self.assertAlmostEqual(parsed_cc["cache_hit_rate"], 33_000 / 40_000, places=4)

        # 2. OpenAI Batch `.jsonl` (`response.body`) + dated OpenAI & `deepseek-reasoner` alias resolution
        batch_jsonl = "\n".join(
            [
                json.dumps(
                    {
                        "id": "batch_req_01",
                        "custom_id": "job-1",
                        "response": {
                            "status_code": 200,
                            "body": {
                                "id": "chatcmpl-01",
                                "model": "gpt-4.1-2025-04-14",
                                "usage": {
                                    "prompt_tokens": 10_000,
                                    "completion_tokens": 2_000,
                                    "prompt_tokens_details": {"cached_tokens": 5_000},
                                },
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "id": "batch_req_02",
                        "custom_id": "job-2",
                        "response": {
                            "status_code": 200,
                            "body": {
                                "id": "chatcmpl-02",
                                "model": "deepseek-reasoner",
                                "usage": {
                                    "prompt_tokens": 8_000,
                                    "completion_tokens": 3_000,
                                    "completion_tokens_details": {"reasoning_tokens": 2_000},
                                },
                            },
                        },
                    }
                ),
            ]
        )
        parsed_batch = pricing_core.parse_usage_log_snippet(batch_jsonl, days_observed=1.0)
        self.assertEqual(parsed_batch["detected_format"], "csv_multimodel_bill")
        self.assertEqual(parsed_batch["total_requests"], 2)
        self.assertEqual(parsed_batch["total_input_tokens"], 18_000)
        self.assertEqual(parsed_batch["cached_input_tokens"], 5_000)
        self.assertEqual(parsed_batch["total_output_tokens"], 5_000)
        self.assertTrue(parsed_batch["output_includes_reasoning"])

        catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        batch_audit = pricing_core.audit_csv_bill(
            models=catalog["models"],
            raw_text=parsed_batch,
            days_observed=1.0,
            usage_mode="automated_backend",
            team_size=1,
            offers=catalog.get("coding_plans"),
        )
        by_raw = {item["raw_model"]: item for item in batch_audit["line_items"]}
        self.assertTrue(by_raw["gpt-4.1-2025-04-14"]["matched_model_id"].startswith("openai/"))
        self.assertIn("deepseek-r1", by_raw["deepseek-reasoner"]["matched_model_id"].lower())
        self.assertTrue(batch_audit["totals"]["has_global_closed_models"])

        # 3. JSON Array (`[...]`) parity with CSV bill
        json_array_bill = json.dumps(
            [json.loads(line) for line in SAMPLE_MULTIMODEL_JSONL.splitlines()],
            ensure_ascii=False,
        )
        parsed_arr = pricing_core.parse_usage_log_snippet(json_array_bill, days_observed=30.0)
        self.assertEqual(parsed_arr["detected_format"], "csv_multimodel_bill")
        self.assertEqual(parsed_arr["source_format"], "json_array_multimodel")
        self.assertEqual(parsed_arr["total_requests"], 45_000)
        self.assertAlmostEqual(parsed_arr["monthly_reported_cost_rmb"], 2723.98, places=2)

        # 4. Zero-token JSONL must raise ValueError (never regex-match prose inside `"content"`)
        empty_jsonl = "\n".join(
            [
                json.dumps({"type": "user", "message": {"role": "user", "content": "input tokens 50000, output tokens 10000"}}),
                json.dumps({"type": "summary", "summary": "No assistant calls"}),
            ]
        )
        with self.assertRaises(ValueError):
            pricing_core.parse_usage_log_snippet(empty_jsonl, days_observed=7.0)

    def test_02_bill_migration_litellm_yaml_same_family_and_cross_surface_parity(self) -> None:
        catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        audit = pricing_core.audit_csv_bill(
            models=catalog["models"],
            raw_text=SAMPLE_OPENROUTER_CSV,
            days_observed=30.0,
            usage_mode="interactive_ide",
            team_size=2,
            offers=catalog.get("coding_plans"),
        )
        by_raw = {item["raw_model"]: item for item in audit["line_items"]}
        for item in audit["line_items"]:
            self.assertTrue(item["recommended_api_model_id"])
            self.assertTrue(item["recommended_api_base_url"].startswith("https://"))
            self.assertTrue(item["recommended_env_key_var"].endswith("_API_KEY"))

        r1_row = by_raw["deepseek/deepseek-r1"]
        self.assertIn(
            r1_row["same_family_cn_model_id"],
            ("tencent-cloud/deepseek-r1", "siliconflow/deepseek-ai/DeepSeek-R1"),
        )
        self.assertAlmostEqual(r1_row["same_family_cn_monthly_rmb"], 256.00, places=2)

        mig = audit["migration_litellm_config"]
        self.assertIn("model_list:", mig["config_yaml"])
        self.assertIn('model_name: "anthropic/claude-sonnet-4"', mig["config_yaml"])
        self.assertIn('model_name: "deepseek/deepseek-r1"', mig["config_yaml"])
        self.assertIn('model_name: "qwen3-coder-next"', mig["config_yaml"])
        self.assertIn("model: openai/", mig["config_yaml"])
        self.assertIn("api_key: os.environ/", mig["config_yaml"])
        self.assertEqual(len(mig["required_env_vars"]), len(set(mig["required_env_vars"])))
        self.assertEqual(mig["distinct_providers_count"], len(mig["required_env_vars"]))
        self.assertIn("LITELLM_MASTER_KEY", mig["env_snippet"])
        self.assertIn("uvx --from 'litellm[proxy]' litellm --config config.yaml --port 4000", mig["env_snippet"])
        self.assertIn("http://127.0.0.1:4000/v1/chat/completions", mig["smoke_test_cmd"])
        self.assertIn('"max_tokens":1', mig["smoke_test_cmd"])
        self.assertIn("sk-sp-", mig["compliance_warning_zh"])

        # Cross-surface JSONL + migration_litellm_config parity across MCP, Cloudflare `/api/budget`, and Coze
        mcp_res = mcp_server.calculate_api_budget(
            model_query="auto",
            usage_snippet=SAMPLE_MULTIMODEL_JSONL,
            days_observed=30.0,
            team_size=2,
        )
        self.assertEqual(mcp_res["parsed_usage_summary"]["detected_format"], "csv_multimodel_bill")
        self.assertEqual(mcp_res["parsed_usage_summary"]["source_format"], "jsonl_multimodel")
        mcp_mig = mcp_res["bill_audit"]["migration_litellm_config"]
        self.assertIn('model_name: "anthropic/claude-sonnet-4"', mcp_mig["config_yaml"])

        cf_cases = self._run_cloudflare_budget_cases(
            [
                {
                    "model_id": "auto",
                    "usage_snippet": SAMPLE_MULTIMODEL_JSONL,
                    "days_observed": "30",
                    "team_size": "2",
                },
                {
                    "model_id": "auto",
                    "usage_snippet": '{"type":"user","message":{"content":"input tokens 9999"}}\n{"type":"summary","summary":"ok"}',
                },
            ]
        )
        self.assertEqual(cf_cases[0]["status"], 200)
        cf_audit = cf_cases[0]["body"]["bill_audit"]
        self.assertAlmostEqual(
            cf_audit["totals"]["optimized_payg_monthly_rmb"],
            mcp_res["bill_audit"]["totals"]["optimized_payg_monthly_rmb"],
            delta=0.05,
        )
        self.assertIn('model_name: "anthropic/claude-sonnet-4"', cf_audit["migration_litellm_config"]["config_yaml"])
        self.assertEqual(cf_cases[1]["status"], 400)

        coze_res = coze_cloud_tool.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "auto",
                "usage_snippet": SAMPLE_MULTIMODEL_JSONL,
                "days_observed": 30,
                "team_size": 2,
            }
        )
        self.assertEqual(coze_res["parsed_usage_summary"]["source_format"], "jsonl_multimodel")
        self.assertIn(
            'model_name: "anthropic/claude-sonnet-4"',
            coze_res["bill_audit"]["migration_litellm_config"]["config_yaml"],
        )

    def test_03_admin_stats_and_reconciler_feature_funnel_breakdown(self) -> None:
        day = "2026-11-15"
        sample_events = [
            {"event_name": "usage_import", "day_bucket": day, "browser_day_id": f"{day}.u1", "route": "/", "slot_id": "file_upload"},
            {"event_name": "usage_import", "day_bucket": day, "browser_day_id": f"{day}.u1", "route": "/", "slot_id": "file_upload"},
            {"event_name": "usage_import", "day_bucket": day, "browser_day_id": f"{day}.u2", "route": "/", "slot_id": "file_upload"},
            {"event_name": "usage_import", "day_bucket": day, "browser_day_id": f"{day}.u3", "route": "/", "slot_id": "paste_apply"},
            {"event_name": "share_summary", "day_bucket": day, "browser_day_id": f"{day}.u1", "route": "/", "slot_id": "bill_audit_gfm"},
            {"event_name": "share_summary", "day_bucket": day, "browser_day_id": f"{day}.u2", "route": "/", "slot_id": "print_pdf_audit"},
            {"event_name": "share_open", "day_bucket": day, "browser_day_id": f"{day}.u4", "route": "/", "slot_id": "shared_query"},
        ]
        rec = events_reconcile.summarize_daily_reconciliation(sample_events, day=day)
        funnel_map = {(row["event_name"], row["slot_id"]): row["unique_users"] for row in rec["feature_funnel"]}
        self.assertEqual(funnel_map[("usage_import", "file_upload")], 2)
        self.assertEqual(funnel_map[("usage_import", "paste_apply")], 1)
        self.assertEqual(funnel_map[("share_summary", "bill_audit_gfm")], 1)
        self.assertEqual(funnel_map[("share_summary", "print_pdf_audit")], 1)
        self.assertEqual(funnel_map[("share_open", "shared_query")], 1)

        node_script = """
import { onRequestPost } from "./functions/events.js";
import { onRequestGet } from "./functions/admin/stats.js";

const rows = [];
const mockDb = {
  prepare(sql) {
    return {
      bind(...args) {
        return {
          async run() {
            if (sql.includes("INSERT INTO telemetry_events")) {
              rows.push({
                day_bucket: args[0],
                event_name: args[1],
                route: args[2],
                browser_day_id: args[3],
                source_channel: args[4],
                offer_id: args[5],
                slot_id: args[6],
                usage_mode: args[7],
                matched_model_id: args[8],
              });
            }
            return { success: true };
          },
          async first() {
            return { estimated_daily_uv: 3, calculations_completed_uv: 2, usage_imports_uv: 2, shares_copied_uv: 2, share_opens_uv: 1 };
          },
          async all() {
            if (sql.includes("event_name") && sql.includes("slot_id") && sql.includes("unique_users")) {
              const day = args[0];
              const target = new Set(["usage_import", "share_copy", "share_summary", "share_open"]);
              const groups = new Map();
              for (const r of rows) {
                if (r.day_bucket !== day || !target.has(r.event_name)) continue;
                const slot = r.slot_id || "unspecified";
                const key = `${r.event_name}::${slot}`;
                if (!groups.has(key)) groups.set(key, new Set());
                groups.get(key).add(r.browser_day_id);
              }
              const results = [...groups.entries()].map(([k, set]) => {
                const [event_name, slot_id] = k.split("::");
                return { event_name, slot_id, unique_users: set.size };
              });
              return { results };
            }
            return { results: [] };
          },
        };
      },
    };
  },
};

const env = { DB: mockDb, ADMIN_STATS_TOKEN: "test-secret-admin-token-1234" };
for (const ev of [
  { event_name: "usage_import", day_bucket: "2026-11-15", browser_day_id: "2026-11-15.a", route: "/", slot_id: "file_upload" },
  { event_name: "usage_import", day_bucket: "2026-11-15", browser_day_id: "2026-11-15.a", route: "/", slot_id: "file_upload" },
  { event_name: "usage_import", day_bucket: "2026-11-15", browser_day_id: "2026-11-15.b", route: "/", slot_id: "file_upload" },
  { event_name: "share_summary", day_bucket: "2026-11-15", browser_day_id: "2026-11-15.a", route: "/", slot_id: "print_pdf_audit" },
]) {
  await onRequestPost({
    request: new Request("https://example.com/events", { method: "POST", body: JSON.stringify(ev) }),
    env,
  });
}

const statsRes = await onRequestGet({
  request: new Request("https://example.com/admin/stats?day=2026-11-15", {
    headers: { Authorization: "Bearer test-secret-admin-token-1234" },
  }),
  env,
});
console.log(JSON.stringify(await statsRes.json()));
"""
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", node_script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        stats_body = json.loads(proc.stdout.strip())
        self.assertIn("feature_funnel", stats_body)
        cf_funnel = {(r["event_name"], r["slot_id"]): r["unique_users"] for r in stats_body["feature_funnel"]}
        self.assertEqual(cf_funnel[("usage_import", "file_upload")], 2)
        self.assertEqual(cf_funnel[("share_summary", "print_pdf_audit")], 1)


class Round8Batch2WebUiPrintAndPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dist_dir = Path(cls._tmp.name) / "dist"
        build_site.build_site(dist_dir=cls.dist_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_04_web_jsonl_upload_per_row_route_override_and_migration_yaml_modal(self) -> None:
        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('accept=".csv,.tsv,.json,.jsonl,.txt,.log"', index_html)
        self.assertIn('id="fillSampleJsonlBtn"', index_html)
        self.assertIn("tryParseJsonRecordsBill", index_html)
        self.assertIn("billRowOverrides", index_html)
        self.assertIn("bill-route-select", index_html)
        self.assertIn("openBillMigrationBtn", index_html)
        self.assertIn('id="downloadConfigYamlBtn"', index_html)
        self.assertIn("buildBillMigrationLiteLlmConfig", index_html)
        self.assertIn("litellm_bill_migration", index_html)
        for i18n_key in ("fillSampleJsonlBtn", "downloadConfigYamlBtn", "printAuditBtn"):
            self.assertIn(f"{i18n_key}:", index_html, f"Missing {i18n_key} in I18N_EN")

    def test_05_web_print_pdf_procurement_sheet_and_media_print_styles(self) -> None:
        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="printAuditBtn"', index_html)
        self.assertIn('id="printAuditStamp"', index_html)
        self.assertIn("@media print", index_html)
        self.assertIn("has-bill-audit", index_html)
        self.assertIn("print_pdf_audit", index_html)
        self.assertIn("window.print()", index_html)

    def test_06_pipeline_verifier_readme_and_marketing_v38_sync(self) -> None:
        self.assertIn("test_round8_product_iteration.py", prepare_release.FILES)
        workflow_yml = (ROOT / "cloudflare" / "daily_refresh.yml").read_text(encoding="utf-8")
        self.assertIn("test_round8_product_iteration.py", workflow_yml)
        self.assertIn("test_round8_product_iteration", workflow_yml)
        verifier_py = (ROOT / "cloudflare" / "verify_release.py").read_text(encoding="utf-8")
        self.assertIn("migration_litellm_config", verifier_py)
        self.assertIn("jsonl_multimodel", verifier_py)
        article = (ROOT / "marketing_pack" / "01_juejin_zhihu_article.md").read_text(encoding="utf-8")
        self.assertIn("config.yaml", article)
        self.assertIn(".jsonl", article)
        if (ROOT / "sync_config_to_cloud.sh").exists():
            sync_sh = (ROOT / "sync_config_to_cloud.sh").read_text(encoding="utf-8")
            self.assertIn("test_round8_product_iteration", sync_sh)
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertRegex(readme, r"\bv3\.(?:[8-9]|\d{2,})\b")
            self.assertIn("test_round8_product_iteration", readme)


if __name__ == "__main__":
    unittest.main()
