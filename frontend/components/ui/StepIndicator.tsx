'use client';

import { cn } from '../../lib/utils';

export interface StepIndicatorProps {
  steps: string[];
  current: number;
  className?: string;
}

const StepIndicator = ({ steps, current, className }: StepIndicatorProps) => {
  return (
    <div
      className={cn('flex flex-col items-center', className)}
      aria-label={`Step ${current + 1} of ${steps.length}: ${steps[current]}`}
    >
      <div className="flex items-center w-full">
        {steps.map((step, index) => {
          const isActive = index === current;
          const isCompleted = index < current;

          return (
            <div
              key={step}
              className="flex items-center flex-1 last:flex-none"
            >
              <div
                data-testid="step-circle"
                aria-hidden="true"
                className={cn(
                  'h-2 w-2 rounded-full flex-none',
                  isActive && 'bg-[var(--color-primary)]',
                  isCompleted && 'bg-[var(--color-primary)]',
                  !isActive && !isCompleted && 'bg-[var(--color-hairline)]'
                )}
              />
              {index < steps.length - 1 && (
                <div
                  aria-hidden="true"
                  data-testid="step-connector"
                  className={cn(
                    'h-px flex-1 mx-2',
                    index < current
                      ? 'bg-[var(--color-primary)]'
                      : 'bg-[var(--color-hairline)]'
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
      <div className="flex w-full mt-[var(--space-sm)]">
        {steps.map((step, index) => {
          const isActive = index === current;
          return (
            <span
              key={step}
              aria-current={isActive ? 'step' : undefined}
              className={cn(
                'flex-1 text-center text-caption-sm',
                isActive && 'font-medium text-[var(--color-ink)]',
                !isActive && 'text-[var(--color-muted)]'
              )}
            >
              {step}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export { StepIndicator };
