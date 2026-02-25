# Contributing to Outlook Email Management Tool / 为 Outlook 邮件管理工具做贡献

First off, thank you for considering contributing to this project! / 首先，感谢你考虑为此项目做贡献！

The following is a set of guidelines for contributing. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request. / 以下是贡献指南。这些主要是指导方针，而非规则。请运用你的最佳判断，并随时在 PR 中提出对本文档的修改建议。

## Table of Contents / 目录

- [Code of Conduct](#code-of-conduct--行为准则)
- [How Can I Contribute?](#how-can-i-contribute--我如何做贡献)
- [Development Setup](#development-setup--开发环境设置)
- [Pull Request Process](#pull-request-process--pr-流程)
- [Style Guidelines](#style-guidelines--风格指南)

## Code of Conduct / 行为准则

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code. / 此项目及其所有参与者均受我们的行为准则约束。参与即表示你同意遵守此准则。

## How Can I Contribute? / 我如何做贡献？

### Reporting Bugs / 报告 Bug

Before creating bug reports, please check the existing issues as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible: / 在创建 bug 报告之前，请检查现有 issue，你可能会发现无需创建新的。创建 bug 报告时，请尽可能包含详细信息：

- Use a clear and descriptive title / 使用清晰描述性的标题
- Describe the exact steps to reproduce the problem / 描述重现问题的确切步骤
- Provide specific examples / 提供具体示例
- Describe the behavior you observed and what you expected / 描述你观察到的行为以及你的期望
- Include screenshots if possible / 如可能，包含截图
- Include your environment details (OS, Python version, etc.) / 包含你的环境详情（操作系统、Python 版本等）

### Suggesting Enhancements / 建议增强功能

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include: / 增强建议通过 GitHub issue 跟踪。创建增强建议时，请包含：

- Use a clear and descriptive title / 使用清晰描述性的标题
- Provide a detailed description of the suggested enhancement / 提供建议增强功能的详细描述
- Explain why this enhancement would be useful / 解释为什么此增强功能有用
- List some examples of how it would be used / 列出一些使用示例

### Your First Code Contribution / 你的第一次代码贡献

Unsure where to begin? You can start by looking through `beginner-friendly` and `help-wanted` issues: / 不确定从哪里开始？你可以从 `beginner-friendly` 和 `help-wanted` issue 开始：

- Beginner-friendly issues - issues which should only require a few lines of code / 初学者友好的 issue - 只需几行代码即可解决
- Help wanted issues - issues which may be more involved / 需要帮助的 issue - 可能涉及更多内容

## Development Setup / 开发环境设置

1. Fork the repository / Fork 仓库
2. Clone your fork / 克隆你的 fork
   ```bash
   git clone https://github.com/YOUR_USERNAME/outlookEmail.git
   cd outlookEmail
   ```

3. Create a virtual environment / 创建虚拟环境
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. Install dependencies / 安装依赖
   ```bash
   pip install -r requirements.txt
   ```

5. Create a branch for your changes / 为你的更改创建分支
   ```bash
   git checkout -b feature/your-feature-name
   ```

6. Make your changes and test them / 进行更改并测试
   ```bash
   python -m unittest discover -s tests -v
   ```

## Pull Request Process / PR 流程

1. Ensure your code follows the project's coding standards / 确保你的代码遵循项目的编码标准
2. Update the documentation if needed / 如需要，更新文档
3. Add tests for new features / 为新功能添加测试
4. Ensure all tests pass / 确保所有测试通过
5. Update the README.md with details of changes if applicable / 如适用，更新 README.md 中的更改详情
6. Create a Pull Request with a clear title and description / 创建带有清晰标题和描述的 PR
7. Link any related issues in the PR description / 在 PR 描述中链接相关 issue

### PR Title Format / PR 标题格式

Use conventional commit format: / 使用约定式提交格式：

- `feat: Add new feature` / `feat: 添加新功能`
- `fix: Fix bug in email fetching` / `fix: 修复邮件获取中的 bug`
- `docs: Update README` / `docs: 更新 README`
- `style: Format code` / `style: 格式化代码`
- `refactor: Refactor authentication` / `refactor: 重构认证`
- `test: Add tests for email service` / `test: 为邮件服务添加测试`
- `chore: Update dependencies` / `chore: 更新依赖`

## Style Guidelines / 风格指南

### Python Code Style / Python 代码风格

- Follow PEP 8 style guide / 遵循 PEP 8 风格指南
- Use meaningful variable and function names / 使用有意义的变量和函数名
- Add docstrings to functions and classes / 为函数和类添加文档字符串
- Keep functions small and focused / 保持函数小而专注
- Use type hints where appropriate / 在适当的地方使用类型提示

### Git Commit Messages / Git 提交消息

- Use the present tense ("Add feature" not "Added feature") / 使用现在时（"Add feature" 而非 "Added feature"）
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...") / 使用祈使语气（"Move cursor to..." 而非 "Moves cursor to..."）
- Limit the first line to 72 characters or less / 第一行限制在 72 个字符以内
- Reference issues and pull requests after the first line / 在第一行之后引用 issue 和 PR

### Testing / 测试

- Write unit tests for new features / 为新功能编写单元测试
- Ensure all tests pass before submitting PR / 提交 PR 前确保所有测试通过
- Aim for high test coverage / 追求高测试覆盖率
- Test edge cases and error conditions / 测试边界情况和错误条件

## Project Structure / 项目结构

```
outlook_web/
├── app.py                  # Application factory
├── routes/                 # Blueprint routes
├── controllers/            # Request handlers
├── services/               # Business logic
├── repositories/           # Data access
├── middleware/             # Middleware
└── security/               # Security modules
```

For detailed architecture information, see `docs/DEV/00002-前后端拆分-开发者指南.md` / 详细架构信息请参见 `docs/DEV/00002-前后端拆分-开发者指南.md`

## Questions? / 有问题？

Feel free to open an issue with your question or reach out to the maintainers. / 随时开启 issue 提问或联系维护者。

## License / 许可证

By contributing, you agree that your contributions will be licensed under the Apache License 2.0. / 通过贡献，你同意你的贡献将在 Apache License 2.0 下授权。

---

Thank you for contributing! / 感谢你的贡献！
