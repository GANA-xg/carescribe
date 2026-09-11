import { render, screen } from '@testing-library/react';
import { StepIndicator } from '../StepIndicator';

describe('StepIndicator', () => {
  it('renders all steps', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={0} />);
    expect(screen.getByText('Upload')).toBeInTheDocument();
    expect(screen.getByText('Process')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
  });

  it('marks current step as active', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={1} />);
    const activeStep = screen.getByText('Process');
    expect(activeStep).toHaveClass('text-[var(--color-ink)]');
    expect(activeStep).toHaveClass('font-medium');
  });

  it('marks previous steps as completed', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={2} />);
    // Upload should be completed (first step)
    const completedCircle = document.querySelectorAll('.bg-[var(--color-primary)]');
    expect(completedCircle.length).toBeGreaterThan(0);
  });

  it('marks future steps as inactive', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={0} />);
    // Process and Review should be inactive
    const inactiveCircle = document.querySelector('.bg-[var(--color-surface-soft)]');
    expect(inactiveCircle).toBeInTheDocument();
  });

  it('displays correct step numbers', () => {
    render(<StepIndicator steps={['Upload', 'Process', 'Review']} current={0} />);
    // Should show 1 for completed/active steps
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('renders in a row layout', () => {
    const { container } = render(<StepIndicator steps={['A', 'B']} current={0} />);
    const indicator = container.firstChild;
    expect(indicator).toHaveClass('flex');
    expect(indicator).toHaveClass('items-center');
    expect(indicator).toHaveClass('justify-between');
  });
});