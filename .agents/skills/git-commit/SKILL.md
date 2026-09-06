---
name: git-commit
description: Validate frontend and backend changes, generate Conventional Commit messages, then stage, commit, and push code when the user requests this submission workflow.
---

# 检查并提交代码

用户要求执行本提交流程时，完成检查、审查修改、生成提交信息、暂存、提交和推送。遵循仓库的 `AGENTS.md`；每个提交只包含一个逻辑变更，不提交生成文件、临时文件或无关修改。

## 检查

在仓库根目录依次运行以下命令，每条成功后才执行下一条：

```bash
npm run lint
npm run format
npm run typecheck
uv run ruff check . --fix
uv run ruff format .
uv run pyright
```

任一命令失败立即停止流程，报告失败命令、具体错误和受影响文件，不继续检查、暂存、提交或推送，也不自行修复后继续。检查命令自动修复或格式化产生的修改保留并告知用户。权限或环境限制导致命令无法完成时，不得视为检查通过。

## 审查修改与提交信息

- 全部检查通过后，使用 `git status --short`、`git diff` 和 `git diff --cached` 获取并检查修改；读取拟提交的未跟踪文件。检查范围包含工具自动修改的内容，不能只查看文件名或统计。
- 按用户授权的任务范围选择文件，排除生成、临时及无关文件。已有暂存内容也必须审查；若混有无法安全分离的无关修改，停止并说明，不擅自撤销用户暂存或改动。
- 没有可提交修改时报告并结束。多个独立逻辑变更分别提交；若同一文件混有无法可靠区分的修改，停止并说明范围不明确。
- 根据实际 diff 生成简洁、准确的 Conventional Commit 消息：`<type>(<scope>): <description>`，scope 可省略。type 使用 `feat`、`fix`、`docs`、`style`、`refactor`、`test`、`chore` 等。例如 `fix(code-fix): wait before checking workflows`。

## 暂存、提交与推送

- 用 `git add -- <明确的文件路径>` 暂存已审查的修改；避免用 `git add .` 将无关文件一并提交。
- 用 `git diff --cached` 核对最终提交内容，并运行 `git diff --cached --check`。失败或内容不符合范围时立即停止，不提交。若检查后又修改了代码，重新运行相关检查后才提交。
- 执行 `git commit -m '<生成的提交信息>'`。失败立即停止并报告，不绕过 hooks、不使用 `--no-verify`，不擅自 amend。
- 提交成功后向当前分支的 upstream 执行普通 `git push`。没有 upstream 时，仅在当前分支和目标远程明确的情况下执行 `git push -u <remote> <branch>`；存在多个无法确定的远程或处于 detached HEAD 时停止并说明。
- 推送失败立即报告，保留本地提交；不自动 pull、rebase、reset 或 force push。
- 最后报告检查结果、提交消息、提交哈希及推送目标与结果；未完成时明确停在哪一步。执行授权已包含在用户调用本流程的请求中，除工具权限要求或必须澄清的范围外，不重复请求确认。
