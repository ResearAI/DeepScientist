'use client';

import { forwardRef, useId } from 'react';
import { cn } from '@/lib/utils';

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  hint?: string;
  containerClassName?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, hint, id, containerClassName, ...props }, ref) => {
    const generatedId = useId();
    const textareaId = id || generatedId;

    return (
      <div className={cn('w-full', containerClassName)}>
        {label && (
          <label
            htmlFor={textareaId}
            className="block text-sm font-medium text-[var(--soft-text-primary)] mb-1.5"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={cn(
            // Base Soft UI styles
            'w-full min-h-[100px] px-4 py-3 rounded-soft-md',
            'bg-[var(--soft-bg-base)] text-[var(--soft-text-primary)]',
            'placeholder:text-[var(--soft-text-tertiary)]',
            'border-none resize-none',
            // Soft UI inset shadow
            'shadow-soft-inset',
            // Focus state
            'focus:outline-none focus:shadow-soft-inset-focus',
            // Transition
            'transition-soft',
            // Disabled state
            'disabled:opacity-50 disabled:cursor-not-allowed',
            // Error state
            error && 'shadow-soft-inset-error',
            className
          )}
          {...props}
        />
        {error && (
          <p className="mt-1.5 text-sm text-[var(--soft-danger)]">{error}</p>
        )}
        {hint && !error && (
          <p className="mt-1.5 text-sm text-[var(--soft-text-tertiary)]">{hint}</p>
        )}
      </div>
    );
  }
);
Textarea.displayName = 'Textarea';

export type { TextareaProps };
