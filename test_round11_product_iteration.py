#!/usr/bin/env python3
"""
Round 11 (v3.11) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. Multi-Client AI Coding Session Ecosystem across Python (`pricing_core.py`), MCP (`mcp_server.py`),
       Cloudflare (`functions/api/budget.js`), Coze (`coze_cloud_tool.py`), and `apify_store_bundle`:
       - Exact OpenAI Codex CLI (`~/.codex/sessions/**/*.jsonl`) parsing:
         * Tracks sticky `turn_context.payload.model` (e.g. `gpt-6-astra`, `codex-mini-latest`) per file.
         * Parses `token_usage_record.payload.usage` (`input_tokens`, `cached_input_tokens` as subset,
           `cache_write_input_tokens` WITHOUT Anthropic additive over-counting, `output_tokens`,
           `reasoning_output_tokens`) and deduplicates `response_id` retries.
         * Skips `event_msg` (`payload.type == "token_count"`) whenever `token_usage_record` exists in that file
           (0% double-counting!), while supporting legacy `event_msg:token_count` (`info.last_token_usage`)
           fallback with cumulative `total_tokens` snapshot deduplication when `token_usage_record` is absent.
       - Exact VS Code Cline / Roo Code (`tasks/<id>/ui_messages.json`) parsing:
         * Parses `say == "api_req_started"` serialized JSON `text` (`tokensIn`, `tokensOut`, `cacheWrites`,
           `cacheReads`, `cost`, `model`) with Anthropic additive cache math (`tokensIn + cacheReads + cacheWrites`)
           while ignoring non-API chat UI rows (`say == "text"`).
       - Explicit 2026 Codex/OpenAI model alias resolution (`gpt-6-astra`, `gpt-5-codex` -> `openai/gpt-5.4`;
         `codex-mini-latest` -> `openai/gpt-5.4-mini`) across all surfaces.
       - PII-safe `sanitize_usage_file_label` preserving `codex/<rollout>.jsonl` and `cline/<task_id>/ui_messages.json`
         with zero OS username leaks (`/Users/alice/...`, `C:\\Users\\alice\\...`).
    2. Upgraded zero-dependency local CLI scanner (`engine_a_mcp_actor/audit_local_claude.py`):
       - `--client {all,claude,codex,cline}` auto-discovers `~/.claude/projects`, `~/.codex/sessions`, and
         VS Code / Cursor Cline & Roo Code `tasks/` directories in one read-only pass, emitting `client_breakdown`
         while maintaining 100% backward compatibility with `scan_claude_projects_dir(root_dir)` and `--dir`.
"""

from __future__ import annotations

import json
import os
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

import coze_cloud_tool  # noqa: E402
import mcp_server  # noqa: E402
import pricing_core  # noqa: E402


CODEX_MODERN_SESSION_JSONL = "\n".join(
    [
        json.dumps(
            {
                "timestamp": "2026-11-15T10:00:00Z",
                "type": "session_meta",
                "payload": {"id": "sess_codex_01", "cwd": "/Users/alice/secret-repo"},
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-11-15T10:00:01Z",
                "type": "turn_context",
                "payload": {"model": "gpt-6-astra", "effort": "high"},
            }
        ),
        # Turn 1: token_usage_record + duplicate retry of resp_codex_01 + matching event_msg(token_count)
        # Note: input_tokens=28833 ALREADY includes cached_input_tokens=14336; cache_write_input_tokens=0 is present!
        json.dumps(
            {
                "timestamp": "2026-11-15T10:00:05Z",
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "turn_1",
                    "response_id": "resp_codex_01",
                    "usage": {
                        "input_tokens": 28833,
                        "cached_input_tokens": 14336,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 200,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 29033,
                    },
                },
            }
        ),
        # Final chunk of resp_codex_01 with higher output_tokens=600 & reasoning_output_tokens=150
        json.dumps(
            {
                "timestamp": "2026-11-15T10:00:06Z",
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "turn_1",
                    "response_id": "resp_codex_01",
                    "usage": {
                        "input_tokens": 28833,
                        "cached_input_tokens": 14336,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 600,
                        "reasoning_output_tokens": 150,
                        "total_tokens": 29433,
                    },
                },
            }
        ),
        # Matching event_msg(token_count) emitted by Codex CLI for Turn 1 — MUST NOT double-count!
        json.dumps(
            {
                "timestamp": "2026-11-15T10:00:06Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 28833,
                            "cached_input_tokens": 14336,
                            "output_tokens": 600,
                            "reasoning_output_tokens": 150,
                            "total_tokens": 29433,
                        },
                        "total_token_usage": {
                            "input_tokens": 28833,
                            "cached_input_tokens": 14336,
                            "output_tokens": 600,
                            "reasoning_output_tokens": 150,
                            "total_tokens": 29433,
                        },
                    },
                },
            }
        ),
        # Turn 2 switches model to codex-mini-latest
        json.dumps(
            {
                "timestamp": "2026-11-15T10:01:00Z",
                "type": "turn_context",
                "payload": {"model": "codex-mini-latest"},
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-11-15T10:01:03Z",
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "turn_2",
                    "response_id": "resp_codex_02",
                    "usage": {
                        "input_tokens": 11167,
                        "cached_input_tokens": 5664,
                        "cache_write_input_tokens": 500,
                        "output_tokens": 400,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 11567,
                    },
                },
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-11-15T10:01:03Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 11167,
                            "cached_input_tokens": 5664,
                            "output_tokens": 400,
                            "reasoning_output_tokens": 0,
                            "total_tokens": 11567,
                        },
                        "total_token_usage": {
                            "input_tokens": 40000,
                            "cached_input_tokens": 20000,
                            "output_tokens": 1000,
                            "reasoning_output_tokens": 150,
                            "total_tokens": 41000,
                        },
                    },
                },
            }
        ),
    ]
)

CODEX_LEGACY_EVENT_ONLY_JSONL = "\n".join(
    [
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-5-codex"}}),
        json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 12000,
                            "cached_input_tokens": 6000,
                            "output_tokens": 500,
                            "reasoning_output_tokens": 100,
                            "total_tokens": 12500,
                        },
                        "total_token_usage": {"total_tokens": 12500},
                    },
                },
            }
        ),
        # Consecutive duplicate snapshot with identical cumulative total_tokens=12500 -> must be skipped!
        json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 12000,
                            "cached_input_tokens": 6000,
                            "output_tokens": 500,
                            "reasoning_output_tokens": 100,
                            "total_tokens": 12500,
                        },
                        "total_token_usage": {"total_tokens": 12500},
                    },
                },
            }
        ),
    ]
)

CLINE_UI_MESSAGES_JSON = json.dumps(
    [
        {
            "ts": 1763100001000,
            "type": "say",
            "say": "text",
            "text": "TOP_SECRET_CLINE_PROMPT_DO_NOT_LEAK",
        },
        {
            "ts": 1763100002000,
            "type": "say",
            "say": "api_req_started",
            "text": json.dumps(
                {
                    "request": "POST /v1/messages",
                    "model": "claude-sonnet-4-20250514",
                    "tokensIn": 2000,
                    "tokensOut": 800,
                    "cacheWrites": 3000,
                    "cacheReads": 15000,
                    "cost": 0.045,
                }
            ),
        },
        # Duplicate ts snapshot in Cline UI stream
        {
            "ts": 1763100002000,
            "type": "say",
            "say": "api_req_started",
            "text": json.dumps(
                {
                    "model": "claude-sonnet-4-20250514",
                    "tokensIn": 2000,
                    "tokensOut": 800,
                    "cacheWrites": 3000,
                    "cacheReads": 15000,
                    "cost": 0.045,
                }
            ),
        },
        {
            "ts": 1763100009000,
            "type": "say",
            "say": "api_req_started",
            "text": json.dumps(
                {
                    "model": "claude-sonnet-4-20250514",
                    "tokensIn": 1000,
                    "tokensOut": 700,
                    "cacheWrites": 0,
                    "cacheReads": 9000,
                    "cost": 0.030,
                }
            ),
        },
    ]
)

CLAUDE_CODE_SESSION_JSONL = "\n".join(
    [
        json.dumps({"type": "user", "message": {"role": "user", "content": "SECRET_CLAUDE_PROMPT"}}),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_cc_r11_01",
                    "model": "claude-opus-4-20250514",
                    "usage": {
                        "input_tokens": 5000,
                        "cache_creation_input_tokens": 5000,
                        "cache_read_input_tokens": 20000,
                        "output_tokens": 2000,
                    },
                },
            }
        ),
    ]
)


class Round11Batch1MultiClientAndCliEcosystemTests(unittest.TestCase):
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

    def test_01_codex_cli_and_cline_parsing_and_alias_parity_across_python_mcp_cf_coze(self) -> None:
        catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        models = catalog["models"]

        # 1. Alias resolution for 2026 OpenAI Codex slugs (exact catalog + generic Codex aliases)
        m_astra, _ = pricing_core.resolve_model_query(models, "gpt-6-astra")
        m_codex5, _ = pricing_core.resolve_model_query(models, "gpt-5-codex")
        m_cmini, _ = pricing_core.resolve_model_query(models, "codex-mini-latest")
        self.assertIsNotNone(m_astra)
        self.assertIsNotNone(m_codex5)
        self.assertIsNotNone(m_cmini)
        self.assertEqual(m_astra["id"], "openai/gpt-6-astra")
        self.assertEqual(m_codex5["id"], "openai/gpt-5.3-codex")
        self.assertEqual(m_cmini["id"], "openai/gpt-5.1-codex-mini")

        # 2. Single-file Codex CLI modern session: exact 1.00x accounting (no event_msg double-count, no cache_write_input_tokens inflation!)
        p_codex = pricing_core.parse_usage_log_snippet(CODEX_MODERN_SESSION_JSONL, days_observed=10)
        self.assertEqual(p_codex["detected_format"], "csv_multimodel_bill")
        self.assertEqual(p_codex["total_requests"], 2)
        self.assertEqual(p_codex["total_input_tokens"], 40_000)  # 28,833 + 11,167
        self.assertEqual(p_codex["cached_input_tokens"], 20_000)  # 14,336 + 5,664
        self.assertEqual(p_codex["total_output_tokens"], 1_000)  # max(200, 600) + 400
        self.assertTrue(p_codex["output_includes_reasoning"])
        self.assertGreaterEqual(p_codex["deduplicated_chunks"], 1)
        by_model = {row["model"]: row for row in p_codex["model_breakdown"]}
        self.assertIn("gpt-6-astra", by_model)
        self.assertIn("codex-mini-latest", by_model)

        # 3. Single-file Legacy Codex CLI fallback (event_msg:token_count only)
        p_legacy = pricing_core.parse_usage_log_snippet(CODEX_LEGACY_EVENT_ONLY_JSONL, days_observed=10)
        self.assertEqual(p_legacy["total_requests"], 1)
        self.assertEqual(p_legacy["total_input_tokens"], 12_000)
        self.assertEqual(p_legacy["cached_input_tokens"], 6_000)
        self.assertEqual(p_legacy["total_output_tokens"], 500)
        self.assertEqual(p_legacy["model_breakdown"][0]["model"], "gpt-5-codex")

        # 4. Single-file VS Code Cline / Roo Code ui_messages.json
        p_cline = pricing_core.parse_usage_log_snippet(CLINE_UI_MESSAGES_JSON, days_observed=10)
        self.assertEqual(p_cline["detected_format"], "csv_multimodel_bill")
        self.assertEqual(p_cline["total_requests"], 2)
        # Turn 1: 2000 + 3000 + 15000 = 20000; Turn 2: 1000 + 0 + 9000 = 10000 => 30,000
        self.assertEqual(p_cline["total_input_tokens"], 30_000)
        self.assertEqual(p_cline["cached_input_tokens"], 24_000)
        self.assertEqual(p_cline["total_output_tokens"], 1_500)
        # Cost: ($0.045 + $0.030) * 7.2 = ¥0.54
        self.assertAlmostEqual(p_cline["reported_cost_rmb"], 0.54, places=2)

        # 5. PII-safe label sanitization for Codex & Cline paths
        lbl_codex = pricing_core.sanitize_usage_file_label(
            "/Users/alice/.codex/sessions/2026/11/15/rollout-abc.jsonl", 1
        )
        lbl_codex_win = pricing_core.sanitize_usage_file_label(
            r"C:\Users\alice\.codex\sessions\2026\11\rollout-win.jsonl", 2
        )
        lbl_cline = pricing_core.sanitize_usage_file_label(
            "/Users/alice/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/1763001/ui_messages.json",
            3,
        )
        self.assertEqual(lbl_codex, "codex/rollout-abc.jsonl")
        self.assertEqual(lbl_codex_win, "codex/rollout-win.jsonl")
        self.assertEqual(lbl_cline, "cline/1763001/ui_messages.json")
        for lbl in (lbl_codex, lbl_codex_win, lbl_cline):
            self.assertNotIn("alice", lbl.lower())

        # 6. 4-File Multi-Client Merge Parity across Python, MCP, Cloudflare /api/budget, and Coze!
        snippets = [
            CODEX_MODERN_SESSION_JSONL,
            CODEX_LEGACY_EVENT_ONLY_JSONL,
            CLINE_UI_MESSAGES_JSON,
            CLAUDE_CODE_SESSION_JSONL,
        ]
        file_names = [
            "/Users/alice/.codex/sessions/2026/11/15/rollout-modern.jsonl",
            "/Users/alice/.codex/sessions/2026/10/01/rollout-legacy.jsonl",
            "/Users/alice/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/1763001/ui_messages.json",
            "/Users/alice/.claude/projects/ai-radar/sess-cc.jsonl",
        ]
        merged_py = pricing_core.merge_usage_log_snippets(
            snippets, days_observed=10, file_names=file_names, models=models
        )
        # Total requests: 2 (codex modern) + 1 (codex legacy) + 2 (cline) + 1 (claude) = 6
        self.assertEqual(merged_py["total_requests"], 6)
        # Total input: 40,000 + 12,000 + 30,000 + 30,000 = 112,000
        self.assertEqual(merged_py["total_input_tokens"], 112_000)
        # Total cached: 20,000 + 6,000 + 24,000 + 20,000 = 70,000
        self.assertEqual(merged_py["cached_input_tokens"], 70_000)
        # Total output: 1,000 + 500 + 1,500 + 2,000 = 5,000
        self.assertEqual(merged_py["total_output_tokens"], 5_000)

        fb_py = merged_py["file_breakdown"]
        self.assertEqual(len(fb_py), 4)
        self.assertEqual(sum(x["requests"] for x in fb_py), 6)
        self.assertEqual(sum(x["input_tokens"] for x in fb_py), 112_000)
        fb_names = {x["file_name"] for x in fb_py}
        self.assertEqual(
            fb_names,
            {
                "codex/rollout-modern.jsonl",
                "codex/rollout-legacy.jsonl",
                "cline/1763001/ui_messages.json",
                "ai-radar/sess-cc.jsonl",
            },
        )
        for nm in fb_names:
            self.assertNotIn("alice", nm.lower())

        audit_py = pricing_core.audit_csv_bill(models, merged_py, days_observed=10, team_size=1)

        mcp_res = mcp_server.calculate_api_budget(
            model_query="auto",
            usage_snippets=snippets,
            usage_file_names=file_names,
            days_observed=10,
            team_size=1,
        )
        self.assertEqual(mcp_res["parsed_usage_summary"]["total_requests"], 6)
        self.assertEqual(mcp_res["parsed_usage_summary"]["total_input_tokens"], 112_000)
        self.assertAlmostEqual(
            mcp_res["bill_audit"]["totals"]["baseline_monthly_rmb"],
            audit_py["totals"]["baseline_monthly_rmb"],
            delta=0.02,
        )

        cf_query: list[tuple[str, str]] = [("model_id", "auto"), ("days_observed", "10"), ("team_size", "1")]
        for s, fn in zip(snippets, file_names):
            cf_query.append(("usage_snippet", s))
            cf_query.append(("usage_file", fn))
        cf_out = self._run_cloudflare_budget_cases([cf_query])[0]
        self.assertEqual(cf_out["status"], 200)
        cf_body = cf_out["body"]
        self.assertEqual(cf_body["parsed_usage_summary"]["total_requests"], 6)
        self.assertEqual(cf_body["parsed_usage_summary"]["total_input_tokens"], 112_000)
        self.assertAlmostEqual(
            cf_body["bill_audit"]["totals"]["baseline_monthly_rmb"],
            audit_py["totals"]["baseline_monthly_rmb"],
            delta=0.05,
        )
        self.assertAlmostEqual(
            cf_body["bill_audit"]["totals"]["optimized_payg_monthly_rmb"],
            audit_py["totals"]["optimized_payg_monthly_rmb"],
            delta=0.05,
        )

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
        self.assertEqual(coze_out["parsed_usage_summary"]["total_requests"], 6)
        self.assertEqual(coze_out["parsed_usage_summary"]["total_input_tokens"], 112_000)
        self.assertAlmostEqual(
            coze_out["bill_audit"]["totals"]["baseline_monthly_rmb"],
            audit_py["totals"]["baseline_monthly_rmb"],
            delta=0.05,
        )

    def test_02_local_cli_scanner_multiclient_discovery_and_backward_compat(self) -> None:
        import audit_local_claude

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_home = Path(tmpdir)
            claude_dir = fake_home / ".claude" / "projects" / "my-saas"
            codex_dir = fake_home / ".codex" / "sessions" / "2026" / "11" / "15"
            cline_dir = (
                fake_home
                / "Library"
                / "Application Support"
                / "Code"
                / "User"
                / "globalStorage"
                / "saoudrizwan.claude-dev"
                / "tasks"
                / "1763001"
            )
            claude_dir.mkdir(parents=True)
            codex_dir.mkdir(parents=True)
            cline_dir.mkdir(parents=True)

            (claude_dir / "sess-cc.jsonl").write_text(CLAUDE_CODE_SESSION_JSONL, encoding="utf-8")
            (codex_dir / "rollout-modern.jsonl").write_text(CODEX_MODERN_SESSION_JSONL, encoding="utf-8")
            (cline_dir / "ui_messages.json").write_text(CLINE_UI_MESSAGES_JSON, encoding="utf-8")

            # 1. Python API: multi-client discovery across Claude + Codex + Cline
            report_all = audit_local_claude.scan_local_coding_logs(
                client="all", home_dir=fake_home, days=10.0, seats=1, offline=True
            )
            self.assertEqual(report_all["active_files_count"], 3)
            self.assertEqual(report_all["total_requests"], 5)  # 1 (claude) + 2 (codex) + 2 (cline)
            self.assertEqual(report_all["total_input_tokens"], 100_000)  # 30k + 40k + 30k
            self.assertEqual(report_all["cached_input_tokens"], 64_000)  # 20k + 20k + 24k
            self.assertEqual(report_all["total_output_tokens"], 4_500)  # 2k + 1k + 1.5k

            cb = {item["client"]: item for item in report_all["client_breakdown"]}
            self.assertEqual(set(cb.keys()), {"claude", "codex", "cline"})
            self.assertEqual(cb["codex"]["requests"], 2)
            self.assertEqual(cb["cline"]["requests"], 2)
            self.assertEqual(cb["claude"]["requests"], 1)

            # 2. Single-client filter (--client codex)
            report_codex = audit_local_claude.scan_local_coding_logs(
                client="codex", home_dir=fake_home, days=10.0, seats=1, offline=True
            )
            self.assertEqual(report_codex["active_files_count"], 1)
            self.assertEqual(report_codex["total_requests"], 2)
            self.assertEqual(report_codex["total_input_tokens"], 40_000)

            # 3. Subprocess CLI test with overridden HOME and --client all --offline --json --export-csv
            csv_path = fake_home / "multiclient_30d.csv"
            env = dict(os.environ)
            env["HOME"] = str(fake_home)
            env["USERPROFILE"] = str(fake_home)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-W",
                    "error",
                    str(ROOT / "engine_a_mcp_actor" / "audit_local_claude.py"),
                    "--client",
                    "all",
                    "--days",
                    "10",
                    "--offline",
                    "--json",
                    "--export-csv",
                    str(csv_path),
                ],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            cli_data = json.loads(proc.stdout)
            self.assertEqual(cli_data["total_requests"], 5)
            self.assertEqual(len(cli_data["client_breakdown"]), 3)
            csv_text = csv_path.read_text(encoding="utf-8")
            self.assertNotIn("SECRET_CLAUDE_PROMPT", csv_text)
            self.assertNotIn("TOP_SECRET_CLINE_PROMPT", csv_text)
            self.assertNotIn("secret-repo", csv_text)

            # 4. Backward compatibility: scan_claude_projects_dir(explicit_codex_dir) also parses Codex .jsonl!
            compat_rep = audit_local_claude.scan_claude_projects_dir(
                fake_home / ".codex" / "sessions", days=10.0, seats=1, offline=True
            )
            self.assertEqual(compat_rep["total_requests"], 2)
            self.assertEqual(compat_rep["total_input_tokens"], 40_000)

            # 5. Flat token_usage_record schema parity + response_id deduplication in audit_local_claude.py
            flat_dir = fake_home / "codex_flat_only"
            flat_dir.mkdir(parents=True)
            (flat_dir / "rollout-flat.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"type": "turn_context", "payload": {"model": "gpt-6-astra"}}),
                        json.dumps(
                            {
                                "type": "token_usage_record",
                                "response_id": "resp_flat_01",
                                "input_tokens": 15000,
                                "cached_input_tokens": 5000,
                                "output_tokens": 800,
                                "reasoning_output_tokens": 100,
                            }
                        ),
                        json.dumps(
                            {
                                "type": "token_usage_record",
                                "response_id": "resp_flat_01",
                                "input_tokens": 15000,
                                "cached_input_tokens": 5000,
                                "output_tokens": 800,
                                "reasoning_output_tokens": 100,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            flat_rep = audit_local_claude.scan_claude_projects_dir(flat_dir, days=10.0, seats=1, offline=True)
            self.assertEqual(flat_rep["active_files_count"], 1)
            self.assertEqual(flat_rep["total_requests"], 1)
            self.assertEqual(flat_rep["deduplicated_chunks"], 1)
            self.assertEqual(flat_rep["total_input_tokens"], 15_000)
            self.assertEqual(flat_rep["cached_input_tokens"], 5_000)
            self.assertEqual(flat_rep["total_output_tokens"], 800)


class Round11Batch2WebOutlierFilterAndNode24CiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import build_site

        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.dist_dir = Path(cls._tmpdir.name) / "dist"
        build_site.build_site(dist_dir=cls.dist_dir, site_url="https://ai-cost-radar-nlu.pages.dev/")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def _eval_web_js(self, extra_js: str, stdin_payload: dict) -> dict:
        js_eval = (
            """
import fs from "node:fs";
import vm from "node:vm";

const html = fs.readFileSync(process.env.INDEX_HTML_PATH, "utf8");
const appDataMatch = html.match(/<script id="app-data" type="application\\/json">([\\s\\S]*?)<\\/script>/);
const inlineMatch = html.match(/<script>\\s*\\(\\(\\) => \\{([\\s\\S]*?)\\}\\)\\(\\);\\s*<\\/script>/);
if (!appDataMatch || !inlineMatch) throw new Error("Missing app-data or inline script");

let body = inlineMatch[1];
const bootIdx = body.lastIndexOf("initBaselines();");
if (bootIdx > 0) body = body.slice(0, bootIdx);
body += "\\nglobalThis.__EXPORTS = { state, sanitizeUsageFileLabelWeb, mergeUsageFilesWeb, parseUsageSnippet, resolveModelFuzzyWeb, auditCsvBillWeb, buildBillAuditMarkdown, importUsageBatchWeb, recomputeActiveBillFromRawFiles, toggleTopOutlierSessionWeb };\\n";

const els = new Map();
const dummyEl = () => ({
  textContent: "",
  innerHTML: "",
  value: "",
  checked: false,
  hidden: false,
  open: false,
  style: {},
  dataset: {},
  options: [],
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  addEventListener() {},
  getAttribute() { return ""; },
  setAttribute() {},
  add() {},
  querySelectorAll() { return []; },
});

const sandbox = {
  console,
  Math,
  Number,
  String,
  Boolean,
  Array,
  Object,
  Set,
  Map,
  Date,
  JSON,
  RegExp,
  Error,
  URLSearchParams,
  Option: function(text, value) { this.textContent = text; this.value = value; },
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  navigator: { clipboard: { writeText: async () => {} } },
  window: { location: { pathname: "/", search: "", href: "https://ai-cost-radar-nlu.pages.dev/" }, history: { replaceState() {} } },
  document: {
    documentElement: { setAttribute() {} },
    getElementById(id) {
      if (id === "app-data") return { textContent: appDataMatch[1] };
      if (!els.has(id)) els.set(id, dummyEl());
      return els.get(id);
    },
    querySelector() { return dummyEl(); },
    querySelectorAll() { return []; },
    addEventListener() {},
  },
  IntersectionObserver: undefined,
  setTimeout: () => 0,
  fetch: async () => ({ ok: true }),
};
vm.createContext(sandbox);
vm.runInContext(body, sandbox);
const inputs = JSON.parse(fs.readFileSync(0, "utf8"));
"""
            + extra_js
        )
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", js_eval],
            cwd=ROOT,
            env={**os.environ, "INDEX_HTML_PATH": str(self.dist_dir / "index.html")},
            input=json.dumps(stdin_payload),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(proc.stdout.strip())

    def test_03_web_codex_cline_parsing_and_multiclient_cli_bar(self) -> None:
        hosted_cli = self.dist_dir / "audit_local_claude.py"
        source_cli = ROOT / "engine_a_mcp_actor" / "audit_local_claude.py"
        self.assertEqual(hosted_cli.read_bytes(), source_cli.read_bytes())

        help_proc = subprocess.run(
            [sys.executable, "-W", "error", str(hosted_cli), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("--client", help_proc.stdout)
        self.assertIn("codex", help_proc.stdout)
        self.assertIn("cline", help_proc.stdout)

        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn(
            "curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py | python3 - --days 30",
            index_html,
        )
        self.assertIn(".codex", index_html)
        self.assertIn("Cline", index_html)

        snippets = [
            CODEX_MODERN_SESSION_JSONL,
            CODEX_LEGACY_EVENT_ONLY_JSONL,
            CLINE_UI_MESSAGES_JSON,
            CLAUDE_CODE_SESSION_JSONL,
        ]
        file_names = [
            "/Users/alice/.codex/sessions/2026/11/15/rollout-modern.jsonl",
            "/Users/alice/.codex/sessions/2026/10/01/rollout-legacy.jsonl",
            "/Users/alice/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/1763001/ui_messages.json",
            "/Users/alice/.claude/projects/ai-radar/sess-cc.jsonl",
        ]
        out = self._eval_web_js(
            """
const { sanitizeUsageFileLabelWeb, resolveModelFuzzyWeb, mergeUsageFilesWeb, auditCsvBillWeb } = sandbox.__EXPORTS;
const merged = mergeUsageFilesWeb(inputs.snippets, 10, inputs.fileNames);
const audit = auditCsvBillWeb(merged);
console.log(JSON.stringify({
  codexAlias: resolveModelFuzzyWeb("gpt-5-codex")?.id || null,
  codexMiniAlias: resolveModelFuzzyWeb("codex-mini-latest")?.id || null,
  astraAlias: resolveModelFuzzyWeb("gpt-6-astra")?.id || null,
  lblCodex: sanitizeUsageFileLabelWeb(inputs.fileNames[0], 1),
  lblCline: sanitizeUsageFileLabelWeb(inputs.fileNames[2], 3),
  merged,
  auditTotals: audit.totals,
}));
""",
            {"snippets": snippets, "fileNames": file_names},
        )
        self.assertEqual(out["astraAlias"], "openai/gpt-6-astra")
        self.assertEqual(out["codexAlias"], "openai/gpt-5.3-codex")
        self.assertEqual(out["codexMiniAlias"], "openai/gpt-5.1-codex-mini")
        self.assertEqual(out["lblCodex"], "codex/rollout-modern.jsonl")
        self.assertEqual(out["lblCline"], "cline/1763001/ui_messages.json")
        self.assertEqual(out["merged"]["total_requests"], 6)
        self.assertEqual(out["merged"]["total_input_tokens"], 112_000)
        self.assertEqual(out["merged"]["cached_input_tokens"], 70_000)
        self.assertEqual(out["merged"]["total_output_tokens"], 5_000)

        catalog = json.loads((ROOT / "shared_data" / "models_live.json").read_text(encoding="utf-8"))
        merged_py = pricing_core.merge_usage_log_snippets(
            snippets, days_observed=10, file_names=file_names, models=catalog["models"]
        )
        audit_py = pricing_core.audit_csv_bill(catalog["models"], merged_py, days_observed=10, team_size=1)
        self.assertAlmostEqual(
            out["auditTotals"]["baseline_monthly_rmb"],
            audit_py["totals"]["baseline_monthly_rmb"],
            delta=0.05,
        )
        self.assertAlmostEqual(
            out["auditTotals"]["optimized_payg_monthly_rmb"],
            audit_py["totals"]["optimized_payg_monthly_rmb"],
            delta=0.05,
        )

    def test_04_web_outlier_session_exclusion_recomputes_steady_state_and_markdown(self) -> None:
        import re

        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        for token in (
            "excludedBillFiles",
            "recomputeActiveBillFromRawFiles",
            "toggleTopOutlierSessionWeb",
            "toggleOutlierTop1Btn",
            "file-include-toggle",
            "exclude_outlier_session",
        ):
            self.assertIn(token, index_html, f"Missing {token} in index.html")

        # 30-day batch:
        # 1) One massive outlier migration spike CSV (25,000 calls on gpt-6-astra -> exceeds Lite 18k cap -> Pro ¥200)
        # 2) Two steady daily sessions totaling 12,000 calls/mo (fits Lite 18k cap -> Lite ¥40!)
        spike_csv = (
            "model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage\n"
            "openai/gpt-6-astra,25000,150000000,20000000,50000000,0,$950.00\n"
        )
        steady_claude_csv = (
            "model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage\n"
            "anthropic/claude-sonnet-4,8000,32000000,6000000,20000000,0,$120.00\n"
        )
        steady_qwen_csv = (
            "model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage\n"
            "qwen3-coder-next,4000,16000000,3000000,10000000,0,$6.00\n"
        )
        out = self._eval_web_js(
            """
const { state, importUsageBatchWeb, recomputeActiveBillFromRawFiles, toggleTopOutlierSessionWeb, auditCsvBillWeb, buildBillAuditMarkdown } = sandbox.__EXPORTS;
if (typeof importUsageBatchWeb !== "function" || typeof recomputeActiveBillFromRawFiles !== "function" || typeof toggleTopOutlierSessionWeb !== "function") {
  throw new Error("Missing outlier exclusion functions on Web runtime");
}
importUsageBatchWeb(inputs.snippets, 30, inputs.fileNames, "multifile_upload");
const auditBefore = auditCsvBillWeb(state.lastUsageImport.parsed);

const toggleRes1 = toggleTopOutlierSessionWeb();
const auditAfterExclude = auditCsvBillWeb(state.lastUsageImport.parsed);
const excludedListAfter = Array.from(state.excludedBillFiles);
state.lang = "zh";
const mdZhAfter = buildBillAuditMarkdown(auditAfterExclude);
state.lang = "en";
const mdEnAfter = buildBillAuditMarkdown(auditAfterExclude);

// Guardrail: refusing to exclude ALL files (must keep >= 1 active file)
const allLabels = state.lastUsageImport.rawFiles.map(f => f.label);
const blockedAllExclude = recomputeActiveBillFromRawFiles(new Set(allLabels));

// Toggle back to restore all 3 files
const toggleRes2 = toggleTopOutlierSessionWeb();
const auditRestored = auditCsvBillWeb(state.lastUsageImport.parsed);

console.log(JSON.stringify({
  beforeTier: auditBefore.coding_plan_option.tier_id,
  beforeCalls: auditBefore.totals.monthly_requests,
  beforeBaseRmb: auditBefore.totals.baseline_monthly_rmb,
  toggleRes1,
  afterTier: auditAfterExclude.coding_plan_option.tier_id,
  afterRenewalRmb: auditAfterExclude.coding_plan_option.renewal_rmb,
  afterCalls: auditAfterExclude.totals.monthly_requests,
  afterBaseRmb: auditAfterExclude.totals.baseline_monthly_rmb,
  allFbLenAfter: state.lastUsageImport.allFileBreakdown.length,
  excludedListAfter,
  excludedListRestored: Array.from(state.excludedBillFiles),
  blockedAllExclude,
  toggleRes2,
  restoredCalls: auditRestored.totals.monthly_requests,
  restoredTier: auditRestored.coding_plan_option.tier_id,
  mdZhAfter,
  mdEnAfter,
}));
""",
            {
                "snippets": [spike_csv, steady_claude_csv, steady_qwen_csv],
                "fileNames": [
                    "/Users/alice/.codex/sessions/2026/11/rollout-spike.csv",
                    "/Users/alice/.claude/projects/core-app/steady-1.csv",
                    "steady-2.csv",
                ],
            },
        )
        # Before exclusion: 37,000 calls/mo -> requires Pro (¥200/mo)
        self.assertEqual(out["beforeCalls"], 37_000)
        self.assertEqual(out["beforeTier"], "pro")

        # After excluding #1 outlier spike (`codex/rollout-spike.csv`): 12,000 calls/mo -> drops to Lite (¥40/mo)!
        self.assertTrue(out["toggleRes1"]["ok"])
        self.assertEqual(out["afterCalls"], 12_000)
        self.assertEqual(out["afterTier"], "lite")
        self.assertEqual(out["afterRenewalRmb"], 40.0)
        self.assertLess(out["afterBaseRmb"], out["beforeBaseRmb"] * 0.2)
        # Drill-down still retains all 3 files so user can re-include the excluded spike!
        self.assertEqual(out["allFbLenAfter"], 3)
        self.assertEqual(out["excludedListAfter"], ["codex/rollout-spike.csv"])

        # Guardrail blocks excluding all 3 files
        self.assertFalse(out["blockedAllExclude"]["ok"])
        self.assertEqual(out["blockedAllExclude"]["reason"], "empty_active")

        # Toggling again restores all 3 files seamlessly
        self.assertTrue(out["toggleRes2"]["ok"])
        self.assertEqual(out["excludedListRestored"], [])
        self.assertEqual(out["restoredCalls"], 37_000)
        self.assertEqual(out["restoredTier"], "pro")

        # Markdown reports clearly annotate excluded spike session in both ZH and EN (0 CJK in EN!)
        self.assertIn("codex/rollout-spike.csv", out["mdZhAfter"])
        self.assertIn("已剔除", out["mdZhAfter"])
        self.assertIn("codex/rollout-spike.csv", out["mdEnAfter"])
        self.assertIn("Excluded", out["mdEnAfter"])
        self.assertIsNone(re.search(r"[\u4e00-\u9fff]", out["mdEnAfter"]), f"CJK leak in EN Markdown: {out['mdEnAfter']}")

    def test_05_github_actions_native_node24_tags_and_v311_pipeline_sync(self) -> None:
        import prepare_release

        workflow_txt = (ROOT / "cloudflare" / "daily_refresh.yml").read_text(encoding="utf-8")
        for expected_tag in (
            "actions/checkout@v7",
            "actions/setup-python@v7",
            "actions/setup-node@v7",
            "actions/upload-artifact@v7",
            "actions/download-artifact@v8",
            "actions/upload-pages-artifact@v5",
            "actions/configure-pages@v6",
            "actions/deploy-pages@v5",
        ):
            self.assertIn(expected_tag, workflow_txt, f"Missing native node24 tag {expected_tag} in daily_refresh.yml")
        for legacy_tag in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/setup-node@v4",
            "actions/upload-artifact@v4",
            "actions/download-artifact@v4",
            "actions/upload-pages-artifact@v3",
            "actions/configure-pages@v5",
            "actions/deploy-pages@v4",
        ):
            self.assertNotIn(legacy_tag, workflow_txt, f"Legacy Node 20 action tag still present: {legacy_tag}")
        self.assertIn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24", workflow_txt)
        self.assertIn("test_round11_product_iteration", workflow_txt)

        self.assertIn("test_round11_product_iteration.py", prepare_release.FILES)
        self.assertRegex(prepare_release.PUBLIC_README, r"\bv3\.(?:1[1-9]|[2-9]\d)\b")
        self.assertRegex(prepare_release.PUBLIC_README, r"\b(?:1[5-9]|[2-9]\d)\s*套验收测试\b")

        verify_txt = (ROOT / "cloudflare" / "verify_release.py").read_text(encoding="utf-8")
        cli_src_txt = (ROOT / "engine_a_mcp_actor" / "audit_local_claude.py").read_text(encoding="utf-8")
        self.assertIn("token_usage_record", verify_txt)
        self.assertIn("scan_local_coding_logs", verify_txt)
        self.assertNotIn("scan_local_coding_clients", verify_txt)
        self.assertIn("def scan_local_coding_logs(", cli_src_txt)
        self.assertIn("radar_data.json", verify_txt)

        # Coze v0.0.1 live bot backward-compatibility feed (`dist/radar_data.json`)
        radar_legacy_path = self.dist_dir / "radar_data.json"
        self.assertTrue(radar_legacy_path.is_file(), "Missing dist/radar_data.json for live Coze bot compatibility")
        radar_payload = json.loads(radar_legacy_path.read_text(encoding="utf-8"))
        api_payload = json.loads((self.dist_dir / "api" / "models_live.json").read_text(encoding="utf-8"))
        self.assertEqual(radar_payload, api_payload)

        if (ROOT / "sync_config_to_cloud.sh").is_file():
            sync_txt = (ROOT / "sync_config_to_cloud.sh").read_text(encoding="utf-8")
            self.assertIn("test_round11_product_iteration", sync_txt)
            self.assertRegex(sync_txt, r"\bv3\.(?:1[1-9]|[2-9]\d)\b")

        if (ROOT / "README.md").is_file():
            root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertRegex(root_readme, r"\bv3\.(?:1[1-9]|[2-9]\d)\b")
        if (ROOT / "engine_b_affiliate_web" / "README.md").is_file():
            web_readme = (ROOT / "engine_b_affiliate_web" / "README.md").read_text(encoding="utf-8")
            self.assertRegex(web_readme, r"\bv3\.(?:1[1-9]|[2-9]\d)\b")

        actor_readme = (ROOT / "engine_a_mcp_actor" / "README.md").read_text(encoding="utf-8")
        self.assertIn("codex", actor_readme.lower())
        apify_readme_path = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "apify_store_bundle" / "README.md"
        if apify_readme_path.is_file():
            self.assertEqual(actor_readme, apify_readme_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
