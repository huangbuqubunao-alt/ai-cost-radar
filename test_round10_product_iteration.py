#!/usr/bin/env python3
"""
Round 10 (v3.10) Autonomous Iteration Acceptance & Regression Suite.

Covers:
  Batch 1:
    1. Zero-dependency local `~/.claude/projects` CLI scanner (`engine_a_mcp_actor/audit_local_claude.py`):
       - Recursively scans `.jsonl` session transcripts modified within `--days N` (excluding stale files older than cutoff).
       - Deduplicates streaming `message.id` chunks globally across files, applies exact Anthropic additive prompt-cache math,
         and ranks both models (`model_breakdown`) and project/session files (`session_breakdown`) by 30-day monthly RMB spend.
       - Works 100% offline (`--offline`) with zero raw log uploads, emits a privacy-safe `web_deep_link` (zero file paths or user prompts),
         and exports a privacy-safe aggregated summary CSV (`--export-csv`) directly re-parseable by `pricing_core.parse_usage_log_snippet`.
    2. Multi-file session / source file drill-down (`file_breakdown`) across Python `pricing_core.py`, `mcp_server.py`,
       Cloudflare `functions/api/budget.js`, Coze `coze_cloud_tool.py`, OpenAPI/Actor schemas, and `apify_store_bundle`:
       - Accepts optional `file_names` / `usage_file_names` / `usage_file` query params alongside `usage_snippets`.
       - Produces `file_breakdown` ranked by `estimated_monthly_rmb` descending, preserving cross-file `message.id` deduplication
         so `sum(f["requests"] for f in file_breakdown) == parsed["total_requests"]` and `sum(f["input_tokens"]) == parsed["total_input_tokens"]`.
       - Sanitizes absolute host paths (e.g. `/Users/alice/.claude/projects/proj-alpha/sess1.jsonl` -> `proj-alpha/sess1.jsonl`) so PII paths never leak.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
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

import build_site  # noqa: E402
import coze_cloud_tool  # noqa: E402
import mcp_server  # noqa: E402
import prepare_release  # noqa: E402
import pricing_core  # noqa: E402


ALPHA_OPUS_SESSION = "\n".join(
    [
        json.dumps({"type": "user", "message": {"role": "user", "content": "SECRET_PROMPT_DO_NOT_LEAK_ALPHA"}}),
        # Streaming chunk 1 of msg_alpha_01
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_alpha_01",
                    "model": "claude-opus-4-20250514",
                    "usage": {
                        "input_tokens": 10000,
                        "cache_creation_input_tokens": 5000,
                        "cache_read_input_tokens": 35000,
                        "output_tokens": 400,
                    },
                },
            }
        ),
        # Final streaming chunk 2 of msg_alpha_01 (output_tokens=4000)
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_alpha_01",
                    "model": "claude-opus-4-20250514",
                    "usage": {
                        "input_tokens": 10000,
                        "cache_creation_input_tokens": 5000,
                        "cache_read_input_tokens": 35000,
                        "output_tokens": 4000,
                    },
                },
            }
        ),
        # Shared cross-file duplicate msg_shared_99 (first seen in alpha with partial output=200)
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_shared_99",
                    "model": "claude-sonnet-4-20250514",
                    "usage": {
                        "input_tokens": 4000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 16000,
                        "output_tokens": 200,
                    },
                },
            }
        ),
    ]
)

BETA_SONNET_SESSION = "\n".join(
    [
        # Overlapping chunk of msg_shared_99 (final output=1200) — must deduplicate without double-counting!
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_shared_99",
                    "model": "claude-sonnet-4-20250514",
                    "usage": {
                        "input_tokens": 4000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 16000,
                        "output_tokens": 1200,
                    },
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_beta_02",
                    "model": "claude-sonnet-4-20250514",
                    "usage": {
                        "input_tokens": 3000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 7000,
                        "output_tokens": 800,
                    },
                },
            }
        ),
    ]
)

CLOUD_WEEK1_CSV = """model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage
deepseek/deepseek-r1,5,20000,5000,10000,3000,$0.05
"""


class Round10Batch1CliScannerAndFileDrilldownTests(unittest.TestCase):
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

    def test_01_local_claude_projects_cli_scanner_offline_and_export(self) -> None:
        import audit_local_claude  # Must exist as standalone zero-dep module in engine_a_mcp_actor/

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            alpha_dir = root / "proj-alpha-core"
            beta_dir = root / "proj-beta-ui"
            stale_dir = root / "proj-old-archive"
            alpha_dir.mkdir(parents=True)
            beta_dir.mkdir(parents=True)
            stale_dir.mkdir(parents=True)

            f_alpha = alpha_dir / "sess-opus.jsonl"
            f_alpha.write_text(ALPHA_OPUS_SESSION, encoding="utf-8")

            f_beta = beta_dir / "sess-sonnet.jsonl"
            f_beta.write_text(BETA_SONNET_SESSION, encoding="utf-8")

            f_empty = beta_dir / "sess-user-only.jsonl"
            f_empty.write_text(
                json.dumps({"type": "user", "message": {"content": "SECRET_USER_TEXT_999"}}),
                encoding="utf-8",
            )

            f_stale = stale_dir / "sess-ancient.jsonl"
            f_stale.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "id": "msg_stale_old",
                            "model": "claude-opus-4-20250514",
                            "usage": {"input_tokens": 900000, "output_tokens": 200000},
                        },
                    }
                ),
                encoding="utf-8",
            )
            old_ts = time.time() - (45 * 86400)
            os.utime(f_stale, (old_ts, old_ts))

            # 1. Direct Python API check (offline=True)
            report = audit_local_claude.scan_claude_projects_dir(root, days=30.0, seats=2, offline=True)
            self.assertEqual(report["active_files_count"], 2)
            self.assertGreaterEqual(report["deduplicated_chunks"], 2)
            # Total deduplicated turns: msg_alpha_01 (1) + msg_shared_99 (1) + msg_beta_02 (1) = 3
            self.assertEqual(report["total_requests"], 3)
            # Input: 50,000 + 20,000 + 10,000 = 80,000 (stale 900k excluded!)
            self.assertEqual(report["total_input_tokens"], 80_000)
            # Cached: 35,000 + 16,000 + 7,000 = 58,000
            self.assertEqual(report["cached_input_tokens"], 58_000)
            # Output: 4,000 + max(200, 1200) + 800 = 6,000
            self.assertEqual(report["total_output_tokens"], 6_000)

            # Session ranking: proj-alpha-core/sess-opus.jsonl must rank #1 by monthly RMB spend
            sessions = report["session_breakdown"]
            self.assertEqual(len(sessions), 2)
            self.assertIn("proj-alpha-core/sess-opus.jsonl", sessions[0]["session_relpath"])
            self.assertGreater(sessions[0]["estimated_monthly_rmb"], sessions[1]["estimated_monthly_rmb"])
            self.assertEqual(sum(s["requests"] for s in sessions), report["total_requests"])

            # Privacy guarantees on web_deep_link: zero prompts, zero local directory names
            deep_link = report["web_deep_link"]
            self.assertTrue(deep_link.startswith("https://ai-cost-radar-nlu.pages.dev/?"))
            self.assertNotIn("SECRET_PROMPT", deep_link)
            self.assertNotIn("proj-alpha-core", deep_link)
            self.assertNotIn(tmpdir, deep_link)

            # 2. Subprocess CLI check (--offline --json --export-csv)
            csv_out = root / "aggregated_summary.csv"
            cli_proc = subprocess.run(
                [
                    sys.executable,
                    "-W",
                    "error",
                    str(ROOT / "engine_a_mcp_actor" / "audit_local_claude.py"),
                    "--dir",
                    str(root),
                    "--days",
                    "30",
                    "--seats",
                    "2",
                    "--offline",
                    "--json",
                    "--export-csv",
                    str(csv_out),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            cli_json = json.loads(cli_proc.stdout)
            self.assertEqual(cli_json["total_requests"], 3)
            self.assertTrue(csv_out.is_file())
            csv_text = csv_out.read_text(encoding="utf-8")
            self.assertNotIn("SECRET_PROMPT", csv_text)
            self.assertNotIn("proj-alpha-core", csv_text)
            reparsed = pricing_core.parse_usage_log_snippet(csv_text, days_observed=30.0)
            self.assertEqual(reparsed["detected_format"], "csv_multimodel_bill")
            self.assertEqual(reparsed["total_requests"], 3)
            self.assertEqual(reparsed["total_input_tokens"], 80_000)
            self.assertEqual(reparsed["total_output_tokens"], 6_000)

    def test_02_multifile_session_file_breakdown_across_python_mcp_cloudflare_and_coze(self) -> None:
        snippets = [ALPHA_OPUS_SESSION, BETA_SONNET_SESSION, CLOUD_WEEK1_CSV]
        raw_names = [
            "/Users/alice/.claude/projects/proj-alpha/sess-opus.jsonl",
            "/Users/alice/.claude/projects/proj-beta/sess-sonnet.jsonl",
            "C:\\Users\\alice\\Downloads\\cloud_week1.csv",
        ]

        # 1. pricing_core.merge_usage_log_snippets
        merged = pricing_core.merge_usage_log_snippets(
            snippets,
            days_observed=3.0,
            file_names=raw_names,
        )
        self.assertEqual(merged["source_format"], "multifile_merged")
        self.assertEqual(merged["merged_files_count"], 3)
        # 3 deduplicated Claude turns + 5 CSV R1 requests = 8
        self.assertEqual(merged["total_requests"], 8)
        self.assertIn("file_breakdown", merged)
        fb = merged["file_breakdown"]
        self.assertEqual(len(fb), 3)
        # Verify PII path sanitization (no /Users/alice or C:\Users\alice leaked!)
        for item in fb:
            self.assertNotIn("alice", item["file_name"].lower())
        # Verify alpha opus file is ranked #1 by estimated_monthly_rmb
        self.assertIn("sess-opus.jsonl", fb[0]["file_name"])
        self.assertGreater(fb[0]["estimated_monthly_rmb"], fb[1]["estimated_monthly_rmb"])
        # Exact accounting conservation across deduplicated files
        self.assertEqual(sum(x["requests"] for x in fb), merged["total_requests"])
        self.assertEqual(sum(x["input_tokens"] for x in fb), merged["total_input_tokens"])
        self.assertEqual(sum(x["output_tokens"] for x in fb), merged["total_output_tokens"])

        # 2. mcp_server.calculate_api_budget parity
        mcp_res = mcp_server.calculate_api_budget(
            model_query="auto",
            usage_snippets=snippets,
            usage_file_names=raw_names,
            days_observed=3.0,
            team_size=1,
        )
        mcp_fb = mcp_res["parsed_usage_summary"]["file_breakdown"]
        self.assertEqual(len(mcp_fb), 3)
        self.assertEqual(mcp_fb[0]["file_name"], fb[0]["file_name"])
        self.assertAlmostEqual(mcp_fb[0]["estimated_monthly_rmb"], fb[0]["estimated_monthly_rmb"], delta=0.05)

        # 3. Cloudflare /api/budget parity (repeated usage_snippet + usage_file query params)
        cf_cases = self._run_cloudflare_budget_cases(
            [
                [
                    ("model_id", "auto"),
                    ("usage_snippet", ALPHA_OPUS_SESSION),
                    ("usage_file", raw_names[0]),
                    ("usage_snippet", BETA_SONNET_SESSION),
                    ("usage_file", raw_names[1]),
                    ("usage_snippet", CLOUD_WEEK1_CSV),
                    ("usage_file", raw_names[2]),
                    ("days_observed", "3"),
                    ("team_size", "1"),
                ]
            ]
        )
        self.assertEqual(cf_cases[0]["status"], 200)
        cf_fb = cf_cases[0]["body"]["parsed_usage_summary"]["file_breakdown"]
        self.assertEqual(len(cf_fb), 3)
        self.assertNotIn("alice", cf_fb[0]["file_name"].lower())
        self.assertIn("sess-opus.jsonl", cf_fb[0]["file_name"])
        self.assertEqual(sum(x["requests"] for x in cf_fb), 8)
        self.assertAlmostEqual(cf_fb[0]["estimated_monthly_rmb"], mcp_fb[0]["estimated_monthly_rmb"], delta=0.05)

        # 4. Coze cloud tool parity
        coze_res = coze_cloud_tool.run_router(
            {
                "action": "calculate_api_budget",
                "model_query": "auto",
                "usage_snippets": snippets,
                "usage_file_names": raw_names,
                "days_observed": 3,
                "team_size": 1,
            }
        )
        coze_fb = coze_res["parsed_usage_summary"]["file_breakdown"]
        self.assertEqual(len(coze_fb), 3)
        self.assertNotIn("alice", coze_fb[0]["file_name"].lower())
        self.assertIn("sess-opus.jsonl", coze_fb[0]["file_name"])
        self.assertEqual(sum(x["requests"] for x in coze_fb), 8)
        self.assertAlmostEqual(coze_fb[0]["estimated_monthly_rmb"], mcp_fb[0]["estimated_monthly_rmb"], delta=0.05)

        # 5. Keep MCP_TOOLS_SPEC at 3 tools & verify apify_store_bundle byte-for-byte sync
        self.assertEqual(len(mcp_server.MCP_TOOLS_SPEC), 3)
        budget_tool = next(t for t in mcp_server.MCP_TOOLS_SPEC if t["name"] == "calculate_api_budget")
        self.assertIn("usage_file_names", budget_tool["inputSchema"]["properties"])

        apify_dir = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "apify_store_bundle"
        if apify_dir.is_dir():
            for fname in ("pricing_core.py", "mcp_server.py", "fetch_and_enrich.py"):
                src = (ROOT / "engine_a_mcp_actor" / fname).read_bytes()
                dst = (apify_dir / fname).read_bytes()
                self.assertEqual(src, dst, f"apify_store_bundle/{fname} drifted from engine_a_mcp_actor/{fname}")


class Round10Batch2WebCliDrilldownAndPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dist_dir = Path(cls._tmp.name) / "dist"
        build_site.build_site(dist_dir=cls.dist_dir, site_url="https://ai-cost-radar-nlu.pages.dev/")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_03_web_hosted_cli_scanner_script_and_copy_command_bar(self) -> None:
        hosted_cli = self.dist_dir / "audit_local_claude.py"
        source_cli = ROOT / "engine_a_mcp_actor" / "audit_local_claude.py"
        self.assertTrue(hosted_cli.is_file(), "dist/audit_local_claude.py must be emitted by build_site.py")
        self.assertEqual(hosted_cli.read_bytes(), source_cli.read_bytes())

        help_proc = subprocess.run(
            [sys.executable, "-W", "error", str(hosted_cli), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("--offline", help_proc.stdout)
        self.assertIn("--export-csv", help_proc.stdout)

        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="localCliAuditBar"', index_html)
        self.assertIn('id="localCliCmdCode"', index_html)
        self.assertIn('id="copyLocalCliCmdBtn"', index_html)
        self.assertIn(
            "curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py | python3 - --days 30",
            index_html,
        )
        self.assertIn("copy_local_cli_cmd", index_html)
        for i18n_key in ("localCliHint", "copyLocalCliCmdBtn", "copiedLocalCliToast"):
            self.assertIn(f"{i18n_key}:", index_html, f"Missing {i18n_key} in I18N_EN")

    def test_04_web_multifile_per_session_cost_drilldown_and_markdown_summary(self) -> None:
        index_html = (self.dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn("sanitizeUsageFileLabelWeb", index_html, "Missing sanitizeUsageFileLabelWeb")
        self.assertIn("buildFileBreakdownWeb", index_html, "Missing buildFileBreakdownWeb")
        self.assertIn('id="usageFileDrilldown"', index_html, "Missing #usageFileDrilldown")
        self.assertIn("file_breakdown", index_html, "Missing file_breakdown")

        # Execute real Web JS functions in Node against the built APP_DATA + inline script
        js_eval = """
import fs from "node:fs";
import vm from "node:vm";

const html = fs.readFileSync(process.env.INDEX_HTML_PATH, "utf8");
const appDataMatch = html.match(/<script id="app-data" type="application\\/json">([\\s\\S]*?)<\\/script>/);
const inlineMatch = html.match(/<script>\\s*\\(\\(\\) => \\{([\\s\\S]*?)\\}\\)\\(\\);\\s*<\\/script>/);
if (!appDataMatch || !inlineMatch) throw new Error("Missing app-data or inline script");

let body = inlineMatch[1];
const bootIdx = body.lastIndexOf("initBaselines();");
if (bootIdx > 0) body = body.slice(0, bootIdx);
body += "\\nglobalThis.__EXPORTS = { state, sanitizeUsageFileLabelWeb, mergeUsageFilesWeb, auditCsvBillWeb, buildBillAuditMarkdown };\\n";

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
      return dummyEl();
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

const { state, sanitizeUsageFileLabelWeb, mergeUsageFilesWeb, auditCsvBillWeb, buildBillAuditMarkdown } = sandbox.__EXPORTS;
const inputs = JSON.parse(fs.readFileSync(0, "utf8"));
const merged = mergeUsageFilesWeb(inputs.snippets, 3, inputs.rawNames);
const audit = auditCsvBillWeb(merged);
state.lang = "zh";
const mdZh = buildBillAuditMarkdown(audit);
state.lang = "en";
const mdEn = buildBillAuditMarkdown(audit);
console.log(JSON.stringify({
  sanitizedSample: sanitizeUsageFileLabelWeb("/Users/alice/.claude/projects/proj-alpha/sess-opus.jsonl", 1),
  merged,
  mdZh,
  mdEn,
}));
"""
        raw_names = [
            "/Users/alice/.claude/projects/proj-alpha/sess-opus.jsonl",
            "/Users/alice/.claude/projects/proj-beta/sess-sonnet.jsonl",
            "C:\\Users\\alice\\Downloads\\cloud_week1.csv",
        ]
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", js_eval],
            cwd=ROOT,
            env={**os.environ, "INDEX_HTML_PATH": str(self.dist_dir / "index.html")},
            input=json.dumps(
                {
                    "snippets": [ALPHA_OPUS_SESSION, BETA_SONNET_SESSION, CLOUD_WEEK1_CSV],
                    "rawNames": raw_names,
                }
            ),
            capture_output=True,
            text=True,
            check=True,
        )
        out = json.loads(proc.stdout.strip())
        self.assertEqual(out["sanitizedSample"], "proj-alpha/sess-opus.jsonl")
        fb = out["merged"]["file_breakdown"]
        self.assertEqual(len(fb), 3)
        for item in fb:
            self.assertNotIn("alice", item["file_name"].lower())
        self.assertIn("sess-opus.jsonl", fb[0]["file_name"])
        self.assertGreater(fb[0]["estimated_monthly_rmb"], fb[1]["estimated_monthly_rmb"])
        self.assertEqual(sum(x["requests"] for x in fb), out["merged"]["total_requests"])
        self.assertEqual(sum(x["input_tokens"] for x in fb), out["merged"]["total_input_tokens"])
        self.assertEqual(sum(x["output_tokens"] for x in fb), out["merged"]["total_output_tokens"])

        self.assertIn("proj-alpha/sess-opus.jsonl", out["mdZh"])
        self.assertIn("proj-alpha/sess-opus.jsonl", out["mdEn"])
        self.assertNotRegex(out["mdEn"], r"[\u4e00-\u9fff]")

    def test_05_ci_node24_upgrade_pipeline_verifier_and_docs_v310_sync(self) -> None:
        self.assertIn("engine_a_mcp_actor/audit_local_claude.py", prepare_release.FILES)
        self.assertIn("test_round10_product_iteration.py", prepare_release.FILES)

        workflow_yml = (ROOT / "cloudflare" / "daily_refresh.yml").read_text(encoding="utf-8")
        self.assertIn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24", workflow_yml)
        self.assertIn("test_round10_product_iteration.py", workflow_yml)
        self.assertIn("test_round10_product_iteration", workflow_yml)

        verifier_py = (ROOT / "cloudflare" / "verify_release.py").read_text(encoding="utf-8")
        self.assertIn("audit_local_claude.py", verifier_py)
        self.assertIn("file_breakdown", verifier_py)

        eng_a_readme = (ROOT / "engine_a_mcp_actor" / "README.md").read_text(encoding="utf-8")
        self.assertIn("audit_local_claude.py", eng_a_readme)
        self.assertIn("file_breakdown", eng_a_readme)

        article = (ROOT / "marketing_pack" / "01_juejin_zhihu_article.md").read_text(encoding="utf-8")
        self.assertIn("audit_local_claude.py", article)
        v2ex = (ROOT / "marketing_pack" / "03_v2ex_showcase_post.md").read_text(encoding="utf-8")
        self.assertIn("audit_local_claude.py", v2ex)

        if (ROOT / "sync_config_to_cloud.sh").is_file():
            sync_sh = (ROOT / "sync_config_to_cloud.sh").read_text(encoding="utf-8")
            self.assertIn("test_round10_product_iteration", sync_sh)
            self.assertIn("v3.10", sync_sh)
        if (ROOT / "README.md").is_file():
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertRegex(readme, r"\bv3\.(?:10|[1-9]\d)\b")
            self.assertIn("audit_local_claude.py", readme)
            self.assertIn("test_round10_product_iteration", readme)
        if (ROOT / "engine_b_affiliate_web" / "README.md").is_file():
            eng_b_readme = (ROOT / "engine_b_affiliate_web" / "README.md").read_text(encoding="utf-8")
            self.assertIn("audit_local_claude.py", eng_b_readme)
            self.assertIn("usageFileDrilldown", eng_b_readme)

        apify_dir = ROOT / "engine_a_mcp_actor" / "publish_bundles" / "apify_store_bundle"
        if apify_dir.is_dir():
            for rel in (
                "pricing_core.py",
                "mcp_server.py",
                "fetch_and_enrich.py",
                "openapi_coze.json",
                "README.md",
                ".actor/input_schema.json",
            ):
                src = (ROOT / "engine_a_mcp_actor" / rel).read_bytes()
                dst = (apify_dir / rel).read_bytes()
                self.assertEqual(src, dst, f"apify_store_bundle/{rel} drifted from engine_a_mcp_actor/{rel}")


if __name__ == "__main__":
    unittest.main()
