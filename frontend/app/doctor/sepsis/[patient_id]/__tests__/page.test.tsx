import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SepsisPage from '../page';
import { useAuthStore } from '../../../../../store/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/doctor/sepsis',
}));

const doctor = {
  id: 'd1',
  name: 'Meera Kumar',
  email: 'doctor@example.com',
  role: 'doctor' as const,
};

const sepsisBody = {
  risk_score: 73,
  risk_level: 'high',
  shap_explanation: [
    { feature: 'temp', value: 0.4 },
    { feature: 'hr', value: 0.25 },
    { feature: 'rr', value: -0.1 },
    { feature: 'wbc', value: 0.15 },
    { feature: 'lactate', value: 0.5 },
  ],
  trend: [
    { date: '2026-09-10', score: 40 },
    { date: '2026-09-11', score: 55 },
    { date: '2026-09-12', score: 73 },
  ],
  explanation: 'Lactate and temperature are the dominant risk drivers.',
  record_id: null,
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
  useAuthStore.setState({ user: doctor, hydrated: true });
});

function fillVitals() {
  const fields: [string, string][] = [
    ['Temperature', '38.5'],
    ['Heart Rate', '110'],
    ['Resp. Rate', '24'],
    ['WBC Count', '14'],
    ['Lactate Level', '3.2'],
  ];
  for (const [label, value] of fields) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
}

describe('sepsis risk screen', () => {
  it('renders five vitals fields with units', () => {
    render(<SepsisPage params={{ patient_id: 'p1' }} />);
    expect(screen.getByLabelText('Temperature')).toBeInTheDocument();
    expect(screen.getByText('°C')).toBeInTheDocument();
    expect(screen.getByLabelText('Heart Rate')).toBeInTheDocument();
    expect(screen.getByText('bpm')).toBeInTheDocument();
    expect(screen.getByLabelText('Resp. Rate')).toBeInTheDocument();
    expect(screen.getByText('breaths/min')).toBeInTheDocument();
    expect(screen.getByLabelText('WBC Count')).toBeInTheDocument();
    expect(screen.getByText('×10³/µL')).toBeInTheDocument();
    expect(screen.getByLabelText('Lactate Level')).toBeInTheDocument();
    expect(screen.getByText('mmol/L')).toBeInTheDocument();
  });

  it('disables Calculate until all fields are filled', () => {
    render(<SepsisPage params={{ patient_id: 'p1' }} />);
    expect(screen.getByRole('button', { name: 'Calculate risk' })).toBeDisabled();
    fillVitals();
    expect(screen.getByRole('button', { name: 'Calculate risk' })).toBeEnabled();
  });

  it('shows the big risk score, level badge and SHAP section', async () => {
    mockFetch(200, sepsisBody);
    render(<SepsisPage params={{ patient_id: 'p1' }} />);
    fillVitals();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate risk' }));

    expect(await screen.findByText('73')).toBeInTheDocument();
    expect(screen.getByText('High risk')).toBeInTheDocument();
    expect(screen.getByText("What's driving this score")).toBeInTheDocument();
    expect(screen.getByText('Risk trend')).toBeInTheDocument();
    expect(
      screen.getByText('Lactate and temperature are the dominant risk drivers.')
    ).toBeInTheDocument();
  });

  it('sends vitals + patient_id in the request body', async () => {
    const fn = mockFetch(200, sepsisBody);
    render(<SepsisPage params={{ patient_id: 'p1' }} />);
    fillVitals();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate risk' }));
    await screen.findByText('73');
    const body = JSON.parse(fn.mock.calls[0][1].body as string);
    expect(body).toEqual({
      patient_id: 'p1',
      vitals: { temp: 38.5, hr: 110, rr: 24, wbc: 14, lactate: 3.2 },
    });
  });

  it('shows an inline error when the model fails', async () => {
    mockFetch(502, { detail: 'Sepsis model unavailable: timeout' });
    render(<SepsisPage params={{ patient_id: 'p1' }} />);
    fillVitals();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate risk' }));
    expect(await screen.findByText(/Sepsis model unavailable/)).toBeInTheDocument();
  });

  it('omits the trend section when there is only one reading', async () => {
    mockFetch(200, { ...sepsisBody, trend: [] });
    render(<SepsisPage params={{ patient_id: 'p1' }} />);
    fillVitals();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate risk' }));
    await screen.findByText('73');
    expect(screen.queryByText('Risk trend')).not.toBeInTheDocument();
  });
});
