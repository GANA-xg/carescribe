import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '../auth';

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
  vi.stubGlobal('fetch', fn);
  return fn;
}

const userBody = { id: 'u1', name: 'Pat', email: 'p@x.com', role: 'patient' };

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: null, hydrated: false, loading: false, error: null });
});

describe('auth store', () => {
  it('hydrates to null user when no token stored', async () => {
    await useAuthStore.getState().hydrate();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().hydrated).toBe(true);
  });

  it('hydrates user from /auth/me when token exists', async () => {
    localStorage.setItem('cs_token', 'tok');
    mockFetch(200, userBody);
    await useAuthStore.getState().hydrate();
    expect(useAuthStore.getState().user?.id).toBe('u1');
  });

  it('stores token + user on login', async () => {
    mockFetch(200, { user: userBody, token: 'tok-1' });
    const user = await useAuthStore.getState().login('p@x.com', 'password123');
    expect(user.role).toBe('patient');
    expect(localStorage.getItem('cs_token')).toBe('tok-1');
    expect(useAuthStore.getState().user?.name).toBe('Pat');
    expect(useAuthStore.getState().error).toBeNull();
  });

  it('sets error message when login fails', async () => {
    mockFetch(401, { detail: 'Invalid credentials' });
    await expect(useAuthStore.getState().login('p@x.com', 'wrongpass1')).rejects.toBeTruthy();
    expect(useAuthStore.getState().error).toBe('Invalid credentials');
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().loading).toBe(false);
  });

  it('stores token + role on register', async () => {
    mockFetch(201, { user: { ...userBody, role: 'doctor' }, token: 'tok-2' });
    const user = await useAuthStore.getState().register('Doc', 'd@x.com', 'password123', 'doctor');
    expect(user.role).toBe('doctor');
    expect(localStorage.getItem('cs_token')).toBe('tok-2');
  });

  it('clears token + user on logout', () => {
    localStorage.setItem('cs_token', 'tok');
    useAuthStore.setState({ user: userBody as never });
    useAuthStore.getState().logout();
    expect(localStorage.getItem('cs_token')).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });
});
