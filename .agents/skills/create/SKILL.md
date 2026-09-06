---
name: create
description: Turn user requirements into a feature specification using create/template.md and save it as a numbered Markdown file such as features/001-user-login.md.
---

# 创建功能需求

将用户描述的需求整理为功能文档，使用 [template.md](template.md) 的结构，写入仓库 `features/`。本流程只创建需求文档；不创建分支、不实施功能、不提交或推送。

## 整理需求

- 读取 `AGENTS.md`、模板及与需求直接相关的现有代码或功能文档，确认已有行为和术语，避免重复定义已有功能。
- 保留模板标题和顺序：`# Feature: <Feature Name>`、`Description`、`Scope`、`Acceptance Criteria`。替换全部占位内容，正文默认使用用户的语言，条目数量按需求调整。
- Description 说明需要实现什么以及目的；Scope 列出具体需求和边界；Acceptance Criteria 使用 `- [ ]` 列出可观察、可验证的预期行为，作为后续开发和审查依据。
- 不臆造业务规则、不扩展用户未要求的功能、不强加实现方案。影响范围或验收结论的关键信息缺失时，先提出简洁问题，确认后再完成文档；可从上下文确定的常规细节自行处理。

## 命名与保存

- 文件名格式为 `<序号>-<功能短名>.md`，例如 `001-user-login.md`。序号至少三位，不足补零；短名使用简洁的小写英文单词，以连字符连接。
- 检查 `features/` 已有编号文件，取最大序号加一；没有编号文件时从 `001` 开始。用户明确指定文件名时优先使用指定名称。
- 写入前确认目标文件不存在，不覆盖已有需求文档；若发生重名，重新检查编号。目录不存在时创建 `features/`。
- 完成后检查模板章节齐全、无占位符、范围与验收标准一致，且验收条目能根据实际行为判断是否通过。检查 Markdown 格式并遵循仓库要求的检查流程。
- 最终明确告知生成的文件名，提供文件链接，简述功能范围。此文件可作为 implement skill 的输入，文件名去掉 `.md` 即后续分支名。
