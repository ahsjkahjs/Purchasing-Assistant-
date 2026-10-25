#!/usr/bin/env python3
"""Auditable local helpers for the auto-procurement skill.

This script never accesses WeChat, sends messages, calls an LLM, or places orders.
It only initializes files, validates requirements and price evidence, prepares drafts,
copies quotation files, scores structured quotation data, and renders reports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSETS = SKILL_ROOT / "assets"
MISSING_VALUES = {"", "未公开", "未查到", "未知", "n/a", "none", "null"}
SUPPORTED_QUOTE_EXTENSIONS = {
    ".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc",
    ".png", ".jpg", ".jpeg", ".txt", ".md",
}
SUPPLIER_FIELDS = [
    "id", "company", "website", "province", "city", "products",
    "manufacturer_grade", "evidence", "contact_name", "phone", "email",
    "wechat", "source_url", "source_date", "match_score", "tier", "notes",
]
BACKGROUND_DIMENSIONS = [
    "工商与实控", "司法与失信", "产能与设备", "资质与认证",
    "客户与业绩", "出口与履约", "财务与开票", "风险信号",
]
BACKGROUND_SKIP_DECISIONS = {"暂不需要", "不需要", "暂缓", "跳过", "否"}


class ProcurementError(Exception):
    """An expected input or workflow error."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: Path):
    if not path.is_file():
        raise ProcurementError(f"缺少文件：{path}")
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProcurementError(f"JSON 无法读取：{path}；{exc}") from exc


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_csv(path: Path, fields, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def update_state(project: Path, stage: str, **details) -> None:
    path = project / "state.json"
    state = load_json(path) if path.exists() else {"project_created_at": now_iso(), "stages": {}}
    state.setdefault("stages", {})[stage] = {"updated_at": now_iso(), **details}
    write_json(path, state)


def is_missing(value) -> bool:
    return value is None or str(value).strip().lower() in MISSING_VALUES


def display(value) -> str:
    return "未公开" if is_missing(value) else str(value).strip()


def valid_url(value) -> bool:
    try:
        parsed = urlparse(str(value))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except (TypeError, ValueError):
        return False


def md(value) -> str:
    return display(value).replace("|", "\\|").replace("\n", " ")


def public_contact_text(supplier, markdown: bool = False) -> str:
    parts = []
    website = supplier.get("website")
    if not is_missing(website):
        parts.append(f"[官网]({website})" if markdown and valid_url(website) else f"网站：{website}")
    for label, field in [("电话", "phone"), ("邮箱", "email"), ("微信", "wechat")]:
        value = supplier.get(field)
        if not is_missing(value):
            parts.append(f"{label}：{value}")
    if not parts:
        return "未公开"
    return "<br>".join(parts) if markdown else "；".join(parts)


def source_link(value) -> str:
    return f"[原文]({value})" if valid_url(value) else md(value)




def number(value, field: str, minimum=None, maximum=None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProcurementError(f"{field} 必须是数字，当前为：{value!r}")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ProcurementError(f"{field} 不得小于 {minimum}")
    if maximum is not None and result > maximum:
        raise ProcurementError(f"{field} 不得大于 {maximum}")
    return result


def command_init(args) -> None:
    project = Path(args.output).expanduser().resolve()
    targets = ["requirement.json", "suppliers.json", "quotes.json", "config.json", "price-estimate.json"]
    existing = [name for name in targets if (project / name).exists()]
    if existing and not args.force:
        raise ProcurementError(f"项目已有文件 {existing}；如需覆盖模板，请显式使用 --force")

    for relative in ["quotes/inbox", "quotes/collected", "outreach", "reports"]:
        (project / relative).mkdir(parents=True, exist_ok=True)
    copies = {
        "requirement.template.json": "requirement.json",
        "suppliers.template.json": "suppliers.json",
        "quotes.template.json": "quotes.json",
        "analysis-config.json": "config.json",
        "price-estimate.template.json": "price-estimate.json",
        "intake-questions.json": "intake-questions.json",
        "background-questions.json": "background-questions.json",
        "background-check.template.json": "background-check.json",
        "rfq-template.md": "outreach/rfq-template.md",
        "ai-quote-extraction.md": "outreach/ai-quote-extraction.md",
    }
    for source, target in copies.items():
        source_path = ASSETS / source
        if not source_path.is_file():
            raise ProcurementError(f"Skill 模板缺失：{source_path}")
        shutil.copyfile(source_path, project / target)
    write_json(project / "state.json", {
        "project_created_at": now_iso(),
        "external_actions": "未执行；企业微信添加和消息发送均需人工处理",
        "stages": {"init": {"updated_at": now_iso(), "status": "已初始化"}},
    })
    print(f"采购项目已初始化：{project}")
    print("下一步：先弹窗补齐需求，再运行 intake；随后做价格评估，最后填写 suppliers.json。")


def requirement_errors(requirement) -> list:
    if not isinstance(requirement, dict):
        return ["requirement.json 必须是对象"]
    errors = []
    if requirement.get("intake_status") != "已确认":
        errors.append("intake_status 必须为“已确认”；先通过弹窗/表单补齐需求")
    for field in ["product_name", "model", "application", "quantity", "unit", "delivery_location",
                  "procurement_strategy", "configuration"]:
        if is_missing(requirement.get(field)):
            errors.append(f"缺需求字段 {field}")
    if not requirement.get("processes"):
        errors.append("processes 至少选择一项主要工艺")
    try:
        if number(requirement.get("quantity"), "quantity", 0.000001) <= 0:
            errors.append("quantity 必须大于 0")
    except ProcurementError as exc:
        errors.append(str(exc))
    return errors


def command_intake(args) -> None:
    project = Path(args.project).expanduser().resolve()
    requirement = load_json(project / "requirement.json")
    errors = requirement_errors(requirement)
    if errors:
        raise ProcurementError("需求尚未确认：" + "；".join(errors))
    processes = "、".join(str(item) for item in requirement.get("processes") or [])
    lines = [
        "# 采购需求确认摘要", "", f"确认时间：{now_iso()}", "",
        f"- 项目：{requirement.get('project_name', '未命名')}",
        f"- 产品：{requirement.get('product_name')}",
        f"- 型号/基准：{requirement.get('model')}",
        f"- 主要工艺：{processes}",
        f"- 应用与工况：{requirement.get('application')}",
        f"- 数量：{requirement.get('quantity')} {requirement.get('unit')}",
        f"- 配置口径：{requirement.get('configuration')}",
        f"- 采购策略：{requirement.get('procurement_strategy')}",
        f"- 收货地：{requirement.get('delivery_location')}",
        f"- 报价截止：{requirement.get('quotation_deadline', '未定')}", "",
        "## 技术规格", "",
    ] + [f"- {item}" for item in requirement.get("specifications") or []]
    if requirement.get("intake_notes"):
        lines += ["", "## 补充说明", "", str(requirement["intake_notes"])]
    lines += ["", "> 本摘要只确认采购口径，不代表技术方案已由厂家校验，也不构成报价或定点。"]
    write_text(project / "reports/requirement-summary.md", "\n".join(lines) + "\n")
    update_state(project, "intake", status="需求已确认", processes=len(requirement.get("processes") or []))
    print(f"需求摘要已生成：{project / 'reports/requirement-summary.md'}")


def rate_range(value, field: str) -> tuple:
    if not isinstance(value, dict):
        raise ProcurementError(f"{field} 必须是包含 low/high 的对象")
    low = number(value.get("low"), f"{field}.low", 0, 1)
    high = number(value.get("high"), f"{field}.high", 0, 1)
    if low > high:
        raise ProcurementError(f"{field}.low 不得大于 high")
    return low, high


def command_price(args) -> None:
    project = Path(args.project).expanduser().resolve()
    requirement = load_json(project / "requirement.json")
    errors = requirement_errors(requirement)
    if errors:
        raise ProcurementError("需求未确认，不能做价格评估：" + "；".join(errors))
    data = load_json(project / "price-estimate.json")
    if not isinstance(data, dict):
        raise ProcurementError("price-estimate.json 必须是对象")
    equipment = display(data.get("equipment"))
    currency = display(data.get("currency"))
    if equipment == "未公开" or currency == "未公开":
        raise ProcurementError("price-estimate.json 缺 equipment 或 currency")
    confidence = data.get("confidence")
    if confidence not in {"低", "中", "高"}:
        raise ProcurementError("confidence 必须为“低/中/高”")
    limitations = [str(item).strip() for item in data.get("limitations") or [] if str(item).strip()]
    if not limitations:
        raise ProcurementError("limitations 至少写一条，列明价格口径和证据边界")

    items = data.get("cost_items") or []
    if not isinstance(items, list) or not items:
        raise ProcurementError("cost_items 必须是非空数组")
    normalized_items = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ProcurementError(f"cost_items 第 {index} 项必须是对象")
        name = display(item.get("name"))
        if name == "未公开" or is_missing(item.get("basis")):
            raise ProcurementError(f"cost_items 第 {index} 项缺 name 或 basis")
        low = number(item.get("low"), f"cost_items[{index}].low", 0.01)
        high = number(item.get("high"), f"cost_items[{index}].high", low)
        normalized_items.append({"name": name, "low": low, "high": high, "basis": str(item["basis"])})

    overhead_low, overhead_high = rate_range(data.get("manufacturing_overhead_rate"), "manufacturing_overhead_rate")
    sales_low, sales_high = rate_range(data.get("sales_management_rate"), "sales_management_rate")
    profit_low, profit_high = rate_range(data.get("profit_rate"), "profit_rate")
    tax_rate = number(data.get("tax_rate"), "tax_rate", 0, 1)
    direct_low = sum(item["low"] for item in normalized_items)
    direct_high = sum(item["high"] for item in normalized_items)
    production_low = direct_low * (1 + overhead_low)
    production_high = direct_high * (1 + overhead_high)
    complete_low = production_low * (1 + sales_low)
    complete_high = production_high * (1 + sales_high)
    ex_factory_low = production_low * (1 + sales_low + profit_low)
    ex_factory_high = production_high * (1 + sales_high + profit_high)
    tax_included_low = ex_factory_low * (1 + tax_rate)
    tax_included_high = ex_factory_high * (1 + tax_rate)

    samples = data.get("market_samples") or []
    if not isinstance(samples, list) or not samples:
        raise ProcurementError("market_samples 至少需要一条公开价格证据")
    normalized_samples = []
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, dict):
            raise ProcurementError(f"market_samples 第 {index} 项必须是对象")
        for field in ["supplier", "model", "price_basis", "sample_type", "source_url", "source_date", "notes"]:
            if is_missing(sample.get(field)):
                raise ProcurementError(f"market_samples 第 {index} 项缺 {field}")
        if not valid_url(sample.get("source_url")):
            raise ProcurementError(f"market_samples 第 {index} 项 source_url 无效")
        try:
            datetime.strptime(str(sample["source_date"]), "%Y-%m-%d")
        except ValueError as exc:
            raise ProcurementError(f"market_samples 第 {index} 项 source_date 必须为 YYYY-MM-DD") from exc
        low = number(sample.get("low"), f"market_samples[{index}].low", 0.01)
        high = number(sample.get("high"), f"market_samples[{index}].high", low)
        normalized_samples.append({
            "supplier": str(sample["supplier"]), "model": str(sample["model"]),
            "low": low, "high": high, "price_basis": str(sample["price_basis"]),
            "sample_type": str(sample["sample_type"]), "source_url": str(sample["source_url"]),
            "source_date": str(sample["source_date"]), "notes": str(sample["notes"]),
        })

    market_low = min(item["low"] for item in normalized_samples)
    market_high = max(item["high"] for item in normalized_samples)
    budget = data.get("budget_recommendation")
    if budget is not None:
        if not isinstance(budget, dict) or is_missing(budget.get("basis")):
            raise ProcurementError("budget_recommendation 必须是含 low/high/basis 的对象")
        budget = {
            "low": number(budget.get("low"), "budget_recommendation.low", 0.01),
            "high": number(budget.get("high"), "budget_recommendation.high", 0.01),
            "basis": str(budget["basis"]),
        }
        if budget["low"] > budget["high"]:
            raise ProcurementError("budget_recommendation.low 不得大于 high")

    def money(value):
        return f"{value:,.0f}"

    result = {
        "generated_at": now_iso(), "equipment": equipment, "currency": currency,
        "confidence": confidence, "limitations": limitations,
        "cost_items": normalized_items,
        "calculations": {
            "direct_cost": {"low": round(direct_low, 2), "high": round(direct_high, 2)},
            "production_cost": {"low": round(production_low, 2), "high": round(production_high, 2)},
            "complete_cost": {"low": round(complete_low, 2), "high": round(complete_high, 2)},
            "factory_price_ex_tax": {"low": round(ex_factory_low, 2), "high": round(ex_factory_high, 2)},
            "factory_price_tax_included": {"low": round(tax_included_low, 2), "high": round(tax_included_high, 2)},
        },
        "market_samples": normalized_samples,
        "market_observed_range": {"low": market_low, "high": market_high},
        "budget_recommendation": budget,
        "decision_boundary": "仅为采购前期估算；公开挂牌价不是正式报价，制造成本不是供应商成本审计",
    }
    write_json(project / "reports/price-estimate-result.json", result)

    lines = [
        "# 设备价格与生产成本评估", "", f"生成时间：{result['generated_at']}",
        f"设备：{equipment}；币种：{currency}；证据置信度：{confidence}", "",
        "## 结果摘要", "",
        "| 口径 | 低值 | 高值 | 说明 |",
        "|---|---:|---:|---|",
        f"| 直接制造成本 | {money(direct_low)} | {money(direct_high)} | 结构、液压、电气、加工、外协、包装等 |",
        f"| 生产制造成本 | {money(production_low)} | {money(production_high)} | 直接成本＋制造费用 |",
        f"| 全成本 | {money(complete_low)} | {money(complete_high)} | 生产制造成本＋销售管理费用，不含利润 |",
        f"| 估算出厂价（未税） | {money(ex_factory_low)} | {money(ex_factory_high)} | 全成本＋利润 |",
        f"| 估算出厂价（含税） | {money(tax_included_low)} | {money(tax_included_high)} | 按税率 {tax_rate:.1%} |",
        f"| 公开样本观察区间 | {money(market_low)} | {money(market_high)} | 口径混合，不可直接作为成交价 |",
    ]
    if budget:
        lines.append(f"| 首轮询价预算参考 | {money(budget['low'])} | {money(budget['high'])} | {budget['basis']} |")
    lines += ["", "## 成本拆分", "", "| 成本项 | 低值 | 高值 | 依据 |", "|---|---:|---:|---|"]
    for item in normalized_items:
        lines.append(f"| {md(item['name'])} | {money(item['low'])} | {money(item['high'])} | {md(item['basis'])} |")
    lines += ["", "## 公开市场价格样本", "",
              "| 厂家/来源 | 型号与配置 | 低值 | 高值 | 类型与口径 | 来源 |",
              "|---|---|---:|---:|---|---|"]
    for sample in normalized_samples:
        lines.append(
            f"| {md(sample['supplier'])} | {md(sample['model'])} | {money(sample['low'])} | "
            f"{money(sample['high'])} | {md(sample['sample_type'])}；{md(sample['price_basis'])}；{md(sample['notes'])} | "
            f"[来源]({sample['source_url']})（{sample['source_date']}） |"
        )
    lines += ["", "## 使用边界", ""] + [f"- {item}" for item in limitations]
    lines += [
        "", "价格评估只用于询价准备和预算控制。正式比价必须使用同一数量、税费、运输、安装和配置口径的报价单。",
    ]
    write_text(project / "reports/price-intelligence.md", "\n".join(lines) + "\n")
    update_state(project, "price", status="价格评估完成", confidence=confidence, samples=len(normalized_samples))
    print(
        f"价格评估完成：生产制造成本 {money(production_low)}–{money(production_high)}；"
        f"公开样本 {money(market_low)}–{money(market_high)}"
    )


def validate_suppliers(suppliers):
    if not isinstance(suppliers, list) or not suppliers:
        raise ProcurementError("suppliers.json 必须是非空数组")
    errors, warnings = [], []
    seen_ids = set()
    contact_owners = {"phone": {}, "wechat": {}}
    required = ["id", "company", "products", "manufacturer_grade", "evidence", "source_url", "source_date"]

    for index, supplier in enumerate(suppliers, start=1):
        if not isinstance(supplier, dict):
            errors.append(f"第 {index} 项不是对象")
            continue
        label = display(supplier.get("id", f"第{index}项"))
        for field in required:
            if is_missing(supplier.get(field)):
                errors.append(f"{label} 缺必填字段 {field}")
        supplier_id = str(supplier.get("id", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", supplier_id):
            errors.append(f"{label} 的 id 只能含字母、数字、下划线和连字符")
        elif supplier_id in seen_ids:
            errors.append(f"供应商 ID 重复：{supplier_id}")
        seen_ids.add(supplier_id)
        if supplier.get("manufacturer_grade") not in {"A", "B", "C"}:
            errors.append(f"{label} 的 manufacturer_grade 必须为 A/B/C")
        try:
            match_score = number(supplier.get("match_score"), f"{label}.match_score", 1, 5)
            if not match_score.is_integer():
                errors.append(f"{label}.match_score 必须为 1–5 的整数")
        except ProcurementError as exc:
            errors.append(str(exc))
        if not is_missing(supplier.get("source_url")) and not valid_url(supplier.get("source_url")):
            errors.append(f"{label}.source_url 不是有效 HTTP(S) URL")
        source_date = str(supplier.get("source_date", ""))
        try:
            datetime.strptime(source_date, "%Y-%m-%d")
        except ValueError:
            errors.append(f"{label}.source_date 必须为 YYYY-MM-DD")

        contact_sources = supplier.get("contact_sources") or {}
        for field in ["phone", "email", "wechat"]:
            value = supplier.get(field)
            if not is_missing(value):
                if not valid_url(contact_sources.get(field, "")):
                    errors.append(f"{label}.{field} 已填写，但 contact_sources.{field} 缺有效来源 URL")
                owners = contact_owners.setdefault(field, {})
                normalized = re.sub(r"\s+", "", str(value)).lower()
                if normalized in owners and owners[normalized] != supplier_id:
                    warnings.append(f"{field} 被 {owners[normalized]} 与 {supplier_id} 共用，需人工核验")
                owners[normalized] = supplier_id
    return errors, warnings


def command_suppliers(args) -> None:
    project = Path(args.project).expanduser().resolve()
    suppliers = load_json(project / "suppliers.json")
    errors, warnings = validate_suppliers(suppliers)
    report = ["供应商清单校验", f"时间：{now_iso()}", f"总数：{len(suppliers)}", ""]
    report += ["错误："] + [f"- {item}" for item in errors] if errors else ["错误：无"]
    report += ["", "警告："] + [f"- {item}" for item in warnings] if warnings else ["", "警告：无"]
    write_text(project / "reports/supplier-validation.txt", "\n".join(report) + "\n")
    if errors:
        update_state(project, "suppliers", status="校验失败", count=len(suppliers), errors=len(errors))
        raise ProcurementError(f"供应商清单有 {len(errors)} 个错误，详见 reports/supplier-validation.txt")

    rows = []
    for supplier in suppliers:
        row = {field: display(supplier.get(field)) for field in SUPPLIER_FIELDS}
        for field in ["phone", "email", "wechat"]:
            row[f"{field}_source"] = display((supplier.get("contact_sources") or {}).get(field))
        row["public_business_contact"] = public_contact_text(supplier)
        rows.append(row)
    csv_fields = SUPPLIER_FIELDS + ["phone_source", "email_source", "wechat_source", "public_business_contact"]
    write_csv(project / "reports/suppliers.csv", csv_fields, rows)

    lines = [
        "# 供货商清单", "", f"> 校验时间：{now_iso()}。联系方式来自所填公开来源，使用前仍需人工复核。", "",
        "| ID | 公司 | 产品 | 厂家等级 | 匹配度 | 公开业务联系 | 来源 |",
        "|---|---|---|---|---:|---|---|",
    ]
    for supplier in suppliers:
        lines.append("| " + " | ".join([
            md(supplier.get("id")), md(supplier.get("company")), md(supplier.get("products")),
            md(supplier.get("manufacturer_grade")), md(supplier.get("match_score")),
            public_contact_text(supplier, markdown=True),
            source_link(supplier.get("source_url")),
        ]) + " |")
    if warnings:
        lines += ["", "## 待核验警告"] + [f"- {item}" for item in warnings]
    write_text(project / "reports/supplier-list.md", "\n".join(lines) + "\n")
    update_state(project, "suppliers", status="清单已生成", count=len(suppliers), warnings=len(warnings))
    print(f"供应商清单已生成：{len(suppliers)} 家；警告 {len(warnings)} 条")


def requirement_text(requirement, supplier) -> str:
    specifications = requirement.get("specifications") or []
    spec_text = "；".join(str(item) for item in specifications) if specifications else "待双方确认"
    return (
        f"你好，我们在采购{requirement.get('product_name', '设备')}"
        f"（型号：{requirement.get('model', '待确认')}），看到贵司经营{supplier.get('products', '相关产品')}。"
        f"本次数量 {requirement.get('quantity', '待确认')} {requirement.get('unit', '')}，"
        f"主要规格：{spec_text}。请按统一询价单提供含税、运费、包装、交期、质保、付款条件和报价有效期，"
        f"并附对应型号资料及质量/认证证明。报价截止：{requirement.get('quotation_deadline', '待确认')}。"
        "如有关键参数需要确认，请直接列出来，我们先统一口径再报价。"
    )


def command_outreach(args) -> None:
    project = Path(args.project).expanduser().resolve()
    suppliers = load_json(project / "suppliers.json")
    errors, _ = validate_suppliers(suppliers)
    if errors:
        raise ProcurementError("供应商清单未通过校验，请先运行 suppliers 并修正错误")
    requirement = load_json(project / "requirement.json")

    add_rows, send_rows = [], []
    drafts = [
        "# 逐家询价草稿", "",
        "> 以下均为草稿，未添加好友、未发送。发送前须人工核对公司、联系人、型号、数量与口径。", "",
    ]
    for supplier in suppliers:
        wechat = display(supplier.get("wechat"))
        add_rows.append({
            "supplier_id": supplier["id"], "company": supplier["company"],
            "website": display(supplier.get("website")),
            "public_wechat": wechat,
            "public_business_contact": public_contact_text(supplier),
            "status": "待人工添加" if wechat != "未公开" else "缺公开微信号",
            "source": display((supplier.get("contact_sources") or {}).get("wechat")),
            "note": "人工核验主体后逐个操作；不得批量绕过平台限制",
        })
        send_rows.append({
            "supplier_id": supplier["id"], "company": supplier["company"],
            "channel": "企业微信/邮件/电话（人工选择）", "status": "待人工确认",
            "sent_at": "", "operator": "", "follow_up": "待报价",
        })
        drafts += [f"## {supplier['id']}｜{supplier['company']}", "", requirement_text(requirement, supplier), ""]

    write_csv(project / "outreach/wechat-add-queue.csv",
              ["supplier_id", "company", "website", "public_wechat", "public_business_contact",
               "status", "source", "note"], add_rows)
    write_csv(project / "outreach/send-queue.csv",
              ["supplier_id", "company", "channel", "status", "sent_at", "operator", "follow_up"], send_rows)
    write_text(project / "outreach/rfq-drafts.md", "\n".join(drafts))

    requirement_lines = [
        f"# 询价单｜{requirement.get('project_name', '采购项目')}", "",
        f"- 产品：{requirement.get('product_name', '待确认')}",
        f"- 型号：{requirement.get('model', '待确认')}",
        f"- 数量：{requirement.get('quantity', '待确认')} {requirement.get('unit', '')}",
        f"- 规格：{'；'.join(requirement.get('specifications') or []) or '待确认'}",
        f"- 收货地：{requirement.get('delivery_location', '待确认')}",
        f"- 要求交期：{requirement.get('required_delivery_date', '待确认')}",
        f"- 报价口径：{requirement.get('currency', 'CNY')}，税率 {requirement.get('tax_rate', '待确认')}，{requirement.get('trade_terms', '待确认')}",
        f"- 报价截止：{requirement.get('quotation_deadline', '待确认')}", "",
        "请回填：含税单价、含税总价、运费、包装费、模具/调试费、交期、质保、付款条件、报价有效期、偏离项。",
    ]
    write_text(project / "outreach/rfq-sheet.md", "\n".join(requirement_lines) + "\n")
    update_state(project, "outreach", status="草稿已生成，等待人工添加与发送", count=len(suppliers), sent=0)
    print("人工添加队列与询价草稿已生成；未执行加好友或发送消息")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned or "quotation"


def command_collect(args) -> None:
    project = Path(args.project).expanduser().resolve()
    inbox, collected = project / "quotes/inbox", project / "quotes/collected"
    inbox.mkdir(parents=True, exist_ok=True)
    collected.mkdir(parents=True, exist_ok=True)
    suppliers = load_json(project / "suppliers.json")
    valid_ids = {str(item.get("id")) for item in suppliers if isinstance(item, dict)}
    existing_by_hash = {}
    for path in collected.iterdir():
        if path.is_file():
            existing_by_hash.setdefault(sha256(path), path)

    rows, seen = [], set()
    files = sorted(path for path in inbox.rglob("*") if path.is_file())
    for source in files:
        digest = sha256(source)
        relative = source.relative_to(inbox).as_posix()
        match = re.match(r"^([A-Za-z0-9_-]+)__", source.name)
        supplier_id = match.group(1) if match else ""
        row = {
            "supplier_id": supplier_id or "未识别", "original_file": relative,
            "collected_file": "", "sha256": digest, "status": "", "note": "",
        }
        if source.suffix.lower() not in SUPPORTED_QUOTE_EXTENSIONS:
            row.update(status="待处理", note="不支持的格式；未复制，不得执行该文件")
        elif not supplier_id or supplier_id not in valid_ids:
            row.update(status="待处理", note="文件名须以有效供应商 ID 加双下划线开头")
        elif digest in seen:
            row.update(status="重复文件", note="本次收件中已有相同内容")
        elif digest in existing_by_hash:
            row.update(status="已归档", note="目标目录已有相同内容，未重复复制")
            row["collected_file"] = existing_by_hash[digest].name
        else:
            original_name = safe_filename(source.name)
            prefix = f"{supplier_id}__"
            stored_name = original_name if original_name.startswith(prefix) else prefix + original_name
            destination = collected / stored_name
            if destination.exists():
                destination = collected / f"{destination.stem}_{digest[:8]}{destination.suffix}"
            shutil.copy2(source, destination)
            existing_by_hash[digest] = destination
            row.update(status="已归档", collected_file=destination.name, note="原件保留在 inbox")
        seen.add(digest)
        rows.append(row)

    fields = ["supplier_id", "original_file", "collected_file", "sha256", "status", "note"]
    write_csv(project / "reports/quote-manifest.csv", fields, rows)
    counts = {status: sum(row["status"] == status for row in rows) for status in ["已归档", "重复文件", "待处理"]}
    update_state(project, "collect", status="归档完成", inbox_files=len(files), **counts)
    print(f"报价归档完成：{counts['已归档']} 份；重复 {counts['重复文件']}；待处理 {counts['待处理']}")


def evidence_fields(quote) -> set:
    evidence = quote.get("evidence") or []
    if not isinstance(evidence, list):
        return set()
    fields = set()
    for item in evidence:
        if isinstance(item, dict) and item.get("field") and item.get("file") and item.get("page") and item.get("quote"):
            fields.add(item["field"])
    return fields


def command_analyze(args) -> None:
    project = Path(args.project).expanduser().resolve()
    quotes = load_json(project / "quotes.json")
    config = load_json(project / "config.json")
    suppliers = {item["id"]: item for item in load_json(project / "suppliers.json")}
    if not isinstance(quotes, list) or not quotes:
        raise ProcurementError("quotes.json 必须是非空数组；先由 AI 从报价原件提取并填写")

    weights = config.get("weights") or {}
    weight_names = ["price", "quality", "delivery", "commercial", "completeness"]
    normalized_weights = {}
    for name in weight_names:
        normalized_weights[name] = number(weights.get(name), f"weights.{name}", 0)
    weight_sum = sum(normalized_weights.values())
    if weight_sum <= 0:
        raise ProcurementError("评分权重之和必须大于 0")
    normalized_weights = {key: value / weight_sum for key, value in normalized_weights.items()}

    prepared, currencies = [], set()
    seen_ids = set()
    required_evidence = {"normalized_total_cost", "quality_score", "lead_time_days"}
    for quote in quotes:
        if not isinstance(quote, dict):
            raise ProcurementError("quotes.json 中每项必须是对象")
        supplier_id = str(quote.get("supplier_id", ""))
        if supplier_id not in suppliers:
            raise ProcurementError(f"报价供应商 ID 不在 suppliers.json：{supplier_id}")
        if supplier_id in seen_ids:
            raise ProcurementError(f"同一供应商存在多份结构化报价，请先选定有效版本：{supplier_id}")
        seen_ids.add(supplier_id)
        item = dict(quote)
        reasons = [str(quote.get("exclusion_reason") or "").strip()]
        missing_evidence = required_evidence - evidence_fields(quote)
        if missing_evidence:
            reasons.append("关键字段缺文件/页码/原文证据：" + "、".join(sorted(missing_evidence)))
        eligible = quote.get("eligible") is True and not missing_evidence
        if quote.get("eligible") is not True and not reasons[0]:
            reasons[0] = "未通过报价完整性或口径检查"
        item["eligible"] = eligible
        item["exclusion_reason"] = "；".join(reason for reason in reasons if reason)
        if not eligible:
            prepared.append(item)
            continue

        item["normalized_total_cost"] = number(quote.get("normalized_total_cost"), f"{supplier_id}.normalized_total_cost", 0.000001)
        item["quality_score"] = number(quote.get("quality_score"), f"{supplier_id}.quality_score", 0, 100)
        item["lead_time_days"] = number(quote.get("lead_time_days"), f"{supplier_id}.lead_time_days", 0.000001)
        item["warranty_months"] = number(quote.get("warranty_months"), f"{supplier_id}.warranty_months", 0)
        item["payment_days"] = number(quote.get("payment_days"), f"{supplier_id}.payment_days", 0)
        item["completeness_score"] = number(quote.get("completeness_score"), f"{supplier_id}.completeness_score", 0, 100)
        item["risk_penalty"] = number(quote.get("risk_penalty", 0), f"{supplier_id}.risk_penalty", 0, 100)
        currencies.add(str(quote.get("currency") or config.get("currency") or "CNY"))
        prepared.append(item)

    eligible_quotes = [quote for quote in prepared if quote["eligible"]]
    if len(currencies) > 1:
        raise ProcurementError("有效报价仍有多个币种，请先换算为同一币种再排名")

    if eligible_quotes:
        minimum_cost = min(quote["normalized_total_cost"] for quote in eligible_quotes)
        fastest_lead = min(quote["lead_time_days"] for quote in eligible_quotes)
        target_warranty = number(config.get("target_warranty_months", 12), "target_warranty_months", 0.000001)
        target_payment = number(config.get("target_payment_days", 30), "target_payment_days", 0.000001)
        for quote in prepared:
            if not quote["eligible"]:
                quote.update(total_score=None, rank=None, shortlist=False)
                continue
            price_score = minimum_cost / quote["normalized_total_cost"] * 100
            delivery_score = fastest_lead / quote["lead_time_days"] * 100
            commercial_score = 50 * min(quote["warranty_months"] / target_warranty, 1) + 50 * min(quote["payment_days"] / target_payment, 1)
            component_scores = {
                "price": price_score, "quality": quote["quality_score"],
                "delivery": delivery_score, "commercial": commercial_score,
                "completeness": quote["completeness_score"],
            }
            total = sum(normalized_weights[key] * value for key, value in component_scores.items()) - quote["risk_penalty"]
            quote["component_scores"] = {key: round(value, 2) for key, value in component_scores.items()}
            quote["total_score"] = round(max(0, total), 2)

        ranked = sorted(eligible_quotes, key=lambda item: (-item["total_score"], item["normalized_total_cost"], item["supplier_id"]))
        shortlist_size = int(number(config.get("shortlist_size", 3), "shortlist_size", 2, 3))
        for rank, quote in enumerate(ranked, start=1):
            quote["rank"] = rank
            quote["shortlist"] = len(eligible_quotes) >= 2 and rank <= shortlist_size
    shortlist = [quote for quote in prepared if quote.get("shortlist")]
    currency = next(iter(currencies), config.get("currency", "CNY"))
    analysis = {
        "generated_at": now_iso(), "currency": currency,
        "weights": {key: round(value, 4) for key, value in normalized_weights.items()},
        "eligible_count": len(eligible_quotes), "shortlist": [quote["supplier_id"] for quote in shortlist],
        "quotes": prepared,
        "decision_boundary": "候选排序仅供人工复核，不构成自动定点或下单决定",
    }
    write_json(project / "reports/analysis.json", analysis)

    score_rows = []
    for quote in sorted(prepared, key=lambda item: (item.get("rank") is None, item.get("rank") or 9999)):
        score_rows.append({
            "supplier_id": quote["supplier_id"], "company": suppliers[quote["supplier_id"]]["company"],
            "eligible": quote["eligible"], "currency": quote.get("currency", currency),
            "normalized_total_cost": quote.get("normalized_total_cost", ""),
            "quality_score": quote.get("quality_score", ""),
            "lead_time_days": quote.get("lead_time_days", ""),
            "total_score": quote.get("total_score") if quote.get("total_score") is not None else "",
            "rank": quote.get("rank") or "", "shortlist": quote.get("shortlist", False),
            "exclusion_reason": quote.get("exclusion_reason", ""),
        })
    write_csv(project / "reports/supplier-scores.csv", list(score_rows[0].keys()), score_rows)

    lines = [
        "# 报价分析报告", "", f"> 生成时间：{analysis['generated_at']}。评分只用于筛选候选，最终定点须人工复核原件。", "",
        f"- 有效报价：{len(eligible_quotes)} 家；结构化报价：{len(prepared)} 家",
        f"- 统一币种：{currency}",
        "- 权重：" + " / ".join(f"{key} {value:.1%}" for key, value in normalized_weights.items()), "",
        "| 排名 | 供应商 | 归一化总成本 | 质量分 | 交期(天) | 总分 | 候选 | 排除/风险说明 |",
        "|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for row in score_rows:
        lines.append(
            f"| {row['rank']} | {md(row['company'])} | {row['normalized_total_cost']} | "
            f"{row['quality_score']} | {row['lead_time_days']} | {row['total_score']} | "
            f"{'是' if row['shortlist'] else '否'} | {md(row['exclusion_reason'])} |"
        )
    if len(eligible_quotes) < 2:
        lines += ["", "## 结论", "", "有效报价不足 2 家，不能形成 2–3 家候选名单。请补充报价或完成缺项追问。"]
    else:
        lines += ["", "## 建议人工复核的候选"]
        for quote in shortlist:
            lines += ["", f"### {quote['rank']}. {suppliers[quote['supplier_id']]['company']}",
                      f"- 总分：{quote['total_score']}；归一化总成本：{quote['normalized_total_cost']} {currency}",
                      f"- 备注：{quote.get('notes') or '无'}", "- 关键证据："]
            for evidence in quote.get("evidence", []):
                if evidence.get("field") in required_evidence:
                    lines.append(f"  - {evidence.get('field')}：`{evidence.get('file')}` 第 {evidence.get('page')} 页，原文“{evidence.get('quote')}”")
    write_text(project / "reports/quote-analysis.md", "\n".join(lines) + "\n")
    update_state(project, "analyze", status="分析完成", eligible=len(eligible_quotes), shortlist=len(shortlist))
    print(f"报价分析完成：有效 {len(eligible_quotes)} 家；候选 {len(shortlist)} 家")


def dimension_weights(config, profile, dimensions) -> dict:
    section = config.get("background_check") or {}
    table = section.get("dimension_weights") or {}
    weights = table.get(profile) or table.get(section.get("default_profile", "均衡"))
    if not isinstance(weights, dict) or not weights:
        return {name: 1 for name in dimensions}
    return {name: number(weights.get(name, 1), f"dimension_weights.{name}", 0) for name in dimensions}


def evaluate_finding(item, dimension, strictness):
    """Return (record, errors). One disclosed fact requires one traceable source."""
    record = {
        "dimension": dimension, "summary": "未获得公开证据", "score": None,
        "confidence": "低", "source_url": "", "source_date": "",
        "status": "未获得公开证据", "flags": [], "redline": False,
    }
    if not isinstance(item, dict) or is_missing(item.get("summary")):
        return record, []
    status = str(item.get("status") or "").strip() or "已核查"
    if status == "未获得公开证据":
        record.update(summary=str(item["summary"]).strip(), status=status)
        return record, []
    errors = []
    source_url = str(item.get("source_url") or "").strip()
    source_date = str(item.get("source_date") or "").strip()
    if not valid_url(source_url):
        errors.append(f"{dimension}：结论缺有效 source_url")
    try:
        datetime.strptime(source_date, "%Y-%m-%d")
    except ValueError:
        errors.append(f"{dimension}：source_date 必须为 YYYY-MM-DD")
    confidence = str(item.get("confidence") or "").strip()
    if confidence not in {"低", "中", "高"}:
        errors.append(f"{dimension}：confidence 必须为“低/中/高”")
    try:
        score = number(item.get("score"), f"{dimension}.score", 1, 5)
        if not score.is_integer():
            errors.append(f"{dimension}：score 必须为 1–5 的整数")
    except ProcurementError as exc:
        errors.append(str(exc))
        score = 3
    if errors:
        return record, errors
    if strictness == "每条结论必须有来源链接" and (not valid_url(source_url) or not source_date):
        errors.append(f"{dimension}：当前证据严格度要求每条结论都带来源链接和日期")
        return record, errors
    record.update(
        summary=str(item["summary"]).strip(), score=int(score), confidence=confidence,
        source_url=source_url, source_date=source_date, status=status,
        flags=[str(flag).strip() for flag in (item.get("flags") or []) if str(flag).strip()],
        redline=item.get("redline") is True,
    )
    return record, errors


def command_duediligence(args) -> None:
    project = Path(args.project).expanduser().resolve()
    suppliers = load_json(project / "suppliers.json")
    errors, _ = validate_suppliers(suppliers)
    if errors:
        raise ProcurementError("供应商清单未通过校验，请先运行 suppliers 并修正错误")
    supplier_map = {item["id"]: item for item in suppliers}
    config = load_json(project / "config.json")
    path = project / "background-check.json"
    if not path.is_file():
        template = ASSETS / "background-check.template.json"
        if not template.is_file():
            raise ProcurementError("Skill 模板缺失：background-check.template.json")
        shutil.copyfile(template, path)
        questions = ASSETS / "background-questions.json"
        if questions.is_file():
            shutil.copyfile(questions, project / "background-questions.json")
        raise ProcurementError(
            f"已生成 {path}；请先用弹窗询问用户是否需要背景调查，"
            "再把 decision、target_suppliers、dimensions 和 findings 回填后重跑"
        )

    data = load_json(path)
    if not isinstance(data, dict):
        raise ProcurementError("background-check.json 必须是对象")
    decision = str(data.get("decision", "")).strip()
    if is_missing(decision) or decision == "待用户弹窗确认":
        raise ProcurementError("decision 未确认：必须先用弹窗询问用户是否需要背景调查，不得替用户决定")
    decision_source = str(data.get("decision_source", "")).strip()
    if decision_source.startswith("未填") or not re.search(r"\d{4}-\d{2}-\d{2}", decision_source):
        raise ProcurementError("decision_source 必须写明弹窗答复摘要与日期（YYYY-MM-DD）")

    skipped = decision in BACKGROUND_SKIP_DECISIONS
    meta_lines = [
        "# 供应商背景调查与综合实力", "", f"生成时间：{now_iso()}", "",
        f"- 用户弹窗决策：{md(decision)}",
        f"- 决策来源：{md(decision_source)}",
    ]
    if skipped:
        lines = meta_lines + [
            "", "用户选择暂不进行背景调查。候选名单仅基于公开寻源与报价评分，"
            "未核验工商主体、司法风险、产能与资质，定点前仍建议人工补做一次性核验。",
        ]
        write_text(project / "reports/supplier-background-check.md", "\n".join(lines) + "\n")
        update_state(project, "background_check", status="用户选择暂缓调查", decision=decision)
        print("用户选择暂缓背景调查；已在完成报告中标注未做背调")
        return

    targets = data.get("target_suppliers") or []
    if not isinstance(targets, list) or not targets:
        raise ProcurementError("decision 为进行调查时，target_suppliers 至少需要一家")
    for supplier_id in targets:
        if supplier_id not in supplier_map:
            raise ProcurementError(f"背景调查对象不在 suppliers.json：{supplier_id}")

    requested = [str(item).strip() for item in (data.get("dimensions") or []) if str(item).strip()]
    requested = requested or list(BACKGROUND_DIMENSIONS)
    findings = data.get("findings") or {}
    if not isinstance(findings, dict):
        raise ProcurementError("findings 必须是以供应商 ID 为键的对象")
    for supplier_id in targets:
        if supplier_id in findings and not isinstance(findings[supplier_id], dict):
            raise ProcurementError(f"findings.{supplier_id} 必须是维度对象")

    section = config.get("background_check") or {}
    profile = str(data.get("weight_profile") or section.get("default_profile") or "均衡")
    weights = dimension_weights(config, profile, requested)
    unverified_score = number(section.get("unverified_score", 3), "unverified_score", 1, 5)
    missing_score = number(section.get("missing_dimension_score", 2), "missing_dimension_score", 1, 5)
    redlines = [str(item).strip() for item in (data.get("redlines") or []) if str(item).strip()]
    strictness = str(data.get("evidence_strictness") or "").strip()
    depth = display(data.get("depth"))
    usage = display(data.get("usage"))

    collected_errors, results = [], []
    for supplier_id in targets:
        supplier_findings = findings.get(supplier_id) or {}
        rows, hits, evidence_count = [], [], 0
        weighted_sum, total_weight = 0.0, 0.0
        for dimension in requested:
            record, record_errors = evaluate_finding(supplier_findings.get(dimension), dimension, strictness)
            if record_errors:
                collected_errors += [f"{supplier_id} / {item}" for item in record_errors]
                continue
            weight = weights.get(dimension, 1)
            if record["score"] is None:
                score = unverified_score if record["status"] == "未获得公开证据" else missing_score
            else:
                score = record["score"]
                evidence_count += 1
            if record["redline"] or any(flag in redlines for flag in record["flags"]):
                hits.append(f"{dimension}：{record['summary']}")
            rows.append({**record, "final_score": score, "weight": weight})
            weighted_sum += weight * score
            total_weight += weight
        if collected_errors:
            continue
        total = round(weighted_sum / total_weight / 5 * 100, 2) if total_weight else 0
        scored = [row for row in rows if row["score"] is not None]
        strengths = [item["dimension"] for item in sorted(scored, key=lambda row: (-row["score"], row["dimension"]))
                     if item["score"] >= 4][:3] or [scored[0]["dimension"]] if scored else []
        weaknesses = [item["dimension"] for item in sorted(scored, key=lambda row: (row["score"], row["dimension"]))
                      if item["score"] <= 2][:3]
        unverified = [row["dimension"] for row in rows if row["score"] is None]
        coverage = round(len(scored) / len(requested) * 100, 1)
        if hits:
            recommendation = "建议剔除或暂缓定点（命中一票否决红线）"
        elif total >= 80:
            recommendation = "综合实力充分，可入围定点"
        elif total >= 65:
            recommendation = "可入围，定点前完成待核验清单"
        else:
            recommendation = "证据不足或偏弱，建议先小批量试单"
        results.append({
            "supplier_id": supplier_id, "company": supplier_map[supplier_id]["company"],
            "total_score": total, "coverage": coverage, "evidence_count": evidence_count,
            "strengths": strengths, "weaknesses": weaknesses,
            "unverified_dimensions": unverified, "redline_hits": hits,
            "recommendation": recommendation, "rows": rows,
        })

    if collected_errors:
        raise ProcurementError("背景调查证据不合规：" + "；".join(collected_errors[:8]))

    results.sort(key=lambda item: (-item["total_score"], item["supplier_id"]))
    payload = {
        "generated_at": now_iso(), "decision": decision, "decision_source": decision_source,
        "depth": depth, "usage": usage, "weight_profile": profile,
        "dimensions": requested, "weights": weights, "redlines": redlines,
        "strictness": strictness, "suppliers": results,
        "decision_boundary": "背调结论来自公开信息查询，不等同于现场验厂；综合实力分不与报价评分合并",
    }
    write_json(project / "reports/background-check-result.json", payload)

    write_csv(
        project / "reports/background-scores.csv",
        ["supplier_id", "company", "total_score", "coverage", "evidence_count",
         "redline_count", "recommendation", "strengths", "weaknesses"],
        [{
            "supplier_id": item["supplier_id"], "company": item["company"],
            "total_score": item["total_score"], "coverage": item["coverage"],
            "evidence_count": item["evidence_count"], "redline_count": len(item["redline_hits"]),
            "recommendation": item["recommendation"],
            "strengths": "、".join(item["strengths"]), "weaknesses": "、".join(item["weaknesses"]),
        } for item in results],
    )

    lines = meta_lines + [
        f"- 调查深度：{md(depth)}；证据严格度：{md(strictness)}；加权口径：{md(profile)}",
        f"- 调查对象：{len(results)} 家；维度：{'、'.join(requested)}",
        "", "## 综合实力排名", "",
        "| 排名 | 公司 | 综合实力分 | 证据覆盖 | 红线命中 | 强项 | 弱项 | 建议 |",
        "|---:|---|---:|---:|---:|---|---|---|",
    ]
    for index, item in enumerate(results, start=1):
        weaknesses = "、".join(item["weaknesses"]) or ("无明确弱项" if not item["unverified_dimensions"] else "未取得证据：" + "、".join(item["unverified_dimensions"]))
        lines.append(
            f"| {index} | {md(item['company'])} | {item['total_score']} | {item['coverage']}% | "
            f"{len(item['redline_hits'])} | {'、'.join(item['strengths']) or '未识别'} | "
            f"{md(weaknesses)} | {md(item['recommendation'])} |"
        )
    lines += ["", "> 综合实力分来自公开信息加权，红线命中优先于分数；分数不与报价评分合并。", ""]
    for index, item in enumerate(results, start=1):
        lines += [
            f"## {index}. {item['company']}（{item['supplier_id']}）", "",
            f"- 综合实力分：{item['total_score']}；证据覆盖 {item['coverage']}%；结论：{item['recommendation']}",
            "",
            "| 维度 | 结论摘要 | 得分 | 置信度 | 来源 |",
            "|---|---|---:|---|---|",
        ]
        for row in item["rows"]:
            source = f"[原文]({row['source_url']})（{row['source_date']}）" if row["source_url"] else "未获得公开证据"
            lines.append(
                f"| {md(row['dimension'])} | {md(row['summary'])} | {row['final_score']} | "
                f"{md(row['confidence'])} | {source} |"
            )
        if item["redline_hits"]:
            lines += ["", "**一票否决命中：**"] + [f"- {md(hit)}" for hit in item["redline_hits"]]
        lines.append("")
    lines += [
        "## 待核验清单", "",
        "- 营业执照、开票资料与合同主体是否一致（现场核对原件）。",
        "- 认证证书编号在发证机关公示平台逐一核验。",
        "- 所供批次的材质单、炉批号、检测报告与产地是否对应。",
        "- 大额或长期合作前建议实地验厂，核对产线、产能与员工规模是否与其自述相符。",
    ]
    write_text(project / "reports/supplier-background-check.md", "\n".join(lines) + "\n")
    update_state(
        project, "background_check", status="背景调查完成", decision=decision,
        targets=len(results), redline_suppliers=sum(1 for item in results if item["redline_hits"]),
    )
    top = results[0]["company"] if results else "无"
    print(
        f"背景调查完成：{len(results)} 家；红线命中 "
        f"{sum(1 for item in results if item['redline_hits'])} 家；综合实力首位：{top}"
    )


def command_report(args) -> None:
    project = Path(args.project).expanduser().resolve()
    state = load_json(project / "state.json")
    analysis_path = project / "reports/analysis.json"
    analysis = load_json(analysis_path) if analysis_path.exists() else None
    price_path = project / "reports/price-estimate-result.json"
    price_result = load_json(price_path) if price_path.exists() else None
    suppliers = load_json(project / "suppliers.json")
    supplier_map = {item["id"]: item["company"] for item in suppliers}
    stages = state.get("stages", {})

    lines = [
        "# 自动采购流程完成报告", "", f"生成时间：{now_iso()}", "",
        "## 流程状态", "",
        "| 阶段 | 状态 | 说明 |",
        "|---|---|---|",
        f"| 需求弹窗采集 | {stages.get('intake', {}).get('status', '未运行')} | 需求须经用户确认，不以默认假设代替 |",
        f"| 成本与市场价格评估 | {stages.get('price', {}).get('status', '未运行')} | 公开挂牌价不等于正式报价；须看 confidence 和 limitations |",
        f"| 供应商清单 | {stages.get('suppliers', {}).get('status', '未运行')} | 当前 suppliers.json 共 {len(suppliers)} 家 |",
        "| 企业微信添加 | 人工待办 | 未实现批量自动添加；队列生成不代表已添加 |",
        f"| 询价发送 | {stages.get('outreach', {}).get('status', '未运行')} | 未执行外部发送，需人工确认 |",
        f"| 报价归档 | {stages.get('collect', {}).get('status', '未运行')} | 已归档 {stages.get('collect', {}).get('已归档', 0)} 份，待处理 {stages.get('collect', {}).get('待处理', 0)} 份 |",
        f"| AI 提取与评分 | {stages.get('analyze', {}).get('status', '未运行')} | AI 提取结果须能追溯至报价原件 |",
        f"| 供应商背景调查 | {stages.get('background_check', {}).get('status', '未运行')} | 须先弹窗确认是否调查；命中红线的厂家不进推荐 |",
        "",
        "## 价格评估摘要", "",
    ]
    if price_result:
        calculations = price_result.get("calculations", {})
        production = calculations.get("production_cost", {})
        tax_price = calculations.get("factory_price_tax_included", {})
        observed = price_result.get("market_observed_range", {})
        lines += [
            f"- 价格证据置信度：{price_result.get('confidence', '未填')}",
            f"- 生产制造成本：{production.get('low', 0):,.0f}–{production.get('high', 0):,.0f} {price_result.get('currency', '')}",
            f"- 估算出厂价（含税）：{tax_price.get('low', 0):,.0f}–{tax_price.get('high', 0):,.0f} {price_result.get('currency', '')}",
            f"- 公开样本观察区间：{observed.get('low', 0):,.0f}–{observed.get('high', 0):,.0f} {price_result.get('currency', '')}",
            "- 详细成本拆分、样本来源和使用边界见 `reports/price-intelligence.md`。",
        ]
    else:
        lines.append("尚未运行价格评估。")
    lines += [
        "",
        "## 候选结果", "",
    ]
    if analysis and analysis.get("shortlist"):
        for index, supplier_id in enumerate(analysis["shortlist"], start=1):
            quote = next(item for item in analysis["quotes"] if item["supplier_id"] == supplier_id)
            lines.append(f"{index}. **{supplier_map[supplier_id]}**：总分 {quote['total_score']}，归一化总成本 {quote['normalized_total_cost']} {analysis['currency']}。")
        lines += ["", "详细证据、排除项和风险见 `reports/quote-analysis.md`；本名单不构成自动定点。"]
    elif analysis:
        lines.append("有效报价不足，未形成 2–3 家候选名单。请补充报价或完成缺项追问。")
    else:
        lines.append("尚未运行报价分析。")
    lines += ["", "## 供应商背景调查（综合实力）", ""]
    background_path = project / "reports/background-check-result.json"
    background = load_json(background_path) if background_path.exists() else None
    if background and background.get("suppliers"):
        for index, item in enumerate(background["suppliers"], start=1):
            lines.append(
                f"{index}. **{item['company']}**：综合实力 {item['total_score']} 分，"
                f"证据覆盖 {item['coverage']}%；{item['recommendation']}。"
                + ("红线命中：" + "；".join(f"{hit.split('：')[0]}｜{hit.split('：')[-1][:60]}…" for hit in item["redline_hits"]) if item["redline_hits"] else "")
            )
        lines.append("")
        lines.append("明细、来源链接和待核验清单见 `reports/supplier-background-check.md`；背调结论来自公开信息，不等同于现场验厂。")
    elif background or stages.get("background_check"):
        lines.append(f"用户决策：{stages.get('background_check', {}).get('decision', '已记录')}；未做背景调查，候选名单未核验工商、司法、产能与资质。")
    else:
        lines.append("尚未运行背景调查。提交候选前须先用弹窗询问用户是否需要调查。")
    lines += [
        "", "## 人工待办与能力边界", "",
        "- 在企业微信中核验主体并逐个添加；不得把队列状态当作添加结果。",
        "- 人工确认并发送询价草稿，记录真实发送时间、执行人和回复状态。",
        "- 复核候选报价原件、技术偏离、质量证明、税费与售后条款后再定点。",
        "- 背景调查结论只代表公开信息查询结果；大额或长期合作前仍建议现场验厂并核对证书编号与材质单。",
        "- 批量自动加好友、自动发微信消息、自动接收微信文件、自动下单均未实现，详见 Skill 中 `references/UNIMPLEMENTED.md`。",
    ]
    write_text(project / "reports/completion-report.md", "\n".join(lines) + "\n")
    update_state(project, "report", status="完成报告已生成")
    print(f"完成报告已生成：{project / 'reports/completion-report.md'}")


def build_parser():
    parser = argparse.ArgumentParser(description="可审计的半自动采购流程；不访问微信、不发送消息、不调用大模型")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="初始化采购项目模板")
    init_parser.add_argument("--output", required=True, help="项目输出目录")
    init_parser.add_argument("--force", action="store_true", help="覆盖已有模板文件")
    init_parser.set_defaults(func=command_init)
    for name, help_text, function in [
        ("intake", "校验用户已确认的需求并生成摘要", command_intake),
        ("price", "校验成本和市场证据并生成价格评估", command_price),
        ("suppliers", "校验供应商并生成清单", command_suppliers),
        ("outreach", "生成人工添加队列和询价草稿", command_outreach),
        ("collect", "复制、去重并登记报价文件", command_collect),
        ("analyze", "校验结构化报价、评分并生成候选", command_analyze),
        ("duediligence", "按用户弹窗决策做供应商背景调查与综合实力评估", command_duediligence),
        ("report", "生成流程完成报告", command_report),
    ]:
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.add_argument("--project", required=True, help="init 创建的采购项目目录")
        subparser.set_defaults(func=function)
    return parser


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
        return 0
    except ProcurementError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"文件操作失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
