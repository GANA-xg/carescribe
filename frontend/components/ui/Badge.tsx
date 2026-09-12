'use client';

import { forwardRef } from 'react';
import { cn } from '../../lib/utils';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger';
  className?: string;
}

const badgeVariants = {
  default:
    'bg-[var(--color-surface-strong)] text-[var(--color-muted)]',
  primary:
    'bg-[var(--color-primary)] text-white',
  success:
    'bg-[#22c55e] text-white',
  warning:
    'bg-[#f97316] text-white',
  danger:
    'bg-[var(--color-primary)] text-white',
};

const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', children }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center rounded-full px-[10px] py-[4px] text-badge font-semibold',
          badgeVariants[variant],
          className
        )}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';

export { Badge };
