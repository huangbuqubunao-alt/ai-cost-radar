#!/usr/bin/env python3
"""
Round 12 (v3.12) Acceptance & Regression Suite — Global Expansion & 8-Client Local AI Spend Auditor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor" / "publish_bundles" / "coze_cn_bundle"))
sys.path.insert(0, str(ROOT / "engine_b_affiliate_web"))
sys.path.insert(0, str(ROOT / "cloudflare"))

import audit_local_claude  # noqa: E402
import coze_cloud_tool  # noqa: E402
import fetch_and_enrich  # noqa: E402
import mcp_server  # noqa: E402
import pricing_core  # noqa: E402


class Round12CatalogAndMultiAgentTests(unittest.TestCase):
    def _run_cloudflare_budget_cases(self, cases: list[list[tuple[str, str]] | dict[str, str]]) -> list[dict]:
        runner = """
import fs from "node:fs";
const source = fs.readFileSync("functions/api/budget.js", "utf8");
const {onRequestGet} = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const {catalog, cases} = JSON.parse(fs.readFileSync(0, "utf8"));
const outputs = [];
for (const query of cases) {
  const qs = new URLSearchParams(query);
  const request = new Request("https://example.test/api/budget?" + qs.toString());
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

    def test_01_grok_and_global_models_pinned_and_aliases_resolved_across_all_surfaces(self) -> None:
        live_cat = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        models = live_cat["models"]
        by_id = {m["id"]: m for m in models}

        self.assertIn("x-ai/grok-4", by_id)
        self.assertIn("x-ai/grok-code-fast-1", by_id)
        self.assertEqual(by_id["x-ai/grok-4"]["region"], "global")
        self.assertAlmostEqual(by_id["x-ai/grok-4"]["input_rmb_per_1m"], 21.6, delta=0.05)
        self.assertAlmostEqual(by_id["x-ai/grok-4"]["output_rmb_per_1m"], 108.0, delta=0.05)
        self.assertEqual(by_id["x-ai/grok-code-fast-1"]["region"], "global")
        self.assertAlmostEqual(by_id["x-ai/grok-code-fast-1"]["input_rmb_per_1m"], 1.44, delta=0.05)
        self.assertAlmostEqual(by_id["x-ai/grok-code-fast-1"]["output_rmb_per_1m"], 10.8, delta=0.05)

        # Python pricing_core fuzzy alias resolution
        self.assertEqual(pricing_core.resolve_model_query(models, "grok-4")[0]["id"], "x-ai/grok-4")
        self.assertEqual(pricing_core.resolve_model_query(models, "grok-build")[0]["id"], "x-ai/grok-4")
        self.assertEqual(pricing_core.resolve_model_query(models, "grok-code-fast-1")[0]["id"], "x-ai/grok-code-fast-1")
        self.assertEqual(pricing_core.resolve_model_query(models, "gemini-2.5-pro")[0]["id"], "google/gemini-4-hydrogen")
        self.assertEqual(pricing_core.resolve_model_query(models, "gemini-2.5-flash")[0]["id"], "google/gemini-3.8-flash")

        # CLI audit_local_claude offline fallback catalog also includes x-ai/grok-4 and x-ai/grok-code-fast-1
        fb_ids = {m["id"] for m in audit_local_claude.EMBEDDED_FALLBACK_MODELS}
        self.assertIn("x-ai/grok-4", fb_ids)
        self.assertIn("x-ai/grok-code-fast-1", fb_ids)
        self.assertIn("google/gemini-4-hydrogen", fb_ids)
        self.assertIn("google/gemini-3.8-flash", fb_ids)

        # Cloudflare /api/budget exact & alias resolution for x-ai/grok-4
        cf_res = self._run_cloudflare_budget_cases([{"model_id": "x-ai/grok-4", "daily_calls": "100"}])[0]
        self.assertEqual(cf_res["status"], 200)
        self.assertEqual(cf_res["body"]["model_id"], "x-ai/grok-4")

    def test_02_eight_client_local_scanner_zst_sqlite_and_global_usd_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_home = Path(tmpdir)
            now_ts = time.time()

            # 1. Claude Code (~/.claude/projects) -> 1 req, in=30000, cached=20000, out=1000
            claude_dir = fake_home / ".claude" / "projects" / "app-one"
            claude_dir.mkdir(parents=True)
            (claude_dir / "sess1.jsonl").write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "id": "msg_cc_1",
                            "model": "claude-sonnet-4-20250514",
                            "usage": {
                                "input_tokens": 5000,
                                "cache_creation_input_tokens": 5000,
                                "cache_read_input_tokens": 20000,
                                "output_tokens": 1000,
                            },
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            # 2. Codex CLI active + .jsonl.zst archive -> 2 reqs total, in=40000 (25k + 15k), cached=20000 (15k + 5k), out=1200 (700 + 500)
            codex_sess_dir = fake_home / ".codex" / "sessions" / "2026" / "11"
            codex_arch_dir = fake_home / ".codex" / "archived_sessions"
            codex_sess_dir.mkdir(parents=True)
            codex_arch_dir.mkdir(parents=True)
            (codex_sess_dir / "rollout-active.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"type": "turn_context", "payload": {"model": "gpt-6-astra"}}),
                        json.dumps(
                            {
                                "type": "token_usage_record",
                                "response_id": "resp_cx_active_1",
                                "input_tokens": 25000,
                                "cached_input_tokens": 15000,
                                "output_tokens": 700,
                                "reasoning_output_tokens": 200,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            archived_raw = (
                "\n".join(
                    [
                        json.dumps({"type": "turn_context", "payload": {"model": "gpt-5-codex"}}),
                        json.dumps(
                            {
                                "type": "token_usage_record",
                                "response_id": "resp_cx_arch_1",
                                "input_tokens": 15000,
                                "cached_input_tokens": 5000,
                                "output_tokens": 500,
                            }
                        ),
                    ]
                )
                + "\n"
            ).encode("utf-8")
            zst_path = codex_arch_dir / "rollout-archived.jsonl.zst"
            try:
                from compression import zstd as _zstd  # type: ignore[attr-defined]

                zst_path.write_bytes(_zstd.compress(archived_raw))
            except ImportError:
                proc_zst = subprocess.run(["zstd", "-c"], input=archived_raw, capture_output=True, check=True)
                zst_path.write_bytes(proc_zst.stdout)

            # 3. Google Antigravity (~/.gemini/antigravity/brain/<conv>/.system_generated/logs/transcript.jsonl)
            # Place BOTH transcript.jsonl AND transcript_full.jsonl to prove zero double-counting!
            # Additive: step 1 (10000 + 0 = 10000, out=400) + step 2 (8000 + 10000 = 18000, out=600) => 2 reqs, in=28000, cached=10000, out=1000
            agy_logs = fake_home / ".gemini" / "antigravity" / "brain" / "conv-agy-01" / ".system_generated" / "logs"
            (agy_logs / "chunks").mkdir(parents=True)
            agy_content = "\n".join(
                [
                    json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "SECRET_AGY_PROMPT"}),
                    json.dumps(
                        {
                            "step_index": 1,
                            "type": "PLANNER_RESPONSE",
                            "source": "MODEL",
                            "input_tokens": 10000,
                            "cache_read_tokens": 0,
                            "output_tokens": 400,
                        }
                    ),
                    json.dumps(
                        {
                            "step_index": 2,
                            "type": "PLANNER_RESPONSE",
                            "source": "MODEL",
                            "input_tokens": 8000,
                            "cache_read_tokens": 10000,
                            "output_tokens": 600,
                        }
                    ),
                ]
            ) + "\n"
            (agy_logs / "transcript.jsonl").write_text(agy_content, encoding="utf-8")
            (agy_logs / "transcript_full.jsonl").write_text(agy_content, encoding="utf-8")
            (agy_logs / "chunks" / "chunk_0.jsonl").write_text(agy_content, encoding="utf-8")

            # 4. OpenCode (~/.local/share/opencode/opencode.db + legacy storage/message)
            # Fresh SQLite row: msg_oc_fresh_1 -> additive in = 10000 + 20000 + 2000 = 32000, cached = 20000, out = 500
            # Stale 90d SQLite row: msg_oc_stale_90d -> MUST BE EXCLUDED when days=30!
            # Legacy JSON duplicate of msg_oc_fresh_1 -> MUST NOT double-count!
            # Legacy JSON unique msg_oc_legacy_2 -> additive in = 5000 + 3000 + 0 = 8000, cached = 3000, out = 300
            # Total OpenCode expected: 2 reqs, in = 40000, cached = 23000, out = 800
            oc_root = fake_home / ".local" / "share" / "opencode"
            oc_msg_dir = oc_root / "storage" / "message" / "ses_01"
            oc_msg_dir.mkdir(parents=True)
            db_path = oc_root / "opencode.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT)"
                )
                fresh_ms = int((now_ts - 3600) * 1000)
                stale_ms = int((now_ts - 90 * 86400) * 1000)
                conn.execute(
                    "INSERT INTO message VALUES (?, ?, ?, ?)",
                    (
                        "msg_oc_fresh_1",
                        "ses_01",
                        fresh_ms,
                        json.dumps(
                            {
                                "role": "assistant",
                                "modelID": "claude-sonnet-4",
                                "providerID": "anthropic",
                                "cost": 0.08,
                                "tokens": {
                                    "input": 10000,
                                    "output": 500,
                                    "reasoning": 100,
                                    "cache": {"read": 20000, "write": 2000},
                                },
                            }
                        ),
                    ),
                )
                conn.execute(
                    "INSERT INTO message VALUES (?, ?, ?, ?)",
                    (
                        "msg_oc_stale_90d",
                        "ses_old",
                        stale_ms,
                        json.dumps(
                            {
                                "role": "assistant",
                                "modelID": "claude-opus-4",
                                "tokens": {"input": 999999, "output": 99999, "cache": {"read": 0, "write": 0}},
                            }
                        ),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            # Duplicate legacy JSON for msg_oc_fresh_1 + unique msg_oc_legacy_2
            (oc_msg_dir / "msg_oc_fresh_1.json").write_text(
                json.dumps(
                    {
                        "id": "msg_oc_fresh_1",
                        "sessionID": "ses_01",
                        "role": "assistant",
                        "modelID": "claude-sonnet-4",
                        "tokens": {"input": 10000, "output": 500, "cache": {"read": 20000, "write": 2000}},
                    }
                ),
                encoding="utf-8",
            )
            (oc_msg_dir / "msg_oc_legacy_2.json").write_text(
                json.dumps(
                    {
                        "id": "msg_oc_legacy_2",
                        "sessionID": "ses_01",
                        "role": "assistant",
                        "modelID": "grok-code-fast-1",
                        "tokens": {"input": 5000, "output": 300, "cache": {"read": 3000, "write": 0}},
                    }
                ),
                encoding="utf-8",
            )

            # 5. xAI Grok CLI (~/.grok/sessions/my-proj/sess-g1/updates.jsonl + summary.json)
            # Inclusive inputTokens=25000 (contains cachedReadTokens=15000) + cacheCreationTokens=1000 => in=26000, cached=15000, out=800
            grok_sess = fake_home / ".grok" / "sessions" / "my-proj" / "sess-g1"
            grok_sess.mkdir(parents=True)
            (grok_sess / "summary.json").write_text(json.dumps({"current_model_id": "grok-4"}), encoding="utf-8")
            (grok_sess / "updates.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"sessionUpdate": "delta", "usage": {"inputTokens": 99999, "outputTokens": 999}}),
                        json.dumps(
                            {
                                "sessionUpdate": "turn_completed",
                                "turnId": "grok_turn_1",
                                "usage": {
                                    "inputTokens": 25000,
                                    "cachedReadTokens": 15000,
                                    "cacheCreationTokens": 1000,
                                    "outputTokens": 800,
                                    "reasoningTokens": 200,
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            # 6. Tencent WorkBuddy & CodeBuddy (~/.workbuddy + ~/.codebuddy) -> 2 reqs, in=20000, cached=8000, out=600
            wb_dir = fake_home / ".workbuddy" / "projects" / "demo-wb"
            cb_dir = fake_home / ".codebuddy" / "projects" / "demo-cb"
            wb_dir.mkdir(parents=True)
            cb_dir.mkdir(parents=True)
            (wb_dir / "s1.jsonl").write_text(
                json.dumps(
                    {
                        "id": "wb_1",
                        "model": "hunyuan-t1-latest",
                        "usage": {"prompt_tokens": 12000, "cached_tokens": 5000, "completion_tokens": 350},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (cb_dir / "s2.jsonl").write_text(
                json.dumps(
                    {
                        "id": "cb_1",
                        "model": "deepseek-v3",
                        "usage": {"prompt_tokens": 8000, "cached_tokens": 3000, "completion_tokens": 250},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            # 7. Qwen Code / Qoder (~/.qwen + ~/.qoder) -> 1 req, in=16000, cached=6000, out=400
            qw_dir = fake_home / ".qwen" / "projects" / "demo-qw"
            qw_dir.mkdir(parents=True)
            (qw_dir / "q1.jsonl").write_text(
                json.dumps(
                    {
                        "id": "qw_1",
                        "model": "qwen3-coder-next",
                        "usage": {"input_tokens": 16000, "cached_input_tokens": 6000, "output_tokens": 400},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            # 8. Cline (VS Code globalStorage) -> 1 req, in=10000 (2000+8000+0), cached=8000, out=500
            cline_dir = (
                fake_home
                / "Library"
                / "Application Support"
                / "Code"
                / "User"
                / "globalStorage"
                / "saoudrizwan.claude-dev"
                / "tasks"
                / "9901"
            )
            cline_dir.mkdir(parents=True)
            (cline_dir / "ui_messages.json").write_text(
                json.dumps(
                    [
                        {
                            "ts": 1763200001000,
                            "type": "say",
                            "say": "api_req_started",
                            "text": json.dumps(
                                {
                                    "model": "claude-sonnet-4",
                                    "tokensIn": 2000,
                                    "tokensOut": 500,
                                    "cacheReads": 8000,
                                    "cacheWrites": 0,
                                }
                            ),
                        }
                    ]
                ),
                encoding="utf-8",
            )

            rep = audit_local_claude.scan_local_coding_logs(
                client="all", home_dir=fake_home, days=30.0, seats=1, offline=True
            )
            cb = {x["client"]: x for x in rep["client_breakdown"]}
            self.assertEqual(
                set(cb.keys()),
                {"claude", "codex", "antigravity", "opencode", "grok", "workbuddy", "qwen", "cline"},
            )
            self.assertEqual(cb["claude"]["requests"], 1)
            self.assertEqual(cb["codex"]["requests"], 2)
            self.assertEqual(cb["codex"]["input_tokens"], 40_000)
            self.assertEqual(cb["antigravity"]["requests"], 2)
            self.assertEqual(cb["antigravity"]["input_tokens"], 28_000)
            self.assertEqual(cb["antigravity"]["cached_input_tokens"], 10_000)
            self.assertEqual(cb["opencode"]["requests"], 2)
            self.assertEqual(cb["opencode"]["input_tokens"], 40_000)
            self.assertEqual(cb["opencode"]["cached_input_tokens"], 23_000)
            self.assertEqual(cb["grok"]["requests"], 1)
            self.assertEqual(cb["grok"]["input_tokens"], 26_000)
            self.assertEqual(cb["grok"]["cached_input_tokens"], 15_000)
            self.assertEqual(cb["workbuddy"]["requests"], 2)
            self.assertEqual(cb["workbuddy"]["input_tokens"], 20_000)
            self.assertEqual(cb["qwen"]["requests"], 1)
            self.assertEqual(cb["qwen"]["input_tokens"], 16_000)
            self.assertEqual(cb["cline"]["requests"], 1)
            self.assertEqual(cb["cline"]["input_tokens"], 10_000)

            # Total across all 8 clients: 1+2+2+2+1+2+1+1 = 12 requests; input = 210,000
            self.assertEqual(rep["total_requests"], 12)
            self.assertEqual(rep["total_input_tokens"], 210_000)

            # Verify Global / USD / English mode & byte-identical audit_ai_spend.py alias
            spend_alias = ROOT / "engine_a_mcp_actor" / "audit_ai_spend.py"
            self.assertTrue(spend_alias.is_file())
            self.assertEqual(
                spend_alias.read_bytes(),
                (ROOT / "engine_a_mcp_actor" / "audit_local_claude.py").read_bytes(),
            )

            env = {**os.environ, "HOME": str(fake_home), "USERPROFILE": str(fake_home)}
            proc_en = subprocess.run(
                [
                    sys.executable,
                    "-W",
                    "error",
                    str(spend_alias),
                    "--client",
                    "all",
                    "--days",
                    "30",
                    "--offline",
                    "--lang",
                    "en",
                    "--region",
                    "global",
                    "--currency",
                    "usd",
                ],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("AI Cost Radar", proc_en.stdout)
            self.assertIn("$", proc_en.stdout)
            self.assertIn("RunPod", proc_en.stdout)
            self.assertIn("lang=en", proc_en.stdout)
            self.assertIn("region=global", proc_en.stdout)
            self.assertNotIn("阿里云百炼", proc_en.stdout)

            rep_global = audit_local_claude.scan_local_coding_logs(
                client="all",
                home_dir=fake_home,
                days=30.0,
                seats=1,
                offline=True,
                lang="en",
                region="global",
                currency="usd",
            )
            self.assertIn("baseline_monthly_usd", rep_global["totals"])
            self.assertIn("optimized_payg_monthly_usd", rep_global["totals"])
            self.assertIn("self_host_verdict", rep_global["totals"])
            self.assertIn("lang=en", rep_global["web_deep_link"])
            self.assertIn("region=global", rep_global["web_deep_link"])
            for row in rep_global["model_breakdown"]:
                self.assertNotIn("aliyun-bailian/", row["recommended_model_id"])

    def test_03_five_surface_new_clients_parity_and_global_bill_audit(self) -> None:
        models = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))["models"]

        agy_snip = "\n".join(
            [
                json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "SECRET_AGY"}),
                json.dumps(
                    {
                        "step_index": 1,
                        "type": "PLANNER_RESPONSE",
                        "input_tokens": 8000,
                        "cache_read_tokens": 12000,
                        "output_tokens": 600,
                    }
                ),
            ]
        )
        grok_snip = "\n".join(
            [
                json.dumps({"sessionUpdate": "delta", "usage": {"inputTokens": 99999, "outputTokens": 999}}),
                json.dumps(
                    {
                        "sessionUpdate": "turn_completed",
                        "turnId": "t_g1",
                        "model": "grok-4",
                        "usage": {
                            "inputTokens": 25000,
                            "cachedReadTokens": 15000,
                            "cacheCreationTokens": 1000,
                            "outputTokens": 800,
                            "reasoningTokens": 200,
                        },
                    }
                ),
            ]
        )
        opencode_snip = json.dumps(
            [
                {
                    "id": "msg_oc_web_1",
                    "sessionID": "ses_99",
                    "role": "assistant",
                    "modelID": "claude-opus-5.5",
                    "tokens": {"input": 10000, "output": 500, "reasoning": 100, "cache": {"read": 20000, "write": 2000}},
                }
            ]
        )
        wb_snip = json.dumps(
            {
                "id": "wb_web_1",
                "model": "hunyuan-t1-latest",
                "usage": {"prompt_tokens": 12000, "cached_tokens": 4000, "completion_tokens": 400},
            }
        ) + "\n" + json.dumps(
            {
                "id": "qw_web_1",
                "model": "qwen3-coder-next",
                "usage": {"input_tokens": 8000, "cached_input_tokens": 3000, "output_tokens": 300},
            }
        )

        snippets = [agy_snip, grok_snip, opencode_snip, wb_snip]
        file_names = [
            "/Users/alice/.gemini/antigravity/brain/conv-xyz/.system_generated/logs/transcript.jsonl",
            "/Users/alice/.grok/sessions/my-repo/sess-77/updates.jsonl",
            "/Users/alice/.local/share/opencode/storage/message/ses_99/msg_oc_web_1.json",
            "C:\\Users\\alice\\.workbuddy\\projects\\demo\\wb_qwen.jsonl",
        ]
        # Expected totals:
        # agy: 1 req, in=20000, cached=12000, out=600
        # grok: 1 req, in=26000, cached=15000, out=800
        # opencode: 1 req, in=32000, cached=20000, out=500
        # wb+qwen: 2 reqs, in=20000, cached=7000, out=700
        # SUM: 5 reqs, in=98000, cached=54000, out=2600
        merged_py = pricing_core.merge_usage_log_snippets(
            snippets, days_observed=10, file_names=file_names, models=models
        )
        self.assertEqual(merged_py["total_requests"], 5)
        self.assertEqual(merged_py["total_input_tokens"], 98_000)
        self.assertEqual(merged_py["cached_input_tokens"], 54_000)
        self.assertEqual(merged_py["total_output_tokens"], 2_600)

        fb_names = {x["file_name"] for x in merged_py["file_breakdown"]}
        self.assertEqual(
            fb_names,
            {
                "antigravity/conv-xyz/transcript.jsonl",
                "grok/sess-77/updates.jsonl",
                "opencode/ses_99/msg_oc_web_1.json",
                "workbuddy/demo/wb_qwen.jsonl",
            },
        )
        for nm in fb_names:
            self.assertNotIn("alice", nm.lower())

        # Domestic default vs Global target_region="global"
        audit_cn = pricing_core.audit_csv_bill(models, merged_py, days_observed=10, team_size=1)
        audit_gl = pricing_core.audit_csv_bill(models, merged_py, days_observed=10, team_size=1, target_region="global")
        self.assertIsNotNone(audit_cn["coding_plan_option"])
        self.assertIsNone(audit_gl["coding_plan_option"])
        for item in audit_gl["line_items"]:
            if item["action"] != "keep_current":
                self.assertNotIn("aliyun-bailian/", item["recommended_model_id"])
                self.assertNotIn("tencent-cloud/", item["recommended_model_id"])
                self.assertIn(item["recommended_env_key_var"], {"NOVITA_API_KEY", "OPENROUTER_API_KEY"})

        # Cloudflare /api/budget parity (both CN default and region=global)
        cf_q_gl: list[tuple[str, str]] = [
            ("model_id", "auto"),
            ("days_observed", "10"),
            ("team_size", "1"),
            ("region", "global"),
        ]
        for s, fn in zip(snippets, file_names):
            cf_q_gl.append(("usage_snippet", s))
            cf_q_gl.append(("usage_file", fn))
        cf_out = self._run_cloudflare_budget_cases([cf_q_gl])[0]
        self.assertEqual(cf_out["status"], 200)
        cf_body = cf_out["body"]
        self.assertEqual(cf_body["parsed_usage_summary"]["total_requests"], 5)
        self.assertEqual(cf_body["parsed_usage_summary"]["total_input_tokens"], 98_000)
        self.assertEqual(cf_body["parsed_usage_summary"]["cached_input_tokens"], 54_000)
        self.assertIsNone(cf_body["bill_audit"]["coding_plan_option"])
        self.assertAlmostEqual(
            cf_body["bill_audit"]["totals"]["optimized_payg_monthly_rmb"],
            audit_gl["totals"]["optimized_payg_monthly_rmb"],
            delta=0.05,
        )

        # Coze parity
        coze_out = coze_cloud_tool.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "auto",
                "usage_snippets": snippets,
                "usage_file_names": file_names,
                "days_observed": 10,
                "team_size": 1,
            }
        )
        self.assertEqual(coze_out["parsed_usage_summary"]["total_requests"], 5)
        self.assertEqual(coze_out["parsed_usage_summary"]["total_input_tokens"], 98_000)

    def test_04_global_affiliate_slots_english_auditor_route_and_dual_cli_hosting(self) -> None:
        import build_site

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dist_default = tmp_path / "dist_default"
            summary = build_site.build_site(
                dist_dir=dist_default,
                site_url="https://ai-cost-radar-nlu.pages.dev/",
            )
            self.assertGreaterEqual(summary["seo_pages_count"], 7)

            # 1. Dual hosted CLI scripts (byte-identical)
            cli_legacy = dist_default / "audit_local_claude.py"
            cli_global = dist_default / "audit_ai_spend.py"
            self.assertTrue(cli_legacy.is_file())
            self.assertTrue(cli_global.is_file())
            self.assertEqual(cli_legacy.read_bytes(), cli_global.read_bytes())

            # 2. 6th static route /ai-coding-spend-auditor/index.html is English-first SSR
            en_page = dist_default / "ai-coding-spend-auditor" / "index.html"
            self.assertTrue(en_page.is_file())
            en_html = en_page.read_text(encoding="utf-8")
            self.assertIn('<html lang="en"', en_html)
            self.assertIn(
                '<link rel="canonical" href="https://ai-cost-radar-nlu.pages.dev/ai-coding-spend-auditor/" />',
                en_html,
            )
            self.assertIn("Claude Code", en_html)
            self.assertIn("Codex", en_html)
            self.assertIn("RunPod", en_html)

            # 3. Affiliate slot apify_affiliate_url exists in DEFAULT_AFFILIATES & config.json
            self.assertIn("apify_affiliate_url", build_site.DEFAULT_AFFILIATES)
            self.assertIn("runpod_affiliate_url", build_site.DEFAULT_AFFILIATES)
            self.assertIn("railway_affiliate_url", build_site.DEFAULT_AFFILIATES)
            cfg_file = ROOT / "config.json"
            if cfg_file.is_file():
                cfg_json = json.loads(cfg_file.read_text(encoding="utf-8"))
                self.assertIn("apify_affiliate_url", cfg_json.get("global_affiliates_usd", {}))

            # 4. Dynamic rel="noopener sponsored" when global affiliate URLs carry referral params vs bare defaults
            custom_cfg = tmp_path / "custom_config.json"
            custom_cfg.write_text(
                json.dumps(
                    {
                        "global_affiliates_usd": {
                            "runpod_affiliate_url": "https://runpod.io?ref=radar123",
                            "apify_affiliate_url": "https://apify.com?fpr=radar123",
                            "railway_affiliate_url": "https://railway.com?referralCode=radar123",
                            "digitalocean_affiliate_url": "https://www.digitalocean.com",
                            "openrouter_url": "https://openrouter.ai",
                        }
                    }
                ),
                encoding="utf-8",
            )
            loaded_aff = build_site.load_affiliates(custom_cfg)
            self.assertEqual(loaded_aff["runpod_affiliate_url"], "https://runpod.io?ref=radar123")
            self.assertEqual(loaded_aff["apify_affiliate_url"], "https://apify.com?fpr=radar123")
            self.assertEqual(loaded_aff["railway_affiliate_url"], "https://railway.com?referralCode=radar123")

            # 5. Route allowlists in functions/events.js and cloudflare/events_reconcile.py include /ai-coding-spend-auditor/
            import events_reconcile

            self.assertIn("/ai-coding-spend-auditor/", events_reconcile.ALLOWED_ROUTES)
            events_js = (ROOT / "functions" / "events.js").read_text(encoding="utf-8")
            self.assertIn('"/ai-coding-spend-auditor/"', events_js)

    def test_05_release_pipeline_public_repo_isolation_and_v312_verify_gate(self) -> None:
        import build_site
        import prepare_release

        # Build main dist/ so cloudflare/verify_release.py validates all 6 pages + dual CLI scripts
        build_site.build_site(site_url="https://ai-cost-radar-nlu.pages.dev/")
        proc_verify = subprocess.run(
            [sys.executable, "-W", "error", str(ROOT / "cloudflare" / "verify_release.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_verify.returncode, 0, proc_verify.stderr or proc_verify.stdout)

        # Public repo export must include audit_ai_spend.py and test_round12_product_iteration.py,
        # and MUST NOT leak docs/GLOBAL_LAUNCH_PLAYBOOK.md!
        self.assertIn("engine_a_mcp_actor/audit_ai_spend.py", prepare_release.FILES)
        self.assertIn("test_round12_product_iteration.py", prepare_release.FILES)
        self.assertNotIn("docs/GLOBAL_LAUNCH_PLAYBOOK.md", prepare_release.FILES)

        playbook = ROOT / "docs" / "GLOBAL_LAUNCH_PLAYBOOK.md"
        if (ROOT / "sync_config_to_cloud.sh").is_file():
            # Authoring workspace check (guarded so CI inside gh_pages_repo also passes cleanly)
            self.assertTrue(playbook.is_file(), "Missing local-only docs/GLOBAL_LAUNCH_PLAYBOOK.md in authoring repo")
            pb_text = playbook.read_text(encoding="utf-8")
            self.assertIn("Show HN", pb_text)
            self.assertIn("PartnerStack", pb_text)
            self.assertIn("Apify", pb_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            pub_target = Path(tmpdir) / "public_export"
            prepare_release.prepare(pub_target)
            self.assertTrue((pub_target / "engine_a_mcp_actor" / "audit_ai_spend.py").is_file())
            self.assertTrue((pub_target / "test_round12_product_iteration.py").is_file())
            self.assertFalse((pub_target / "docs" / "GLOBAL_LAUNCH_PLAYBOOK.md").exists())

    def test_06_unified_novita_ai_and_railway_global_monetization_consolidation(self) -> None:
        """Verify Plan A consolidation: unified Novita AI (API + Coding Plan + GPU) + Railway proxy, Apify removed from UI matrix."""
        import build_site
        import fetch_and_enrich

        # 1. Config & DEFAULT_AFFILIATES support novita_affiliate_url + active user referral URLs
        self.assertIn("novita_affiliate_url", build_site.DEFAULT_AFFILIATES)
        cfg_json = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        gl_cfg = cfg_json.get("global_affiliates_usd", {})
        self.assertIn("novita.ai", gl_cfg.get("novita_affiliate_url", ""))
        self.assertIn("railway.com", gl_cfg.get("railway_affiliate_url", ""))

        # 2. Curated Novita AI global models carry novita_affiliate_url, api.novita.ai base URL, and NOVITA_API_KEY
        aff_map = fetch_and_enrich.resolve_affiliate_map(cfg_json)
        self.assertIn("novita_affiliate_url", aff_map)
        novita_models = fetch_and_enrich.build_curated_global_partner_models(aff_map)
        self.assertGreaterEqual(len(novita_models), 3)
        for nm in novita_models:
            self.assertEqual(nm["region"], "global")
            self.assertEqual(nm["provider_config_key"], "novita_affiliate_url")
            self.assertIn("api.novita.ai", nm["api_base_url"])
            self.assertEqual(pricing_core._resolve_model_env_key_var(nm), "NOVITA_API_KEY")

        # 3. Built HTML surfaces Novita AI + Railway in partner matrix and removes off-topic apify-agent-tools card
        with tempfile.TemporaryDirectory() as tmpdir:
            dist_tmp = Path(tmpdir) / "dist"
            build_site.build_site(dist_dir=dist_tmp, site_url="https://ai-cost-radar-nlu.pages.dev/")
            en_html = (dist_tmp / "ai-coding-spend-auditor" / "index.html").read_text(encoding="utf-8")
            self.assertIn("novita-ai-cloud", en_html)
            self.assertIn("railway-litellm-host", en_html)
            self.assertNotIn('id: "apify-agent-tools"', en_html)
            self.assertTrue(
                build_site.is_sponsored_link(
                    "https://railway.com?referralCode=aTaBV1",
                    config_key="railway_affiliate_url",
                )
            )
            self.assertTrue(
                build_site.is_sponsored_link(
                    "https://novita.ai/?ref=ngyxnguh&utm_source=affiliate",
                    config_key="novita_affiliate_url",
                )
            )
            self.assertIn('id="cfgModalPartnerCta"', en_html)
            self.assertIn("renderNovitaCompanionCtaHtml", en_html)
            self.assertIn("syncConfigModalPartnerCta", en_html)
            self.assertIn("primary_result_novita", en_html)
            self.assertIn("config_modal_novita", en_html)

    def test_07_agent_guardian_bilingual_landing_page_and_telemetry(self) -> None:
        """Verify Task D-01: /agent-guardian/ bilingual SSR page (>=4 tables), verified facts, cross-links & D1 telemetry route."""
        from html.parser import HTMLParser
        import build_site
        import events_reconcile

        class GuardianParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.tables: list[str] = []
                self.canonical: str | None = None
                self.json_ld_types: list[str] = []
                self._in_json_ld = False
                self._buf: list[str] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                attr_map = dict(attrs)
                if tag == "table":
                    self.tables.append(attr_map.get("id") or "")
                elif tag == "link" and attr_map.get("rel") == "canonical":
                    self.canonical = attr_map.get("href")
                elif tag == "script" and attr_map.get("type") == "application/ld+json":
                    self._in_json_ld = True
                    self._buf = []

            def handle_endtag(self, tag: str) -> None:
                if tag == "script" and self._in_json_ld:
                    self._in_json_ld = False
                    payload = json.loads("".join(self._buf))
                    if isinstance(payload, dict) and "@type" in payload:
                        self.json_ld_types.append(str(payload["@type"]))

            def handle_data(self, data: str) -> None:
                if self._in_json_ld:
                    self._buf.append(data)

        with tempfile.TemporaryDirectory() as tmpdir:
            dist_tmp = Path(tmpdir) / "dist"
            summary = build_site.build_site(
                dist_dir=dist_tmp,
                site_url="https://ai-cost-radar-nlu.pages.dev/",
            )
            self.assertGreaterEqual(summary["seo_pages_count"], 7)

            ag_page = dist_tmp / "agent-guardian" / "index.html"
            self.assertTrue(ag_page.is_file(), "Missing dist/agent-guardian/index.html")
            ag_html = ag_page.read_text(encoding="utf-8")

            parser = GuardianParser()
            parser.feed(ag_html)
            self.assertEqual(
                parser.canonical,
                "https://ai-cost-radar-nlu.pages.dev/agent-guardian/",
            )
            self.assertGreaterEqual(len(parser.tables), 4, f"Expected >= 4 tables, got {parser.tables}")
            self.assertEqual(
                set(parser.tables),
                {
                    "agBareVsGuardianTable",
                    "agModeCompareTable",
                    "agCliMatrixTable",
                    "agReleaseMatrixTable",
                },
            )
            self.assertIn("SoftwareApplication", parser.json_ld_types)
            self.assertIn("FAQPage", parser.json_ld_types)

            # Strictly verified v3.20.0 facts from Agent Guardian README.md
            for expected_fact in (
                "v3.20.0",
                "XNU Seatbelt",
                "HostNetworkBroker",
                "502",
                "403",
                "Claude Code",
                "Codex CLI",
                "Gemini CLI",
                "OpenCode",
                "ag mcp vault-secrets",
                "--worktree",
                "Dist/Agent-Guardian-3.20.0-arm64.dmg".lower(),
                "cargo test --locked --offline",
                'data-offer-id="agent-guardian-mac-dmg"',
                'data-offer-id="agent-guardian-waitlist"',
                "data-zh=",
                "data-en=",
            ):
                self.assertIn(expected_fact.lower(), ag_html.lower())

            # Inline JS syntax check via node --check
            import re

            scripts = re.findall(r"<script>([\s\S]*?)</script>", ag_html)
            self.assertGreaterEqual(len(scripts), 1)
            for script in scripts:
                subprocess.run(["node", "--check"], input=script, text=True, check=True)

            # Sitemap & cross-links from index.html and /ai-coding-spend-auditor/
            sitemap_xml = (dist_tmp / "sitemap.xml").read_text(encoding="utf-8")
            self.assertIn("https://ai-cost-radar-nlu.pages.dev/agent-guardian/", sitemap_xml)
            root_html = (dist_tmp / "index.html").read_text(encoding="utf-8")
            auditor_html = (dist_tmp / "ai-coding-spend-auditor" / "index.html").read_text(encoding="utf-8")
            self.assertIn("agent-guardian/", root_html)
            self.assertIn("../agent-guardian/", auditor_html)

        # D1 route allowlists in both events_reconcile.py and functions/events.js
        self.assertIn("/agent-guardian/", events_reconcile.ALLOWED_ROUTES)
        ok, _, clean = events_reconcile.validate_event_payload(
            {
                "event_name": "affiliate_click",
                "day_bucket": "2026-11-22",
                "browser_day_id": "ag_test_user_01",
                "route": "/agent-guardian/",
                "offer_id": "agent-guardian-mac-dmg",
                "slot_id": "guardian_hero_dmg",
            }
        )
        self.assertTrue(ok)
        self.assertEqual(clean["route"], "/agent-guardian/")
        self.assertEqual(clean["offer_id"], "agent-guardian-mac-dmg")

        events_js = (ROOT / "functions" / "events.js").read_text(encoding="utf-8")
        self.assertIn('"/agent-guardian/"', events_js)

        node_events_runner = """
import fs from "node:fs";
const source = fs.readFileSync("functions/events.js", "utf8");
const { onRequestPost } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
let capturedBinds = null;
const mockDb = {
  prepare() {
    return {
      bind(...args) {
        capturedBinds = args;
        return { run: async () => ({ success: true }) };
      }
    };
  }
};
const req = new Request("https://example.test/events", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    event_name: "affiliate_click",
    day_bucket: "2026-11-22",
    browser_day_id: "ag_user_1234",
    route: "/agent-guardian/",
    source_channel: "direct_or_unknown",
    offer_id: "agent-guardian-waitlist",
    slot_id: "guardian_hero_waitlist"
  })
});
const res = await onRequestPost({ request: req, env: { DB: mockDb } });
console.log(JSON.stringify({ status: res.status, capturedBinds }));
"""
        proc_ev = subprocess.run(
            ["node", "--input-type=module", "-e", node_events_runner],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        ev_out = json.loads(proc_ev.stdout.strip())
        self.assertEqual(ev_out["status"], 202)
        self.assertEqual(ev_out["capturedBinds"][2], "/agent-guardian/")
        self.assertEqual(ev_out["capturedBinds"][5], "agent-guardian-waitlist")


if __name__ == "__main__":
    unittest.main()
