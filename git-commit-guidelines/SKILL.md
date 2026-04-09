---
name: git-commit-guidelines
description: Git 提交规范与 Conventional Commits 规则指引。用于需要编写、检查或解释 Git 提交信息、提交粒度、提交类型、破坏性变更标记或提交流程的场景。
---

# Git 提交规范

## 文档信息

- 日期: 2026-01-20
- 执行者: Codex
- 来源: D:\Projects\TestCX\git-commit.md

## 概览

遵循 Conventional Commits，统一提交信息格式、提交粒度与提交流程，保证日志可读且便于生成变更记录。

## 提交粒度

- 保持单次提交只包含一类变更（功能/修复/文档）。
- 提交前先整理改动，避免混入无关格式化或临时调试。
- 确保每个提交都可构建、可运行，便于回滚。
- 大改动拆分为多个可审查的小提交。

## 提交信息格式

```
<type>[(scope)]: <summary>

[body]

[footer]
```

- 使用约定的 type（见下表），必要时补充 scope。
- scope 使用模块或目录（例如 app、data、scripts），无明确范围可省略。
- summary 使用中文、动词开头，长度不超过 50 字，不加句号。
- 需要时在正文补充动机、影响或迁移方式。

## 提交类型

| 类型 | 说明 |
| --- | --- |
| 🎉 init | 项目初始化 |
| ✨ feat | 新功能 |
| 🐞 fix | 错误修复 |
| 📃 docs | 文档变更 |
| 🌈 style | 代码格式化（不影响代码逻辑） |
| 🦄 refactor | 代码重构（不新增功能或修复错误） |
| 🎈 perf | 性能优化 |
| 🧪 test | 测试相关 |
| 🔧 build | 构建系统或外部依赖 |
| 🐎 ci | CI 配置相关 |
| 🐳 chore | 构建过程或辅助工具的变动 |
| ↩ revert | 撤销提交 |

## 破坏性变更

- 在 type 后添加 `!`，或在正文写明 `BREAKING CHANGE: ...`。
- 明确写出受影响范围与升级指引。

## 提交流程

- 先执行 `git status` 确认改动范围。
- 使用 `git add <files>` 仅添加相关文件。
- 运行 `npm run lint` 通过后再提交。
- 使用 `git commit -m "..."` 完成提交。
- 需要时 `git push` 并发起 PR。
