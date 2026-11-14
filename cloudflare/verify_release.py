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
    if args.remote:
        base = args.remote.rstrip("/") + "/"
        for file in pages:
            path = file.relative_to(DIST).as_posix().removesuffix("index.html")
            body = subprocess.check_output(["curl", "-fsS", "--retry", "3", base + path], text=True)
            assert '<table' in body and SITE in body, f"Invalid production page: {path}"
        live = json.loads(subprocess.check_output(["curl", "-fsS", "--retry", "3", base + "api/models_live.json"], text=True))
        assert live == catalog, "Production catalog differs from release artifact"
        code = subprocess.check_output(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", base + "admin/stats"], text=True)
        assert code == "401", f"Admin must fail closed; got {code}"
    print(f"Verified {len(pages)} pages, inline JavaScript, catalog" + (" and production endpoints" if args.remote else ""))


if __name__ == "__main__":
    main()
