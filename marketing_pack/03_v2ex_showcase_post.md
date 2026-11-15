# V2EX `/go/create` 帖文草稿（可复算硬核版）

## 标题
做了一个可复算的国产 Coding Plan 额度与按量盈亏计算器（修掉了常见的缓存全折与 ¥200 封顶误导）

## 正文

最近在用 Claude Code 和 Cline 接国内模型时，发现不少比价表有两个严重误导：
1. 把「包月套餐」当成无限封顶——实际上按每月 30 天算，每天 5,000 次模型 API 调用就是 15 万次/月，已经超出阿里云百炼、腾讯云、火山方舟 Pro 月额度上限（90,000 次/月）整整 6 万次；而且腾讯/火山 Lite 月上限只有 18,000 次（每 5 小时 1,200 次），百炼 Lite 已停新购。
2. 一开 Prompt Cache 就把全部输入按 2 折算——实际上 50% 命中率 × 0.2 命中系数，输入有效系数是 `0.60` 而不是 `0.20`。

周末把各家官方文档（截至 `2026-11-13`）逐条核对了一遍，做成了一个纯静态开源比价页（关闭 JS 也能直接看原生 `<table>` 价格表、额度窗口和官方出处链接）：

- 套餐与按量回本精算页：https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/
- 每天 5,000 次调用超额复算示例：https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/?calls=5000&in=4000&out=1000&cache=0.5&mode=interactive_ide&qv=2026-11-13
- DeepSeek vs 千问（含隐式思考 Token 倍率可调假设）：https://ai-cost-radar-nlu.pages.dev/deepseek-vs-qwen/
- 开源仓库与 JSON 数据源：https://github.com/huangbuqubunao-alt/ai-cost-radar

### 目前做对的几件事：
- **首月价与续费原价拆开算**：比如百炼 Pro 新客首月 ¥39.90、续费 ¥200/月，同一组调用量分别给出首月省多少、续费月还划不划算（超 9 万次时还支持 `N×Pro 打底 + 溢出按量` 混合拆单）。
- **本地多文件账单/会话合并与一行 CLI 扫描**：支持直接把多份 OpenRouter CSV 或 Claude Code `.jsonl` 会话拖进浏览器纯本地内存去重合并（含按会话消耗排行与零改代码 `LiteLLM config.yaml` 导出），也支持终端一行只读扫描本地 `~/.claude/projects`（零上传）：`curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py | python3 - --days 30`。
- **自动排除违规场景**：勾选「非交互式后端 / 批处理 API」时直接排除三家仅限交互式 IDE 的个人 Coding Plan。
- **专属端点防呆弹窗**：选 `腾讯 Coding Plan + Claude Code` 生成 `https://api.lkeap.cloud.tencent.com/coding/anthropic`（`ANTHROPIC_BASE_URL` + `sk-sp-`），选按量则生成标准 OpenAI 兼容端点，并可一键下载 `~/.claude/settings.json`，避免买了套餐却继续扣按量余额。

### 透明说明：
- 页面内阿里云/腾讯云/硅基流动入口带有官方联盟推广参数（不影响官方价格，无已核验配置项均直接跳官方文档）。
- 为统计哪张卡片真正有用，启用了同源轻量 `/events` 接口记录按日轮换随机标识的「估算日 UV」与视口曝光点击率（无第三方统计 SDK、不记录 IP 或搜索词文本）。

欢迎各位 V 友挑刺或补充实测踩坑案例！
