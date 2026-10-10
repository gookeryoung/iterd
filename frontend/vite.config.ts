import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 构建产物输出到后端 static 目录，由 FastAPI 同源托管
export default defineConfig({
  base: '/',
  plugins: [react()],
  build: {
    outDir: '../src/iterd/static',
    emptyOutDir: true,
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
