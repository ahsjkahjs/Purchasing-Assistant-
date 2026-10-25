# 数据规范

所有 JSON 使用 UTF-8。`assets/*.example.json` 全部为虚构功能样例，不得直接用于真实采购。

## requirement.json

关键字段：`product_name`、`model`、`application`、`processes`、`configuration`、`procurement_strategy`、`specifications`、`quantity`、`unit`、`currency`、`delivery_location`、`required_delivery_date`、`tax_rate`、`trade_terms`、`warranty_months`、`payment_days`、`quotation_deadline`。

`intake_status` 必须由 `待交互采集` 改为 `已确认` 后才能运行 `intake` 和 `price`。`processes` 是用户选择的主要工艺数组；`configuration` 和 `procurement_strategy` 记录弹窗选择，不得由 AI 自动填成推荐项。

`specifications` 应写可检验指标和图纸版本，不写“质量好”“性能强”这类不可验收描述。

## price-estimate.json

| 字段 | 规则 |
|---|---|
| equipment / currency / confidence | 设备和币种；置信度为低/中/高 |
| limitations | 至少一条，说明税运、配置和证据边界 |
| cost_items | 非空数组，每项含 name、low、high、basis |
| manufacturing_overhead_rate | low/high 制造费用率 |
| sales_management_rate | low/high 销售管理费用率 |
| profit_rate | low/high 利润率 |
| tax_rate | 0–1 的税率 |
| market_samples | 至少一条公开样本，字段见下 |
| budget_recommendation | 可选，含 low/high/basis |

`market_samples` 每条必须含 `supplier`、`model`、`low`、`high`、`price_basis`、`sample_type`、`source_url`、`source_date`、`notes`。脚本输出生产制造成本、全成本、估算未税/含税出厂价和公开样本观察区间；公开样本区间不能直接称为成交价。

## suppliers.json

数组每项字段：

| 字段 | 规则 |
|---|---|
| id | 唯一，仅字母、数字、`_`、`-`，如 `SUP-001` |
| company | 公开登记或官网主体全称 |
| website / province / city | 官网和所在地；未知写 `未公开` |
| products | 主营产品及规格，不写空泛行业名 |
| manufacturer_grade | `A` / `B` / `C` |
| evidence | 厂家等级证据摘要 |
| contact_name / phone / email / wechat | 仅公开业务联系方式；未知写 `未公开` |
| contact_sources | 对已填 phone/email/wechat 逐项给 HTTP(S) 来源 URL |
| source_url | 企业或产品主来源 URL |
| source_date | 来源核验日，`YYYY-MM-DD` |
| match_score | 1–5 整数，5 表示规格完全覆盖 |
| tier / notes | 分层与风险、客服/表单等备注 |

## 报价文件命名

把人工收到的原件放入 `quotes/inbox/`：

```text
SUP-001__2026-10-25-正式报价.pdf
SUP-002__技术偏离表.xlsx
```

双下划线前必须是 `suppliers.json` 中已存在的 ID。支持 `.pdf`、Office/CSV、常见图片、`.txt` 和 `.md`；不支持的文件不会复制。归档脚本保留原件并计算 SHA-256，不运行宏或程序。

## quotes.json

每个供应商只保留一份已选定的有效结构化报价。字段：

| 字段 | 类型与规则 |
|---|---|
| supplier_id | 已存在的供应商 ID |
| currency | 归一化后的币种；参与排名的报价必须一致 |
| normalized_total_cost | 同数量、同税运口径的总成本，正数 |
| quality_score | 0–100，按质量细则和证据评分 |
| lead_time_days | 正数，统一为日历天或工作天后比较 |
| warranty_months | 不小于 0 |
| payment_days | 不小于 0；统一口径后填写 |
| completeness_score | 0–100，报价必填项完整程度 |
| risk_penalty | 0–100，风险扣分；通常 0–20，重大风险应直接排除 |
| eligible | 只有口径完整且可比较才为 `true` |
| exclusion_reason | 排除或待追问原因 |
| notes | 技术偏离、异常价格和质量说明 |
| evidence | 证据数组，见下 |

证据格式：

```json
{
  "field": "lead_time_days",
  "file": "SUP-001__quote.pdf",
  "page": "2",
  "quote": "合同签订后 35 个日历日发货"
}
```

`normalized_total_cost`、`quality_score`、`lead_time_days` 三项缺文件、页码或原文证据时，脚本会强制排除该报价。页码应与阅读器一致；图片可写 `1`，特殊位置应在原文或备注中说明。

## config.json

- `weights`：`price`、`quality`、`delivery`、`commercial`、`completeness`，默认 40/35/10/10/5；脚本自动归一化。
- `target_warranty_months`：质保目标，默认 12。
- `target_payment_days`：付款账期目标，默认 30。
- `shortlist_size`：2 或 3，默认 3；有效报价不足 2 家时不给候选。
- `currency`：缺省币种，不替代真实换算。
- `background_check.dimension_weights`：按口径（`均衡`/`制造能力优先`/`合规与风险优先`/`履约与交付优先`）给八个维度配权，脚本按已评维度归一化。
- `background_check.unverified_score`：标注"未获得公开证据"的维度计分，默认 3，不作负分。
- `background_check.missing_dimension_score`：完全缺维度的计分，默认 2，并在报告中标注"该维度未做调查"。

## background-check.json

- `decision`：用户弹窗答复，`进行`/`暂不需要` 等；缺失或为 `待用户弹窗确认` 时脚本报错。
- `decision_source`：弹窗答复摘要与日期（`YYYY-MM-DD`），脚本强制校验日期存在。
- `target_suppliers`：被调查供应商 ID，必须在 `suppliers.json` 中存在。
- `dimensions`：所选维度，留空则按八个默认维度全查。
- `depth` / `weight_profile` / `redlines` / `evidence_strictness` / `usage`：调查深度、加权口径、一票否决项、证据严格度和用途。
- `findings[供应商ID][维度]`：`summary`、`score`（1–5）、`confidence`（低/中/高）、`source_url`、`source_date`、`status`（`已核查`/`未获得公开证据`）、`flags`、`redline`。
- 已披露结论必须带 `source_url` 与 `source_date`；`status="未获得公开证据"` 可不填来源，按 `unverified_score` 计分。
