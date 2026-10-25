# 上传 GitHub 操作手册（auto-procurement Skill）

本仓库已具备上传条件。文档给出三种上传路径，任选其一即可，不需要三种都做。

## 0. 上传前自检（已全部通过）

| 检查项 | 状态 | 说明 |
|---|---|---|
| 文件完整性 | 通过 | 33 个受版本控制文件，含 SKILL.md、脚本、模板、参考文档、测试、CI |
| 单元测试 | 通过 | `python -m unittest discover -s tests` 11 项全绿 |
| CI 配置 | 通过 | `.github/workflows/test.yml` 在 Ubuntu/Windows × Python 3.9/3.12 四组合上执行编译、测试、CLI 冒烟 |
| 目录打包 | 通过 | `dist/auto-procurement.zip` 33 个文件，已排除 `.git`、`__pycache__`、`dist/`、`.env`、`*.zip` |
| 敏感数据 | 通过 | 仓库内示例均为虚构数据（虚构示例甲/乙、example.com），无真实联系方式；真实采购项目目录不在仓库内 |
| 许可证 | 通过 | MIT LICENSE、SECURITY.md、CONTRIBUTING.md、CHANGELOG.md 齐备 |

> **重要**：`aluminum-plate-procurement/` 和 `500t-hydraulic-press-procurement/` 两个目录包含真实厂家联系人电话、微信、邮箱和比价数据，**不要上传到公开 GitHub 仓库**。它们在本仓库之外，`git status` 不会涉及。

---

## 方式 A：网页上传（最省事，不需要 SSH 密钥和令牌）

1. 打开 <https://github.com/new>，填写：
   - Repository name：`auto-procurement`
   - Description：`半自动工业采购 Skill：弹窗采集需求、成本与市场价评估、公开寻源、报价归档、AI 比价，收尾可对候选做背景调查并给综合实力分`
   - 选 **Public**，勾选 **Add a README file** 的反面——**不要勾**，因为我们本地已有 README
   - License 先选 **None**（仓库里已有 MIT LICENSE），或选 MIT 让 GitHub 自己生成（二选一，别重复）
2. 创建完成后进入仓库页，点 **Add file → Upload files**。
3. 把下面这些拖进去（可以整目录拖，浏览器支持）：
   ```
   SKILL.md  README.md  CHANGELOG.md  CONTRIBUTING.md  LICENSE  SECURITY.md
   .gitignore  .gitattributes
   scripts/  references/  assets/  tests/  .github/
   ```
   数量约 33 个文件，远低于 GitHub 单次 100 个文件的限制。
4. 底部填 Commit message：`feat: 发布 auto-procurement skill v0.3.0`，选 **Commit directly to the main branch**，提交。
5. 去 **Actions** 页确认 CI 四组合全绿；去 **Settings → About** 加 topics：`procurement`、`skill`、`automation`、`python`。

> 不要直接拖 `auto-procurement/` 整个上层文件夹，否则线上会多一层嵌套目录。

---

## 方式 B：git 命令行（HTTPS + Personal Access Token）

本机没有 `gh` CLI，也没有 SSH 公钥，所以用 **HTTPS + PAT** 最稳。

### B1. 生成令牌

GitHub 右上角头像 → **Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic)**：
- 勾 **repo**（私有/公开仓库读写）
- 有效期建议 90 天
- 生成后立刻复制那串 `ghp_...`，关掉页面就看不到第二次了

### B2. 在本机执行（把尖括号内容换成你自己的）

```bash
cd /d/workbuddydata/2026-10-25-14-52-20/auto-procurement

# 1) 设置提交身份（只需一次）
git config user.name  "<你的GitHub用户名>"
git config user.email "<你GitHub绑定的邮箱>"

# 2) 首次提交（文件已全部 git add 过）
git add -A
git commit -m "feat: 发布 auto-procurement skill v0.3.0"

# 3) 关联远端。先在 GitHub 网页新建一个空仓库 auto-procurement（不要勾 README / LICENSE / .gitignore）
git remote add origin https://github.com/<你的用户名>/auto-procurement.git
git branch -M main

# 4) 推送。用户名填 GitHub 用户名，密码填刚才那串 PAT（不是登录密码）
git push -u origin main
```

Windows 上如果弹不出凭据框，把令牌写进地址一次即可（之后系统会记住）：
```bash
git push https://<你的用户名>:<PAT>@github.com/<你的用户名>/auto-procurement.git main
```

### B3. 后续更新

```bash
git add -A
git commit -m "<改动说明>"
git push
```

---

## 方式 C：GitHub Desktop（图形界面，不想碰命令行就选这个）

1. 装 <https://desktop.github.com/> 并登录 GitHub 账号。
2. **File → Add local repository**，选 `D:\workbuddydata\2026-10-25-14-52-20\auto-procurement`。
3. 左下角 Summary 填 `feat: 发布 auto-procurement skill v0.3.0` → **Commit to main**。
4. 右上角 **Publish repository**，名称 `auto-procurement`，Public 可选/org 可选，**取消勾选 "Keep this code private"** 才是公开。
5. Publish。Desktop 会自动建远端仓库并推送。

> Desktop 首次提交时如果提示要 author 信息，填 GitHub 用户名和邮箱即可。

---

## 发布 Release（建议做，方便别人一键下载 Skill）

推送成功后：

1. 仓库页右侧 **Releases → Create a new release**。
2. Tag version 填 `v0.3.0`，标题 `auto-procurement v0.3.0`。
3. 正文粘贴 CHANGELOG 里 0.3.0 的条目。
4. 把 `dist/auto-procurement.zip` 拖到 **Attach binaries** 区域（这个文件被 `.gitignore` 忽略，不会污染源码仓库，正好适合放在 Release 里）。
5. Publish release。

别人拿到 zip 后：解压目录改名为 `auto-procurement`（或保持内部 `auto-procurement/` 那层），放进 WorkBuddy 的 skills 目录即可使用。

---

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `Support for password authentication was removed` | 用了登录密码当推送密码 | 必须改用 PAT（方式 B1） |
| 推送后 CI 显示 import 报错 | Python 版本差异 | CI 已覆盖 3.9/3.12，若红了自己先本地 `python -m unittest discover -s tests` 复现 |
| 网页拖 zip 进去结构多一层 | 直接拖了外层文件夹 | 用 Release 附件或按方式 A 逐层拖内容 |
| 把真实采购数据传上去了 | 误拖了项目目录 | 立刻 **Settings → Danger Zone → Make private**，再用 `git rm --cached` 清掉并强制推送 |
