import { render, screen } from '@testing-library/react';
import { Badge } from '../Badge';

describe('Badge', () => {
  it('renders children', () => {
    render(<Badge>Badge text</Badge>);
    expect(screen.getByText('Badge text')).toBeInTheDocument();
  });

  it('renders with default variant', () => {
    render(<Badge data-testid="badge">Default</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-white');
    expect(badge).toHaveClass('text-[var(--color-ink)]');
  });

  it('renders with primary variant', () => {
    render(<Badge variant="primary" data-testid="badge">Primary</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-[var(--color-primary)]');
    expect(badge).toHaveClass('text-white');
  });

  it('renders with new variant', () => {
    render(<Badge variant="new" data-testid="badge">NEW</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-white');
    expect(badge).toHaveClass('text-[var(--color-primary)]');
    expect(badge).toHaveClass('border-[var(--color-primary)]');
    expect(badge).toHaveTextContent('NEW');
  });

  it('is rounded fully', () => {
    render(<Badge data-testid="badge">Test</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('rounded-full');
  });

  it('applies custom className', () => {
    render(<Badge className="custom-badge" data-testid="badge">Test</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('custom-badge');
  });
});