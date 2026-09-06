---
name: implement
description: Implement a feature from a features Markdown specification, create its branch, plan and develop the changes, run git-commit, create a PR, and launch code-fix in a new Windows Terminal WSL window.
---

# 功能开发流程

输入为仓库 `features/` 下的功能 Markdown 文件。用户调用本流程即授权完成开发、提交、推送、创建 PR 和启动监听；遵循 `AGENTS.md` 及工具权限要求。任一步失败停止后续步骤，报告具体问题和已完成的操作，不自动重复创建 PR 或启动监听。

## 1. 读取需求并创建分支

- 读取用户指定的 feature 文件及 `AGENTS.md`。未指定路径时检查新增的 `features/**/*.md`，仅有一个候选时采用它；多个候选且无法判断时询问具体文件。
- 阅读需求、验收标准及相关实现，检查当前分支和工作区。允许本次 feature 文档尚未提交；无关修改不能混入功能提交，无法安全分离时停止说明，不覆盖或清理用户文件。
- 分支名取 feature 文件相对 `features/` 的路径，去掉 `.md`：`features/aa.md` 对应 `aa`，`features/auth/login.md` 对应 `auth/login`。保持该映射，供 code-review 按分支查找验收标准。
- 使用 `git check-ref-format --branch <branch>` 校验名称。创建前记录当前分支为默认 PR base；用户指定 base 时采用用户值，并从对应分支创建。base 无法确定时先澄清，不猜测。
- 使用 `git switch -c <branch> <base>` 创建并切换分支。不得覆盖已有分支；恢复执行时，只有确认已有分支属于同一 feature 才继续。

## 2. 规划与实现

- 后端代码必须写在仓库根目录 `backend/` 及其子目录中，前端代码必须写在仓库根目录 `frontend/` 及其子目录中；不得在其他目录放置前后端业务代码。

- 基于需求和代码形成简短实施计划与任务清单，列明涉及模块、实施顺序和验证方式，再逐项实现并更新任务状态。不要求用户额外批准常规实施计划；不额外生成计划文档，除非用户要求。
- 遵循现有架构和编码风格，按验收标准实现功能，不扩展无关需求。必要时添加或运行能验证实际行为的测试。
- 实施计划和验证完成后，逐条核对 feature 文档的 `Acceptance Criteria`：有实际证据确认满足的条目将 `- [ ]` 改为 `- ✅`；未满足或当前无法验证的条目改为 `- ❌`，并在末尾简述原因。不得删除、弱化或改写原验收标准，也不得将未验证的条目标记为完成。将回写后的 feature 文档纳入本次功能提交，并在最终报告中列出未完成项。
- 实现完成后执行 [git-commit skill](../git-commit/SKILL.md)，由它负责前后端检查、审查修改、生成提交消息、add、commit 和 push。本次 feature 文档应随功能提交；不重复维护一套检查或提交规则。
- 只有确认检查、提交和推送成功才进入创建 PR 阶段；检查失败按 git-commit 的规则停止。

## 3. 创建 PR

根据最终变更生成 PR 标题和正文，正文说明具体行为变化及真实验证结果。使用 `scripts/common/github-api.py` 中的 `create_pull_request()`，head 为 feature 分支，base 为建分支前确定的目标分支。

在仓库根目录使用 `uv run python` 执行 Python 调用；数据通过结构化输入或临时 JSON 文件传入，不将标题或正文拼入 shell 命令。导入和调用方式：

```python
import sys
from importlib import import_module

sys.path.insert(0, "scripts")
github_api = import_module("common.github-api")
url = github_api.create_pull_request(
    repo,
    title=title,
    body=body,
    head=branch,
    base=base,
)
```

上述变量取当前仓库和本次实际变更。恢复流程时先检查同仓库、同 head/base 的 open PR，存在则复用；创建超时先核查远程结果，不盲目重试。记录成功创建或复用的 PR URL。

## 4. 启动监听并结束

PR 就绪后，在仍停留于 feature 分支的仓库根目录，打开新的 Windows Terminal 窗口，在当前 WSL 发行版运行 `scripts/code-fix.py`：

```python
import os
import shlex
import subprocess

cwd = os.getcwd()
wsl = ["wsl.exe"]
if os.environ.get("WSL_DISTRO_NAME"):
    wsl.extend(["--distribution", os.environ["WSL_DISTRO_NAME"]])
subprocess.Popen([
    "wt.exe", "-w", "new",
    *wsl, "bash", "-lc",
    f"cd {shlex.quote(cwd)} && uv run scripts/code-fix.py",
])
```

使用 `shlex.quote` 保留含空格或单引号的目录路径。不得在启动后切换该工作区分支，否则监听脚本会使用错误的分支上下文。若缺少 `wt.exe`、`wsl.exe` 或启动失败，报告 PR URL 与启动错误，不声称监听已运行。

启动调用返回后结束 skill，不等待 code-fix 完成。最终报告 feature 路径、分支、提交、PR URL 和终端启动情况；仅启动终端不代表修复或后续提交已经成功。
