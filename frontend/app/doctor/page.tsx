'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import AuthenticatedShell from '../../components/shared/AuthenticatedShell';
import { Button, Card } from '../../components/ui';
import { api } from '../../lib/api';
import { useAuthStore } from '../../store/auth';
import type { DoctorPatient } from '../../lib/types';

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

function lastVisitLabel(iso: string | null): string {
  if (!iso) return 'No visits yet';
  const d = new Date(iso);
  return `Last visit: ${d.toLocaleDateString()}`;
}

function PatientRow({ patient }: { patient: DoctorPatient }) {
  return (
    <Card padding="md" className="flex items-center gap-[var(--space-base)]">
      <div
        className="flex h-11 w-11 flex-none items-center justify-center rounded-full bg-[var(--color-surface-strong)] text-caption font-semibold text-[var(--color-ink)]"
        aria-hidden="true"
      >
        {initials(patient.name)}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-title-sm text-[var(--color-ink)]">{patient.name}</p>
        <p className="truncate text-body-sm text-[var(--color-muted)]">
          {lastVisitLabel(patient.last_visit)}
        </p>
      </div>
      <div className="hidden min-[744px]:flex gap-[var(--space-sm)]">
        <Link href={`/patient/passport?pid=${patient.id}`} aria-label={`View records for ${patient.name}`}>
          <Button size="sm" variant="secondary">
            View Records
          </Button>
        </Link>
        <Link href={`/doctor/imaging/${patient.id}`} aria-label={`Open imaging for ${patient.name}`}>
          <Button size="sm" variant="secondary">
            Imaging
          </Button>
        </Link>
        <Link href={`/doctor/sepsis/${patient.id}`} aria-label={`Open risk tools for ${patient.name}`}>
          <Button size="sm" variant="secondary">
            Risk
          </Button>
        </Link>
      </div>
    </Card>
  );
}

function PatientSkeleton() {
  return (
    <Card padding="md" className="flex items-center gap-[var(--space-base)]">
      <div className="skeleton h-11 w-11 rounded-full flex-none" />
      <div className="flex-1">
        <div className="skeleton h-4 w-1/3 mb-[var(--space-sm)]" />
        <div className="skeleton h-3 w-1/4" />
      </div>
    </Card>
  );
}

function DoctorBody() {
  const user = useAuthStore((s) => s.user)!;
  const [query, setQuery] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['doctor-patients'],
    queryFn: () => api.doctor.listPatients(),
  });

  const filtered = useMemo(() => {
    const patients = data?.patients ?? [];
    if (!query.trim()) return patients;
    const q = query.trim().toLowerCase();
    return patients.filter(
      (p) => p.name.toLowerCase().includes(q) || p.email.toLowerCase().includes(q)
    );
  }, [data, query]);

  return (
    <>
      <h1 className="text-[28px] font-bold text-[var(--color-ink)] mt-8">
        Good to see you, {user.name.split(/\s+/)[0]}.
      </h1>
      <p className="text-body-md text-[var(--color-muted)] mt-[var(--space-xxs)]">
        {data ? `${data.patients.length} patients under your care.` : 'Loading patients…'}
      </p>

      <div className="mt-6">
        <label htmlFor="patient-search" className="sr-only">
          Search patients by name or email
        </label>
        <div className="relative">
          <Search
            className="absolute left-[var(--space-base)] top-1/2 -translate-y-1/2 h-5 w-5 text-[var(--color-muted)]"
            aria-hidden="true"
          />
          <input
            id="patient-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search patients by name or email…"
            className="w-full h-[52px] rounded-full shadow-card border border-[var(--color-hairline)] bg-white pl-[48px] pr-[var(--space-base)] text-body-md text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ink)]"
          />
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-[var(--space-sm)]" role="list" aria-label="Patient list">
        {isLoading ? (
          <>
            <PatientSkeleton />
            <PatientSkeleton />
            <PatientSkeleton />
          </>
        ) : error ? (
          <Card padding="lg" className="text-center">
            <p className="text-body-md text-[var(--color-error)]" role="alert">
              Couldn&apos;t load the patient list. Please refresh.
            </p>
          </Card>
        ) : filtered.length === 0 ? (
          <Card padding="lg" className="text-center">
            <p className="text-body-md text-[var(--color-muted)]">No patients match your search.</p>
          </Card>
        ) : (
          filtered.map((p) => <PatientRow key={p.id} patient={p} />)
        )}
      </div>
    </>
  );
}

export default function DoctorDashboardPage() {
  return (
    <AuthenticatedShell>
      <DoctorBody />
    </AuthenticatedShell>
  );
}
