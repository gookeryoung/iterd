import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// 构建产物输出到后端 static 目录，由 FastAPI 同源托管
export default defineConfig({
  base: '/',
  plugins: [react()],
  build: {
    outDir: '../src/iterd/static',
    emptyOutDir: true,
    // antd 全家族（antd + @ant-design + rc-* + @emotion）压缩后约 1057KB（gzip 约 331KB），
    // 内部互相依赖，是可拆出的最小无环单元；阈值仅用于约束其余业务/vendor chunk
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        // 按依赖族拆分：antd 全家族、react 系（含 @tanstack/use-sync-external-store
        // 与 @remix-run/router，避免跨组循环 chunk）、其余 vendor；业务代码在 index（约 55KB）
        manualChunks(id: string): string | undefined {
          if (!id.includes('node_modules')) {
            return undefined;
          }
          if (id.includes('antd') || id.includes('@ant-design') || id.includes('rc-') || id.includes('@emotion') || id.includes('dayjs') || id.includes('classnames')) {
            return 'antd';
          }
          if (id.includes('react') || id.includes('scheduler') || id.includes('@tanstack') || id.includes('use-sync-external-store') || id.includes('@remix-run')) {
            return 'react';
          }
          return 'vendor';
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  // ── Vitest 测试配置（不影响构建行为）────────────────────────────────
  test: {
    // antd 5 组件在 happy-dom 下兼容性欠佳，选择 jsdom
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // 每个用例结束后自动 restore 所有 spyOn mock，防止异常分支的 mock 泄漏到后续用例
    restoreMocks: true,
    // antd 渲染 + MSW 拦截链路在并行 worker 下偶发超时，放宽阈值不改变断言语义
    testTimeout: 10_000,
    // 单元/组件测试遵循就近放置约定：src 下的 *.test.ts(x)
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      // 测试设施与类型声明不纳入覆盖率统计
      exclude: [
        'src/test/**',
        'src/**/*.test.{ts,tsx}',
        'src/**/*.spec.{ts,tsx}',
        'src/**/*.d.ts',
        'src/vite-env.d.ts',
      ],
      // CI 下只输出 text + json-summary（check-coverage.mjs 依赖 json-summary），
      // 省去 html 报告生成开销；本地保留 html 便于浏览
      reporter: process.env.CI ? ['text', 'json-summary'] : ['text', 'json-summary', 'html'],
      reportsDirectory: 'coverage',
    },
  },
});
