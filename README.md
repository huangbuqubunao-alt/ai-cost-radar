# 智算省钱路由台 · AI Cost Radar (2026 Bilingual LLM API & GPU Cost Calculator)

- **在线比价主站 (Live Web App)**: [https://huangbuqubunao-alt.github.io/ai-cost-radar/](https://huangbuqubunao-alt.github.io/ai-cost-radar/)
- **免费实时 JSON API (Live 80+ Models Feed)**: [https://huangbuqubunao-alt.github.io/ai-cost-radar/api/models_live.json](https://huangbuqubunao-alt.github.io/ai-cost-radar/api/models_live.json)

## 自动化能力 (Zero-Cost 24h Cloud Automation)

本仓库由 GitHub Actions (`.github/workflows/daily_refresh.yml`) 每日 `00:00 UTC` 自动执行：
1. `engine_a_mcp_actor/fetch_and_enrich.py`：拉取全球 OpenRouter 最新实时价格并融合国内直连人民币通道（阿里云百炼、腾讯云、硅基流动、火山方舟）。
2. `engine_b_affiliate_web/build_site.py`：编译中英双语、¥/$ 一键切换的 AI API 月账单计算器、80/20 混合省钱路由与 GPU 私有化自建回本分析站。
3. 自动同步 `/api/models_live.json` 静态 JSON 接口（供扣子 Coze 云端插件、MCP Server 与外部 Agent 免服务器直接读取）并发布至 GitHub Pages。
