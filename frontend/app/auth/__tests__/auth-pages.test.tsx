import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from '../login/page';
import RegisterPage from '../register/page';

const push = vi.fn();
vi.stubGlobal('scrollTo', () => {});
Object.defineProperty(window, 'location', {
  value: { href: 'http://localhost/', push },
  writable: true,
});

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
  mockFetch(200, { id: 'u1', name: 'Pat', email: 'p@x.com', role: 'patient' });
});

describe('login page', () => {
  it('renders the brand and copy', () => {
    render(<LoginPage />);
    expect(screen.getByText('CareScribe')).toBeInTheDocument();
    expect(screen.getByText('Your health, in your hands.')).toBeInTheDocument();
  });

  it('renders email + password fields with labels', () => {
    render(<LoginPage />);
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });

  it('shows inline validation errors on bad submit', async () => {
    render(<LoginPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => {
      expect(screen.getByText('Enter a valid email address')).toBeInTheDocument();
      expect(
        screen.getByText('Password must be at least 8 characters')
      ).toBeInTheDocument();
    });
  });

  it('shows server error message on 401', async () => {
    mockFetch(401, { detail: 'Invalid credentials' });
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'p@x.com' } });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'wrongpassword' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });
  });

  it('signs in and stores the token', async () => {
    mockFetch(200, {
      user: { id: 'u1', name: 'Pat', email: 'p@x.com', role: 'patient' },
      token: 'tok-1',
    });
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'p@x.com' } });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => {
      expect(localStorage.getItem('cs_token')).toBe('tok-1');
    });
  });
});

describe('register page', () => {
  it('renders all fields and the role selector', () => {
    render(<RegisterPage />);
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: "I'm a Patient" })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: "I'm a Doctor" })).toBeInTheDocument();
  });

  it('disables submit until a role is selected', async () => {
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Pat' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'p@x.com' } });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password123' },
    });
    expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled();
  });

  it('enables submit once a role is selected', async () => {
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Pat' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'p@x.com' } });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: "I'm a Patient" }));
    expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled();
  });

  it('allows exactly one selected role at a time', async () => {
    render(<RegisterPage />);
    const patientBtn = screen.getByRole('button', { name: "I'm a Patient" });
    const doctorBtn = screen.getByRole('button', { name: "I'm a Doctor" });
    fireEvent.click(patientBtn);
    expect(patientBtn).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(doctorBtn);
    expect(doctorBtn).toHaveAttribute('aria-pressed', 'true');
    expect(patientBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('registers and stores the token', async () => {
    mockFetch(201, {
      user: { id: 'u1', name: 'Pat', email: 'p@x.com', role: 'patient' },
      token: 'tok-reg',
    });
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Pat' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'p@x.com' } });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: "I'm a Patient" }));
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => {
      expect(localStorage.getItem('cs_token')).toBe('tok-reg');
    });
  });
});
