'use client';

import { forwardRef, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

export const Modal = forwardRef<HTMLDivElement, ModalProps>(
  ({ open, onClose, title, description, children, className, size = 'md' }, ref) => {
    const overlayRef = useRef<HTMLDivElement>(null);
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
      setMounted(true);
    }, []);

    useEffect(() => {
      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onClose();
        }
      };

      if (open) {
        document.addEventListener('keydown', handleEscape);
        document.body.style.overflow = 'hidden';
      }

      return () => {
        document.removeEventListener('keydown', handleEscape);
        document.body.style.overflow = 'unset';
      };
    }, [open, onClose]);

    const handleOverlayClick = (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) {
        onClose();
      }
    };

    if (!open || !mounted) return null;

    return createPortal(
      <div
        ref={overlayRef}
        onClick={handleOverlayClick}
        className="fixed inset-0 z-[10000] flex items-start justify-center overflow-y-auto bg-black/50 p-3 backdrop-blur-sm animate-in fade-in duration-200 sm:items-center sm:p-6"
      >
        <div
          ref={ref}
          className={cn(
            'relative flex min-h-0 max-h-[calc(100dvh-1.5rem)] flex-col overflow-hidden bg-soft-bg-surface rounded-soft-lg border border-soft-border shadow-soft-lg sm:max-h-[calc(100dvh-3rem)]',
            'animate-in zoom-in-95 duration-200',
            size === 'sm' && 'w-full max-w-sm',
            size === 'md' && 'w-full max-w-md',
            size === 'lg' && 'w-full max-w-lg',
            size === 'xl' && 'w-full max-w-xl',
            className
          )}
        >
          {/* Header */}
          {(title || description) && (
            <div className="px-6 py-4 border-b border-soft-border">
              {title && (
                <h2 className="text-lg font-semibold text-soft-text-primary">
                  {title}
                </h2>
              )}
              {description && (
                <p className="mt-1 text-sm text-soft-text-secondary">
                  {description}
                </p>
              )}
            </div>
          )}

          {/* Close button */}
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-4 top-4 z-[60] pointer-events-auto"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>

          {/* Content */}
          <div className="modal-scrollbar min-h-0 flex-1 overflow-y-auto px-6 py-4">
            {children}
          </div>
        </div>
      </div>,
      document.body
    );
  }
);
Modal.displayName = 'Modal';

interface ModalFooterProps extends React.HTMLAttributes<HTMLDivElement> {}

export const ModalFooter = forwardRef<HTMLDivElement, ModalFooterProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'flex items-center justify-end gap-3 px-6 py-4 border-t border-soft-border bg-soft-bg-elevated/50 rounded-b-soft-lg',
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);
ModalFooter.displayName = 'ModalFooter';

interface ConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning' | 'default';
  loading?: boolean;
}

export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'default',
  loading,
}: ConfirmModalProps) {
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm">
      <p className="text-soft-text-secondary">{description}</p>
      <ModalFooter className="-mx-6 -mb-4 mt-4">
        <Button variant="secondary" onClick={onClose} disabled={loading}>
          {cancelText}
        </Button>
        <Button
          onClick={onConfirm}
          loading={loading}
          className={cn(
            variant === 'danger' && 'bg-red-500 hover:bg-red-600',
            variant === 'warning' && 'bg-amber-500 hover:bg-amber-600'
          )}
        >
          {confirmText}
        </Button>
      </ModalFooter>
    </Modal>
  );
}
