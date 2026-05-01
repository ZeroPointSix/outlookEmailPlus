/**
 * Jest 配置文件 — 标准模式批量拉取邮件行为测试
 *
 * 运行方式：
 *   npx jest --config tests/batch-fetch/jest.config.js
 */

module.exports = {
  testEnvironment: 'jsdom',
  rootDir: '../../',
  testMatch: ['**/tests/batch-fetch/**/*.test.js'],
  testTimeout: 10000,
  verbose: true,
  setupFilesAfterEnv: ['<rootDir>/tests/batch-fetch/setup.js'],
};
