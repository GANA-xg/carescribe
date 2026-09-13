'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight } from 'lucide-react';
import AuthenticatedShell from '../../../components/shared/AuthenticatedShell';
import { Badge, Card } from '../../../components/ui';
import { api } from '../../../lib/api';
import { useAuthStore } from '../../../store/auth';
import type { HealthRecord } from '../../../lib/types';
import { patientIdOf } from '../../../lib/types';

type Tab = 'all' | 'prescription' | 'imaging' | 'lab';

const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'prescription', label: 'Prescriptions' },
  { key: 'imaging', label: 'Imaging' },
  { key: 'lab', label: 'Labs' },
];

const RECORD_ICONS: Record<string, string> = {
  prescription: '💊',
  imaging: '🩻',
  lab: '🧪',
  sepsis_score: '🩺',
  diagnosis: '🏥',
};

function iconFor(type: string): string {
  return RECORD_ICONS[type] ?? '🏥';
}

function typeLabel(type: string): string {
  return type.charAt(0).toUpperCase().replace('_', ' ') + type.slice(1).replace('_', ' ');
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function RecordDetail({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <dl className="flex flex-col gap-[var(--space-base)]">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="text-caption-sm text-[var(--color-muted)]">
            {key.replace(/_/g, ' ')}
          </dt>
          <dd className="text-body-sm text-[var(--color-ink)] mt-[var(--space-xxs)] break-words whitespace-pre-wrap">
            {typeof value === 'object' && value !== null
              ? JSON.stringify(value, null, 2)
              : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function PassportBody() {
  const user = useAuthStore((s) => s.user)!;
  const params = useSearchParams();
  const doctorViewing = params.get('pid');
  const patientId = doctorViewing ?? patientIdOf(user);

  const [tab, setTab] = useState<Tab>('all');
  const [selected, setSelected] = useState<HealthRecord | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['passport', patientId],
    queryFn: () => api.passport.get(patientId),
  });

  useEffect(() => {
    setSelected(null);
  }, [patientId]);

  const records = useMemo(() => {
    const all = data?.records ?? [];
    if (tab === 'all') return all;
    return all.filter((r) => r.type === tab || (tab === 'lab' && r.type === 'lab_result'));
  }, [data, tab]);

  return (
    <>
      <div className="flex items-baseline justify-between mt-8 flex-wrap gap-[var(--space-sm)]">
        <h1 className="text-[28px] font-bold text-[var(--color-ink)]">Health Passport</h1>
        {data && (
          <Badge>{data.summary.total} records</Badge>
        )}
      </div>
      {doctorViewing && (
        <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
          Viewing a patient&apos;s passport as a doctor.
        </p>
      )}

      {/* Filter tabs */}
      <div
        className="flex gap-[var(--space-lg)] mt-[var(--space-base)] border-b border-[var(--color-hairline)] overflow-x-auto"
        role="tablist"
        aria-label="Filter records"
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`pb-[var(--space-sm)] text-nav whitespace-nowrap ${
              tab === t.key
                ? 'text-[var(--color-primary)] border-b-2 border-[var(--color-primary)]'
                : 'text-[var(--color-ink)]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="mt-[var(--space-base)] flex flex-col gap-[var(--space-sm)]" role="list" aria-label="Health records">
        {isLoading ? (
          <>
            <Card padding="md" className="flex items-center gap-[var(--space-base)]">
              <div className="skeleton h-6 w-6 rounded-full" />
              <div className="flex-1">
                <div className="skeleton h-4 w-1/3 mb-[var(--space-xs)]" />
                <div className="skeleton h-3 w-1/5" />
              </div>
            </Card>
            <Card padding="md" className="flex items-center gap-[var(--space-base)]">
              <div className="skeleton h-6 w-6 rounded-full" />
              <div className="flex-1">
                <div className="skeleton h-4 w-1/4 mb-[var(--space-xs)]" />
                <div className="skeleton h-3 w-1/6" />
              </div>
            </Card>
          </>
        ) : error ? (
          <Card padding="lg" className="text-center">
            <p className="text-body-md text-[var(--color-error)]" role="alert">
              Couldn&apos;t load your passport. Please refresh.
            </p>
          </Card>
        ) : records.length === 0 ? (
          <Card padding="lg" className="text-center">
            <p className="text-body-md text-[var(--color-muted)]">No records in this view yet.</p>
          </Card>
        ) : (
          records.map((record) => (
            <Card
              key={record.id}
              padding="md"
              className="flex items-center gap-[var(--space-base)] cursor-pointer"
              onClick={() => setSelected(record)}
              role="listitem"
            >
              <span className="text-[24px] leading-none" aria-hidden="true">
                {iconFor(record.type)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-title-sm text-[var(--color-ink)]">{typeLabel(record.type)}</p>
                <p className="text-body-sm text-[var(--color-muted)]">
                  {formatDate(record.created_at)}
                </p>
              </div>
              <ChevronRight
                className="h-5 w-5 text-[var(--color-muted)] flex-none"
                aria-hidden="true"
              />
            </Card>
          ))
        )}
      </div>

      {/* Slide-in detail panel */}
      {selected && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-[var(--color-scrim)]"
            onClick={() => setSelected(null)}
            aria-hidden="true"
          />
          <aside
            className="absolute right-0 top-0 h-full w-full min-[744px]:w-96 bg-white shadow-card p-[var(--space-lg)] overflow-y-auto"
            role="dialog"
            aria-modal="true"
            aria-label={`${typeLabel(selected.type)} record details`}
          >
            <div className="flex items-center justify-between mb-[var(--space-base)]">
              <div className="flex items-center gap-[var(--space-sm)]">
                <span className="text-[24px]" aria-hidden="true">{iconFor(selected.type)}</span>
                <h2 className="text-display-sm text-[var(--color-ink)]">{typeLabel(selected.type)}</h2>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-body-sm text-[var(--color-muted)] hover:text-[var(--color-ink)]"
                aria-label="Close record details"
              >
                ✕
              </button>
            </div>
            <p className="text-body-sm text-[var(--color-muted)] mb-[var(--space-lg)]">
              {formatDate(selected.created_at)} · via {selected.source === 'ocr' ? 'OCR upload' : 'manual entry'}
            </p>
            <RecordDetail data={selected.data} />
          </aside>
        </div>
      )}
    </>
  );
}

export default function PassportPage() {
  return (
    <AuthenticatedShell>
      <Suspense fallback={null}>
        <PassportBody />
      </Suspense>
    </AuthenticatedShell>
  );
}
