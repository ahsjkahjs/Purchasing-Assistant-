# auto-procurement

可审计的半自动采购 Skill：先通过弹窗确认需求并评估生产成本与市场价格，再做供应商寻源、公开联系方式清单、逐家询价、报价归档、AI 证据提取和 2–3 家候选评分。

适用于工业设备、零部件、原材料等采购场景。它不是微信机器人，也不会自动下单。

> 想把本 Skill 发布到自己的 GitHub？步骤见 [GITHUB-UPLOAD.md](GITHUB-UPLOAD.md)（网页上传 / git 命令行 / GitHub Desktop 三条路径 + Release 发布）。

## 功能与现实边界

| 阶段 | 当前能力 | 状态 |
|---|---|---|
| 1. 弹窗采集需求 | 两轮交互问题，确认工艺、参数基准、配置、数量、交付地和采购策略 | 已实现问题库和需求校验 |
| 2. 成本与市场价格评估 | 成本拆分、估算出厂价、公开样本区间、预算参考和置信度 | 已实现计算与报告 |
| 3. 查询主要供货商 | AI 检索公开来源，官网、电话、邮箱、公开微信合并到“公开业务联系”栏 | 已实现清单校验 |
| 4. 企业微信批量加好友 | 生成人工添加队列；不绕过验证码、对方同意或平台风控 | **未实现自动添加** |
| 5. 批量发送资料并询价 | 生成统一询价单、逐家话术和发送台账 | **未实现自动发送** |
| 6. 集中收集报价 | 人工保存到收件目录后，脚本复制归档、SHA-256 去重、登记异常 | 已实现 |
| 7. AI 分析与优选 | AI 提取带文件/页码/原文的证据；脚本归一化评分并筛选 2–3 家候选 | 已实现工作流与评分 |
| 8. 供应商背景调查 | 弹窗询问是否需要；工商、司法、产能、资质、业绩等公开信息逐个核实并给综合实力分 | 已实现调查与评分 |
| 9. 完成报告 | 汇总需求、价格、供应商、候选、背调结论、风险和人工待办 | 已实现 |

完整边界见 [无法开发说明](references/UNIMPLEMENTED.md)。所有 `*.example.json` 都是虚构样例，禁止直接用于真实采购。

## 环境

- WorkBuddy 或其他能读取 `SKILL.md` 的 AI Agent；
- Python 3.9+；
- 脚本仅使用 Python 标准库，无需安装第三方依赖；
- PDF、Office、扫描件由承载 Skill 的 AI 读取，Python 脚本不内置 OCR/LLM；
- 弹窗需要宿主支持交互式问题组件；不支持时降级为 Markdown 表单。

## 快速开始

```bash
python scripts/procurement.py init --output ./procurement-data
```

1. 读取 `procurement-data/intake-questions.json`，通过弹窗分两轮询问用户；
2. 把答案写入 `requirement.json`，设 `intake_status` 为 `已确认`；
3. 检索成本与价格证据，填写 `price-estimate.json`；
4. 检索供货商，填写 `suppliers.json`。

```bash
python scripts/procurement.py intake --project ./procurement-data
python scripts/procurement.py price --project ./procurement-data
python scripts/procurement.py suppliers --project ./procurement-data
python scripts/procurement.py outreach --project ./procurement-data
```

人工在企业微信中核验并添加联系人、确认并发送询价。收到报价后，将文件按 `SUP-001__报价单.pdf` 命名并放入 `procurement-data/quotes/inbox/`：

```bash
python scripts/procurement.py collect --project ./procurement-data
```

让 AI 按 `assets/ai-quote-extraction.md` 读取归档报价并填写 `quotes.json`，再执行：

```bash
python scripts/procurement.py analyze --project ./procurement-data
python scripts/procurement.py report --project ./procurement-data
```

主要结果：

- `reports/requirement-summary.md`：弹窗确认后的需求摘要；
- `reports/price-intelligence.md`：成本、出厂价估算、公开样本区间和边界；
- `reports/suppliers.csv`：供应商及合并后的公开业务联系方式；
- `outreach/wechat-add-queue.csv`：人工添加队列；
- `outreach/rfq-drafts.md`：逐家询价草稿；
- `reports/quote-manifest.csv`：报价归档与异常清单；
- `reports/quote-analysis.md`：质量、价格、交期、证据和候选分析；
- `reports/completion-report.md`：完成报告。

## 公开业务联系栏

`supplier-list.md` 将官网、电话、邮箱和公开微信合并在一栏；CSV 保留 `website`、`phone`、`email`、`wechat` 分字段，并额外提供 `public_business_contact` 合并字段。查不到的联系方式写“未公开”，不推测。

## 价格评估原则

必须区分直接制造成本、生产制造成本、全成本、估算出厂价、公开挂牌价和正式报价。市场样本要记录型号配置、税运口径、来源和日期。公开挂牌价不是成交价；区域厂低价不能冒充第一梯队品牌价格。详见 [价格评估规范](references/price-intelligence.md)。

## 作为 WorkBuddy Skill 安装

将整个 `auto-procurement` 文件夹复制到以下任一位置：

- 用户级：`~/.workbuddy/skills/auto-procurement/`；
- 项目级：项目中的 `.workbuddy/skills/auto-procurement/`。

不要只复制 `SKILL.md`，否则模板、问题库和脚本会缺失。重新开启会话后，可用“帮我启动自动采购流程”“先评估设备价格再找供应商”等请求触发。

## 评分原则

默认权重为价格 40%、质量 35%、交期 10%、商务 10%、完整性 5%，再扣风险分。报价必须先统一数量、币种、税费、包装、运输和其他费用口径；关键字段没有报价原件证据时自动失去候选资格。

候选排序不是自动定点。异常低价、技术偏离、证书相关性、验厂、样品检测和合同条款仍需人工复核。详见 [评分规范](references/scoring.md)。

## 打包

```bash
python scripts/package_skill.py --skill . --output ./dist
```

生成的 zip 会排除 `.git`、缓存、虚拟环境、密钥和本地输出。打包前仍建议使用 Skill 规范校验器检查 `SKILL.md`。

## GitHub 上传

仓库已包含 README、MIT License、`.gitignore`、贡献与安全说明及 CI。创建一个新的 GitHub 仓库后，在本目录执行：

```bash
git add .
git commit -m "Improve procurement intake, price intelligence, and contact output"
git branch -M main
git remote add origin https://github.com/<你的账号>/auto-procurement.git
git push -u origin main
```

上传前检查没有真实报价、联系方式清单、账号凭据或聊天导出。真实 `procurement-data/` 默认被忽略。

## 测试

```bash
python -m unittest discover -s tests -v
python -m compileall scripts tests
```

CI 会对 Ubuntu、Windows 和多个 Python 版本执行相同测试。

## 文档索引

- [SKILL.md](SKILL.md)：Agent 工作流与检查点
- [价格评估](references/price-intelligence.md)
- [数据规范](references/data-schema.md)
- [寻源规范](references/sourcing.md)
- [评分规范](references/scoring.md)
- [命令行参考](references/cli.md)
- [无法开发说明](references/UNIMPLEMENTED.md)
- [更新记录](CHANGELOG.md)

## License

[MIT](LICENSE)
