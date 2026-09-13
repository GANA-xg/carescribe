// Auth store — token in localStorage, user in memory.
// Persisting only the token keeps PII out of localStorage.

import { create } from 'zustand';
import { api, getToken, setToken } from '../lib/api';
import type { User } from '../lib/types';

type AuthState = {
  user: User | null;
  hydrated: boolean;
  loading: boolean;
  error: string | null;
  hydrate: () => Promise<void>;
  login: (email: string, password: string) => Promise<User>;
  register: (
    name: string,
    email: string,
    password: string,
    role: 'patient' | 'doctor'
  ) => Promise<User>;
  logout: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  hydrated: false,
  loading: false,
  error: null,

  hydrate: async () => {
    if (!getToken()) {
      set({ hydrated: true, user: null });
      return;
    }
    set({ loading: true });
    try {
      const user = await api.auth.me();
      set({ user, hydrated: true, loading: false });
    } catch {
      // 401 handler already cleared the token
      set({ user: null, hydrated: true, loading: false });
    }
  },

  login: async (email, password) => {
    set({ loading: true, error: null });
    try {
      const { user, token } = await api.auth.login({ email, password });
      setToken(token);
      set({ user, loading: false });
      return user;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Sign in failed';
      set({ error: msg, loading: false });
      throw e;
    }
  },

  register: async (name, email, password, role) => {
    set({ loading: true, error: null });
    try {
      const { user, token } = await api.auth.register({ name, email, password, role });
      setToken(token);
      set({ user, loading: false });
      return user;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Registration failed';
      set({ error: msg, loading: false });
      throw e;
    }
  },

  logout: () => {
    setToken(null);
    set({ user: null });
  },
}));

export function homeFor(user: User | null): string {
  if (!user) return '/auth/login';
  return user.role === 'doctor' ? '/doctor' : '/patient';
}
