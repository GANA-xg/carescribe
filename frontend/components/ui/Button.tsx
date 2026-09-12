'use client';

import { forwardRef } from 'react';
import { cn } from '../../lib/utils';

export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'pill';
export type ButtonSize = 'md' | 'sm';

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const buttonBaseClasses =
  'inline-flex items-center justify-center rounded-[var(--rounded-sm)] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40';

const variantClasses = {
  primary:
    'bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-active)] disabled:cursor-not-allowed disabled:bg-[var(--color-primary-disabled)]',
  secondary:
    'bg-white text-[var(--color-ink)] border border-[var(--color-ink)] hover:bg-[var(--color-surface-soft)]',
  tertiary:
    'bg-transparent text-[var(--color-ink)] hover:bg-[var(--color-surface-soft)]',
  pill:
    'bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-active)] rounded-full',
};

const sizeClasses = {
  md: 'h-[var(--space-xxl)] px-[var(--space-lg)] text-button-md',
  sm: 'h-[var(--space-lg)] px-[var(--space-base)] text-button-sm',
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', loading, children, disabled, ...props }, ref) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        className={cn(
          buttonBaseClasses,
          variantClasses[variant],
          sizeClasses[size],
          className
        )}
        disabled={isDisabled}
        {...props}
      >
        {loading ? (
          <span
            className="animate-spin inline-block h-[18px] w-[18px] rounded-full border-2 border-white border-t-transparent"
            role="status"
            aria-label="Loading"
          />
        ) : (
          children
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';

export { Button };