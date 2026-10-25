import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "procurement.py"
ASSETS = ROOT / "assets"


class ProcurementWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tempdir.name) / "project"
        self.run_cli("init", "--output", str(self.project))
        shutil.copyfile(ASSETS / "suppliers.example.json", self.project / "suppliers.json")

    def tearDown(self):
        self.tempdir.cleanup()

    def run_cli(self, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def read_json(self, relative):
        return json.loads((self.project / relative).read_text(encoding="utf-8"))

    def test_full_local_workflow(self):
        self.run_cli("suppliers", "--project", self.project)
        self.run_cli("outreach", "--project", self.project)
        self.assertTrue((self.project / "reports/suppliers.csv").is_file())
        self.assertIn("缺公开微信号", (self.project / "outreach/wechat-add-queue.csv").read_text(encoding="utf-8-sig"))
        self.assertIn("未执行加好友", self.run_cli("outreach", "--project", self.project).stdout)

        for supplier_id, name in [("SUP-001", "quote-a.pdf"), ("SUP-002", "quote-b.pdf"), ("SUP-003", "quote-c.pdf")]:
            (self.project / "quotes/inbox" / f"{supplier_id}__{name}").write_bytes((supplier_id + " fictional quote").encode())
        (self.project / "quotes/inbox" / "SUP-001__duplicate.pdf").write_bytes(b"SUP-001 fictional quote")
        (self.project / "quotes/inbox" / "UNKNOWN__quote.pdf").write_bytes(b"unknown")
        (self.project / "quotes/inbox" / "SUP-001__macro.exe").write_bytes(b"not executable")
        self.run_cli("collect", "--project", self.project)
        manifest = (self.project / "reports/quote-manifest.csv").read_text(encoding="utf-8-sig")
        self.assertIn("重复文件", manifest)
        self.assertIn("不支持的格式", manifest)
        self.assertEqual(len(list((self.project / "quotes/collected").iterdir())), 3)
        self.assertTrue((self.project / "quotes/inbox/SUP-001__quote-a.pdf").is_file())

        shutil.copyfile(ASSETS / "quotes.example.json", self.project / "quotes.json")
        self.run_cli("analyze", "--project", self.project)
        self.run_cli("report", "--project", self.project)
        analysis = self.read_json("reports/analysis.json")
        self.assertEqual(analysis["eligible_count"], 3)
        self.assertEqual(len(analysis["shortlist"]), 3)
        self.assertEqual(analysis["quotes"][0]["supplier_id"], "SUP-001")
        completion = (self.project / "reports/completion-report.md").read_text(encoding="utf-8")
        self.assertIn("人工待办", completion)
        self.assertIn("未实现批量自动添加", completion)
        self.assertNotIn("全流程自动完成", completion)

    def test_contact_requires_item_level_source(self):
        suppliers = self.read_json("suppliers.json")
        suppliers[0]["wechat"] = "fictional-public-account"
        (self.project / "suppliers.json").write_text(json.dumps(suppliers, ensure_ascii=False), encoding="utf-8")
        self.run_cli("suppliers", "--project", self.project, expected=1)
        validation = (self.project / "reports/supplier-validation.txt").read_text(encoding="utf-8")
        self.assertIn("contact_sources.wechat", validation)
        self.assertFalse((self.project / "reports/suppliers.csv").exists())

    def test_insufficient_eligible_quotes_returns_no_shortlist(self):
        quotes = self.read_json(ASSETS / "quotes.example.json")
        for quote in quotes[1:]:
            quote["eligible"] = False
            quote["exclusion_reason"] = "虚构测试：缺统一税运口径"
        (self.project / "quotes.json").write_text(json.dumps(quotes, ensure_ascii=False), encoding="utf-8")
        self.run_cli("analyze", "--project", self.project)
        analysis = self.read_json("reports/analysis.json")
        self.assertEqual(analysis["eligible_count"], 1)
        self.assertEqual(analysis["shortlist"], [])
        report = (self.project / "reports/quote-analysis.md").read_text(encoding="utf-8")
        self.assertIn("有效报价不足 2 家", report)

    def test_missing_evidence_is_forced_ineligible(self):
        quotes = self.read_json(ASSETS / "quotes.example.json")
        quotes[0]["evidence"] = [item for item in quotes[0]["evidence"] if item["field"] != "quality_score"]
        (self.project / "quotes.json").write_text(json.dumps(quotes, ensure_ascii=False), encoding="utf-8")
        self.run_cli("analyze", "--project", self.project)
        analysis = self.read_json("reports/analysis.json")
        quote = next(item for item in analysis["quotes"] if item["supplier_id"] == "SUP-001")
        self.assertFalse(quote["eligible"])
        self.assertIn("quality_score", quote["exclusion_reason"])


    def test_intake_price_and_combined_contact_column(self):
        requirement = self.read_json("requirement.json")
        requirement.update({
            "intake_status": "已确认",
            "product_name": "虚构500吨四柱液压机",
            "model": "5000kN标准四柱",
            "application": "虚构压制成型测试",
            "processes": ["压制成型"],
            "configuration": "普通PLC",
            "procurement_strategy": "综合性价比",
        })
        (self.project / "requirement.json").write_text(json.dumps(requirement, ensure_ascii=False), encoding="utf-8")
        self.run_cli("intake", "--project", self.project)
        summary = (self.project / "reports/requirement-summary.md").read_text(encoding="utf-8")
        self.assertIn("压制成型", summary)
        self.assertIn("普通PLC", summary)

        shutil.copyfile(ASSETS / "price-estimate.example.json", self.project / "price-estimate.json")
        self.run_cli("price", "--project", self.project)
        result = self.read_json("reports/price-estimate-result.json")
        self.assertEqual(result["market_observed_range"], {"low": 180000.0, "high": 250000.0})
        self.assertGreater(result["calculations"]["production_cost"]["high"], 0)
        price_report = (self.project / "reports/price-intelligence.md").read_text(encoding="utf-8")
        self.assertIn("生产制造成本", price_report)
        self.assertIn("公开样本观察区间", price_report)

        suppliers = self.read_json("suppliers.json")
        suppliers[0]["phone"] = "0000-0000000"
        suppliers[0]["contact_sources"]["phone"] = "https://example.com/contact"
        (self.project / "suppliers.json").write_text(json.dumps(suppliers, ensure_ascii=False), encoding="utf-8")
        self.run_cli("suppliers", "--project", self.project)
        supplier_list = (self.project / "reports/supplier-list.md").read_text(encoding="utf-8")
        self.assertIn("公开业务联系", supplier_list)
        self.assertIn("[官网](https://example.com/supplier-a)", supplier_list)
        self.assertIn("电话：0000-0000000", supplier_list)
        self.assertIn("[原文](https://example.com/supplier-a)", supplier_list)
        csv_text = (self.project / "reports/suppliers.csv").read_text(encoding="utf-8-sig")
        self.assertIn("public_business_contact", csv_text)

    def test_intake_rejects_unconfirmed_requirement(self):
        result = self.run_cli("intake", "--project", self.project, expected=1)
        self.assertIn("intake_status", result.stderr)
        self.assertFalse((self.project / "reports/requirement-summary.md").exists())


    def background_payload(self, decision="进行", findings=None, **overrides):
        payload = {
            "decision": decision,
            "decision_source": "虚构测试：用户弹窗选择对 SUP-001/SUP-002 做标准背调（2026-10-25）",
            "target_suppliers": ["SUP-001", "SUP-002"],
            "dimensions": ["工商与实控", "司法与失信", "产能与设备", "资质与认证"],
            "depth": "标准",
            "weight_profile": "均衡",
            "redlines": ["失信被执行/限高"],
            "evidence_strictness": "每条结论必须有来源链接",
            "usage": "内部决策参考",
            "notes": "",
            "findings": findings if findings is not None else self.sample_findings(),
        }
        payload.update(overrides)
        return payload

    def sample_findings(self, second_flags=None):
        return {
            "SUP-001": {
                "工商与实控": {"summary": "虚构：统一信用代码与经营范围含制造", "score": 5, "confidence": "高",
                               "source_url": "https://example.com/gsxt/sup001", "source_date": "2026-10-25",
                               "status": "已核查", "flags": []},
                "司法与失信": {"summary": "虚构：未见失信被执行记录", "score": 5, "confidence": "中",
                               "source_url": "https://example.com/zxgk/sup001", "source_date": "2026-10-25",
                               "status": "已核查", "flags": []},
                "产能与设备": {"summary": "虚构：自有两条产线", "score": 4, "confidence": "中",
                               "source_url": "https://example.com/plant/sup001", "source_date": "2026-10-25",
                               "status": "已核查", "flags": []},
                "资质与认证": {"summary": "虚构：体系证书编号可核验", "score": 4, "confidence": "中",
                               "source_url": "https://example.com/cert/sup001", "source_date": "2026-10-25",
                               "status": "已核查", "flags": []},
            },
            "SUP-002": {
                "工商与实控": {"summary": "虚构：经营范围以批发为主", "score": 2, "confidence": "中",
                               "source_url": "https://example.com/gsxt/sup002", "source_date": "2026-10-25",
                               "status": "已核查", "flags": ["主体不符/贸易商冒充厂家"]},
                "司法与失信": {"summary": "虚构：存在失信被执行记录", "score": 1, "confidence": "高",
                               "source_url": "https://example.com/zxgk/sup002", "source_date": "2026-10-25",
                               "status": "已核查", "flags": ["失信被执行/限高"]},
                "产能与设备": {"summary": "未获得公开证据", "status": "未获得公开证据", "flags": []},
                "资质与认证": {"summary": "未获得公开证据", "status": "未获得公开证据", "flags": []},
            },
        }

    def write_background(self, **kwargs):
        (self.project / "background-check.json").write_text(
            json.dumps(self.background_payload(**kwargs), ensure_ascii=False), encoding="utf-8")

    def test_duediligence_ranks_strength_and_flags_redline(self):
        self.run_cli("suppliers", "--project", self.project)
        self.write_background()
        self.run_cli("duediligence", "--project", self.project)
        result = self.read_json("reports/background-check-result.json")
        self.assertEqual(result["suppliers"][0]["supplier_id"], "SUP-001")
        self.assertIn("工商与实控", result["suppliers"][0]["strengths"])
        self.assertEqual(result["suppliers"][0]["weaknesses"], [])
        self.assertIn("司法与失信", result["suppliers"][1]["weaknesses"])
        self.assertEqual(result["suppliers"][1]["strengths"], ["工商与实控"])
        self.assertIn("资质与认证", result["suppliers"][1]["unverified_dimensions"])
        self.assertEqual(result["suppliers"][1]["redline_hits"][0].split("：")[0], "司法与失信")
        self.assertIn("建议剔除或暂缓定点", result["suppliers"][1]["recommendation"])
        self.assertLess(result["suppliers"][1]["coverage"], 100)
        report = (self.project / "reports/supplier-background-check.md").read_text(encoding="utf-8")
        self.assertIn("综合实力排名", report)
        self.assertIn("[原文](https://example.com/gsxt/sup001)", report)
        self.assertIn("未获得公开证据", report)
        self.assertIn("待核验清单", report)

    def test_duediligence_requires_user_decision(self):
        self.run_cli("suppliers", "--project", self.project)
        result = self.run_cli("duediligence", "--project", self.project, expected=1)
        self.assertIn("弹窗询问用户", result.stderr)
        payload = self.background_payload(decision="待用户弹窗确认")
        (self.project / "background-check.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = self.run_cli("duediligence", "--project", self.project, expected=1)
        self.assertIn("decision 未确认", result.stderr)
        payload = self.background_payload(decision_source="用户口述，无日期")
        (self.project / "background-check.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.assertIn("decision_source", self.run_cli("duediligence", "--project", self.project, expected=1).stderr)

    def test_duediligence_rejects_unsourced_conclusion(self):
        self.run_cli("suppliers", "--project", self.project)
        findings = self.sample_findings()
        findings["SUP-001"]["产能与设备"].update(source_url="", source_date="")
        self.write_background(findings=findings)
        result = self.run_cli("duediligence", "--project", self.project, expected=1)
        self.assertIn("缺有效 source_url", result.stderr)
        self.assertFalse((self.project / "reports/background-check-result.json").exists())

    def test_duediligence_can_be_declined_by_user(self):
        self.run_cli("suppliers", "--project", self.project)
        self.write_background(decision="暂不需要")
        self.run_cli("duediligence", "--project", self.project)
        report = (self.project / "reports/supplier-background-check.md").read_text(encoding="utf-8")
        self.assertIn("暂不进行背景调查", report)
        self.run_cli("report", "--project", self.project)
        completion = (self.project / "reports/completion-report.md").read_text(encoding="utf-8")
        self.assertIn("供应商背景调查", completion)
        self.assertIn("暂不需要", completion)

    def test_clean_package_excludes_git_and_caches(self):
        git_file = ROOT / ".git" / "fictional-test-secret"
        cache_dir = ROOT / "scripts" / "__pycache__"
        cache_file = cache_dir / "fictional.pyc"
        created_git = not git_file.exists()
        created_cache = not cache_file.exists()
        try:
            if created_git:
                git_file.parent.mkdir(exist_ok=True)
                git_file.write_text("not a real secret", encoding="utf-8")
            if created_cache:
                cache_dir.mkdir(exist_ok=True)
                cache_file.write_bytes(b"cache")
            output = Path(self.tempdir.name) / "dist"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/package_skill.py"), "--output", str(output)],
                text=True, encoding="utf-8", capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(output / "auto-procurement.zip") as archive:
                names = archive.namelist()
            self.assertTrue(any(name.endswith("SKILL.md") for name in names))
            self.assertFalse(any("/.git/" in name or "__pycache__" in name for name in names))
        finally:
            if created_git and git_file.exists():
                git_file.unlink()
            if created_cache and cache_file.exists():
                cache_file.unlink()
            if cache_dir.exists() and not any(cache_dir.iterdir()):
                cache_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
