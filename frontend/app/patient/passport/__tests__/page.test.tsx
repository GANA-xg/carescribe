import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PassportPage from '../page';
import { useAuthStore } from '../../../../store/auth';

vi.mock('next/navigation', () => ({
  usePathname: () => '/patient/passport',
  useSearchParams: () => new URLSearchParams(),
}));

function renderPassport() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PassportPage />
    </QueryClientProvider>
  );
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
      data: { drugs: ['Paracetamol'], diagnosis: 'Fever', date: '2026-09-01' },
      source: 'ocr',
      created_at: '2026-09-01T10:00:00Z',
    },
    {
      id: 'r2',
      type: 'lab',
      data: { hemoglobin: '13.5 g/dL' },
      source: 'manual',
      created_at: '2026-08-20T10:00:00Z',
    },
    {
      id: 'r3',
      type: 'imaging',
      data: { modality: 'MRI', notes: 'No abnormality' },
      source: 'manual',
      created_at: '2026-07-15T10:00:00Z',
    },
  ],
  fhir_resources: [],
  summary: { total: 3, last_updated: '2026-09-01T10:00:00Z', conditions: ['Fever'], medications: ['Paracetamol'] },
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

describe('health passport', () => {
  it('renders the title and record count', async () => {
    mockFetch(200, passportBody);
    renderPassport();
    expect(await screen.findByText('Health Passport')).toBeInTheDocument();
    const badge = await screen.findByText(
      (_, element) => element?.textContent === '3 records' && element.tagName === 'SPAN'
    );
    expect(badge).toBeInTheDocument();
  });

  it('renders the filter tabs', async () => {
    mockFetch(200, passportBody);
    renderPassport();
    expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Prescriptions' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Imaging' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Labs' })).toBeInTheDocument();
  });

  it('lists all records by default', async () => {
    mockFetch(200, passportBody);
    renderPassport();
    expect(await screen.findAllByRole('listitem')).toHaveLength(3);
  });

  it('filters to prescriptions only', async () => {
    mockFetch(200, passportBody);
    renderPassport();
    await screen.findAllByRole('listitem');
    fireEvent.click(screen.getByRole('tab', { name: 'Prescriptions' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('filters to labs only', async () => {
    mockFetch(200, passportBody);
    renderPassport();
    await screen.findAllByRole('listitem');
    fireEvent.click(screen.getByRole('tab', { name: 'Labs' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('opens the slide-in detail panel on record tap', async () => {
    mockFetch(200, passportBody);
    renderPassport();
    const items = await screen.findAllByRole('listitem');
    fireEvent.click(items[0]);
    expect(
      screen.getByRole('dialog', { name: /Prescription record details/i })
    ).toBeInTheDocument();
    expect(screen.getByText('drugs')).toBeInTheDocument();
  });

  it('closes the panel via the close button', async () => {
    mockFetch(200, passportBody);
    renderPassport();
    const items = await screen.findAllByRole('listitem');
    fireEvent.click(items[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Close record details' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes the panel when the backdrop is tapped', async () => {
    mockFetch(200, passportBody);
    const { container } = renderPassport();
    const items = await screen.findAllByRole('listitem');
    fireEvent.click(items[0]);
    const backdrop = container.querySelector('.bg-\\[var\\(--color-scrim\\)\\]');
    fireEvent.click(backdrop as HTMLElement);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows an empty state when a filter has no records', async () => {
    mockFetch(200, {
      records: [],
      fhir_resources: [],
      summary: { total: 0, last_updated: null, conditions: [], medications: [] },
    });
    renderPassport();
    expect(await screen.findByText('No records in this view yet.')).toBeInTheDocument();
  });
});
