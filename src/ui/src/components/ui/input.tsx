'use client';

import { forwardRef, useId } from 'react';
import { cn } from '@/lib/utils';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, hint, id, style, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id || generatedId;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-[var(--soft-text-primary)] mb-1.5"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            // Base Soft UI styles
            'w-full h-12 px-4 rounded-soft-md',
            'bg-[var(--soft-bg-base)] text-[var(--soft-text-primary)]',
            'placeholder:text-[var(--soft-text-tertiary)]',
            'border-none',
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
          style={{
            WebkitTextFillColor: 'currentColor',
            ...style,
          }}
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
Input.displayName = 'Input';

export type { InputProps };
