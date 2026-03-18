import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig(({ mode }) => {
  const proxyTarget =
    process.env.VITE_PROXY_TARGET || process.env.VITE_API_URL || 'http://127.0.0.1:20999'

  return {
    base: '/ui/',
    plugins: [react()],
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      target: 'esnext',
      minify: false,
      reportCompressedSize: false,
    },
    optimizeDeps: {
      esbuildOptions: {
        target: 'esnext',
      },
    },
    resolve: {
      alias: [
        { find: /^@\//, replacement: `${resolve(__dirname, 'src')}/` },
        {
          find: /^@reduxjs\/toolkit$/,
          replacement: resolve(__dirname, 'node_modules/@reduxjs/toolkit/dist/redux-toolkit.legacy-esm.js'),
        },
        {
          find: /^react-redux$/,
          replacement: resolve(__dirname, 'node_modules/react-redux/dist/react-redux.mjs'),
        },
        { find: /^motion-dom$/, replacement: resolve(__dirname, 'node_modules/motion-dom/dist/cjs/index.js') },
        { find: /^@xterm\/xterm$/, replacement: resolve(__dirname, 'node_modules/@xterm/xterm/lib/xterm.js') },
        {
          find: /^@xterm\/addon-webgl$/,
          replacement: resolve(__dirname, 'node_modules/@xterm/addon-webgl/lib/addon-webgl.js'),
        },
        {
          find: /^@xterm\/xterm\/css\/xterm\.css$/,
          replacement: resolve(__dirname, 'node_modules/@xterm/xterm/css/xterm.css'),
        },
        { find: /^next\/navigation$/, replacement: resolve(__dirname, 'src/compat/next-navigation.ts') },
        { find: /^next\/link$/, replacement: resolve(__dirname, 'src/compat/next-link.tsx') },
        { find: /^next\/dynamic$/, replacement: resolve(__dirname, 'src/compat/next-dynamic.tsx') },
      ],
    },
    server: {
      host: '0.0.0.0',
      port: 21888,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/assets': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
