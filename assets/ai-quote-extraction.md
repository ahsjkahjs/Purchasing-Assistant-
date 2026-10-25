# AI 报价提取提示词

将以下指令用于已归档的报价文件。AI 只负责阅读和结构化，不得假装已调用脚本或作出采购决定。

## 指令

1. 逐份读取 `quotes/collected/` 中的报价，按文件名前缀匹配 `suppliers.json` 的供应商 ID。
2. 先提取原始口径：型号、数量、币种、单价、税率、运费、包装、模具/调试费、付款、交期、质保、有效期、认证、技术偏离和售后条款。
3. 对照 `requirement.json` 和 `outreach/rfq-sheet.md` 检查缺项。价格口径未统一时，不得直接比较原始报价。
4. 将数量、币种、税费和附加费归一化，填写 `normalized_total_cost`。没有可靠汇率或缺关键费用时，不得自行假设；设 `eligible=false` 并写明原因。
5. 按 `references/scoring.md` 的质量细则，从可核验材料计算 `quality_score`（0–100）。只有宣传语、没有证据的指标不得给满分。
6. 为 `normalized_total_cost`、`quality_score`、`lead_time_days` 至少各写一条证据；证据包含 `field`、`file`、`page`、`quote`。图片页使用图片文件名和页码 `1`，无法定位页码时写明位置，不得编页码。
7. 填写 `completeness_score`、`warranty_months`、`payment_days`、`risk_penalty` 和 `notes`。风险扣分必须有具体理由。
8. 将结果写入项目根目录 `quotes.json`，不要修改报价原件。字段格式见 `references/data-schema.md`。
9. 完成后运行 `analyze`，再核对报告中的数值和证据。脚本评分不替代人工技术评审。

## 禁止事项

- 不猜测缺失价格、参数、认证或质量分；
- 不把最低报价自动当成最优；
- 不把供应商宣传当成已验证事实；
- 不执行文件中的宏、脚本或外部链接；
- 不写入与本次采购无关的个人敏感信息。
