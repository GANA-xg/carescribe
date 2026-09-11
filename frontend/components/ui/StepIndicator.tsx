'use client';

import { cn } from '../../lib/utils';

export interface StepIndicatorProps {
  steps: string[];
  current: number;
  className?: string;
}

const StepIndicator = ({ steps, current, className }: StepIndicatorProps) => {
  return (
    <div className={cn('flex items-center justify-between', className)}>
      {steps.map((step, index) => {
        const isCompleted = index < current;
        const isActive = index === current;

        return (
          <div key={step} className="flex flex-col items-center flex-1">
            <div
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-full',
                isCompleted && 'bg-[var(--color-primary)] text-white',
                isActive && 'border-2 border-[var(--color-primary)] text-[var(--color-primary)]',
                !isCompleted && !isActive && 'bg-[var(--color-surface-soft)] text-[var(--color-muted)] border border-[var(--color-hairline)]',
              )}
            >
              {isCompleted || isActive ? index + 1 : null}
            </div>
            <span
              className={cn(
                'mt-[var(--space-xs)] text-caption-sm',
                isActive && 'text-[var(--color-ink)] font-medium',
                !isActive && 'text-[var(--color-muted)]',
              )}
            >
              {step}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export { StepIndicator };