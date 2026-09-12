import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SymptomsPage from '../page';
import { useAuthStore } from '../../../../store/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/patient/symptoms',
}));

const patient = {
  id: 'p1',
  name: 'Ananya Rao',
  email: 'patient@example.com',
  role: 'patient' as const,
};

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
  vi.stubGlobal('fetch', fn);
  return fn;
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: patient, hydrated: true });
});

describe('symptom checker', () => {
  it('renders the disclaimer always visible', () => {
    render(<SymptomsPage />);
    expect(
      screen.getByText('⚠️ Please consult a qualified doctor before taking any action.')
    ).toBeInTheDocument();
  });

  it('starts with the check button disabled', () => {
    render(<SymptomsPage />);
    expect(screen.getByRole('button', { name: 'Check symptoms' })).toBeDisabled();
  });

  it('adds a symptom chip on Enter', () => {
    render(<SymptomsPage />);
    const input = screen.getByLabelText('Type a symptom and press Enter');
    fireEvent.change(input, { target: { value: 'fever' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByText('fever')).toBeInTheDocument();
  });

  it('ignores duplicate symptoms', () => {
    render(<SymptomsPage />);
    const input = screen.getByLabelText('Type a symptom and press Enter');
    fireEvent.change(input, { target: { value: 'fever' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.change(input, { target: { value: 'Fever' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getAllByText(/fever/i).length).toBe(1);
  });

  it('removes a symptom chip via ×', () => {
    render(<SymptomsPage />);
    const input = screen.getByLabelText('Type a symptom and press Enter');
    fireEvent.change(input, { target: { value: 'fever' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'Remove fever' }));
    expect(screen.queryByText('fever')).not.toBeInTheDocument();
  });

  it('enables the check button once symptoms exist', () => {
    render(<SymptomsPage />);
    const input = screen.getByLabelText('Type a symptom and press Enter');
    fireEvent.change(input, { target: { value: 'fever' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByRole('button', { name: 'Check symptoms' })).toBeEnabled();
  });

  it('caps at 10 symptoms', () => {
    render(<SymptomsPage />);
    const input = screen.getByLabelText('Type a symptom and press Enter');
    for (let i = 1; i <= 11; i++) {
      fireEvent.change(input, { target: { value: `symptom ${i}` } });
      fireEvent.keyDown(input, { key: 'Enter' });
    }
    expect(screen.getByText(/Maximum 10 symptoms reached/)).toBeInTheDocument();
    expect(input).toBeDisabled();
  });

  it('shows results with severity badges (color + text)', async () => {
    mockFetch(200, {
      possible_conditions: [
        { name: 'Common cold', score: 0.7 },
        { name: 'Viral fever', score: 0.5 },
      ],
      severity: 'high',
      see_doctor: true,
    });
    render(<SymptomsPage />);
    const input = screen.getByLabelText('Type a symptom and press Enter');
    fireEvent.change(input, { target: { value: 'fever' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'Check symptoms' }));

    expect(await screen.findByText('Common cold')).toBeInTheDocument();
    expect(screen.getByText('Viral fever')).toBeInTheDocument();
    const highBadges = screen.getAllByText('High severity');
    expect(highBadges.length).toBe(2);
    expect(highBadges[0]).toHaveClass('bg-[var(--color-primary)]');
    expect(screen.getByText(/recommend seeing a doctor soon/)).toBeInTheDocument();
  });

  it('shows low severity as green with text label', async () => {
    mockFetch(200, {
      possible_conditions: [{ name: 'Mild allergy', score: 0.4 }],
      severity: 'low',
      see_doctor: false,
    });
    render(<SymptomsPage />);
    const input = screen.getByLabelText('Type a symptom and press Enter');
    fireEvent.change(input, { target: { value: 'sneeze' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'Check symptoms' }));
    expect(await screen.findByText('Mild allergy')).toBeInTheDocument();
    const lowBadge = screen.getByText('Low severity');
    expect(lowBadge).toHaveClass('bg-[#22c55e]');
  });

  it('shows inline error when the check fails', async () => {
    mockFetch(502, { detail: 'Symptom model unavailable' });
    render(<SymptomsPage />);
    const input = screen.getByLabelText('Type a symptom and press Enter');
    fireEvent.change(input, { target: { value: 'fever' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'Check symptoms' }));
    expect(await screen.findByText('Symptom model unavailable')).toBeInTheDocument();
  });
});
