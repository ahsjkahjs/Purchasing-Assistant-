# 命令行参考

要求 Python 3.9+，仅使用标准库。所有命令均在本机运行，不访问微信、不发送消息、不调用大模型。

```bash
python scripts/procurement.py --help
```

## init

```bash
python scripts/procurement.py init --output ./procurement-data
```

创建空白模板和目录，包括 `price-estimate.json` 和 `intake-questions.json`。已有模板时默认停止；`--force` 会覆盖模板文件，真实项目使用前应先备份。

## intake

```bash
python scripts/procurement.py intake --project ./procurement-data
```

要求 `requirement.json` 的 `intake_status` 为 `已确认`，并检查工艺、配置、采购策略、数量等字段。生成 `reports/requirement-summary.md`。交互问题库位于 `assets/intake-questions.json`，应由宿主的弹窗组件询问用户。

## price

```bash
python scripts/procurement.py price --project ./procurement-data
```

校验 `price-estimate.json` 的成本依据和市场样本，计算生产制造成本、全成本、估算出厂价和公开样本区间。生成 `reports/price-intelligence.md` 和 `reports/price-estimate-result.json`。

## suppliers

```bash
python scripts/procurement.py suppliers --project ./procurement-data
```

校验来源、ID、厂家等级、匹配度和日期，生成 CSV、Markdown 和校验文本。Markdown 的“公开业务联系”合并官网、电话、邮箱和公开微信；CSV 同时保留分字段和 `public_business_contact` 合并字段。有错误时退出码为 1。

## outreach

```bash
python scripts/procurement.py outreach --project ./procurement-data
```

生成人工添加队列、待确认发送队列、逐家询价草稿和统一询价单。不执行外部动作。

## collect

```bash
python scripts/procurement.py collect --project ./procurement-data
```

扫描 `quotes/inbox/`，把符合命名和格式要求的文件复制到 `quotes/collected/`。原件不移动、不删除；重复内容不重复归档。

## analyze

```bash
python scripts/procurement.py analyze --project ./procurement-data
```

读取 AI 已填写且有证据的 `quotes.json`，按 `config.json` 评分。生成 `analysis.json`、评分 CSV 和报价分析报告。有效报价不足 2 家时不给候选。

## duediligence

```bash
python scripts/procurement.py duediligence --project ./procurement-data
```

按用户弹窗决策做供应商背景调查。首次运行若缺少 `background-check.json` 会生成模板并提示先弹窗；`decision` 未确认或 `decision_source` 缺日期一律报错。用户选择"暂不需要"时写入未做背调的说明；选择调查时校验 `findings` 的每项结论是否带来源与日期，然后生成 `background-check-result.json`、`background-scores.csv` 和 `supplier-background-check.md`（综合实力排名＋逐家明细＋待核验清单）。命中红线的厂家标注为建议剔除或暂缓定点。

## report

```bash
python scripts/procurement.py report --project ./procurement-data
```

汇总本地阶段状态、候选名单、背景调查结论、人工待办和未实现项，生成 `completion-report.md`。

## 数据与隐私

真实项目可能包含报价、联系人和商业条款。不要把真实 `procurement-data/`、`.env`、账号凭据或聊天导出提交到公开 GitHub；仓库 `.gitignore` 已默认忽略常见真实数据目录。
