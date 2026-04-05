import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import App from '@/App'
import { ToastProvider } from '@/components/ui/toast'
import { initializeBuiltinPlugins, scheduleCommonPluginPreload } from '@/lib/plugin/init'
import { useThemeStore } from '@/lib/stores/theme'
import '@/index.css'

useThemeStore.getState().initTheme()
initializeBuiltinPlugins()
if (typeof window !== 'undefined') {
  queueMicrotask(() => {
    scheduleCommonPluginPreload()
  })
}

function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            refetchOnWindowFocus: false,
          },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Providers>
      <App />
    </Providers>
  </React.StrictMode>
)
