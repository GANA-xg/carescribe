'use client';

import React from 'react';

type Props = { children: React.ReactNode };
type State = { error: Error | null };

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="flex flex-col items-center justify-center h-64 gap-[var(--space-base)]"
          role="alert"
        >
          <p className="text-body-md text-[var(--color-error)]">Something went wrong.</p>
          <button
            onClick={() => this.setState({ error: null })}
            className="text-body-sm text-[var(--color-primary)] underline"
            aria-label="Try again"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
