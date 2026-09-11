'use client';

import { forwardRef } from 'react';
import { cn } from '../../lib/utils';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'primary' | 'new';
  className?: string;
}

const badgeVariants = {
  default:
    'inline-flex items-center rounded-full bg-white px-[var(--space-sm)] py-[var(--space-xxs)] text-badge text-[var(--color-ink)]',
  primary:
    'inline-flex items-center rounded-full bg-[var(--color-primary)] px-[var(--space-sm)] py-[var(--space-xxs)] text-badge text-white',
  new:
    'inline-flex items-center rounded-full bg-white px-[var(--space-sm)] py-[var(--space-xxs)] text-tag text-[var(--color-primary)] uppercase border border-[var(--color-primary)]',
};

const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', children }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(badgeVariants[variant], className)}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';

export { Badge };