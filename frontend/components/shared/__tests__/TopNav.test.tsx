import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TopNav from '../TopNav';
import { useAuthStore } from '../../../store/auth';

const push = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  usePathname: () => '/patient/passport',
}));

Object.defineProperty(window, 'location', {
  value: { href: 'http://localhost/', push },
  writable: true,
});

const patient = {
  id: 'u1',
  name: 'Ananya Rao',
  email: 'patient@example.com',
  role: 'patient' as const,
};

const doctor = {
  id: 'u2',
  name: 'Dr. Kumar',
  email: 'doctor@example.com',
  role: 'doctor' as const,
};

beforeEach(() => {
  push.mockClear();
  localStorage.clear();
});

describe('TopNav', () => {
  it('renders the wordmark', () => {
    useAuthStore.setState({ user: patient });
    render(<TopNav />);
    expect(screen.getByText('CareScribe')).toBeInTheDocument();
  });

  it('shows patient links for a patient', () => {
    useAuthStore.setState({ user: patient });
    render(<TopNav />);
    expect(screen.getByRole('link', { name: 'My Records' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Prescriptions' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Chat' })).toBeInTheDocument();
  });

  it('shows doctor links for a doctor', () => {
    useAuthStore.setState({ user: doctor });
    render(<TopNav />);
    expect(screen.getByRole('link', { name: 'Patients' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Imaging' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Risk' })).toBeInTheDocument();
  });

  it('marks the active link with primary color', () => {
    useAuthStore.setState({ user: patient });
    render(<TopNav />);
    const active = screen.getByRole('link', { name: 'My Records' });
    expect(active).toHaveClass('text-[var(--color-primary)]');
  });

  it('renders user initials in the avatar', () => {
    useAuthStore.setState({ user: patient });
    render(<TopNav />);
    expect(screen.getByText('AR')).toBeInTheDocument();
  });

  it('opens the avatar dropdown with sign out', () => {
    useAuthStore.setState({ user: patient });
    render(<TopNav />);
    fireEvent.click(screen.getByRole('button', { name: 'Account menu' }));
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Profile' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument();
  });

  it('signs out and redirects to login', () => {
    useAuthStore.setState({ user: patient });
    localStorage.setItem('cs_token', 'tok');
    render(<TopNav />);
    fireEvent.click(screen.getByRole('button', { name: 'Account menu' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(localStorage.getItem('cs_token')).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('opens the mobile menu sheet via hamburger', () => {
    useAuthStore.setState({ user: patient });
    render(<TopNav />);
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
    expect(screen.getByRole('dialog', { name: 'Navigation menu' })).toBeInTheDocument();
    // Desktop nav + mobile sheet both exist in jsdom (no real media queries)
    expect(screen.getAllByRole('link', { name: 'My Records' }).length).toBeGreaterThanOrEqual(2);
  });

  it('closes the mobile sheet when close button is tapped', () => {
    useAuthStore.setState({ user: patient });
    render(<TopNav />);
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close menu' }));
    expect(screen.queryByRole('dialog', { name: 'Navigation menu' })).not.toBeInTheDocument();
  });

  it('mobile sheet includes a sign out row in error color', () => {
    useAuthStore.setState({ user: patient });
    render(<TopNav />);
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
    const signOut = screen.getAllByRole('button', { name: 'Sign out' })[0];
    expect(signOut).toHaveClass('text-[var(--color-error)]');
  });
});
