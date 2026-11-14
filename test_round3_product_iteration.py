#!/usr/bin/env python3
"""
Round 3 (v3.3) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. Share telemetry closed loop (`share_copy` / `share_summary` in `functions/events.js`,
       `functions/admin/stats.js`, `cloudflare/events_reconcile.py`, and `ui_template.py`).
    2. Engine A (`pricing_core`, `mcp_server`, `openapi_coze.json`, `apify_store_bundle`) model alias &
       `api_model_id` resolution, `GET /api/budget` full query parameter parity, FX constant parity,
       and `marketing_pack` endpoint accuracy (`tc-code-latest`).
    3. Anti-rot price diff tracking (`price_changes` in `fetch_and_enrich.py`) and dynamic Atom XML
       feed generation (`dist/feeds/price-changes.xml` in `build_site.py`).
"""

from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT / "engine_b_affiliate_web"))
sys.path.insert(0, str(ROOT / "cloudflare"))

import build_site  # noqa: E402
import events_reconcile  # noqa: E402
import fetch_and_enrich  # noqa: E402
import mcp_server  # noqa: E402
import pricing_core  # noqa: E402


class Round3Batch1TelemetryAndEngineAParityTests(unittest.TestCase):
    def test_01_share_copy_and_share_summary_telemetry_accepted_across_events_stats_reconcile_and_ui(self) -> None:
        # 1. Python reconciliation validator & aggregator
        ok_copy, reason_copy, _ = events_reconcile.validate_event_payload(
            {
                "event_name": "share_copy",
                "day_bucket": "2026-11-15",
                "browser_day_id": "2026-11-15.userA1",
                "route": "/coding-plan-2026/",
                "slot_id": "share_link",
            }
        )
        self.assertTrue(ok_copy, msg=f"share_copy rejected by events_reconcile: {reason_copy}")

        ok_sum, reason_sum, _ = events_reconcile.validate_event_payload(
            {
                "event_name": "share_summary",
                "day_bucket": "2026-11-15",
                "browser_day_id": "2026-11-15.userB2",
                "route": "/coding-plan-2026/",
                "slot_id": "verdict_brief",
            }
        )
        self.assertTrue(ok_sum, msg=f"share_summary rejected by events_reconcile: {reason_sum}")

        rec = events_reconcile.summarize_daily_reconciliation(
            [
                {
                    "event_name": "result_view",
                    "day_bucket": "2026-11-15",
                    "browser_day_id": "2026-11-15.userA1",
                    "route": "/coding-plan-2026/",
                },
                {
                    "event_name": "share_copy",
                    "day_bucket": "2026-11-15",
                    "browser_day_id": "2026-11-15.userA1",
                    "route": "/coding-plan-2026/",
                    "slot_id": "share_link",
                },
                {
                    "event_name": "share_summary",
                    "day_bucket": "2026-11-15",
                    "browser_day_id": "2026-11-15.userB2",
                    "route": "/coding-plan-2026/",
                    "slot_id": "verdict_brief",
                },
                {
                    "event_name": "share_open",
                    "day_bucket": "2026-11-15",
                    "browser_day_id": "2026-11-15.userC3",
                    "route": "/coding-plan-2026/",
                    "slot_id": "shared_query",
                },
            ],
            day="2026-11-15",
        )
        self.assertEqual(rec.get("shares_copied_uv"), 2)
        self.assertEqual(rec.get("share_opens_uv"), 1)

        # 2. Cloudflare Pages Functions: `functions/events.js` & `functions/admin/stats.js`
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
            const day = args[0];
            const d = rows.filter(r => r.day_bucket === day);
            const uv = new Set(d.map(r => r.browser_day_id)).size;
            const calc = new Set(d.filter(r => r.event_name === "result_view").map(r => r.browser_day_id)).size;
            const copied = new Set(
              d.filter(r => r.event_name === "share_copy" || r.event_name === "share_summary").map(r => r.browser_day_id)
            ).size;
            const opened = new Set(d.filter(r => r.event_name === "share_open").map(r => r.browser_day_id)).size;
            return {
              estimated_daily_uv: uv,
              calculations_completed_uv: calc,
              shares_copied_uv: sql.includes("shares_copied_uv") ? copied : undefined,
              share_opens_uv: opened,
            };
          },
          async all() {
            return { results: [] };
          },
        };
      },
    };
  },
};

async function postEv(payload) {
  const req = new Request("https://example.com/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const res = await onRequestPost({ request: req, env: { DB: mockDb } });
  return { status: res.status, body: await res.json() };
}

const r1 = await postEv({
  event_name: "share_copy",
  day_bucket: "2026-11-15",
  browser_day_id: "2026-11-15.u1",
  route: "/coding-plan-2026/",
  slot_id: "share_link",
});
const r2 = await postEv({
  event_name: "share_summary",
  day_bucket: "2026-11-15",
  browser_day_id: "2026-11-15.u2",
  route: "/coding-plan-2026/",
  slot_id: "verdict_brief",
});
const rBad = await postEv({
  event_name: "unlisted_event",
  day_bucket: "2026-11-15",
  browser_day_id: "2026-11-15.u3",
});

const statsReq = new Request("https://example.com/admin/stats?day=2026-11-15", {
  headers: { Authorization: "Bearer super-secret-admin-token" },
});
const statsRes = await onRequestGet({
  request: statsReq,
  env: { DB: mockDb, ADMIN_STATS_TOKEN: "super-secret-admin-token" },
});
const statsBody = await statsRes.json();

console.log(JSON.stringify({ r1, r2, rBad, statsBody }));
"""
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", node_script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        js_out = json.loads(proc.stdout.strip())
        self.assertEqual(js_out["r1"]["status"], 202)
        self.assertEqual(js_out["r2"]["status"], 202)
        self.assertEqual(js_out["rBad"]["status"], 400)
        self.assertEqual(js_out["statsBody"].get("shares_copied_uv"), 2)

        # 3. UI template wires both `#shareCalcBtn` (`share_link`) and `#copySummaryBtn` (`verdict_brief`)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dist = Path(tmpdir)
            build_site.build_site(output_dir=tmp_dist)
            html_doc = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")
            self.assertIn('slot_id: "share_link"', html_doc)
            self.assertIn('slot_id: "verdict_brief"', html_doc)
            self.assertIn('trackEvent("share_copy"', html_doc)

    def test_02_engine_a_alias_resolution_http_get_params_openapi_and_marketing_parity(self) -> None:
        # 1. Exact `api_model_id` & vendor prefix alias resolution in `mcp_server.calculate_api_budget`
        r_hunyuan = mcp_server.calculate_api_budget(model_query="hunyuan-t1-latest")
        self.assertEqual(r_hunyuan["matched_model"]["id"], "tencent-cloud/hunyuan-t1")
        self.assertIsNone(r_hunyuan.get("match_note"))

        r_aliyun = mcp_server.calculate_api_budget(model_query="aliyun/qwen3.5-plus")
        self.assertEqual(r_aliyun["matched_model"]["id"], "aliyun-bailian/qwen3.5-plus")
        self.assertIsNone(r_aliyun.get("match_note"))

        r_doubao = mcp_server.calculate_api_budget(model_query="doubao-seed-2-0-pro-250415")
        self.assertEqual(r_doubao["matched_model"]["id"], "volcengine/doubao-seed-2.0-pro")
        self.assertIsNone(r_doubao.get("match_note"))

        # 2. HTTP `GET /api/budget` on `ModelRouterHTTPHandler` forwards `model_id`, `cache_hit_rate`,
        #    `reasoning_multiplier`, `output_includes_reasoning`, `usage_mode`, and `peak_5h_calls`
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        mcp_server.ModelRouterHTTPHandler.enable_x402 = False
        httpd = mcp_server.ThreadingHTTPServer(("127.0.0.1", port), mcp_server.ModelRouterHTTPHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = (
                f"http://127.0.0.1:{port}/api/budget"
                "?model_id=aliyun-bailian/qwen3-coder-next"
                "&daily_requests=5000&avg_input_tokens=4000&avg_output_tokens=1000"
                "&cache_hit_rate=0.5&usage_mode=automated_backend&peak_5h_calls=7500"
            )
            with urllib.request.urlopen(url, timeout=5) as resp:
                http_data = json.loads(resp.read().decode("utf-8"))
        finally:
            httpd.shutdown()
            httpd.server_close()

        self.assertEqual(http_data["matched_model"]["id"], "aliyun-bailian/qwen3-coder-next")
        self.assertAlmostEqual(http_data["budget_estimate"]["monthly_rmb"], 1152.0, places=2)
        self.assertEqual(http_data["query"]["usage_mode"], "automated_backend")
        self.assertEqual(http_data["query"]["peak_5h_calls"], 7500)

        # 3. `openapi_coze.json` documents v3 parameters
        openapi_spec = json.loads((ROOT / "engine_a_mcp_actor" / "openapi_coze.json").read_text(encoding="utf-8"))
        budget_props = (
            openapi_spec["paths"]["/api/budget"]["post"]["requestBody"]["content"]["application/json"]["schema"][
                "properties"
            ]
        )
        for field in (
            "cache_hit_rate",
            "reasoning_multiplier",
            "output_includes_reasoning",
            "usage_mode",
            "peak_5h_calls",
        ):
            self.assertIn(field, budget_props)

        # 4. FX fallback parity + marketing_pack `tc-code-latest` + apify_store_bundle byte parity
        self.assertAlmostEqual(build_site.DEFAULT_FX_USD_TO_RMB, fetch_and_enrich.FX_USD_TO_RMB, places=4)
        juejin_md = (ROOT / "marketing_pack" / "01_juejin_zhihu_article.md").read_text(encoding="utf-8")
        self.assertIn('export ANTHROPIC_MODEL="tc-code-latest"', juejin_md)
        self.assertNotIn('export ANTHROPIC_MODEL="hunyuan-t1"', juejin_md)

        apify_bundle_dir = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "apify_store_bundle"
        if apify_bundle_dir.is_dir():
            for fname in ("pricing_core.py", "mcp_server.py", "fetch_and_enrich.py"):
                src = (ROOT / "engine_a_mcp_actor" / fname).read_text(encoding="utf-8")
                bundle = (apify_bundle_dir / fname).read_text(encoding="utf-8")
                self.assertEqual(src, bundle, msg=f"apify_store_bundle/{fname} drifted from engine_a_mcp_actor/{fname}")

    def test_03_catalog_price_diff_tracking_and_dynamic_atom_feed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_models_path = tmp_root / "models_live.json"
            tmp_dist = tmp_root / "dist"

            # Seed an older snapshot where `aliyun-bailian/qwen3.5-plus` had input=1.0 RMB instead of 0.8 RMB
            seed_catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
            for m in seed_catalog["models"]:
                if m["id"] == "aliyun-bailian/qwen3.5-plus":
                    m["input_rmb_per_1m"] = 1.0
                    m["output_rmb_per_1m"] = 2.5
                    break
            seed_catalog["price_changes"] = [
                {
                    "detected_at": "2026-11-12T00:00:00Z",
                    "entity_type": "model",
                    "id": "tencent-cloud/deepseek-v3",
                    "name": "腾讯云: DeepSeek-V3.2 满血专线版",
                    "change_type": "price_update",
                    "summary_zh": "输入单价 ¥2.50 -> ¥2.00 / 1M，输出单价 ¥9.00 -> ¥8.00 / 1M",
                }
            ]
            tmp_models_path.write_text(json.dumps(seed_catalog, ensure_ascii=False, indent=2), encoding="utf-8")

            with mock.patch.object(
                fetch_and_enrich,
                "fetch_openrouter_raw",
                return_value=(fetch_and_enrich.FALLBACK_OPENROUTER_RAW, "fallback_snapshot+curated_cn_2026"),
            ):
                refreshed_1 = fetch_and_enrich.refresh_models_live(output_path=tmp_models_path)
                self.assertIn("price_changes", refreshed_1)
                changes_1 = refreshed_1["price_changes"]
                qwen_changes = [c for c in changes_1 if c.get("id") == "aliyun-bailian/qwen3.5-plus"]
                self.assertEqual(len(qwen_changes), 1)
                self.assertIn("0.8", qwen_changes[0]["summary_zh"])

                # Re-running with identical prices carries forward recent `price_changes` history
                refreshed_2 = fetch_and_enrich.refresh_models_live(output_path=tmp_models_path)
                self.assertGreaterEqual(len(refreshed_2.get("price_changes", [])), 2)

            build_site.build_site(output_dir=tmp_dist, models_path=tmp_models_path)
            atom_xml = (tmp_dist / "feeds" / "price-changes.xml").read_text(encoding="utf-8")
            root_el = ET.fromstring(atom_xml)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root_el.findall("atom:entry", ns)
            self.assertGreaterEqual(len(entries), 3)
            self.assertIn("aliyun-bailian/qwen3.5-plus", atom_xml)


class Round3Batch2HybridRouterAndFullFaqI18nTests(unittest.TestCase):
    def test_04_interactive_hybrid_router_controls_share_params_and_litellm_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dist = Path(tmpdir)
            build_site.build_site(output_dir=tmp_dist)
            cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        # 1. Interactive Tiered Routing controls inside `#hybridAdviceBox`
        self.assertIn('id="hybridRatioSelect"', cp_html)
        self.assertIn('id="hybridRoutineSelect"', cp_html)
        self.assertIn('id="openHybridConfigBtn"', cp_html)

        # 2. LiteLLM routing YAML snippet generator
        self.assertIn("function buildLiteLlmRoutingConfig(", cp_html)
        self.assertIn("model_list:", cp_html)
        self.assertIn("router_settings:", cp_html)

        # 3. URL share & restore support for `split` and `routine`
        self.assertIn('params.set("split"', cp_html)
        self.assertIn('params.set("routine"', cp_html)
        self.assertIn('params.has("split")', cp_html)
        self.assertIn('params.has("routine")', cp_html)

    def test_05_full_page_english_i18n_including_faq_and_ssr_reference_summaries(self) -> None:
        import re

        cjk_re = re.compile(r"[\u4e00-\u9fff]")
        self.assertGreaterEqual(len(build_site.FAQ_ENTRIES), 5)
        for idx, item in enumerate(build_site.FAQ_ENTRIES):
            self.assertIn("q_en", item, msg=f"FAQ #{idx} missing q_en")
            self.assertIn("a_en", item, msg=f"FAQ #{idx} missing a_en")
            self.assertTrue(item["q_en"].strip())
            self.assertTrue(item["a_en"].strip())
            self.assertIsNone(cjk_re.search(item["q_en"]), msg=f"CJK leak in FAQ #{idx} q_en")
            self.assertIsNone(cjk_re.search(item["a_en"]), msg=f"CJK leak in FAQ #{idx} a_en")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dist = Path(tmpdir)
            build_site.build_site(output_dir=tmp_dist)
            cp_html = (tmp_dist / "coding-plan-2026" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="ssrCodingPlanDetails"', cp_html)
        self.assertIn("Expand Static Official Rules &amp; Worked Examples", cp_html)
        self.assertIn("Why is a ¥200/mo Coding Plan Pro still not enough at 5,000 model calls/day?", cp_html)
        self.assertIn('data-en="Atom Feed"', cp_html)
        self.assertIn('data-en="Status Badge"', cp_html)
        self.assertIn("Built:", cp_html)


if __name__ == "__main__":
    unittest.main()
