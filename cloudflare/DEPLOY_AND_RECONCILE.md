# Cloudflare Pages + D1 商业落地页部署与联盟对账手册 (`Option A`)

> **原则**：前端不引入第三方统计 SDK、不购买云服务器、不自行篡改云厂商官方短链参数（`EGH3k1cs`、`vlxk7knp`）。即使 `/events` 超出免费层限额或离线不可达，用户的计算与官方跳转 100% 正常工作。

## 1. 先核验 1 个确定有现金佣金的推广商品 (SKU)

仅凭 URL 含 `userCode=vlxk7knp` 或 `EGH3k1cs`，不能默认每笔订单都有 20%～35% 现金返利。上线冷启动前请先在两个联盟后台完成 **1 个确定可返佣 SKU** 的核对：

1. **阿里云云大使后台** ([ambassador.aliyun.com](https://ambassador.aliyun.com))：
   - 打开「推广素材 / 当月返利商品规则表」，确认：
     - **ECS / 轻量应用服务器新购**（本站 `/dify-openclaw-cloud-server/` 与自建缓存网关推荐卡对应的商品）当月返利比例与新老客限制；
     - 核查 **阿里云百炼 Coding Plan (`bailian.console.aliyun.com/?userCode=vlxk7knp`)** 是否纳入当月有效返利清单。若未纳入，保留百炼官方链接作为客观导购信任锚点，将现金转化验证集中在已确认返利的云主机 SKU 上。
2. **腾讯云推广者 (CPS) 后台** ([cloud.tencent.com/act/partner/cps](https://cloud.tencent.com/act/partner/cps))：
   - 在「推广链接管理」查看 `https://curl.qcloud.com/EGH3k1cs` 关联的具体活动页与可返佣产品范围（如轻量云 / HAI / 知识引擎 LKEAP）。
   - 若后台支持生成「子推广位 / 多推广链接」，可为 `/coding-plan-2026/` 与 `/deepseek-vs-qwen/` 分别生成独立官方短链填入 `config.json`；**切勿手工在官方短链后拼接未授权参数**。

## 2. 部署到 Cloudflare Pages + D1 免费层（4 条命令）

生产项目为 `ai-cost-radar`，D1 已绑定为 `DB`。首次建库和初始化步骤仅适用于新环境。当前主站使用直接上传，从仓库根目录重新构建和部署。

```bash
# 1. 登录 Cloudflare 账号（浏览器一键授权）
npx wrangler login

# 2. 创建免费 D1 数据库并复制输出的 database_id 填入 wrangler.toml
npx wrangler d1 create ai-cost-radar-events

# 3. 初始化事件表与联盟结算台账表
npx wrangler d1 execute ai-cost-radar-events --remote --file=cloudflare/d1_schema.sql

# 4. 重新按目标域名构建静态页并一键部署 Pages + Functions (/events, /admin/stats)
SITE_BASE_URL="https://ai-cost-radar-nlu.pages.dev/" python3 engine_b_affiliate_web/build_site.py
npx wrangler pages deploy engine_b_affiliate_web/dist --project-name ai-cost-radar
```

生产环境已经设置 Pages Secret `ADMIN_STATS_TOKEN`。本机副本存放于 macOS 登录钥匙串，服务为 `ai-cost-radar.pages.admin`，账户为 `production`。在钥匙串访问中可以查找。仅在可信终端运行以下命令读取当天报表，密钥通过管道传递。

```bash
{ printf 'Authorization: Bearer '; security find-generic-password -s ai-cost-radar.pages.admin -a production -w; } | curl -fsS -H @- https://ai-cost-radar-nlu.pages.dev/admin/stats
```

报表默认使用 UTC 日期。页面使用的估算 UV 与厂商实际订单独立记录。2000-01-01 为发布自检日期，业务报表排除此日。`cloudflare/daily_refresh.yml` 将替换旧任务：北京时间每日 08:00 刷新，经全部验收后发布 Cloudflare 与 GitHub 镜像，再持久化已发布快照。实时源离线、测试失败或部署失败均保留现有线上版本并显示失败。当前仍需在 GitHub Actions Secrets 中配置 `CLOUDFLARE_API_TOKEN` 后验证首个自动发布；本地 OAuth 不会复制给 GitHub。

## 3. 每日对账口径与命令

对外统一使用 **「估算日 UV」** 口径（按日轮换随机浏览器标识，不含跨日追踪，跨设备/清理存储/广告拦截会产生自然偏差）。

- **查询当日漏斗与去重卡片点击率 (`CTR = 点击该卡去重浏览器数 ÷ 视口曝光去重浏览器数`)**：
  ```bash
  curl -sS -H "Authorization: Bearer $ADMIN_STATS_TOKEN" \
    "https://ai-cost-radar-nlu.pages.dev/admin/stats?day=2026-11-13" | python3 -m json.tool
  ```
- **录入联盟后台真实有效订单与已结算人民币**：
  ```bash
  curl -sS -X POST -H "Authorization: Bearer $ADMIN_STATS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"day_bucket":"2026-11-13","vendor":"aliyun","valid_orders":1,"pending_rmb":23.80,"settled_rmb":0,"notes":"ECS 2C4G 新客首单核对"}' \
    "https://ai-cost-radar-nlu.pages.dev/admin/stats"
  ```

## 4. 自动发布与恢复

- GitHub Actions Secret `CLOUDFLARE_ACCOUNT_ID` 已配置。还需专用 API Token：仅指定账户的 `Account / Cloudflare Pages / Edit`，存为 `CLOUDFLARE_API_TOKEN`，不能使用 Global API Key。该权限可部署账户内 Pages 项目，需妥善保管并按期轮换。官方指南：https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/。
- 工作流固定 Wrangler 4.162.0 和 Node 22，无应用生产依赖。PR 只验收，不持有部署密钥；部署任务使用独立 environment。
- `/api/budget` 是无状态、只读预算接口，从当前静态 JSON 计算，不调用付费模型、不写入事件表。`/api/openapi.json` 提供扣子导入定义。
- 已验证的生产发布：`f435a335`（新增预算工具）；前一已验证版本为 `4435e2a3`。回滚可在 Pages Deployments 对已验证历史 production deployment 选择 Rollback。D1 事件与台账数据不随静态发布回滚而删除。
- 本地同步使用 `sync_config_to_cloud.sh`，先要求部署 checkout 干净，再快进同步。公开 config 只含联盟链接；钱包和收款准备状态不复制。
