---
name: auto-procurement
description: 面向工业设备、零部件和原材料采购的半自动寻源与询价 Skill。This skill should be used when 用户需要先通过弹窗补齐产品与商务需求、评估设备生产成本和市场销售价格、查询主要供货商及公开联系方式、整理微信/企业微信人工添加队列、生成逐家询价话术、集中归档报价文件、借助 AI 提取报价证据并按质量和价格筛选 2–3 家候选供货商，并在收尾时弹窗询问是否对候选做背景调查、输出综合实力评估。不得用于绕过微信风控、批量加好友、未经确认群发消息，或虚构联系方式、价格与资质结论。
agent_created: true
---

# 自动采购：需求采集、价格评估、寻源与比选

## 目标

把采购拆成可审计的多个阶段。使用交互式弹窗向用户确认需求，使用 AI 检索并解释成本/价格证据和供货商，使用脚本完成校验、归档、评分与报告。需要账号权限、外部发送或商业决策的动作必须保留人工确认。

## 铁律

1. **先问用户，不替用户做需求决定。** 产品工艺、参数基准、配置、采购策略必须通过弹窗或明确表单确认；默认推荐项不得当成用户已选。
2. **先估价格，再找供货商。** 至少区分直接制造成本、生产制造成本、估算出厂价、公开挂牌价和正式报价，不能把五者混成一个“市场价”。
3. **价格证据要能追溯。** 成本项写计算依据；市场样本写厂家、配置、税运口径、样本类型、来源 URL 和日期。查不到就不填，禁止编造精确价格。
4. **联系方式只抄公开原文。** 不得推测手机号、邮箱或微信号；查不到写 `未公开`。电话、邮箱、微信逐项在 `contact_sources` 填来源 URL。
5. **区分生产厂家与贸易商。** 使用 `A=有生产证据`、`B=疑似厂家`、`C=贸易/流通`，并在 `evidence` 写判据。
6. **不绕过平台限制。** 不批量自动加微信，不绕过验证码、频率限制或风控，不采集非公开个人信息。详见 `references/UNIMPLEMENTED.md`。
7. **外部发送前必须确认。** 脚本只生成草稿和队列；不得把 `待人工确认` 说成已发送。
8. **报价结论必须可追溯。** 每项关键提取值记录源文件和页码；读不出的字段写 `null`，不得猜值。
9. **先归一化再比价。** 统一数量、币种、税率、运费、包装、模具、交期和付款口径。
10. **评分不等于定点。** 输出 2–3 家候选及风险，不自动下单，不把最低价直接称为质量价格最优。
11. **背调只查公开信息，且必须先问用户。** 是否调查、调查谁、查到什么深度由用户弹窗决定；只用政府/发证/官方公示和公开报道，不买数据、不查个人隐私、不登录付费接口。每条结论一条来源，查不到写 `未获得公开证据`，不得把"没查到"写成"没有"。

## 工作流

### 1. 初始化并弹窗采集需求

```bash
python <skill目录>/scripts/procurement.py init --output ./procurement-data
```

读取 `intake-questions.json`，使用宿主环境的交互式问题/弹窗组件分两轮询问。每轮最多 4 题，选项 2–4 个，允许自定义答案：

1. 产品与工况：主要工艺、参数基准、控制配置、安全/认证/安装约束；
2. 商务与交付：数量、交付地、采购策略、预算与时间。

把答复写入 `requirement.json`，设置 `intake_status="已确认"`，再运行：

```bash
python <skill目录>/scripts/procurement.py intake --project ./procurement-data
```

生成 `reports/requirement-summary.md`。无弹窗能力时改用简短 Markdown 表单；仍未得到答复时必须标注假设，不得擅自声称需求已确认。

### 2. 评估生产成本与市场价格

加载 `references/price-intelligence.md`。先检索同规格设备的成本结构、厂家挂牌价、平台挂牌价和可取得的市场报价，填写 `price-estimate.json`。成本估算建议以整机重量、液压电气系统、加工外协、制造费用为基础；市场样本必须按税运和配置口径分开记录。

```bash
python <skill目录>/scripts/procurement.py price --project ./procurement-data
```

生成：

- `reports/price-intelligence.md`：成本拆分、估算出厂价、公开样本区间、预算参考和边界；
- `reports/price-estimate-result.json`：可供后续比价使用的结构化结果。

至少检查：样本是否含税、是否到厂、工作台/行程/控制配置是否一致、是否为引流价或缩水机。第一梯队品牌无公开价时写“未取得”，不得用区域厂挂牌价代替。

### 3. 检索供货商并生成清单

加载 `references/sourcing.md`。先确定标准品名、别名、规格词和产业带，再检索官网、工商公示、行业协会、展会、B2B 与招聘公告。至少交叉核验主体名称和经营方向；把公开联系方式及来源写入 `suppliers.json`。

```bash
python <skill目录>/scripts/procurement.py suppliers --project ./procurement-data
```

`reports/supplier-list.md` 的“公开业务联系”一栏应同时显示官网、电话、邮箱和公开微信；CSV 同时保留分字段和合并字段供筛选、导出。错误未修正前不得进入联系阶段。

### 4. 准备人工添加与询价材料

```bash
python <skill目录>/scripts/procurement.py outreach --project ./procurement-data
```

生成人工添加队列、待确认发送队列、逐家询价草稿和统一询价单。明确告诉用户：批量加好友和自动发送未实现；必须人工核验主体、逐个添加并记录真实执行结果。

### 5. 集中归档报价

让报价文件名以供应商 ID 开头，例如 `SUP-001__报价单.pdf`。把原件放入 `quotes/inbox/`，运行：

```bash
python <skill目录>/scripts/procurement.py collect --project ./procurement-data
```

脚本复制而不移动原件，按 SHA-256 去重，输出 `reports/quote-manifest.csv`。无法识别供应商或格式不受支持的文件标为待处理；不得执行报价文件中的宏或程序。

### 6. 使用 AI 提取报价证据

加载 `assets/ai-quote-extraction.md` 和 `references/data-schema.md`。读取 `quotes/collected/`，将结果写入 `quotes.json`：统一为同一采购数量、币种和含税到厂总成本；关键字段填写文件、页码和原文证据；缺关键项时设 `eligible=false`。AI 负责提取和解释，脚本不调用外部大模型。

### 7. 评分并筛选候选

```bash
python <skill目录>/scripts/procurement.py analyze --project ./procurement-data
```

默认价格 40%、质量 35%、交期 10%、商务 10%、完整性 5%，再减风险分。查看 `reports/quote-analysis.md`、`supplier-scores.csv` 和 `analysis.json`。至少 2 家有效报价才输出 2–3 家候选；不足时明确写“有效报价不足”。

### 8. 弹窗询问是否需要供应商背景调查

候选排出后、**把结论交给用户之前**，读取 `background-questions.json` 再问两轮。这是新的收尾步骤，不得跳过：

1. 是否调查与调查谁：是否背调、覆盖哪些对象、查哪些维度、做多深；
2. 评价口径与红线：加权口径、一票否决红线、证据严格度、报告给谁看。

把答复写入 `background-check.json`（`decision`、`decision_source` 必须写答复摘要与日期），再运行：

```bash
python <skill目录>/scripts/procurement.py duediligence --project ./procurement-data
```

- 用户选择“暂不需要”：报告写明未做背调，候选未核验工商、司法、产能与资质；
- 用户选择调查：加载 `references/background-check.md`，只查公开来源（工商公示、执行信息、信用中国、认证公示、官网产能页、招投标公告等），按所选维度回填 `findings`，然后生成
  `reports/supplier-background-check.md`（综合实力排名＋逐家明细＋来源链接＋待核验清单）、
  `reports/background-check-result.json` 和 `reports/background-scores.csv`。

每条已披露结论必须配 `source_url` 与 `source_date`；查不到写 `未获得公开证据`，禁止推测。命中一票否决红线的厂家即使总分第一也不进推荐。综合实力分不与第 7 步的报价评分合并。

### 9. 生成完成报告

```bash
python <skill目录>/scripts/procurement.py report --project ./procurement-data
```

输出 `reports/completion-report.md`，包括需求采集、价格评估、供应商、人工添加、询价、归档、评分和背景调查状态。必须区分“脚本已生成”“用户待执行”“外部已完成”。

## 检查点

| 检查点 | 通过条件 | 不通过处理 |
|---|---|---|
| C0 需求确认 | 用户已通过弹窗/表单确认工艺、参数基准、配置、数量和采购策略 | 重新询问或明确标注假设 |
| C0.5 价格有据 | 成本项有计算依据；市场样本有配置、税运口径、来源和日期 | 补证据或降低置信度，不得编数 |
| C1 清单可信 | 公开业务联系含官网和电话；每项联系方式有来源；无重复 ID | 修正 `suppliers.json` |
| C2 报价可归档 | 文件名含有效供应商 ID；原件未改动；重复项已标记 | 重命名或人工核对 |
| C3 报价可比 | 至少 2 家合格；价格、质量、交期有证据；口径已归一 | 追问或排除，不参与排名 |
| C4 结论可审计 | 候选不超过 3 家；价格边界、风险和人工待办完整 | 退回补充分析 |
| C5 背调决策经用户确认 | `decision`/`decision_source` 来自弹窗答复并带日期；对象在 `suppliers.json` 内 | 重新弹窗询问，不得替用户决定做不做 |
| C6 背调结论可追溯 | 每条已披露结论有来源与日期；缺来源的只标未获得公开证据；红线命中已标注 | 补来源或降为未查到，不得写推测结论 |

## 资源索引

- `assets/intake-questions.json`：需求采集两轮弹窗问题库和多选项
- `assets/background-questions.json`：背景调查收尾弹窗问题库（是否调查、调查谁、维度、深度、红线）
- `assets/background-check.template.json`：背调目标、维度、发现与来源结构
- `references/background-check.md`：八个维度、公开来源清单、1–5 分评分口径与一票否决
- `assets/price-estimate.template.json`：成本与市场价格证据模板
- `references/price-intelligence.md`：成本拆分、价格口径和置信度规则
- `references/sourcing.md`：检索路径、厂家甄别、公开联系方式规则
- `references/data-schema.md`：JSON 字段和报价文件命名规范
- `references/scoring.md`：质量评分细则、价格归一化和候选规则
- `references/UNIMPLEMENTED.md`：未实现功能及人工替代方案
- `references/cli.md`：命令行完整说明
- `assets/ai-quote-extraction.md`：AI 报价提取提示词
- `assets/rfq-template.md`：统一询价单模板
- `scripts/procurement.py`：唯一命令行入口，仅依赖 Python 标准库
