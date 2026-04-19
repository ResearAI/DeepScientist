import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

function resolveManualChunk(id: string) {
  const normalizedId = id.replace(/\\/g, '/')
  if (!normalizedId.includes('/node_modules/')) {
    return undefined
  }
  if (normalizedId.includes('monaco-editor') || normalizedId.includes('@monaco-editor')) {
    return 'plugin-monaco'
  }
  if (normalizedId.includes('/pdfjs-dist/') || normalizedId.includes('/unpdf/')) {
    return 'plugin-pdf'
  }
  if (
    normalizedId.includes('/novel/') ||
    normalizedId.includes('/@tiptap/') ||
    normalizedId.includes('/yjs/') ||
    normalizedId.includes('/y-protocols/') ||
    normalizedId.includes('/prosemirror-') ||
    normalizedId.includes('/lowlight/')
  ) {
    return 'plugin-notebook'
  }
  if (normalizedId.includes('/@xterm/') || normalizedId.includes('/xterm/')) {
    return 'plugin-terminal'
  }
  return undefined
}

export default defineConfig(({ mode }) => {
  const proxyTarget =
    process.env.VITE_PROXY_TARGET || process.env.VITE_API_URL || 'http://127.0.0.1:20999'
  const browserEnv = {
    NODE_ENV: mode,
    NEXT_PUBLIC_API_URL: process.env.VITE_API_URL || process.env.NEXT_PUBLIC_API_URL || '',
    NEXT_PUBLIC_ENABLE_COPILOT_FILES: process.env.NEXT_PUBLIC_ENABLE_COPILOT_FILES || '',
    NEXT_PUBLIC_CLI_ATTACH_ADDON: process.env.NEXT_PUBLIC_CLI_ATTACH_ADDON || '',
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || '',
    NEXT_PUBLIC_APP_VERSION: process.env.NEXT_PUBLIC_APP_VERSION || '',
    NEXT_PUBLIC_COMMIT_HASH: process.env.NEXT_PUBLIC_COMMIT_HASH || '',
    NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA: process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA || '',
    NEXT_PUBLIC_GIT_COMMIT_SHA: process.env.NEXT_PUBLIC_GIT_COMMIT_SHA || '',
    NEXT_PUBLIC_GIT_SHA: process.env.NEXT_PUBLIC_GIT_SHA || '',
  }

  return {
    base: '/ui/',
    publicDir: false,
    plugins: [react()],
    define: {
      'process.env': browserEnv,
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      target: 'esnext',
      minify: mode === 'development' ? false : 'esbuild',
      reportCompressedSize: false,
      rollupOptions: {
        output: {
          manualChunks: resolveManualChunk,
        },
      },
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
