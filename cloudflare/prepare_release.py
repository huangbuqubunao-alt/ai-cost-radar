"""Copy only public release sources; never export wallet/account readiness or local state."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "engine_a_mcp_actor/pricing_core.py", "engine_a_mcp_actor/fetch_and_enrich.py",
    "engine_a_mcp_actor/mcp_server.py", "engine_a_mcp_actor/apify_main.py",
    "engine_a_mcp_actor/test_engine_a.py", "engine_a_mcp_actor/Dockerfile",
    "engine_a_mcp_actor/openapi_coze.json",
    "engine_a_mcp_actor/README.md", "engine_a_mcp_actor/.actor/actor.json",
    "engine_a_mcp_actor/.actor/input_schema.json", "engine_a_mcp_actor/.actor/pay_per_event.json",
    "engine_a_mcp_actor/publish_bundles/coze_cn_bundle/coze_cloud_tool.py",
    "engine_a_mcp_actor/publish_bundles/coze_cn_bundle/openapi_coze_live.json",
    "engine_a_mcp_actor/publish_bundles/coze_cn_bundle/COZE_PUBLISH_STEPS.md",
    "engine_b_affiliate_web/build_site.py", "engine_b_affiliate_web/ui_template.py",
    "engine_c_bounty_radar/bounty_core.py", "engine_c_bounty_radar/scan_bounties.py",
    "engine_c_bounty_radar/sandbox_prepare.py",
    "test_codex_v3_acceptance.py", "test_upgrade_2026_roadmap.py", "test_cloudflare_budget.py",
    "test_round1_product_iteration.py", "test_round2_product_iteration.py", "test_round3_product_iteration.py",
    "test_round4_product_iteration.py", "test_round5_product_iteration.py", "test_round6_product_iteration.py",
    "test_round7_product_iteration.py", "test_round8_product_iteration.py",
    "functions/api/budget.js",
    "functions/events.js", "functions/admin/stats.js", "wrangler.toml",
    "cloudflare/d1_schema.sql", "cloudflare/events_reconcile.py",
    "cloudflare/verify_release.py", "cloudflare/prepare_release.py",
    "cloudflare/daily_refresh.yml", "cloudflare/DEPLOY_AND_RECONCILE.md",
    "shared_data/models_live.json",
    "marketing_pack/01_juejin_zhihu_article.md", "marketing_pack/02_xiaohongshu_cards.html",
    "marketing_pack/02_xiaohongshu_copy.md", "marketing_pack/03_v2ex_showcase_post.md",
]


def prepare(target):
    target = target.resolve()
    if target == ROOT:
        raise ValueError("Release target must differ from source tree")
    for relative in FILES:
        assert (ROOT / relative).is_file(), f"Missing release input: {relative}"
    for relative in FILES:
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, dest)
    config = json.loads((ROOT / "config.json").read_text())
    public = {key: config[key] for key in ("domestic_affiliates_rmb", "global_affiliates_usd")}
    (target / "config.json").write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n")
    workflow = target / ".github/workflows/daily_refresh.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "cloudflare/daily_refresh.yml", workflow)
    print(f"Prepared {len(FILES)} public release inputs in {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    prepare(parser.parse_args().target)
