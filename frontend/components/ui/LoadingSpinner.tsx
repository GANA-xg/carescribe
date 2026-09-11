'use client';

import { cn } from '../../lib/utils';
import { Loader2 } from 'lucide-react';

export interface LoadingSpinnerProps {
  className?: string;
  message?: string;
}

const LoadingSpinner = ({ className, message }: LoadingSpinnerProps) => {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-[var(--space-sm)]', className)}>
      <Loader2 className="h-8 w-8 animate-spin text-[var(--color-primary)]" />
      {message && (
        <p className="text-body-md text-[var(--color-muted)]">
          {message}
        </p>
      )}
    </div>
  );
};

export { LoadingSpinner };