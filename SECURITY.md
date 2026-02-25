# Security Policy / 安全策略

## Supported Versions / 支持的版本

We release patches for security vulnerabilities for the following versions: / 我们为以下版本发布安全漏洞补丁：

| Version / 版本 | Supported / 支持          |
| -------------- | ------------------------- |
| latest (main)  | :white_check_mark:        |
| < latest       | :x:                       |

## Reporting a Vulnerability / 报告漏洞

**Please do not report security vulnerabilities through public GitHub issues.** / **请勿通过公开的 GitHub issue 报告安全漏洞。**

If you discover a security vulnerability, please send an email to: / 如果你发现安全漏洞，请发送邮件至：

**Email / 邮箱:** 3052147989@qq.com

Please include the following information in your report: / 请在报告中包含以下信息：

- Type of vulnerability / 漏洞类型
- Full paths of source file(s) related to the vulnerability / 与漏洞相关的源文件完整路径
- Location of the affected source code (tag/branch/commit or direct URL) / 受影响源代码的位置（tag/分支/commit 或直接 URL）
- Step-by-step instructions to reproduce the issue / 重现问题的分步说明
- Proof-of-concept or exploit code (if possible) / 概念验证或漏洞利用代码（如可能）
- Impact of the vulnerability / 漏洞的影响

## Response Timeline / 响应时间表

- **Initial Response / 初始响应:** We will acknowledge receipt of your vulnerability report within 48 hours. / 我们将在 48 小时内确认收到你的漏洞报告。
- **Status Update / 状态更新:** We will provide a more detailed response within 7 days, indicating the next steps in handling your report. / 我们将在 7 天内提供更详细的响应，说明处理报告的后续步骤。
- **Fix Timeline / 修复时间表:** We will work to fix confirmed vulnerabilities as quickly as possible, typically within 30 days. / 我们将尽快修复已确认的漏洞，通常在 30 天内。

## Disclosure Policy / 披露政策

- Please give us reasonable time to fix the vulnerability before public disclosure. / 请在公开披露前给我们合理的时间修复漏洞。
- We will credit you in the security advisory unless you prefer to remain anonymous. / 我们将在安全公告中致谢你，除非你希望保持匿名。
- We will coordinate with you on the disclosure timeline. / 我们将与你协调披露时间表。

## Security Best Practices / 安全最佳实践

When using this application, please follow these security best practices: / 使用此应用时，请遵循以下安全最佳实践：

### For Users / 用户

1. **Strong Passwords / 强密码**
   - Use a strong, unique password for the web interface / 为 Web 界面使用强且唯一的密码
   - Change the default password immediately / 立即更改默认密码
   - Use at least 12 characters with mixed case, numbers, and symbols / 使用至少 12 个字符，包含大小写、数字和符号

2. **SECRET_KEY Management / SECRET_KEY 管理**
   - Always set a strong SECRET_KEY environment variable / 始终设置强 SECRET_KEY 环境变量
   - Never commit SECRET_KEY to version control / 切勿将 SECRET_KEY 提交到版本控制
   - Use a cryptographically secure random string / 使用加密安全的随机字符串
   - Generate with: `python -c 'import secrets; print(secrets.token_hex(32))'`

3. **HTTPS / HTTPS**
   - Always use HTTPS in production / 生产环境始终使用 HTTPS
   - Use a reverse proxy (Nginx/Caddy) with SSL/TLS / 使用带 SSL/TLS 的反向代理（Nginx/Caddy）
   - Enable HSTS (HTTP Strict Transport Security) / 启用 HSTS（HTTP 严格传输安全）

4. **Access Control / 访问控制**
   - Limit access to trusted networks / 限制对受信任网络的访问
   - Use firewall rules to restrict access / 使用防火墙规则限制访问
   - Consider using VPN for remote access / 考虑使用 VPN 进行远程访问

5. **Regular Updates / 定期更新**
   - Keep the application updated to the latest version / 保持应用更新到最新版本
   - Monitor security advisories / 监控安全公告
   - Update dependencies regularly / 定期更新依赖

6. **Data Backup / 数据备份**
   - Regularly backup the database file / 定期备份数据库文件
   - Store backups securely / 安全存储备份
   - Test backup restoration / 测试备份恢复

### For Developers / 开发者

1. **Input Validation / 输入验证**
   - Always validate and sanitize user input / 始终验证和净化用户输入
   - Use parameterized queries to prevent SQL injection / 使用参数化查询防止 SQL 注入
   - Implement proper error handling / 实现适当的错误处理

2. **Authentication & Authorization / 认证与授权**
   - Use bcrypt for password hashing / 使用 bcrypt 进行密码哈希
   - Implement rate limiting for login attempts / 为登录尝试实施速率限制
   - Use secure session management / 使用安全的会话管理

3. **Data Protection / 数据保护**
   - Encrypt sensitive data at rest / 加密静态敏感数据
   - Use HTTPS for data in transit / 使用 HTTPS 传输数据
   - Implement proper access controls / 实施适当的访问控制

4. **Dependencies / 依赖**
   - Keep dependencies up to date / 保持依赖最新
   - Use Dependabot for automated updates / 使用 Dependabot 自动更新
   - Review security advisories / 审查安全公告

5. **Code Review / 代码审查**
   - Review all code changes for security issues / 审查所有代码更改的安全问题
   - Use static analysis tools / 使用静态分析工具
   - Follow secure coding practices / 遵循安全编码实践

## Known Security Features / 已知安全特性

This application includes the following security features: / 此应用包含以下安全特性：

- **XSS Protection / XSS 防护:** DOMPurify sanitization and iframe sandboxing / DOMPurify 净化和 iframe 沙箱隔离
- **CSRF Protection / CSRF 防护:** Flask-WTF token validation / Flask-WTF token 验证
- **Data Encryption / 数据加密:** Fernet symmetric encryption for sensitive data / Fernet 对称加密敏感数据
- **Rate Limiting / 速率限制:** Login attempt throttling / 登录尝试限流
- **Audit Logging / 审计日志:** Sensitive operation tracking / 敏感操作跟踪
- **Password Hashing / 密码哈希:** bcrypt with salt / bcrypt 加盐

For more details, see the security section in README.md / 更多详情请参见 README.md 中的安全部分

## Security Updates / 安全更新

Security updates will be released as soon as possible after a vulnerability is confirmed. We will: / 安全更新将在漏洞确认后尽快发布。我们将：

- Release a patch version / 发布补丁版本
- Publish a security advisory / 发布安全公告
- Update the CHANGELOG / 更新 CHANGELOG
- Notify users through GitHub releases / 通过 GitHub releases 通知用户

## Contact / 联系方式

For security-related questions or concerns, please contact: / 有关安全相关的问题或疑虑，请联系：

- **Email / 邮箱:** 3052147989@qq.com
- **GitHub Issues:** For non-security bugs only / 仅用于非安全 bug

---

Thank you for helping keep this project secure! / 感谢你帮助保持此项目的安全！
