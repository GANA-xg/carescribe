'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button, Card, Input } from '../../../components/ui';
import { homeFor, useAuthStore } from '../../../store/auth';
import Link from 'next/link';

const loginSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

type LoginValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const login = useAuthStore((s) => s.login);
  const loading = useAuthStore((s) => s.loading);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register: registerField,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (values: LoginValues) => {
    setServerError(null);
    try {
      const user = await login(values.email, values.password);
      window.location.href = homeFor(user);
    } catch (e) {
      setServerError(e instanceof Error && e.message ? e.message : 'Sign in failed');
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-[var(--space-base)] bg-[var(--color-canvas)]">
      <div className="w-full max-w-[400px] flex flex-col items-center">
        <h1 className="text-display-md text-[var(--color-ink)]">CareScribe</h1>
        <p className="text-body-md text-[var(--color-muted)] mt-[var(--space-xxs)] mb-[var(--space-lg)]">
          Your health, in your hands.
        </p>

        <Card padding="lg" className="w-full">
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-[var(--space-base)]" noValidate>
            <Input
              label="Email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              error={errors.email?.message}
              {...registerField('email')}
            />
            <Input
              label="Password"
              type="password"
              placeholder="Your password"
              autoComplete="current-password"
              error={errors.password?.message}
              {...registerField('password')}
            />

            {serverError && (
              <p role="alert" className="text-body-sm text-[var(--color-error)]">
                {serverError}
              </p>
            )}

            <Button type="submit" loading={loading} aria-label="Sign in" className="w-full">
              Sign in
            </Button>
          </form>
        </Card>

        <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-base)]">
          Don&apos;t have an account?{' '}
          <Link href="/auth/register" className="text-[var(--color-primary)] underline">
            Register →
          </Link>
        </p>
      </div>
    </main>
  );
}
