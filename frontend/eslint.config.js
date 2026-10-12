// ESLint 配置 —— 面向 React + TypeScript + Vite 项目.
// 使用 eslint.config.js 扁平配置（ESLint 9+ 格式）.
//
// 运行: pnpm lint (检查) | pnpm lint:fix (自动修复)

import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import testingLibrary from 'eslint-plugin-testing-library'

export default tseslint.config(
  // 忽略文件（优先级最高）
  { ignores: ['dist', 'node_modules', 'coverage', 'playwright-report', 'test-results', '.auth', 'src/iterd/static'] },

  // JavaScript 推荐规则
  js.configs.recommended,

  // TypeScript 推荐规则
  ...tseslint.configs.recommended,

  // React 规则
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { react },
    settings: { react: { version: 'detect' } },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      // 组件 props 由 TS 类型约束，不需要运行时 PropTypes
      'react/prop-types': 'off',
    },
  },

  // React Hooks 规则
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
    },
  },

  // Vite React Refresh 规则
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { 'react-refresh': reactRefresh },
    rules: {
      ...reactRefresh.configs.vite.rules,
      // 关闭：允许入口/布局文件同时导出组件与工具
      'react-refresh/only-export-components': 'off',
    },
  },

  // 项目自定义规则（最后覆盖）
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        navigator: 'readonly',
        localStorage: 'readonly',
        console: 'readonly',
      },
    },
    rules: {
      // 允许未使用的变量（以 _ 开头）
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // 允许非空断言 `!`
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },

  // Node.js 脚本（覆盖率校验等构建期脚本）—— 提供 Node 全局
  {
    files: ['scripts/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        console: 'readonly',
        process: 'readonly',
      },
    },
  },

  // E2E / Playwright 配置代码放宽规则（fixture 类型天然需要 any / 声明但不用的辅助变量）
  {
    files: ['tests/**/*.ts', 'playwright.config.ts'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },

  // Testing Library 组件测试规则 —— 防"同步 getBy 与异步渲染竞态"（AntD portal 类 UI 异步挂载，
  // 本地机器快掩盖、CI 稳定失败）
  {
    files: ['src/**/*.{test,spec}.{ts,tsx}', 'src/test/**/*.{ts,tsx}'],
    plugins: { 'testing-library': testingLibrary },
    rules: {
      // 异步查询（findBy*）必须 await，事件后的出现/消失断言禁止同步 getBy/queryBy 抢跑
      'testing-library/await-async-queries': 'error',
      'testing-library/await-async-utils': 'error',
      // 不允许 await 同步查询（掩盖真实异步时序）
      'testing-library/no-await-sync-queries': 'error',
      // waitFor 回调内禁止副作用（setState/fireEvent 等），防止轮询放大竞态
      'testing-library/no-wait-for-side-effects': 'error',
      // 出现断言优先 findBy 而非 waitFor(getBy)
      'testing-library/prefer-find-by': 'error',
    },
  },
)
