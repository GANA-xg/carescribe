// CL-16 accessibility audit — axe-core on every route's rendered markup.
// Screens are rendered with seeded auth + mocked API data so the full
// component tree (including record lists) is audited, not just shells.

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from '../store/auth';

import LoginPage from '../app/auth/login/page';
import RegisterPage from '../app/auth/register/page';
import PatientDashboard from '../app/patient/page';
import UploadPage from '../app/patient/upload/page';
import PassportPage from '../app/patient/passport/page';
import SymptomsPage from '../app/patient/symptoms/page';
import DrugsPage from '../app/patient/drugs/page';
import ChatPage from '../app/patient/chat/page';
import DiagnosisComparePage from '../app/patient/diagnosis-compare/page';
import DoctorDashboard from '../app/doctor/page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/patient',
  useSearchParams: () => new URLSearchParams('drugs=Paracetamol'),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const patient = {
  id: 'p1',
  name: 'Ananya Rao',
  email: 'patient@example.com',
  role: 'patient' as const,
};

const passportBody = {
  records: [
    { id: 'r1', type: 'prescription', data: { drugs: ['Paracetamol'] }, source: 'ocr', created_at: '2026-09-01T10:00:00Z' },
  ],
  fhir_resources: [],
  summary: { total: 1, last_updated: null, conditions: [], medications: [] },
};

const patientsBody = {
  patients: [{ id: 'p1', name: 'Ananya Rao', email: 'a@x.com', last_visit: null }],
};

function mockApi(body: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const key = url.includes('/passport')
        ? 'passport'
        : url.includes('/patients')
          ? 'patients'
          : url.includes('/drugs/compare')
            ? 'drugs'
            : 'default';
      const payload = body[key] ?? {};
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) } as Response);
    })
  );
}

function withClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

async function expectClean(html: string, name: string) {
  const results = await axe(html);
  const serious = results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious' || v.impact === 'moderate'
  );
  if (serious.length > 0) {
    const summary = serious.map((v) => `${v.id} (${v.impact}): ${v.help}`).join('; ');
    throw new Error(`${name} — accessibility violations: ${summary}`);
  }
  expect(true).toBe(true);
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: patient, hydrated: true });
  mockApi({
    passport: passportBody,
    patients: patientsBody,
    drugs: { drugs: [{ name: 'Paracetamol', found: true, brand_name: 'Crocin', brand_price: 30, generic_name: 'Paracetamol', generic_price: 5, saving: 25 }] },
    default: { reply: 'ok', sources: [], citations: [] },
  });
});

describe('accessibility audit', () => {
  it('login page has no serious axe violations', async () => {
    const { container } = render(<LoginPage />);
    await expectClean(container.innerHTML, 'login');
  });

  it('register page has no serious axe violations', async () => {
    const { container } = render(<RegisterPage />);
    await expectClean(container.innerHTML, 'register');
  });

  it('patient dashboard has no serious axe violations', async () => {
    const { container } = render(withClient(<PatientDashboard />));
    await waitFor(() => screen.getByText('Recent Prescriptions'));
    await expectClean(container.innerHTML, 'patient dashboard');
  });

  it('upload page has no serious axe violations', async () => {
    const { container } = render(withClient(<UploadPage />));
    await expectClean(container.innerHTML, 'upload');
  });

  it('passport page has no serious axe violations', async () => {
    const { container } = render(withClient(<PassportPage />));
    await waitFor(() => screen.getByRole('tab', { name: 'All' }));
    await expectClean(container.innerHTML, 'passport');
  });

  it('symptoms page has no serious axe violations', async () => {
    const { container } = render(<SymptomsPage />);
    await expectClean(container.innerHTML, 'symptoms');
  });

  it('drugs page has no serious axe violations', async () => {
    const { container } = render(withClient(<DrugsPage />));
    await waitFor(() => screen.getByText('Crocin'));
    await expectClean(container.innerHTML, 'drugs');
  });

  it('chat page has no serious axe violations', async () => {
    const { container } = render(<ChatPage />);
    await expectClean(container.innerHTML, 'chat');
  });

  it('diagnosis compare page has no serious axe violations', async () => {
    const { container } = render(<DiagnosisComparePage />);
    await expectClean(container.innerHTML, 'diagnosis compare');
  });

  it('doctor dashboard (as patient role is fine for markup audit) has no serious axe violations', async () => {
    const { container } = render(withClient(<DoctorDashboard />));
    await waitFor(() => screen.getByRole('searchbox'));
    await expectClean(container.innerHTML, 'doctor dashboard');
  });
});
