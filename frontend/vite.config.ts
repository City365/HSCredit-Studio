import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    // 注意：proxy 在某些环境下 ECONNREFUSED，前端走 VITE_API_BASE_URL 直连后端
    // （依赖后端 CORS 允许 http://localhost:3000）
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'antd-vendor': ['antd', '@ant-design/icons'],
          'charts-vendor': ['echarts', 'echarts-for-react'],
          'flow-vendor': ['@xyflow/react', 'reactflow'],
          'monaco-vendor': ['@monaco-editor/react', 'monaco-editor'],
        },
      },
    },
    chunkSizeWarningLimit: 1024,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup.ts'],
    css: false,
  },
});
