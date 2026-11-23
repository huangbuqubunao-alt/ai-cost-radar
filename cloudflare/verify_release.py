"""Check the actual release output, optionally including read-only production probes."""
from html.parser import HTMLParser
import argparse
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "engine_b_affiliate_web" / "dist"
SITE = "https://ai-cost-radar-nlu.pages.dev/"


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = 0
        self.canonical = None
        self.inline = False
        self.json_script = False
        self.scripts = []
        self.json_blocks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.tables += 1
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")
        if tag == "script":
            self.inline = not attrs.get("src") and attrs.get("type", "") in ("", "text/javascript", "application/javascript", "module")
            self.json_script = attrs.get("type", "") in ("application/json", "application/ld+json")

    def handle_endtag(self, tag):
        if tag == "script":
            self.inline = False
            self.json_script = False

    def handle_data(self, data):
        if self.inline:
            self.scripts.append(data)
        if self.json_script:
            self.json_blocks.append(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", help="Read-only HTTP verification of deployed assets")
    args = parser.parse_args()
    pages = sorted(DIST.rglob("*.html"))
    assert len(pages) >= 8, f"Expected >= 8 landing pages, found {len(pages)}"
    for required_rel in ("agent-guardian/index.html", "deepseek-v4-vs-claude-code/index.html"):
        assert (DIST / required_rel).is_file(), f"Missing required SEO landing page: {required_rel}"
    page_canonicals: set[str] = set()
    for file in pages:
        page = Page()
        page.feed(file.read_text())
        relative = file.relative_to(DIST).as_posix().removesuffix("index.html")
        assert page.canonical == SITE + relative, f"Wrong canonical: {file}"
        page_canonicals.add(page.canonical)
        assert page.tables >= 4, f"Missing static comparison tables: {file}"
        for script in page.scripts:
            subprocess.run(["node", "--check"], input=script, text=True, check=True)
        for data in page.json_blocks:
            json.loads(data)
    sitemap_xml = (DIST / "sitemap.xml").read_text(encoding="utf-8")
    sitemap_tree = ET.fromstring(sitemap_xml)
    sitemap_ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_locs = [el.text.strip() for el in sitemap_tree.findall("sm:url/sm:loc", sitemap_ns) if el.text]
    assert len(sitemap_locs) >= len(pages), (
        f"sitemap.xml route count ({len(sitemap_locs)}) is smaller than generated pages ({len(pages)})"
    )
    for loc in sitemap_locs:
        assert loc.startswith(SITE), f"Unexpected sitemap loc outside canonical base {SITE}: {loc}"
        rel = loc[len(SITE):].strip("/")
        expected_html = (DIST / "index.html") if not rel else (DIST / rel / "index.html")
        assert expected_html.is_file(), f"sitemap.xml route missing generated HTML file: {loc} -> {expected_html}"
    assert set(sitemap_locs) == page_canonicals, (
        f"sitemap.xml routes {sorted(sitemap_locs)} differ from generated pages {sorted(page_canonicals)}"
    )
    catalog = json.loads((DIST / "api/models_live.json").read_text())
    radar_compat = json.loads((DIST / "radar_data.json").read_text())
    assert radar_compat == catalog, "dist/radar_data.json differs from dist/api/models_live.json"
    assert catalog["total_models"] == len(catalog["models"])
    assert catalog["quote_verified_date"], "Missing manual quote verification date"
    assert isinstance(catalog.get("price_changes"), list), "Missing price_changes list in catalog"
    assert isinstance(catalog.get("official_rule_audit"), dict), "Missing official_rule_audit in catalog"
    atom_xml = (DIST / "feeds/price-changes.xml").read_text()
    assert '<feed xmlns="http://www.w3.org/2005/Atom">' in atom_xml, "Invalid Atom XML feed"
    cli_dist = DIST / "audit_local_claude.py"
    cli_spend_dist = DIST / "audit_ai_spend.py"
    cli_src = ROOT / "engine_a_mcp_actor" / "audit_local_claude.py"
    cli_spend_src = ROOT / "engine_a_mcp_actor" / "audit_ai_spend.py"
    assert cli_dist.is_file(), "Missing dist/audit_local_claude.py"
    assert cli_spend_dist.is_file(), "Missing dist/audit_ai_spend.py"
    assert cli_dist.read_bytes() == cli_src.read_bytes(), "dist/audit_local_claude.py differs from engine_a_mcp_actor/audit_local_claude.py"
    assert cli_spend_dist.read_bytes() == cli_spend_src.read_bytes(), "dist/audit_ai_spend.py differs from engine_a_mcp_actor/audit_ai_spend.py"
    assert cli_dist.read_bytes() == cli_spend_dist.read_bytes(), "dist/audit_ai_spend.py must stay byte-synced with dist/audit_local_claude.py"
    cli_dist_txt = cli_dist.read_text(encoding="utf-8")
    assert "def scan_claude_projects_dir(" in cli_dist_txt and "def scan_local_coding_logs(" in cli_dist_txt, (
        "dist/audit_local_claude.py missing expected CLI entrypoints"
    )
    if args.remote:
        import http.client
        import time
        from urllib.parse import quote, urlsplit

        parsed_base = urlsplit(args.remote.rstrip("/") + "/")
        conn_cls = http.client.HTTPSConnection if parsed_base.scheme == "https" else http.client.HTTPConnection
        conn: http.client.HTTPConnection | None = None

        def request_remote(rel_path_and_query: str) -> tuple[int, str]:
            nonlocal conn
            target_path = parsed_base.path.rstrip("/") + "/" + rel_path_and_query.lstrip("/")
            for attempt in range(6):
                try:
                    if conn is None:
                        conn = conn_cls(parsed_base.netloc, timeout=20)
                    conn.request("GET", target_path, headers={"Connection": "keep-alive", "User-Agent": "ai-cost-radar-verifier/3.2"})
                    resp = conn.getresponse()
                    raw = resp.read().decode("utf-8", errors="replace")
                    return resp.status, raw
                except OSError:
                    if conn is not None:
                        conn.close()
                        conn = None
                    if attempt < 5:
                        time.sleep(0.8 * (attempt + 1))
                        continue
                    raise
            raise RuntimeError("unreachable")

        def run_remote_assertions() -> None:
            for file in pages:
                path = file.relative_to(DIST).as_posix().removesuffix("index.html")
                status, body = request_remote(path)
                assert status == 200 and "<table" in body and SITE in body, f"Invalid production page {path}: HTTP {status}"
            st_live, body_live = request_remote("api/models_live.json")
            assert st_live == 200, f"models_live.json returned HTTP {st_live}"
            live = json.loads(body_live)
            assert live == catalog, "Production catalog differs from release artifact"
            st_radar, body_radar = request_remote("radar_data.json")
            assert st_radar == 200 and json.loads(body_radar) == catalog, (
                f"radar_data.json returned HTTP {st_radar} or differed from catalog"
            )
            st_budget, body_budget = request_remote("api/budget?model_id=qwen3-coder-next&daily_requests=5000&cache_hit_rate=0.5")
            assert st_budget == 200, f"/api/budget returned HTTP {st_budget}: {body_budget}"
            budget = json.loads(body_budget)
            assert budget.get("status") == "ok" and budget.get("model_id") == "aliyun-bailian/qwen3-coder-next", f"Invalid /api/budget: {budget}"
            assert budget.get("monthly_requests") == 150000, f"Unexpected /api/budget monthly_requests: {budget}"
            assert budget.get("recommended_overflow_hybrid_plan_id") == "aliyun-coding-plan", f"Missing v3.4 overflow hybrid recommendation: {budget}"
            st_team, body_team = request_remote("api/budget?model_id=qwen3-coder-next&daily_requests=6000&avg_input_tokens=4000&avg_output_tokens=1000&cache_hit_rate=0.5&team_size=5")
            assert st_team == 200, f"/api/budget team_size=5 returned HTTP {st_team}: {body_team}"
            team_budget = json.loads(body_team)
            assert team_budget.get("team_size") == 5 and team_budget.get("recommended_same_family_plan_id") == "aliyun-coding-plan", f"Unexpected /api/budget team_size=5 payload: {team_budget}"
            st_mo, body_mo = request_remote("api/budget?model_id=qwen3-coder-next&monthly_requests=90000&monthly_input_m=360&monthly_output_m=90&cached_input_m=216")
            assert st_mo == 200, f"/api/budget monthly totals returned HTTP {st_mo}: {body_mo}"
            mo_budget = json.loads(body_mo)
            assert abs(float(mo_budget.get("monthly_rmb", 0)) - 656.64) < 0.02, f"Unexpected /api/budget monthly_rmb: {mo_budget}"
            csv_sample = (
                "model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage\n"
                "anthropic/claude-sonnet-4,15000,60000000,12000000,30000000,0,$315.00\n"
                "deepseek/deepseek-r1,10000,40000000,10000000,20000000,6000000,$42.00\n"
                "qwen3-coder-next,20000,80000000,16000000,40000000,0,$21.33\n"
            )
            st_csv, body_csv = request_remote(
                f"api/budget?model_id=auto&usage_snippet={quote(csv_sample, safe='')}&days_observed=30&team_size=2"
            )
            assert st_csv == 200, f"/api/budget CSV bill_audit returned HTTP {st_csv}: {body_csv}"
            csv_budget = json.loads(body_csv)
            assert "bill_audit" in csv_budget and csv_budget["bill_audit"]["totals"]["distinct_models_count"] == 3, (
                f"Unexpected /api/budget bill_audit: {csv_budget}"
            )
            assert "migration_litellm_config" in csv_budget["bill_audit"] and "model_list:" in csv_budget["bill_audit"]["migration_litellm_config"]["config_yaml"], (
                f"Missing migration_litellm_config in /api/budget: {csv_budget}"
            )
            jsonl_sample = (
                '{"type":"assistant","message":{"id":"msg_v1","model":"claude-sonnet-4-20250514","usage":{"input_tokens":2000,"cache_read_input_tokens":18000,"output_tokens":1000}}}\n'
                '{"type":"assistant","message":{"id":"msg_v2","model":"deepseek-reasoner","usage":{"prompt_tokens":8000,"completion_tokens":2000}}}\n'
            )
            st_jsonl, body_jsonl = request_remote(
                f"api/budget?model_id=auto&usage_snippet={quote(jsonl_sample, safe='')}&days_observed=1&team_size=1"
            )
            assert st_jsonl == 200, f"/api/budget JSONL bill_audit returned HTTP {st_jsonl}: {body_jsonl}"
            jsonl_budget = json.loads(body_jsonl)
            assert jsonl_budget.get("parsed_usage_summary", {}).get("source_format") == "jsonl_multimodel", (
                f"Unexpected JSONL parsed_usage_summary: {jsonl_budget}"
            )
            csv_part = (
                "model_permaslug,requests,tokens_prompt,tokens_completion,native_tokens_cached,native_tokens_reasoning,usage\n"
                "qwen3-coder-next,5,25000,5000,10000,0,$0.02\n"
            )
            st_multi, body_multi = request_remote(
                f"api/budget?model_id=auto"
                f"&usage_snippet={quote(jsonl_sample, safe='')}&usage_file={quote('/Users/alice/.claude/projects/proj-alpha/sess1.jsonl', safe='')}"
                f"&usage_snippet={quote(csv_part, safe='')}&usage_file={quote('C:\\Users\\alice\\Downloads\\cloud.csv', safe='')}"
                f"&days_observed=1&team_size=1"
            )
            assert st_multi == 200, f"/api/budget multi-file merge returned HTTP {st_multi}: {body_multi}"
            multi_budget = json.loads(body_multi)
            multi_summary = multi_budget.get("parsed_usage_summary", {})
            assert multi_summary.get("source_format") == "multifile_merged", (
                f"Unexpected multi-file source_format: {multi_summary}"
            )
            assert multi_summary.get("merged_files_count") == 2, (
                f"Unexpected merged_files_count: {multi_summary}"
            )
            fb_live = multi_summary.get("file_breakdown", [])
            assert len(fb_live) == 2 and all("alice" not in str(x.get("file_name", "")).lower() for x in fb_live), (
                f"Unexpected multi-file file_breakdown: {multi_summary}"
            )
            codex_sample = (
                '{"type":"turn_context","payload":{"model":"gpt-6-astra"}}\n'
                '{"type":"token_usage_record","response_id":"resp_v311","input_tokens":10000,"cached_input_tokens":5000,"output_tokens":400,"reasoning_output_tokens":100}\n'
            )
            st_codex, body_codex = request_remote(
                f"api/budget?model_id=auto"
                f"&usage_snippet={quote(codex_sample, safe='')}&usage_file={quote('/Users/alice/.codex/sessions/2026/11/rollout-verify.jsonl', safe='')}"
                f"&usage_snippet={quote(csv_part, safe='')}&usage_file={quote('C:\\Users\\alice\\Downloads\\cloud.csv', safe='')}"
                f"&days_observed=1&team_size=1"
            )
            assert st_codex == 200, f"/api/budget Codex CLI multi-file returned HTTP {st_codex}: {body_codex}"
            codex_summary = json.loads(body_codex).get("parsed_usage_summary", {})
            codex_fb = codex_summary.get("file_breakdown", [])
            assert any(x.get("file_name") == "codex/rollout-verify.jsonl" for x in codex_fb) and all(
                "alice" not in str(x.get("file_name", "")).lower() for x in codex_fb
            ), f"Unexpected Codex CLI file_breakdown: {codex_summary}"
            st_cli, body_cli = request_remote("audit_local_claude.py")
            assert st_cli == 200 and "scan_claude_projects_dir" in body_cli and "scan_local_coding_logs" in body_cli, (
                f"/audit_local_claude.py returned HTTP {st_cli}"
            )
            st_cli2, body_cli2 = request_remote("audit_ai_spend.py")
            assert st_cli2 == 200 and body_cli2 == body_cli, (
                f"/audit_ai_spend.py returned HTTP {st_cli2} or drifted from /audit_local_claude.py"
            )
            st_en_page, body_en_page = request_remote("ai-coding-spend-auditor/")
            assert st_en_page == 200 and '<html lang="en"' in body_en_page, (
                f"/ai-coding-spend-auditor/ returned HTTP {st_en_page}"
            )
            st_feed, body_feed = request_remote("feeds/price-changes.xml")
            assert st_feed == 200 and "<feed" in body_feed, f"/feeds/price-changes.xml returned HTTP {st_feed}"
            st_admin, _ = request_remote("admin/stats")
            assert st_admin == 401, f"Admin must fail closed; got {st_admin}"

        try:
            for remote_attempt in range(4):
                try:
                    run_remote_assertions()
                    break
                except AssertionError:
                    if conn is not None:
                        conn.close()
                        conn = None
                    if remote_attempt < 3:
                        time.sleep(2.5)
                        continue
                    raise
        finally:
            if conn is not None:
                conn.close()
    print(f"Verified {len(pages)} pages, inline JavaScript, catalog" + (" and production endpoints" if args.remote else ""))


if __name__ == "__main__":
    main()
