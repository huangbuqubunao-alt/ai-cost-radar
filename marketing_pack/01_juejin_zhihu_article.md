# 每天 5,000 次调用，为什么 ¥200 包月仍然不够用？——2026 国内 Coding Plan 额度与按量盈亏实算

很多刚把 Claude Code、Cline 或 Cursor 切到国产大模型的开发者，看到各家云厂商推出的 **Coding Plan 包月编程套餐**，第一反应往往是：「买个最高档 Pro 包月，是不是就能把全组或重度 Agent 的账单彻底封顶了？」

先直接给可复算的结论：**按每月 30 天折算，如果你的工作流达到每天 5,000 次模型调用，月调用量就是 150,000 次（15 万次）——这已经超出阿里云百炼、腾讯云、火山方舟个人 Pro 套餐月上限（90,000 次）整整 60,000 次（6 万次）。**

不仅如此，买错档位、算漏次月续费原价、或者填错专属端点，都可能让你「买了包月还在扣按量余额」。

为了把这件事算明白，我根据各家官方文档（核验日：`2026-11-13`）整理了一份开源静态可复算比价表。你可以直接点下面的参数链接现场验算：

- 🔗 **5,000 次/天超额复算案例**：https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/?calls=5000&in=4000&out=1000&cache=0.5&mode=interactive_ide&qv=2026-11-13
- 🔗 **800 次/天个人开发盈亏案例**：https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/?calls=800&in=4000&out=1000&cache=0.5&mode=interactive_ide&qv=2026-11-13
- 🔗 **5 人团队多席位合规采购对账案例**：https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/?calls=6000&seats=5&in=4000&out=1000&cache=0.5&mode=interactive_ide&qv=2026-11-13

---

## 一、最容易踩的第一个坑：「用户提问次数」≠「模型调用次数」

各家 Coding Plan 官方文档里的额度单位，全部是 **模型 API 调用次数（Requests）**，而不是你在聊天框里按回车的「提问次数」。

在 Claude Code、Cline、Roo Code 或 Cursor Agent 模式下，你输入一句「帮我排查这个模块的单测报错并修好」，Agent 在后台通常会经历：
1. 搜索目录与读取多个源码文件（3～8 次工具调用）
2. 修改代码并运行终端测试（2～6 次调用）
3. 根据报错输出继续迭代修复（5～15 次调用）

也就是说，**1 次复杂提问触发 10～25 次模型调用是常态**。如果你每天高强度让 Agent 跑 200～250 个任务闭环，日均模型调用很容易冲上 **3,000～5,000 次**。

---

## 二、官方规则核验表：首月价、续费原价与三层滚动上限

截至 `2026-11-13`，国内主流三家 Coding Plan 的官方公开规则如下（均附官方文档出处，建议购买前再次核对当期活动）：

| 厂商与套餐 | 可购状态 | 新客首月价 | 目录/续费原价 | 每 5 小时上限 | 每周上限 | 每月上限 | 官方规则文档 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **阿里云百炼 Lite** | 已停新购 | — | ¥40/月 (仅存量) | 1,200 次 | 9,000 次 | 18,000 次 | [百炼官方说明](https://help.aliyun.com/zh/model-studio/coding-plan) |
| **阿里云百炼 Pro** | 可新购 | **¥39.90** (新客限量) | **¥200/月** | **6,000 次** | **45,000 次** | **90,000 次** | [百炼官方说明](https://help.aliyun.com/zh/model-studio/coding-plan) |
| **腾讯云 LKEAP Lite** | 可新购 | 以控制台当期活动为准 | **¥40/月** | **1,200 次** | **9,000 次** | **18,000 次** | [腾讯云官方说明](https://cloud.tencent.com/document/product/1823/130092) |
| **腾讯云 LKEAP Pro** | 可新购 | 以控制台当期活动为准 | **¥200/月** | **6,000 次** | **45,000 次** | **90,000 次** | [腾讯云官方说明](https://cloud.tencent.com/document/product/1823/130092) |
| **火山方舟 Lite / Pro** | 可新购 | 以官网当期活动为准 | **¥40 / ¥200** | 1,200 / 6,000 次 | 9,000 / 45,000 次 | 18,000 / 90,000 次 | [火山方舟文档](https://www.volcengine.com/docs/82379) |

这里有三个决定你买不买得对的关键细节：

1. **首月促销 ≠ 长期成本**：比如百炼 Pro 新客首月活动价为 `¥39.90`，但次月续费恢复 `¥200/月`。如果你的同模型按量月账单只有 `¥90`（例如开了 50% Prompt 缓存命中），首月薅完特惠后次月继续自动续费就会反亏 `¥110/月`。
2. **三层窗口同时生效**：即便你全月总调用没超 `90,000 次`，只要某天下午集中重构在 **5 小时内撞满 6,000 次（Lite 仅 1,200 次）**，当前窗口就会触发限流等待。
3. **严禁用于自动化后端**：百炼、腾讯与火山方舟官方文档均明确规定，个人 Coding Plan **仅限交互式 AI 编程工具使用**，禁止用于自动化批处理脚本、爬虫或对外提供业务 API。跑自动化后端请直接按量付费。

---

## 三、算账不能拍脑袋：缓存命中率与思考 Token 怎么算？

很多比价器一勾选「开启缓存」，就把全部输入直接按 2 折算，这会严重低估按量账单。真实的单月输入成本应当把 **缓存命中率（Hit Rate）** 和 **命中单价折扣（Hit Factor）** 拆开：

- 例如：单月输入 `100 万 Token`（1M），常规输入价 `¥1.00 / 1M`，缓存命中价 `¥0.20 / 1M`，实际缓存命中率 `50%`：
  - 未命中部分：`0.5M × ¥1.00 = ¥0.50`
  - 命中部分：`0.5M × ¥0.20 = ¥0.10`
  - **真实输入成本 = `¥0.60`**（而不是 `¥0.20`）。

同理，使用深度推理模型（如 `DeepSeek-R1`、`Hunyuan-T1`、`Qwen3.5-Plus` 思考模式）时，如果填表里的「平均输出 Token」只统计了屏幕可见回复，还需要乘上隐式思维链（CoT）倍率（通常 `2.0x～3.0x`）；如果日志里的 `completion_tokens` 已经包含了 `reasoning_tokens`，就不应再重复相乘。

---

## 四、最隐蔽的扣费陷阱：买了套餐却填了「普通按量 Base URL」

这是社区里最常见的一个真实踩坑：**开通了 Coding Plan，拿到了专属 Key（如 `sk-sp-xxxx`），却在客户端里填了通用按量 API 的 Base URL**，或者反过来用普通按量 Key 调套餐接口，导致要么报错、要么继续扣账户现金余额！

以官方文档为准，不同客户端与计费方式的端点是严格区分的：

### 1. 阿里云百炼 Coding Plan 专属端点
- **Claude Code（Anthropic 原生协议，务必先 `unset ANTHROPIC_API_KEY` 防止旧环境变量抢占，推荐持久化写入 `~/.claude/settings.json`）**：
  ```bash
  unset ANTHROPIC_API_KEY
  export ANTHROPIC_BASE_URL="https://coding.dashscope.aliyuncs.com/apps/anthropic"
  export ANTHROPIC_AUTH_TOKEN="sk-sp-你的百炼套餐专属Key"
  export ANTHROPIC_MODEL="qwen3.5-plus"
  export ANTHROPIC_SMALL_FAST_MODEL="qwen3.5-plus"
  ```
- **Cursor / Cline（OpenAI 兼容协议）**：
  - Base URL：`https://coding.dashscope.aliyuncs.com/v1`（注意不是按量的 `dashscope.aliyuncs.com/compatible-mode/v1`）

### 2. 腾讯云 LKEAP Coding Plan 专属端点
- **Claude Code（Anthropic 原生协议）**：
  ```bash
  unset ANTHROPIC_API_KEY
  export ANTHROPIC_BASE_URL="https://api.lkeap.cloud.tencent.com/coding/anthropic"
  export ANTHROPIC_AUTH_TOKEN="sk-sp-你的腾讯套餐专属Key"
  export ANTHROPIC_MODEL="tc-code-latest"
  export ANTHROPIC_SMALL_FAST_MODEL="tc-code-latest"
  ```
- **Cursor / Cline / CodeBuddy（OpenAI 兼容协议）**：
  - Base URL：`https://api.lkeap.cloud.tencent.com/coding/v3`（注意不是按量的 `api.lkeap.cloud.tencent.com/v1`）

### 3. 火山方舟 Coding Plan 专属端点
- **Claude Code（Anthropic 原生协议）**：
  ```bash
  unset ANTHROPIC_API_KEY
  export ANTHROPIC_BASE_URL="https://ark.cn-beijing.volces.com/api/coding"
  export ANTHROPIC_AUTH_TOKEN="ark-coding-plan-你的火山方舟套餐Key"
  export ANTHROPIC_MODEL="doubao-seed-2.0-code"
  export ANTHROPIC_SMALL_FAST_MODEL="doubao-seed-2.0-code"
  ```
- **Cursor / Cline / Trae（OpenAI 兼容协议）**：
  - Base URL：`https://ark.cn-beijing.volces.com/api/coding/v3`（注意不是按量的 `ark.cn-beijing.volces.com/api/v3`）

> **防踩坑加分技巧**：为了避免每次开新终端忘配环境变量、或被残留的 `ANTHROPIC_API_KEY` 覆盖，建议直接在站内端点生成器一键下载 `~/.claude/settings.json`（同时设置 `ANTHROPIC_MODEL` 与后台轻量任务 `ANTHROPIC_SMALL_FAST_MODEL`），并复制运行 `max_tokens: 1` 的连通性自检 `curl` 命令现场确认网关与模型 ID 无误。

---

## 五、在线自查与多文件 CSV / JSONL 批量账单瘦身审计工具（纯本地解析 · 支持月度基线快照对比与零改代码 `config.yaml` 迁移）

我把上面这套公式、三层额度核验、场景排除（交互式 IDE vs 自动化后端）、OpenRouter / 云控制台多模型 CSV 账单与多个 Claude Code `~/.claude/projects/*.jsonl` 会话文件批量拖拽合并去重与按会话消耗排行钻取（纯浏览器内存解析，零上传）、本地月度基线快照留存与前后省钱差额对比、一键生成保持原模型别名的 LiteLLM 零改代码迁移网关 `config.yaml`、`settings.json` 专属端点生成器以及一页式 PDF 立项对账单打印功能做成了静态页面：

👉 **https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/**

如果你不想手动打开隐藏文件夹翻找 `.jsonl` 会话，也可以直接在终端运行开源只读单文件扫描器（100% 本地统计 `~/.claude/projects`，零原始日志上传，直出高消耗会话排行与脱敏复算深链）：

```bash
curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py | python3 - --days 30
```

**透明披露**：
1. 页面核心价格表与验算案例均在构建期编译为原生 HTML `<table>`，关闭 JavaScript 也可直接核对价格、额度、核验日期与官方文档出处。
2. 页面部分云厂商控制台入口带有官方合作伙伴推广参数（不改变官方售价）；同时页面使用第一方同源轻量接口按日轮换随机标识统计「估算日 UV」与卡片曝光点击率（不收集 IP、不含第三方统计 SDK、不跨日追踪），即使统计接口不可达也完全不影响本地测算与跳转。

如果你发现某家厂商调整了最新额度或续费规则，欢迎直接对照页面底部的官方链接指正！
