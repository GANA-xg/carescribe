'use client';

import { useEffect, type ReactNode } from 'react';
import TopNav from './TopNav';
import ErrorBoundary from './ErrorBoundary';
import { useAuthStore } from '../../store/auth';
import { LoadingSpinner } from '../ui';

export default function AuthenticatedShell({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const hydrated = useAuthStore((s) => s.hydrated);
  const hydrate = useAuthStore((s) => s.hydrate);

  useEffect(() => {
    if (!hydrated) void hydrate();
  }, [hydrated, hydrate]);

  if (!hydrated || (hydrated && !user)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner message="Loading CareScribe…" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--color-canvas)]">
      <TopNav />
      <main className="mx-auto w-full max-w-[1128px] px-[var(--space-base)] min-[744px]:px-[var(--space-lg)] pb-[var(--space-section)]">
        <ErrorBoundary>{children}</ErrorBoundary>
      </main>
    </div>
  );
}
