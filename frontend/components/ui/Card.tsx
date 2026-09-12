'use client';

import { forwardRef } from 'react';
import { cn } from '../../lib/utils';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  padding?: 'sm' | 'md' | 'lg';
}

const paddingClasses = {
  sm: 'p-[var(--space-sm)]',
  md: 'p-[var(--space-base)]',
  lg: 'p-[var(--space-lg)]',
};

const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, children, padding = 'md', ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'bg-white rounded-[var(--rounded-md)]',
          'hover:shadow-card transition-shadow',
          paddingClasses[padding],
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

export { Card };