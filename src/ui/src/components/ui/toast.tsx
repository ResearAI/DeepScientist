'use client'

import * as React from 'react'
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PngIcon } from '@/components/ui/png-icon'
import { redactSensitive, truncateText } from '@/lib/bugbash/sanitize'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export type ToastAction = {
  label: string
  onClick: () => void
  ariaLabel?: string
}

export interface Toast {
  id: string
  type: ToastType
  title: string
  description?: string
  details?: string
  action?: ToastAction
  duration?: number
  createdAt?: number
  read?: boolean
}

// Shadcn-style toast options for convenience
export interface ToastOptions {
  title: string
  description?: string
  details?: string
  action?: ToastAction
  variant?: 'default' | 'destructive' | 'success' | 'warning'
  duration?: number
}

type ToastListener = (toast: Omit<Toast, 'id'>) => void

const toastListeners = new Set<ToastListener>()
const pendingToasts: Array<Omit<Toast, 'id'>> = []
const MAX_PENDING_TOASTS = 20

function describeUnhandledReason(reason: unknown) {
  if (reason instanceof Error) {
    return {
      message: reason.message || reason.name || 'Unhandled rejection',
      stack: reason.stack,
    }
  }
  if (typeof reason === 'string') {
    return {
      message: reason || 'Unhandled rejection',
      stack: undefined,
    }
  }
  if (typeof Event !== 'undefined' && reason instanceof Event) {
    const eventType = String(reason.type || '').trim()
    return {
      message: eventType ? `Unhandled rejection (Event: ${eventType})` : 'Unhandled rejection (Event)',
      stack: undefined,
    }
  }
  if (reason && typeof reason === 'object') {
    try {
      const serialized = JSON.stringify(reason)
      if (serialized && serialized !== '{}') {
        return {
          message: `Unhandled rejection (${serialized})`,
          stack: undefined,
        }
      }
    } catch {
      // Ignore serialization failure and fall back to constructor naming.
    }
    const constructorName =
      typeof (reason as { constructor?: { name?: unknown } }).constructor?.name === 'string'
        ? String((reason as { constructor?: { name?: string } }).constructor?.name)
        : 'Object'
    return {
      message: `Unhandled rejection (${constructorName})`,
      stack: undefined,
    }
  }
  return {
    message: 'Unhandled rejection',
    stack: undefined,
  }
}

function registerToastListener(listener: ToastListener) {
  toastListeners.add(listener)
  if (pendingToasts.length) {
    pendingToasts.splice(0).forEach((item) => listener(item))
  }
  return () => {
    toastListeners.delete(listener)
  }
}

interface ToastContextValue {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
  markToastRead: (id: string) => void
  markAllRead: () => void
  clearToasts: () => void
  // Shadcn-compatible toast function
  toast: (options: ToastOptions) => void
}

const ToastContext = React.createContext<ToastContextValue | undefined>(undefined)

export function useToast() {
  const context = React.useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}

interface ToastProviderProps {
  children: React.ReactNode
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = React.useState<Toast[]>([])

  const addToast = React.useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).slice(2, 9)
    const newToast: Toast = {
      ...toast,
      id,
      createdAt: Date.now(),
      read: false,
    }
    setToasts((prev) => {
      const next = [...prev, newToast]
      // keep a reasonable cap
      return next.length > 200 ? next.slice(next.length - 200) : next
    })
  }, [])

  const removeToast = React.useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const markToastRead = React.useCallback((id: string) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, read: true } : t)))
  }, [])

  const markAllRead = React.useCallback(() => {
    setToasts((prev) => prev.map((t) => ({ ...t, read: true })))
  }, [])

  const clearToasts = React.useCallback(() => {
    setToasts([])
  }, [])

  // Shadcn-compatible toast function that maps variant to type
  const toast = React.useCallback((options: ToastOptions) => {
    const variantToType: Record<string, ToastType> = {
      default: 'info',
      destructive: 'error',
      success: 'success',
      warning: 'warning',
    }
    addToast({
      type: variantToType[options.variant || 'default'] || 'info',
      title: options.title,
      description: options.description,
      details: options.details,
      action: options.action,
      duration: options.duration,
    })
  }, [addToast])

  React.useEffect(() => registerToastListener(addToast), [addToast])

  // Capture global frontend errors into notifications (best-effort).
  React.useEffect(() => {
    const onError = (event: ErrorEvent) => {
      if ((event.error as { __dsHandled?: boolean } | null)?.__dsHandled) return
      const message = event.error?.message || event.message || 'Unhandled error'
      const stack = event.error?.stack
      const details = stack ? truncateText(redactSensitive(stack), 4000) : undefined
      addToast({
        type: 'error',
        title: 'Frontend error',
        description: redactSensitive(message),
        details,
        duration: 0,
      })
    }

    const onRejection = (event: PromiseRejectionEvent) => {
      if ((event.reason as { __dsHandled?: boolean } | null)?.__dsHandled) return
      const { message, stack } = describeUnhandledReason(event.reason)
      const details = stack ? truncateText(redactSensitive(stack), 4000) : undefined
      addToast({
        type: 'error',
        title: 'Unhandled rejection',
        description: redactSensitive(message),
        details,
        duration: 0,
      })
    }

    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onRejection)
    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onRejection)
    }
  }, [addToast])

  return (
    <ToastContext.Provider
      value={{ toasts, addToast, removeToast, markToastRead, markAllRead, clearToasts, toast }}
    >
      {children}
      <ToastContainer />
    </ToastContext.Provider>
  )
}

function ToastContainer() {
  return null
}

// P3-2 fix: Use semantic color tokens instead of hardcoded colors
const toastIcons: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle className="h-5 w-5 text-success" />,
  error: (
    <PngIcon
      name="AlertCircle"
      size={20}
      className="h-5 w-5"
      fallback={<AlertCircle className="h-5 w-5 text-destructive" />}
    />
  ),
  warning: (
    <PngIcon
      name="AlertTriangle"
      size={20}
      className="h-5 w-5"
      fallback={<AlertTriangle className="h-5 w-5 text-warning" />}
    />
  ),
  info: <Info className="h-5 w-5 text-primary" />,
}

const toastStyles: Record<ToastType, string> = {
  success: 'border-l-4 border-l-success',
  error: 'border-l-4 border-l-destructive',
  warning: 'border-l-4 border-l-warning',
  info: 'border-l-4 border-l-primary',
}

interface ToastItemProps {
  toast: Toast
  onClose: () => void
}

function ToastItem({ toast, onClose }: ToastItemProps) {
  return (
    <div
      className={cn(
        'relative flex items-start gap-3 p-4 rounded-lg bg-surface',
        'shadow-[6px_6px_12px_hsl(var(--shadow-dark)),-6px_-6px_12px_hsl(var(--shadow-light))]',
        'animate-in slide-in-from-right-full fade-in-0 duration-300',
        toastStyles[toast.type]
      )}
    >
      <div className="flex-shrink-0 mt-0.5">
        {toastIcons[toast.type]}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description && (
          <p className="mt-1 text-sm text-muted-foreground">{toast.description}</p>
        )}
        {toast.details ? (
          <details className="mt-2 text-xs text-muted-foreground">
            <summary className="cursor-pointer select-none">Details</summary>
            <pre className="mt-1 whitespace-pre-wrap break-words">
              {toast.details}
            </pre>
          </details>
        ) : null}
        {toast.action ? (
          <button
            type="button"
            className="mt-2 inline-flex items-center rounded-md border border-border px-2 py-1 text-xs font-medium text-foreground hover:bg-muted/60"
            aria-label={toast.action.ariaLabel || toast.action.label}
            onClick={() => {
              toast.action?.onClick()
              onClose()
            }}
          >
            {toast.action.label}
          </button>
        ) : null}
      </div>
      <button
        onClick={onClose}
        className="flex-shrink-0 p-1 rounded hover:bg-muted/50 transition-colors"
      >
        <X className="h-4 w-4 text-muted-foreground" />
        <span className="sr-only">Close</span>
      </button>
    </div>
  )
}

// Convenience functions for toast creation
export function toast(options: Omit<Toast, 'id'>) {
  if (toastListeners.size === 0) {
    pendingToasts.push(options)
    if (pendingToasts.length > MAX_PENDING_TOASTS) {
      pendingToasts.shift()
    }
    return
  }
  toastListeners.forEach((listener) => listener(options))
}

export { ToastContainer, ToastItem }
