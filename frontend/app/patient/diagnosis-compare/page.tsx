'use client';

import { useState } from 'react';
import AuthenticatedShell from '../../../components/shared/AuthenticatedShell';
import { Button, Card } from '../../../components/ui';
import { api } from '../../../lib/api';
import type { DiagnosisCompareResponse } from '../../../lib/types';

type Panel = { date: string; text: string };

const EMPTY: Panel = { date: '', text: '' };

function compareEnabled(a: Panel, b: Panel): boolean {
  return Boolean(a.text.trim() && b.text.trim() && a.date && b.date);
}

export default function DiagnosisComparePage() {
  const [panelA, setPanelA] = useState<Panel>(EMPTY);
  const [panelB, setPanelB] = useState<Panel>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DiagnosisCompareResponse | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.diagnosis.compare({
        diagnosis_a: panelA.text,
        diagnosis_b: panelB.text,
        date_a: panelA.date,
        date_b: panelB.date,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : 'Comparison failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthenticatedShell>
      <h1 className="text-[28px] font-bold text-[var(--color-ink)] mt-8">Compare Diagnoses</h1>
      <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
        Check whether two diagnoses from different visits or doctors agree.
      </p>

      <div className="grid grid-cols-1 gap-4 min-[744px]:grid-cols-2 mt-6">
        {(['A', 'B'] as const).map((side) => {
          const value = side === 'A' ? panelA : panelB;
          const setValue = side === 'A' ? setPanelA : setPanelB;
          return (
            <Card key={side} padding="md">
              <p className="text-title-md text-[var(--color-ink)]">Diagnosis {side}</p>
              <div className="mt-[var(--space-sm)]">
                <label htmlFor={`date-${side}`} className="block text-caption text-[var(--color-ink)] mb-[var(--space-xxs)]">
                  Date
                </label>
                <input
                  id={`date-${side}`}
                  type="date"
                  value={value.date}
                  onChange={(e) => setValue({ ...value, date: e.target.value })}
                  className="w-full h-[56px] rounded-[var(--rounded-sm)] border border-[var(--color-hairline)] bg-white px-[var(--space-base)] text-body-md text-[var(--color-ink)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ink)]"
                />
              </div>
              <div className="mt-[var(--space-sm)]">
                <label htmlFor={`text-${side}`} className="block text-caption text-[var(--color-ink)] mb-[var(--space-xxs)]">
                  Diagnosis text
                </label>
                <textarea
                  id={`text-${side}`}
                  rows={4}
                  value={value.text}
                  onChange={(e) => setValue({ ...value, text: e.target.value })}
                  placeholder="e.g. Acute sinusitis"
                  className="w-full rounded-[var(--rounded-sm)] border border-[var(--color-hairline)] bg-white px-[var(--space-base)] py-[var(--space-sm)] text-body-md text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ink)]"
                />
              </div>
            </Card>
          );
        })}
      </div>

      <div className="mt-[var(--space-lg)]">
        <Button
          aria-label="Compare diagnoses"
          loading={loading}
          disabled={!compareEnabled(panelA, panelB)}
          onClick={run}
        >
          Compare Diagnoses
        </Button>
      </div>

      {error && (
        <Card padding="md" className="mt-[var(--space-base)]">
          <p role="alert" className="text-body-sm text-[var(--color-error)]">
            {error}
          </p>
        </Card>
      )}

      {result && (
        <Card padding="lg" className="mt-6">
          <div className="flex items-center gap-[var(--space-base)]">
            {result.agreement ? (
              <span className="text-[48px] leading-none" style={{ color: '#22c55e' }} aria-hidden="true">✓</span>
            ) : (
              <span className="text-[48px] leading-none text-[var(--color-primary)]" aria-hidden="true">✗</span>
            )}
            <p className="text-[20px] font-bold text-[var(--color-ink)]">
              {result.agreement ? 'Diagnoses agree' : 'Conflict detected'}
            </p>
          </div>

          {result.icd_codes.length > 0 && (
            <div className="mt-[var(--space-lg)]">
              <p className="text-title-md text-[var(--color-ink)] mb-[var(--space-sm)]">ICD codes</p>
              <div className="flex flex-wrap gap-[var(--space-base)]">
                {result.icd_codes.map((code) => (
                  <div
                    key={code}
                    className="rounded-[var(--rounded-sm)] bg-[var(--color-surface-soft)] px-[var(--space-base)] py-[var(--space-sm)]"
                  >
                    <p className="text-badge font-semibold text-[var(--color-ink)]">{code}</p>
                    <p className="text-caption-sm text-[var(--color-muted)]">ICD-10</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-body-md text-[var(--color-body)] mt-[var(--space-lg)]">
            {result.explanation}
          </p>
        </Card>
      )}
    </AuthenticatedShell>
  );
}
