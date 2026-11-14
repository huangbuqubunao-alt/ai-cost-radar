# 智算省钱路由台 · AI Cost Radar

主站：[https://ai-cost-radar-nlu.pages.dev/](https://ai-cost-radar-nlu.pages.dev/)。Cloudflare Pages 提供静态价格表、预算计算及第一方事件统计。

- [价格 JSON](https://ai-cost-radar-nlu.pages.dev/api/models_live.json) 与 [OpenAPI 定义](https://ai-cost-radar-nlu.pages.dev/api/openapi.json) 可公开读取。
- `/api/budget` 按精确 `model_id`、请求量、Token、缓存命中率和思考输出口径计算月费，并检查 Coding Plan 月额度及 5 小时峰值。后端调用不适用交互式编程套餐。
- GitHub Pages 保留为镜像，canonical 和分享链接均指向主站。统计与预算服务部署在 Cloudflare。
- `.github/workflows/daily_refresh.yml` 在北京时间每日 08:00 刷新；先通过全部验收，再发布两个站点，最后保存已发布快照。首次自动发布还需配置 `CLOUDFLARE_API_TOKEN`；参考 [部署手册](cloudflare/DEPLOY_AND_RECONCILE.md)。
- 国内报价与套餐规则为人工核验快照，在线价格刷新不等于重新核验国内套餐。页面分别展示两类日期。

本地验证：

```sh
python3 -W error -m unittest -v test_codex_v3_acceptance test_upgrade_2026_roadmap test_cloudflare_budget engine_a_mcp_actor.test_engine_a
python3 engine_b_affiliate_web/build_site.py --site-url https://ai-cost-radar-nlu.pages.dev/
python3 cloudflare/verify_release.py
```

公开配置仅含推广链接。佣金按联盟后台当月 SKU 资格和真实结算对账；邀请码余额、积分与现金不混同。MCP/Actor 示例保存在源码中，未作为主站付费服务发布。
