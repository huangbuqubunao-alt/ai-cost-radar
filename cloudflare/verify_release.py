"""Check the actual release output, optionally including read-only production probes."""
from html.parser import HTMLParser
import argparse
import json
from pathlib import Path
import subprocess

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
    assert len(pages) == 5, f"Expected 5 landing pages, found {len(pages)}"
    for file in pages:
        page = Page()
        page.feed(file.read_text())
        relative = file.relative_to(DIST).as_posix().removesuffix("index.html")
        assert page.canonical == SITE + relative, f"Wrong canonical: {file}"
        assert page.tables >= 4, f"Missing static comparison tables: {file}"
        for script in page.scripts:
            subprocess.run(["node", "--check"], input=script, text=True, check=True)
        for data in page.json_blocks:
            json.loads(data)
    catalog = json.loads((DIST / "api/models_live.json").read_text())
    assert catalog["total_models"] == len(catalog["models"])
    assert catalog["quote_verified_date"], "Missing manual quote verification date"
    assert isinstance(catalog.get("price_changes"), list), "Missing price_changes list in catalog"
    atom_xml = (DIST / "feeds/price-changes.xml").read_text()
    assert '<feed xmlns="http://www.w3.org/2005/Atom">' in atom_xml, "Invalid Atom XML feed"
    if args.remote:
        import http.client
        import time
        from urllib.parse import urlsplit

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

        try:
            for file in pages:
                path = file.relative_to(DIST).as_posix().removesuffix("index.html")
                status, body = request_remote(path)
                assert status == 200 and "<table" in body and SITE in body, f"Invalid production page {path}: HTTP {status}"
            st_live, body_live = request_remote("api/models_live.json")
            assert st_live == 200, f"models_live.json returned HTTP {st_live}"
            live = json.loads(body_live)
            assert live == catalog, "Production catalog differs from release artifact"
            st_budget, body_budget = request_remote("api/budget?model_id=qwen3-coder-next&daily_requests=5000&cache_hit_rate=0.5")
            assert st_budget == 200, f"/api/budget returned HTTP {st_budget}: {body_budget}"
            budget = json.loads(body_budget)
            assert budget.get("status") == "ok" and budget.get("model_id") == "aliyun-bailian/qwen3-coder-next", f"Invalid /api/budget: {budget}"
            assert budget.get("monthly_requests") == 150000, f"Unexpected /api/budget monthly_requests: {budget}"
            st_feed, body_feed = request_remote("feeds/price-changes.xml")
            assert st_feed == 200 and "<feed" in body_feed, f"/feeds/price-changes.xml returned HTTP {st_feed}"
            st_admin, _ = request_remote("admin/stats")
            assert st_admin == 401, f"Admin must fail closed; got {st_admin}"
        finally:
            if conn is not None:
                conn.close()
    print(f"Verified {len(pages)} pages, inline JavaScript, catalog" + (" and production endpoints" if args.remote else ""))


if __name__ == "__main__":
    main()
