'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button, Card, Input } from '../../../components/ui';
import { homeFor, useAuthStore } from '../../../store/auth';
import Link from 'next/link';

const registerSchema = z.object({
  name: z.string().min(1, 'Enter your name'),
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

type RegisterValues = z.infer<typeof registerSchema>;
type Role = 'patient' | 'doctor';

export default function RegisterPage() {
  const registerUser = useAuthStore((s) => s.register);
  const loading = useAuthStore((s) => s.loading);
  const [role, setRole] = useState<Role | null>(null);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register: registerField,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { name: '', email: '', password: '' },
  });

  const onSubmit = async (values: RegisterValues) => {
    if (!role) {
      setRoleError('Choose whether you are a patient or a doctor');
      return;
    }
    setRoleError(null);
    setServerError(null);
    try {
      const user = await registerUser(values.name, values.email, values.password, role);
      window.location.href = homeFor(user);
    } catch (e) {
      setServerError(e instanceof Error && e.message ? e.message : 'Registration failed');
    }
  };

  const roleCard = (value: Role, label: string) => {
    const selected = role === value;
    return (
      <button
        type="button"
        onClick={() => {
          setRole(value);
          setRoleError(null);
        }}
        aria-pressed={selected}
        aria-label={label}
        className={`flex flex-col items-center justify-center gap-[var(--space-xxs)] rounded-[var(--rounded-md)] border-2 bg-white p-[var(--space-base)] text-center transition-colors ${
          selected
            ? 'border-[var(--color-primary)] text-[var(--color-primary)]'
            : 'border-[var(--color-hairline)] text-[var(--color-ink)] hover:border-[var(--color-border-strong)]'
        }`}
      >
        <span className="text-[24px] leading-none" aria-hidden="true">
          {value === 'patient' ? '🧑' : '👨‍⚕️'}
        </span>
        <span className="text-caption">{label}</span>
      </button>
    );
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
              label="Name"
              type="text"
              placeholder="Your full name"
              autoComplete="name"
              error={errors.name?.message}
              {...registerField('name')}
            />
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
              placeholder="At least 8 characters"
              autoComplete="new-password"
              error={errors.password?.message}
              {...registerField('password')}
            />

            <div>
              <p className="text-caption text-[var(--color-ink)] mb-[var(--space-sm)]">I am a…</p>
              <div className="grid grid-cols-2 gap-3">
                {roleCard('patient', "I'm a Patient")}
                {roleCard('doctor', "I'm a Doctor")}
              </div>
              {roleError && (
                <p role="alert" className="text-body-sm text-[var(--color-error)] mt-[var(--space-sm)]">
                  {roleError}
                </p>
              )}
            </div>

            {serverError && (
              <p role="alert" className="text-body-sm text-[var(--color-error)]">
                {serverError}
              </p>
            )}

            <Button
              type="submit"
              loading={loading}
              disabled={!role}
              aria-label="Create account"
              className="w-full"
            >
              Create account
            </Button>
          </form>
        </Card>

        <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-base)]">
          Already have an account?{' '}
          <Link href="/auth/login" className="text-[var(--color-primary)] underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
