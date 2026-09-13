import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PatientDashboard from '../page';
import { useAuthStore } from '../../../store/auth';

function renderDashboard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PatientDashboard />
    </QueryClientProvider>
  );
}

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockImplementation((url: string) =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(typeof body === 'function' ? body(url) : body),
    } as Response)
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}

const patient = {
  id: 'p1',
  name: 'Ananya Rao',
  email: 'patient@example.com',
  role: 'patient' as const,
};

const passportBody = {
  records: [
    {
      id: 'r1',
      type: 'prescription',
      data: { drugs: ['Paracetamol', 'Amoxicillin'], diagnosis: 'Fever', date: '2026-09-01' },
      source: 'ocr',
      created_at: '2026-09-01T10:00:00Z',
    },
    {
      id: 'r2',
      type: 'diagnosis',
      data: { diagnosis: 'Hypertension' },
      source: 'manual',
      created_at: '2026-08-20T10:00:00Z',
    },
  ],
  fhir_resources: [],
  summary: { total: 2, last_updated: '2026-09-01T10:00:00Z', conditions: ['Fever'], medications: ['Paracetamol'] },
};

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: patient, hydrated: true });
});

describe('patient dashboard', () => {
  it('greets the user by first name', async () => {
    mockFetch(200, passportBody);
    renderDashboard();
    expect(
      await screen.findByText(/Good (morning|afternoon|evening), Ananya 👋/)
    ).toBeInTheDocument();
  });

  it('renders the three action cards', async () => {
    mockFetch(200, passportBody);
    renderDashboard();
    expect(screen.getByText('Upload Prescription')).toBeInTheDocument();
    expect(screen.getByText('Health Passport')).toBeInTheDocument();
    expect(screen.getByText('Chat Assistant')).toBeInTheDocument();
  });

  it('marks the upload card with a primary left accent border', async () => {
    mockFetch(200, passportBody);
    const { container } = renderDashboard();
    const accent = container.querySelector('.border-l-2.border-\\[var\\(--color-primary\\)\\]');
    expect(accent).toBeInTheDocument();
  });

  it('shows exactly one primary (upload) action button', async () => {
    mockFetch(200, passportBody);
    renderDashboard();
    await screen.findByText('Recent Prescriptions');
    const primaryButtons = screen
      .getAllByRole('button')
      .filter((b) => b.className.includes('bg-[var(--color-primary)]'));
    expect(primaryButtons.length).toBe(1);
  });

  it('lists prescription records with drug names and dates', async () => {
    mockFetch(200, passportBody);
    renderDashboard();
    expect(await screen.findByText('Paracetamol, Amoxicillin')).toBeInTheDocument();
    expect(screen.getByText('2026-09-01')).toBeInTheDocument();
  });

  it('links each prescription card to its detail page', async () => {
    mockFetch(200, passportBody);
    renderDashboard();
    const link = await screen.findByRole('link', { name: /Paracetamol, Amoxicillin/ });
    expect(link).toHaveAttribute('href', '/patient/prescriptions/r1');
  });

  it('shows the empty state when there are no prescriptions', async () => {
    mockFetch(200, {
      records: [
        { id: 'r2', type: 'diagnosis', data: { diagnosis: 'Hypertension' }, source: 'manual', created_at: null },
      ],
      fhir_resources: [],
      summary: { total: 1, last_updated: null, conditions: [], medications: [] },
    });
    renderDashboard();
    expect(await screen.findByText('No prescriptions yet')).toBeInTheDocument();
    const emptyLink = screen.getByRole('link', { name: 'Upload your first prescription →' });
    expect(emptyLink).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Upload your first prescription' })
    ).toBeInTheDocument();
  });

  it('shows skeleton cards while loading', async () => {
    let resolvePassport: (v: Response | PromiseLike<Response>) => void = () => {};
    const fn = vi.fn().mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolvePassport = resolve;
        })
    );
    vi.stubGlobal('fetch', fn);
    const { container } = renderDashboard();
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
    resolvePassport({ ok: true, status: 200, json: () => Promise.resolve(passportBody) } as Response);
    await waitFor(() => {
      expect(screen.getByText('Paracetamol, Amoxicillin')).toBeInTheDocument();
    });
  });
});
