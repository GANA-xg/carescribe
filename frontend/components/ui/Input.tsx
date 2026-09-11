'use client';

import { forwardRef, useId } from 'react';
import { cn } from '../../lib/utils';

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id || `input-${generatedId}`;
    const errorId = `${inputId}-error`;
    const labelId = `${inputId}-label`;

    return (
      <div className="flex flex-col gap-[var(--space-xs)]">
        {label && (
          <label
            htmlFor={inputId}
            id={labelId}
            className="text-caption text-[var(--color-ink)]"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={!!error}
          aria-describedby={error ? errorId : undefined}
          className={cn(
            'flex h-[56px] w-full rounded-[var(--rounded-sm)] border bg-white px-[var(--space-base)] text-body-md text-[var(--color-ink)]',
            'placeholder:text-[var(--color-muted)]',
            'focus:outline-none focus:ring-2 focus:ring-[var(--color-ink)]',
            'focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
            error && 'border-[var(--color-error)]',
            !error && 'border-[var(--color-hairline)]',
            className
          )}
          {...props}
        />
        {error && (
          <p
            id={errorId}
            className="text-caption text-[var(--color-error)]"
            role="alert"
          >
            {error}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export { Input };