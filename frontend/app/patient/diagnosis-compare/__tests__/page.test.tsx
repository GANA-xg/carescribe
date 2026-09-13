import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DiagnosisComparePage from '../page';
import { useAuthStore } from '../../../../store/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/patient/diagnosis-compare',
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

function fillAll() {
  fireEvent.change(screen.getByLabelText('Date', { selector: '#date-A' }), {
    target: { value: '2026-09-01' },
  });
  fireEvent.change(screen.getByLabelText('Date', { selector: '#date-B' }), {
    target: { value: '2026-09-10' },
  });
  fireEvent.change(screen.getByLabelText('Diagnosis text', { selector: '#text-A' }), {
    target: { value: 'Acute sinusitis' },
  });
  fireEvent.change(screen.getByLabelText('Diagnosis text', { selector: '#text-B' }), {
    target: { value: 'Bacterial sinusitis' },
  });
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: patient, hydrated: true });
});

describe('diagnosis comparator', () => {
  it('renders two diagnosis panels', () => {
    render(<DiagnosisComparePage />);
    expect(screen.getByText('Diagnosis A')).toBeInTheDocument();
    expect(screen.getByText('Diagnosis B')).toBeInTheDocument();
    expect(screen.getAllByLabelText('Date').length).toBe(2);
    expect(screen.getAllByLabelText('Diagnosis text').length).toBe(2);
  });

  it('disables compare until all four fields are filled', () => {
    render(<DiagnosisComparePage />);
    expect(screen.getByRole('button', { name: 'Compare diagnoses' })).toBeDisabled();
    fillAll();
    expect(screen.getByRole('button', { name: 'Compare diagnoses' })).toBeEnabled();
  });

  it('shows agreement result with green check', async () => {
    mockFetch(200, {
      agreement: true,
      conflict_details: null,
      icd_codes: ['J01.9'],
      explanation: 'Both map to ICD-10 J01.9 — same diagnosis.',
    });
    render(<DiagnosisComparePage />);
    fillAll();
    fireEvent.click(screen.getByRole('button', { name: 'Compare diagnoses' }));
    expect(await screen.findByText('Diagnoses agree')).toBeInTheDocument();
    expect(screen.getByText('J01.9')).toBeInTheDocument();
    expect(screen.getByText('Both map to ICD-10 J01.9 — same diagnosis.')).toBeInTheDocument();
  });

  it('shows conflict result with red cross', async () => {
    mockFetch(200, {
      agreement: false,
      conflict_details: 'Codes differ',
      icd_codes: ['J01.9', 'J02.9'],
      explanation: 'ICD codes differ (J01.9 vs J02.9) and similarity is below threshold.',
    });
    render(<DiagnosisComparePage />);
    fillAll();
    fireEvent.click(screen.getByRole('button', { name: 'Compare diagnoses' }));
    expect(await screen.findByText('Conflict detected')).toBeInTheDocument();
    expect(screen.getByText('J02.9')).toBeInTheDocument();
  });

  it('sends both diagnoses and dates in the request', async () => {
    const fn = mockFetch(200, {
      agreement: true,
      conflict_details: null,
      icd_codes: [],
      explanation: 'ok',
    });
    render(<DiagnosisComparePage />);
    fillAll();
    fireEvent.click(screen.getByRole('button', { name: 'Compare diagnoses' }));
    await screen.findByText('Diagnoses agree');
    const body = JSON.parse(fn.mock.calls[0][1].body as string);
    expect(body).toEqual({
      diagnosis_a: 'Acute sinusitis',
      diagnosis_b: 'Bacterial sinusitis',
      date_a: '2026-09-01',
      date_b: '2026-09-10',
    });
  });

  it('shows an inline error when the API fails', async () => {
    mockFetch(500, { detail: 'Comparator unavailable' });
    render(<DiagnosisComparePage />);
    fillAll();
    fireEvent.click(screen.getByRole('button', { name: 'Compare diagnoses' }));
    expect(await screen.findByText('Comparator unavailable')).toBeInTheDocument();
  });
});
