'use client';

import { Suspense, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import AuthenticatedShell from '../../../components/shared/AuthenticatedShell';
import { Badge, Button, Card } from '../../../components/ui';
import { api } from '../../../lib/api';
import type { DrugComparison } from '../../../lib/types';

function rupees(value: number | undefined): string {
  if (value === undefined || value === null) return '—';
  return `₹${value % 1 === 0 ? value.toFixed(0) : value.toFixed(2)}`;
}

function DrugRow({
  drug,
  selected,
  onToggle,
}: {
  drug: DrugComparison;
  selected: boolean;
  onToggle: () => void;
}) {
  if (!drug.found) {
    return (
      <Card padding="md">
        <div className="flex items-center justify-between gap-[var(--space-base)]">
          <div>
            <p className="text-title-sm text-[var(--color-ink)]">{drug.name}</p>
            <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
              No generic alternative found for this name.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card padding="md">
      <div className="flex flex-col gap-[var(--space-sm)] min-[744px]:flex-row min-[744px]:items-center min-[744px]:justify-between">
        <div className="min-w-0">
          <div className="flex items-baseline gap-[var(--space-sm)]">
            <p className="text-title-sm text-[var(--color-ink)] truncate">{drug.brand_name}</p>
            <span className="text-body-sm text-[var(--color-muted)]">{rupees(drug.brand_price)}</span>
          </div>
          <div className="flex items-baseline gap-[var(--space-sm)] mt-[var(--space-xxs)]">
            <p className="text-body-sm text-[var(--color-ink)] truncate">
              {drug.generic_name}
            </p>
            <span className="text-body-sm text-[var(--color-muted)]">
              {rupees(drug.generic_price)}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-[var(--space-base)]">
          {drug.saving !== undefined && drug.saving > 0 && (
            <Badge variant="primary">Save {rupees(drug.saving)}</Badge>
          )}
          <Button
            size="sm"
            variant={selected ? 'primary' : 'secondary'}
            aria-label={selected ? `Remove ${drug.name} from order` : `Add ${drug.name} to order`}
            onClick={onToggle}
          >
            {selected ? 'Remove' : 'Add to order'}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function DrugsBody() {
  const params = useSearchParams();
  const drugParam = params.get('drugs') ?? '';
  const drugNames = useMemo(
    () =>
      drugParam
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    [drugParam]
  );

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [ordered, setOrdered] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['drug-compare', drugNames],
    queryFn: () => api.drugs.compare(drugNames),
    enabled: drugNames.length > 0,
  });

  const drugs = data?.drugs ?? [];
  const selectedDrugs = drugs.filter((d) => selected.has(d.name));
  const totalSavings = selectedDrugs.reduce((sum, d) => sum + (d.saving ?? 0), 0);

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  if (drugNames.length === 0) {
    return (
      <>
        <h1 className="text-[22px] font-bold text-[var(--color-ink)] mt-8">Generic Alternatives</h1>
        <Card padding="lg" className="mt-6 text-center">
          <p className="text-body-md text-[var(--color-muted)]">
            No drugs selected. Save a prescription first — then compare its prices here.
          </p>
        </Card>
      </>
    );
  }

  return (
    <>
      <h1 className="text-[22px] font-bold text-[var(--color-ink)] mt-8">Generic Alternatives</h1>

      {isLoading ? (
        <div className="flex flex-col gap-[var(--space-sm)] mt-6">
          <Card padding="md">
            <div className="skeleton h-4 w-1/3 mb-[var(--space-sm)]" />
            <div className="skeleton h-3 w-1/4" />
          </Card>
          <Card padding="md">
            <div className="skeleton h-4 w-1/3 mb-[var(--space-sm)]" />
            <div className="skeleton h-3 w-1/4" />
          </Card>
        </div>
      ) : error ? (
        <Card padding="lg" className="mt-6 text-center">
          <p className="text-body-md text-[var(--color-error)]" role="alert">
            Couldn&apos;t load prices. Please refresh.
          </p>
        </Card>
      ) : (
        <div className="flex flex-col gap-[var(--space-sm)] mt-6">
          {drugs.map((drug) => (
            <DrugRow
              key={drug.name}
              drug={drug}
              selected={selected.has(drug.name)}
              onToggle={() => toggle(drug.name)}
            />
          ))}
        </div>
      )}

      {/* Order summary */}
      {drugs.length > 0 && !ordered && (
        <div className="fixed bottom-0 left-0 right-0 bg-[var(--color-canvas)] border-t border-[var(--color-hairline)] p-[var(--space-base)] shadow-card min-[744px]:static min-[744px]:border-0 min-[744px]:mt-6 min-[744px]:p-0">
          <div className="flex items-center justify-between gap-[var(--space-base)] min-[744px]:max-w-[480px]">
            <p className="text-body-sm text-[var(--color-ink)]">
              {selected.size} generic{selected.size === 1 ? '' : 's'} selected ·{' '}
              <span className="font-semibold">Total savings: {rupees(totalSavings)}</span>
            </p>
            <Button
              aria-label="Confirm order"
              disabled={selected.size === 0}
              onClick={() => setOrdered(true)}
            >
              Confirm Order
            </Button>
          </div>
        </div>
      )}

      {ordered && (
        <Card padding="lg" className="mt-6 text-center" role="status">
          <p className="text-body-md text-[var(--color-ink)]">
            Your order has been placed ✓
          </p>
          <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
            You saved {rupees(totalSavings)} by choosing generics.
          </p>
        </Card>
      )}
    </>
  );
}

export default function DrugsPage() {
  return (
    <AuthenticatedShell>
      <Suspense fallback={null}>
        <DrugsBody />
      </Suspense>
    </AuthenticatedShell>
  );
}
