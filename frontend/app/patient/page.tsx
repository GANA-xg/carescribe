'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import AuthenticatedShell from '../../components/shared/AuthenticatedShell';
import { Button, Card } from '../../components/ui';
import { api } from '../../lib/api';
import { useAuthStore } from '../../store/auth';
import type { HealthRecord } from '../../lib/types';
import { patientIdOf } from '../../lib/types';

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'morning';
  if (h < 17) return 'afternoon';
  return 'evening';
}

function RxCard({ record }: { record: HealthRecord }) {
  const data = (record.data ?? {}) as {
    drugs?: string[];
    diagnosis?: string;
    date?: string;
  };
  const drugLine = (data.drugs ?? []).join(', ');
  const when =
    data.date ??
    (record.created_at ? new Date(record.created_at).toLocaleDateString() : '');
  return (
    <Link href={`/patient/prescriptions/${record.id}`} className="block" aria-label={`Prescription: ${drugLine || 'view details'}`}>
      <Card padding="md" className="h-full">
        <p className="text-title-sm text-[var(--color-ink)] truncate">{drugLine || 'Prescription'}</p>
        {data.diagnosis && (
          <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)] truncate">{data.diagnosis}</p>
        )}
        <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-sm)]">{when}</p>
      </Card>
    </Link>
  );
}

function RxSkeleton() {
  return (
    <Card padding="md">
      <div className="skeleton h-4 w-3/4 mb-[var(--space-sm)]" />
      <div className="skeleton h-3 w-1/2 mb-[var(--space-sm)]" />
      <div className="skeleton h-3 w-1/3" />
    </Card>
  );
}

function DashboardBody() {
  const user = useAuthStore((s) => s.user)!;
  const [prescriptionRecords, setPrescriptionRecords] = useState<HealthRecord[] | null>(null);

  const passport = useQuery({
    queryKey: ['passport', patientIdOf(user)],
    queryFn: () => api.passport.get(patientIdOf(user)),
  });

  // Dashboard shows prescriptions; type=prescription records from the passport.
  const prescriptions = useMemo<HealthRecord[]>(() => {
    if (prescriptionRecords !== null) return prescriptionRecords;
    return (passport.data?.records ?? []).filter((r) => r.type === 'prescription');
  }, [passport.data, prescriptionRecords]);

  const loading = passport.isLoading;
  const firstName = user.name.split(/\s+/)[0];

  return (
    <>
      <h1 className="text-[28px] font-bold text-[var(--color-ink)] mt-8">
        Good {greeting()}, {firstName} 👋
      </h1>

      <div className="grid grid-cols-1 gap-4 min-[744px]:grid-cols-3 mt-6">
        {/* Upload — the one primary action on this screen */}
        <div className="border-l-2 border-[var(--color-primary)]">
          <Card padding="lg" className="h-full">
            <span className="text-[24px] leading-none" aria-hidden="true">📷</span>
            <h2 className="text-title-md text-[var(--color-ink)] mt-[var(--space-sm)]">
              Upload Prescription
            </h2>
            <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
              Snap a photo — we read it for you.
            </p>
            <div className="mt-[var(--space-lg)]">
              <Link href="/patient/upload" className="block">
                <Button aria-label="Upload prescription">Upload prescription</Button>
              </Link>
            </div>
          </Card>
        </div>

        <Card padding="lg" className="h-full">
          <span className="text-[24px] leading-none" aria-hidden="true">📋</span>
          <h2 className="text-title-md text-[var(--color-ink)] mt-[var(--space-sm)]">
            Health Passport
          </h2>
          <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
            {passport.data
              ? `${passport.data.summary.total} record${passport.data.summary.total === 1 ? '' : 's'}`
              : 'All your records in one place.'}
          </p>
          <div className="mt-[var(--space-lg)]">
            <Link href="/patient/passport" className="block">
              <Button variant="secondary" aria-label="Open health passport">
                Open passport
              </Button>
            </Link>
          </div>
        </Card>

        <Card padding="lg" className="h-full">
          <span className="text-[24px] leading-none" aria-hidden="true">💬</span>
          <h2 className="text-title-md text-[var(--color-ink)] mt-[var(--space-sm)]">
            Chat Assistant
          </h2>
          <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
            Ask anything about your health records.
          </p>
          <div className="mt-[var(--space-lg)]">
            <Link href="/patient/chat" className="block">
              <Button variant="secondary" aria-label="Open chat assistant">
                Start chatting
              </Button>
            </Link>
          </div>
        </Card>
      </div>

      <section aria-labelledby="recent-rx-heading" className="mt-10">
        <h2 id="recent-rx-heading" className="text-[20px] font-bold text-[var(--color-ink)]">
          Recent Prescriptions
        </h2>

        {loading ? (
          <div className="grid grid-cols-1 gap-3 min-[744px]:grid-cols-3 mt-[var(--space-base)]">
            <RxSkeleton />
            <RxSkeleton />
            <RxSkeleton />
          </div>
        ) : prescriptions.length === 0 ? (
          <div className="flex flex-col items-center gap-[var(--space-sm)] py-[var(--space-xl)]">
            <span className="text-[48px] leading-none" aria-hidden="true">💊</span>
            <p className="text-body-md text-[var(--color-muted)]">No prescriptions yet</p>
            <Link href="/patient/upload">
              <Button aria-label="Upload your first prescription">
                Upload your first prescription →
              </Button>
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 min-[744px]:grid-cols-3 mt-[var(--space-base)]">
            {prescriptions.slice(0, 3).map((record) => (
              <RxCard key={record.id} record={record} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

export default function PatientDashboardPage() {
  return (
    <AuthenticatedShell>
      <DashboardBody />
    </AuthenticatedShell>
  );
}
