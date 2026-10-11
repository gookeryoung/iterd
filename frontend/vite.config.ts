import { defineConfig } from 'vite';
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
});
