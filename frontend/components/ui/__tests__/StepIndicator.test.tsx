import { render, screen } from '@testing-library/react';
import { StepIndicator } from '../StepIndicator';

describe('StepIndicator', () => {
  it('renders all steps', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={0} />);
    expect(screen.getByText('Upload')).toBeInTheDocument();
    expect(screen.getByText('Process')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
  });

  it('renders one dot per step', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={0} />);
    const circles = document.querySelectorAll('[data-testid="step-circle"]');
    expect(circles.length).toBe(3);
  });

  it('marks current step dot as active with primary color', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={1} />);
    const circles = document.querySelectorAll('[data-testid="step-circle"]');
    expect(circles[1]).toHaveClass('bg-[var(--color-primary)]');
  });

  it('marks previous steps as completed with primary color', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={2} />);
    const circles = document.querySelectorAll('[data-testid="step-circle"]');
    expect(circles[0]).toHaveClass('bg-[var(--color-primary)]');
    expect(circles[1]).toHaveClass('bg-[var(--color-primary)]');
    expect(circles[2]).toHaveClass('bg-[var(--color-primary)]');
  });

  it('marks future steps as inactive with hairline color', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={0} />);
    const circles = document.querySelectorAll('[data-testid="step-circle"]');
    expect(circles[1]).toHaveClass('bg-[var(--color-hairline)]');
    expect(circles[2]).toHaveClass('bg-[var(--color-hairline)]');
  });

  it('renders connectors between dots', () => {
    render(<StepIndicator steps={['A', 'B', 'C']} current={0} />);
    const connectors = document.querySelectorAll('[data-testid="step-connector"]');
    expect(connectors.length).toBe(2);
  });

  it('styles active step label with ink color and medium weight', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={1} />);
    const activeLabel = screen.getByText('Process');
    expect(activeLabel).toHaveClass('text-[var(--color-ink)]');
    expect(activeLabel).toHaveClass('font-medium');
  });

  it('marks active step with aria-current', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={0} />);
    expect(screen.getByText('Upload')).toHaveAttribute('aria-current', 'step');
  });

  it('exposes overall step status via aria-label', () => {
    render(<StepIndicator steps={['Capture', 'Processing', 'Review']} current={1} />);
    expect(screen.getByLabelText('Step 2 of 3: Processing')).toBeInTheDocument();
  });
});
