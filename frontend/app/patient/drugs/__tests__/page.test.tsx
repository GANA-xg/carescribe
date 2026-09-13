import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DrugsPage from '../page';
import { useAuthStore } from '../../../../store/auth';

vi.mock('next/navigation', () => ({
  usePathname: () => '/patient/drugs',
  useSearchParams: () => new URLSearchParams('drugs=Paracetamol,Amoxicillin'),
}));

function renderDrugs() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DrugsPage />
    </QueryClientProvider>
  );
}

const patient = {
  id: 'p1',
  name: 'Ananya Rao',
  email: 'patient@example.com',
  role: 'patient' as const,
};

const compareBody = {
  drugs: [
    {
      name: 'Paracetamol',
      found: true,
      brand_name: 'Crocin',
      brand_price: 30,
      generic_name: 'Paracetamol',
      generic_price: 5,
      saving: 25,
      saving_pct: 83,
      formulation: 'Tablet',
    },
    {
      name: 'Amoxicillin',
      found: true,
      brand_name: 'Augmentin',
      brand_price: 150,
      generic_name: 'Amoxicillin',
      generic_price: 45,
      saving: 105,
      saving_pct: 70,
      formulation: 'Capsule',
    },
  ],
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

describe('drug comparison page', () => {
  it('renders the title', async () => {
    mockFetch(200, compareBody);
    renderDrugs();
    expect(await screen.findByText('Generic Alternatives')).toBeInTheDocument();
  });

  it('shows brand and generic rows with prices', async () => {
    mockFetch(200, compareBody);
    renderDrugs();
    expect(await screen.findByText('Crocin')).toBeInTheDocument();
    expect(screen.getByText('₹30')).toBeInTheDocument();
    expect(screen.getByText('Augmentin')).toBeInTheDocument();
    expect(screen.getByText('₹150')).toBeInTheDocument();
    expect(screen.getByText('₹5')).toBeInTheDocument();
    expect(screen.getByText('₹45')).toBeInTheDocument();
  });

  it('shows savings badges per drug', async () => {
    mockFetch(200, compareBody);
    renderDrugs();
    expect(await screen.findByText('Save ₹25')).toBeInTheDocument();
    expect(screen.getByText('Save ₹105')).toBeInTheDocument();
  });

  it('starts with zero selected and disabled confirm', async () => {
    mockFetch(200, compareBody);
    renderDrugs();
    expect(await screen.findByText('Crocin'));
    expect(screen.getByText(/0 generics selected/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm order' })).toBeDisabled();
  });

  it('adds a drug to the order and shows total savings', async () => {
    mockFetch(200, compareBody);
    renderDrugs();
    await screen.findByText('Crocin');
    fireEvent.click(screen.getByRole('button', { name: 'Add Paracetamol to order' }));
    expect(screen.getByText(/1 generic selected/)).toBeInTheDocument();
    expect(screen.getByText('Total savings: ₹25')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm order' })).toBeEnabled();
  });

  it('removes a drug from the order', async () => {
    mockFetch(200, compareBody);
    renderDrugs();
    await screen.findByText('Crocin');
    fireEvent.click(screen.getByRole('button', { name: 'Add Paracetamol to order' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove Paracetamol from order' }));
    expect(screen.getByText(/0 generics selected/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm order' })).toBeDisabled();
  });

  it('confirms the order with a success message', async () => {
    mockFetch(200, compareBody);
    renderDrugs();
    await screen.findByText('Crocin');
    fireEvent.click(screen.getByRole('button', { name: 'Add Paracetamol to order' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm order' }));
    expect(await screen.findByText('Your order has been placed ✓')).toBeInTheDocument();
  });

  it('handles unknown drugs gracefully', async () => {
    mockFetch(200, {
      drugs: [{ name: 'Unobtainium', found: false }],
    });
    renderDrugs();
    expect(
      await screen.findByText('No generic alternative found for this name.')
    ).toBeInTheDocument();
  });
});
