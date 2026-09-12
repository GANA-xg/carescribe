import { render } from '@testing-library/react';
import { Badge } from '../Badge';

describe('Badge', () => {
  it('renders children', () => {
    const { container } = render(<Badge>Default</Badge>);
    expect(container.textContent).toBe('Default');
  });

  it('renders with default variant', () => {
    const { container } = render(<Badge>Default</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge).toHaveClass('bg-[var(--color-surface-strong)]');
    expect(badge).toHaveClass('text-[var(--color-muted)]');
  });

  it('renders with primary variant', () => {
    const { container } = render(<Badge variant="primary">Primary</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge).toHaveClass('bg-[var(--color-primary)]');
    expect(badge).toHaveClass('text-white');
  });

  it('renders with success variant', () => {
    const { container } = render(<Badge variant="success">Low</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge).toHaveClass('bg-[#22c55e]');
    expect(badge).toHaveClass('text-white');
  });

  it('renders with warning variant', () => {
    const { container } = render(<Badge variant="warning">Medium</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge).toHaveClass('bg-[#f97316]');
  });

  it('renders with danger variant', () => {
    const { container } = render(<Badge variant="danger">High</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge).toHaveClass('bg-[var(--color-primary)]');
    expect(badge).toHaveClass('text-white');
  });

  it('is fully rounded', () => {
    const { container } = render(<Badge>Test</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge).toHaveClass('rounded-full');
  });

  it('applies custom className', () => {
    const { container } = render(<Badge className="custom-badge">Test</Badge>);
    const badge = container.firstChild as HTMLElement;
    expect(badge).toHaveClass('custom-badge');
  });
});
