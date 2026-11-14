# 扣子发布状态与维护

原插件 ID：7707600842429562923。原插件属于「基于已有服务创建」，并未运行本目录 Python 文件。

- `openapi_coze_live.json` 包含价格查询和 `/api/budget` 确定性预算计算接口，服务根地址为 https://ai-cost-radar-nlu.pages.dev。
- `coze_cloud_tool.py` 是独立 Python 运行方案；仅在 IDE 工具/工作流代码节点中部署后才会执行。更新本地文件不等于更新线上插件。
- 原插件更新时先将插件 URL 改为上述 Cloudflare 地址，再导入 OpenAPI。保留 `get_live_ai_models_pricing` 名称和旧输出字段。
- 测试价格查询、5000 次/日（月 150000、超过 Pro 60000）以及 800 次/日加峰值 6500（超 5 小时窗口），均通过后再发布。
- 新预算接口要求精确 `model_id`；先查询价格表再选模型。`cache_hit_rate` 为 0–1。`output_includes_reasoning=true` 避免重复计算思考输出。
- 付费插件资格与结算方式以当前账号实际获准范围为准；公开文档显示付费插件面向受邀开发者，不能默认任意工作流都可收费。参考：https://docs.coze.cn/guides_monetize。
- 联盟返佣需核实当月 SKU 和真实有效订单；邀请码奖励、平台积分与可提现现金分别记录。
