import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DoctorDashboard from '../page';
import { useAuthStore } from '../../../store/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/doctor',
}));

function renderDoctor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DoctorDashboard />
    </QueryClientProvider>
  );
}

const doctor = {
  id: 'd1',
  name: 'Meera Kumar',
  email: 'doctor@example.com',
  role: 'doctor' as const,
};

const patientsBody = {
  patients: [
    { id: 'p1', name: 'Ananya Rao', email: 'ananya@example.com', last_visit: '2026-09-01T10:00:00Z' },
    { id: 'p2', name: 'Ravi Shah', email: 'ravi@example.com', last_visit: null },
  ],
  generated_at: '2026-09-12T00:00:00Z',
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

describe('doctor dashboard', () => {
  it('greets the doctor', async () => {
    mockFetch(200, patientsBody);
    renderDoctor();
    expect(await screen.findByText('Good to see you, Meera.')).toBeInTheDocument();
  });

  it('shows patient count', async () => {
    mockFetch(200, patientsBody);
    renderDoctor();
    expect(await screen.findByText('2 patients under your care.')).toBeInTheDocument();
  });

  it('renders the search bar', async () => {
    mockFetch(200, patientsBody);
    renderDoctor();
    expect(
      screen.getByRole('searchbox', { name: 'Search patients by name or email' })
    ).toBeInTheDocument();
  });

  it('lists patients with initials, name and last visit', async () => {
    mockFetch(200, patientsBody);
    renderDoctor();
    expect(await screen.findByText('Ananya Rao')).toBeInTheDocument();
    expect(screen.getByText('Ravi Shah')).toBeInTheDocument();
    expect(screen.getByText(/Last visit:/)).toBeInTheDocument();
    expect(screen.getByText('No visits yet')).toBeInTheDocument();
    expect(screen.getByText('AR')).toBeInTheDocument();
    expect(screen.getByText('RS')).toBeInTheDocument();
  });

  it('filters patients as you type', async () => {
    mockFetch(200, patientsBody);
    renderDoctor();
    await screen.findByText('Ananya Rao');
    const search = screen.getByRole('searchbox');
    fireEvent.change(search, { target: { value: 'ravi' } });
    expect(screen.queryByText('Ananya Rao')).not.toBeInTheDocument();
    expect(screen.getByText('Ravi Shah')).toBeInTheDocument();
  });

  it('shows the empty result state when nothing matches', async () => {
    mockFetch(200, patientsBody);
    renderDoctor();
    await screen.findByText('Ananya Rao');
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } });
    expect(screen.getByText('No patients match your search.')).toBeInTheDocument();
  });

  it('shows action links per patient row', async () => {
    mockFetch(200, patientsBody);
    renderDoctor();
    await screen.findByText('Ananya Rao');
    expect(
      screen.getByRole('link', { name: 'View records for Ananya Rao' })
    ).toHaveAttribute('href', '/patient/passport?pid=p1');
    expect(
      screen.getByRole('link', { name: 'Open imaging for Ananya Rao' })
    ).toHaveAttribute('href', '/doctor/imaging/p1');
  });

  it('shows an error card when the API fails', async () => {
    mockFetch(500, { detail: 'boom' });
    renderDoctor();
    expect(await screen.findByText("Couldn't load the patient list. Please refresh.")).toBeInTheDocument();
  });

  it('shows skeleton rows while loading', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => new Promise<Response>(() => {}))
    );
    const { container } = renderDoctor();
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThanOrEqual(3);
  });
});
