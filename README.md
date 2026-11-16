# 智算省钱路由台 · AI Cost Radar (v3.12)

主站：[https://ai-cost-radar-nlu.pages.dev/](https://ai-cost-radar-nlu.pages.dev/) · Global English Auditor：[https://ai-cost-radar-nlu.pages.dev/ai-coding-spend-auditor/](https://ai-cost-radar-nlu.pages.dev/ai-coding-spend-auditor/)。Cloudflare Pages 提供静态价格表、8 大 AI 编程客户端本地只读账单审计、稳态峰值去噪、预算计算及第一方匿名事件统计。

- [价格 JSON](https://ai-cost-radar-nlu.pages.dev/api/models_live.json)、[OpenAPI 定义](https://ai-cost-radar-nlu.pages.dev/api/openapi.json) 与 [零依赖 8 客户端本地扫描脚本](https://ai-cost-radar-nlu.pages.dev/audit_ai_spend.py)（兼容旧入口 [audit_local_claude.py](https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py)）可公开读取。
- 终端一行只读审计本地 Claude Code、OpenAI Codex（含 `.jsonl.zst` 归档）、Google Antigravity、OpenCode (`opencode.db`)、xAI Grok CLI、WorkBuddy/CodeBuddy、Qwen 与 Cline（零上传）：
  - 国内中文/人民币：`curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_ai_spend.py | python3 - --days 30`
  - 海外英文/USD：`curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_ai_spend.py | python3 - --days 30 --lang en --region global`
- `/api/budget` 支持精确 `model_id` 或多文件 `usage_snippet` + `usage_file` 批量合并去重（支持 `region=global` 海外工作马模型推荐与国内 `cn` 模式），并核验 Coding Plan 月额度及 5 小时峰值（后端调用自动排除交互式编程套餐）。
- GitHub Pages 保留为只读镜像，canonical 和分享链接均指向主站。统计与预算服务部署在 Cloudflare。
- `.github/workflows/daily_refresh.yml` 全面升级原生 Node 24 Actions，在北京时间每日 08:00 刷新；先通过全部 16 套验收测试，再发布两个站点，最后保存已发布快照。参考 [部署手册](cloudflare/DEPLOY_AND_RECONCILE.md)。
- 国内报价与套餐规则为人工核验快照，在线价格刷新不等于重新核验国内套餐。页面分别展示两类日期。

本地验证：

```sh
python3 -W error -m unittest -v test_codex_v3_acceptance test_upgrade_2026_roadmap test_cloudflare_budget test_round1_product_iteration test_round2_product_iteration test_round3_product_iteration test_round4_product_iteration test_round5_product_iteration test_round6_product_iteration test_round7_product_iteration test_round8_product_iteration test_round9_product_iteration test_round10_product_iteration test_round11_product_iteration test_round12_product_iteration engine_a_mcp_actor.test_engine_a
python3 engine_b_affiliate_web/build_site.py --site-url https://ai-cost-radar-nlu.pages.dev/
python3 cloudflare/verify_release.py
```

公开配置仅含推广链接。佣金按联盟后台当月 SKU 资格和真实结算对账；邀请码余额、积分与现金不混同。MCP/Actor 示例保存在源码中，未作为主站付费服务发布。
