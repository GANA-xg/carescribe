import { render, screen, fireEvent } from '@testing-library/react';
import { Input } from '../Input';

describe('Input', () => {
  it('renders without label', () => {
    render(<Input placeholder="Enter text" />);
    const input = screen.getByPlaceholderText('Enter text');
    expect(input).toBeInTheDocument();
  });

  it('renders with label', () => {
    render(<Input label="Email address" id="email" />);
    const input = screen.getByLabelText('Email address');
    expect(input).toBeInTheDocument();
  });

  it('shows error message when error prop is provided', () => {
    render(<Input label="Email" error="Invalid email" id="email" />);
    const input = screen.getByLabelText('Email');
    const error = screen.getByRole('alert');
    expect(input).toBeInTheDocument();
    expect(error).toHaveTextContent('Invalid email');
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });

  it('does not show error message when no error', () => {
    render(<Input label="Email" id="email" />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('applies correct border color when has error', () => {
    render(<Input error="Required" id="test" />);
    const input = screen.getByRole('textbox');
    expect(input).toHaveClass('border-[var(--color-error)]');
  });

  it('applies default border color when no error', () => {
    render(<Input id="test" />);
    const input = screen.getByRole('textbox');
    expect(input).toHaveClass('border-[var(--color-hairline)]');
  });

  it('handles focus state', () => {
    render(<Input id="test" />);
    const input = screen.getByRole('textbox');
    fireEvent.focus(input);
    expect(input).toHaveClass('focus:ring-2');
    expect(input).toHaveClass('focus:ring-[var(--color-ink)]');
  });

  it('is disabled when disabled prop is true', () => {
    render(<Input disabled id="test" />);
    const input = screen.getByRole('textbox');
    expect(input).toBeDisabled();
  });
});