'use client';

import { forwardRef } from 'react';
import { cn } from '../../lib/utils';

export interface CardProps {
  children: React.ReactNode;
  padding?: 'sm' | 'md' | 'lg';
  className?: string;
}

const paddingClasses = {
  sm: 'p-[var(--space-sm)]',
  md: 'p-[var(--space-base)]',
  lg: 'p-[var(--space-lg)]',
};

const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, children, padding = 'md' }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'bg-white rounded-[var(--rounded-md)]',
          'hover:shadow-card transition-shadow',
          paddingClasses[padding],
          className
        )}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

export { Card };