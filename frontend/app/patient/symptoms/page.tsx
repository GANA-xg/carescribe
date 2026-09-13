'use client';

import { useState } from 'react';
import AuthenticatedShell from '../../../components/shared/AuthenticatedShell';
import { Badge, Button, Card } from '../../../components/ui';
import { api } from '../../../lib/api';
import type { PossibleCondition } from '../../../lib/types';

const MAX_SYMPTOMS = 10;

type Severity = 'low' | 'medium' | 'high';

const SEVERITY_VARIANT: Record<Severity, 'success' | 'warning' | 'danger'> = {
  low: 'success',
  medium: 'warning',
  high: 'danger',
};

function severityLabel(s: string): Severity {
  if (s === 'medium' || s === 'high') return s;
  return 'low';
}

export default function SymptomsPage() {
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    possible_conditions: PossibleCondition[];
    severity: string;
    see_doctor: boolean;
  } | null>(null);

  const addSymptom = () => {
    const value = draft.trim();
    if (!value) return;
    if (symptoms.length >= MAX_SYMPTOMS) return;
    if (symptoms.some((s) => s.toLowerCase() === value.toLowerCase())) {
      setDraft('');
      return;
    }
    setSymptoms((prev) => [...prev, value]);
    setDraft('');
  };

  const removeSymptom = (symptom: string) => {
    setSymptoms((prev) => prev.filter((s) => s !== symptom));
  };

  const check = async () => {
    setChecking(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.symptoms.check(symptoms);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : 'Symptom check failed.');
    } finally {
      setChecking(false);
    }
  };

  return (
    <AuthenticatedShell>
      <h1 className="text-[22px] font-bold text-[var(--color-ink)] mt-8">Symptom Checker</h1>
      <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
        Add up to {MAX_SYMPTOMS} symptoms, then check possible conditions.
      </p>

      <Card padding="md" className="mt-[var(--space-base)]">
        <div className="flex flex-wrap gap-[var(--space-sm)] mb-[var(--space-sm)]">
          {symptoms.map((symptom) => (
            <span
              key={symptom}
              className="inline-flex items-center gap-[var(--space-xxs)] rounded-full bg-[var(--color-surface-strong)] px-[12px] py-[6px] text-body-sm text-[var(--color-ink)]"
            >
              {symptom}
              <button
                onClick={() => removeSymptom(symptom)}
                aria-label={`Remove ${symptom}`}
                className="text-[var(--color-muted)] hover:text-[var(--color-error)]"
              >
                ×
              </button>
            </span>
          ))}
          {symptoms.length === 0 && (
            <p className="text-body-sm text-[var(--color-muted)]">No symptoms added yet.</p>
          )}
        </div>

        <label htmlFor="symptom-input" className="sr-only">
          Type a symptom and press Enter
        </label>
        <input
          id="symptom-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addSymptom();
            }
          }}
          placeholder="Type a symptom and press Enter…"
          disabled={symptoms.length >= MAX_SYMPTOMS}
          className="w-full h-[48px] rounded-[var(--rounded-sm)] border border-[var(--color-hairline)] bg-white px-[var(--space-base)] text-body-md text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ink)] disabled:opacity-40"
        />
        {symptoms.length >= MAX_SYMPTOMS && (
          <p className="text-caption-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
            Maximum {MAX_SYMPTOMS} symptoms reached.
          </p>
        )}
      </Card>

      <div className="mt-[var(--space-lg)]">
        <Button
          aria-label="Check symptoms"
          loading={checking}
          disabled={symptoms.length === 0}
          onClick={check}
        >
          Check Symptoms
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
        <section aria-label="Possible conditions" className="mt-6">
          <h2 className="text-title-md text-[var(--color-ink)] mb-[var(--space-sm)]">
            Possible conditions
          </h2>
          <div className="flex flex-col gap-[var(--space-sm)]">
            {result.possible_conditions.map((condition) => (
              <Card key={condition.name} padding="md">
                <div className="flex items-center justify-between gap-[var(--space-base)]">
                  <p className="text-title-sm text-[var(--color-ink)]">{condition.name}</p>
                  <Badge variant={SEVERITY_VARIANT[severityLabel(result.severity)]}>
                    {severityLabel(result.severity) === 'low'
                      ? 'Low'
                      : severityLabel(result.severity) === 'medium'
                        ? 'Medium'
                        : 'High'}
                    {' '}severity
                  </Badge>
                </div>
              </Card>
            ))}
          </div>
          {result.see_doctor && (
            <Card padding="md" className="mt-[var(--space-sm)]">
              <p className="text-body-sm text-[var(--color-ink)]">
                Based on these symptoms, we recommend seeing a doctor soon.
              </p>
            </Card>
          )}
        </section>
      )}

      <p className="text-[13px] text-[var(--color-muted)] mt-[var(--space-lg)]">
        ⚠️ Please consult a qualified doctor before taking any action.
      </p>
    </AuthenticatedShell>
  );
}
