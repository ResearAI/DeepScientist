import { X } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function OverlayDialog({
  open,
  title,
  description,
  onClose,
  children,
  className,
  hideHeader = false,
  dataOnboardingId,
  closeButtonDataOnboardingId,
}: {
  open: boolean
  title: string
  description?: string
  onClose: () => void
  children: ReactNode
  className?: string
  hideHeader?: boolean
  dataOnboardingId?: string
  closeButtonDataOnboardingId?: string
}) {
  if (!open) {
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-3 backdrop-blur-md sm:p-6"
      onClick={onClose}
    >
      <div
        className={cn(
          'morandi-surface view-panel relative flex max-h-[92dvh] w-full max-w-6xl flex-col overflow-hidden rounded-[32px]',
          className
        )}
        role="dialog"
        aria-modal="true"
        data-onboarding-id={dataOnboardingId}
        onClick={(event) => event.stopPropagation()}
      >
        {hideHeader ? null : (
          <div className="flex items-start justify-between gap-4 border-b border-black/[0.06] px-5 py-4 dark:border-white/[0.08] sm:px-6">
            <div className="min-w-0 space-y-1">
              <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
              {description ? <p className="text-sm leading-6 text-muted-foreground">{description}</p> : null}
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              aria-label="Close dialog"
              data-onboarding-id={closeButtonDataOnboardingId}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        )}
        <div className="feed-scrollbar modal-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {children}
        </div>
      </div>
    </div>
  )
}
