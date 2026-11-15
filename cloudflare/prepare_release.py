"""Copy only public release sources; never export wallet/account readiness or local state."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "engine_a_mcp_actor/pricing_core.py", "engine_a_mcp_actor/fetch_and_enrich.py",
    "engine_a_mcp_actor/mcp_server.py", "engine_a_mcp_actor/apify_main.py",
    "engine_a_mcp_actor/audit_local_claude.py",
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
    "test_round7_product_iteration.py", "test_round8_product_iteration.py", "test_round9_product_iteration.py",
    "test_round10_product_iteration.py",
    "functions/api/budget.js",
    "functions/events.js", "functions/admin/stats.js", "wrangler.toml",
    "cloudflare/d1_schema.sql", "cloudflare/events_reconcile.py",
    "cloudflare/verify_release.py", "cloudflare/prepare_release.py",
    "cloudflare/daily_refresh.yml", "cloudflare/DEPLOY_AND_RECONCILE.md",
    "shared_data/models_live.json",
    "marketing_pack/01_juejin_zhihu_article.md", "marketing_pack/02_xiaohongshu_cards.html",
    "marketing_pack/02_xiaohongshu_copy.md", "marketing_pack/03_v2ex_showcase_post.md",
]


PUBLIC_README = """# 智算省钱路由台 · AI Cost Radar (v3.10)

主站：[https://ai-cost-radar-nlu.pages.dev/](https://ai-cost-radar-nlu.pages.dev/)。Cloudflare Pages 提供静态价格表、多模型账单瘦身审计、预算计算及第一方匿名事件统计。

- [价格 JSON](https://ai-cost-radar-nlu.pages.dev/api/models_live.json)、[OpenAPI 定义](https://ai-cost-radar-nlu.pages.dev/api/openapi.json) 与 [零依赖本地 Claude Code 扫描脚本](https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py) 可公开读取。
- 终端一行只读审计本地 `~/.claude/projects`（零上传）：`curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py | python3 - --days 30`。
- `/api/budget` 支持精确 `model_id` 或多文件 `usage_snippet` + `usage_file` 批量合并去重（输出逐模型瘦身审计与按文件/会话来源消耗排行 `file_breakdown`），并核验 Coding Plan 月额度及 5 小时峰值（后端调用自动排除交互式编程套餐）。
- GitHub Pages 保留为只读镜像，canonical 和分享链接均指向主站。统计与预算服务部署在 Cloudflare。
- `.github/workflows/daily_refresh.yml` 在北京时间每日 08:00 刷新；先通过全部 14 套验收测试，再发布两个站点，最后保存已发布快照。参考 [部署手册](cloudflare/DEPLOY_AND_RECONCILE.md)。
- 国内报价与套餐规则为人工核验快照，在线价格刷新不等于重新核验国内套餐。页面分别展示两类日期。

本地验证：

```sh
python3 -W error -m unittest -v test_codex_v3_acceptance test_upgrade_2026_roadmap test_cloudflare_budget test_round1_product_iteration test_round2_product_iteration test_round3_product_iteration test_round4_product_iteration test_round5_product_iteration test_round6_product_iteration test_round7_product_iteration test_round8_product_iteration test_round9_product_iteration test_round10_product_iteration engine_a_mcp_actor.test_engine_a
python3 engine_b_affiliate_web/build_site.py --site-url https://ai-cost-radar-nlu.pages.dev/
python3 cloudflare/verify_release.py
```

公开配置仅含推广链接。佣金按联盟后台当月 SKU 资格和真实结算对账；邀请码余额、积分与现金不混同。MCP/Actor 示例保存在源码中，未作为主站付费服务发布。
"""


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
    (target / "README.md").write_text(PUBLIC_README, encoding="utf-8")
    workflow = target / ".github/workflows/daily_refresh.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "cloudflare/daily_refresh.yml", workflow)
    print(f"Prepared {len(FILES)} public release inputs in {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    prepare(parser.parse_args().target)
