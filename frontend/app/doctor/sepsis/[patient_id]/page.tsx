'use client';

import { useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import AuthenticatedShell from '../../../../components/shared/AuthenticatedShell';
import { Badge, Button, Card, Input } from '../../../../components/ui';
import { api } from '../../../../lib/api';
import type { SepsisRiskResponse, ShapItem } from '../../../../lib/types';

type VitalsForm = {
  temp: string;
  hr: string;
  rr: string;
  wbc: string;
  lactate: string;
};

const EMPTY_VITALS: VitalsForm = { temp: '', hr: '', rr: '', wbc: '', lactate: '' };

const FIELDS: { key: keyof VitalsForm; label: string; unit: string }[] = [
  { key: 'temp', label: 'Temperature', unit: '°C' },
  { key: 'hr', label: 'Heart Rate', unit: 'bpm' },
  { key: 'rr', label: 'Resp. Rate', unit: 'breaths/min' },
  { key: 'wbc', label: 'WBC Count', unit: '×10³/µL' },
  { key: 'lactate', label: 'Lactate Level', unit: 'mmol/L' },
];

const FEATURE_LABELS: Record<string, string> = {
  temp: 'Temp',
  hr: 'HR',
  rr: 'RR',
  wbc: 'WBC',
  lactate: 'Lactate',
};

const RISK_VARIANT = { low: 'success', medium: 'warning', high: 'danger' } as const;

type ShapBar = ShapItem & { color: string; label: string };

function SepsisBody({ patientId }: { patientId: string }) {
  const [vitals, setVitals] = useState<VitalsForm>(EMPTY_VITALS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SepsisRiskResponse | null>(null);

  const setField = (key: keyof VitalsForm, value: string) =>
    setVitals((prev) => ({ ...prev, [key]: value }));

  const filled = FIELDS.every((f) => vitals[f.key].trim() !== '' && !isNaN(Number(vitals[f.key])));

  const calculate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.clinical.sepsisRisk(patientId, {
        temp: Number(vitals.temp),
        hr: Number(vitals.hr),
        rr: Number(vitals.rr),
        wbc: Number(vitals.wbc),
        lactate: Number(vitals.lactate),
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : 'Risk calculation failed.');
    } finally {
      setLoading(false);
    }
  };

  const shapData: ShapBar[] =
    result?.shap_explanation.map((item) => ({
      ...item,
      color: item.value >= 0 ? 'var(--color-primary)' : '#22c55e',
      label: FEATURE_LABELS[item.feature] ?? item.feature,
    })) ?? [];

  const trendData =
    result?.trend?.map((t) => ({ date: t.date, score: t.score })) ?? [];

  return (
    <>
      <h1 className="text-[28px] font-bold text-[var(--color-ink)] mt-8">Sepsis Risk</h1>
      <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
        Enter the latest vitals to score this patient.
      </p>

      <Card padding="lg" className="mt-[var(--space-base)]">
        <div className="grid grid-cols-1 gap-[var(--space-base)] min-[744px]:grid-cols-2">
          {FIELDS.map((field) => (
            <div key={field.key} className="flex items-end gap-[var(--space-sm)]">
              <div className="flex-1">
                <Input
                  label={field.label}
                  type="number"
                  inputMode="decimal"
                  value={vitals[field.key]}
                  onChange={(e) => setField(field.key, e.target.value)}
                  placeholder="0"
                />
              </div>
              <span className="text-caption-sm text-[var(--color-muted)] pb-[var(--space-base)] whitespace-nowrap">
                {field.unit}
              </span>
            </div>
          ))}
        </div>

        {error && (
          <p role="alert" className="text-body-sm text-[var(--color-error)] mt-[var(--space-base)]">
            {error}
          </p>
        )}

        <div className="mt-[var(--space-lg)]">
          <Button
            aria-label="Calculate risk"
            loading={loading}
            disabled={!filled}
            onClick={calculate}
          >
            Calculate Risk
          </Button>
        </div>
      </Card>

      {result && (
        <Card padding="lg" className="mt-6">
          <div className="flex items-center gap-[var(--space-base)] flex-wrap">
            <p className="text-[64px] font-bold leading-none text-[var(--color-ink)]">
              {Math.round(result.risk_score)}
            </p>
            <Badge variant={RISK_VARIANT[result.risk_level as keyof typeof RISK_VARIANT] ?? 'success'}>
              {result.risk_level.charAt(0).toUpperCase() + result.risk_level.slice(1)} risk
            </Badge>
          </div>

          {shapData.length > 0 && (
            <div className="mt-6">
              <h2 className="text-title-md text-[var(--color-ink)] mb-[var(--space-sm)]">
                What&apos;s driving this score
              </h2>
              <div style={{ width: '100%', height: 200 }}>
                <ResponsiveContainer>
                  <BarChart data={shapData} layout="vertical" margin={{ left: 16, right: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hairline)" />
                    <XAxis type="number" stroke="var(--color-muted)" fontSize={12} />
                    <YAxis
                      type="category"
                      dataKey="label"
                      stroke="var(--color-muted)"
                      fontSize={12}
                      width={64}
                    />
                    <Tooltip
                      formatter={(value) => [String(value), 'Impact']}
                      labelFormatter={(label) => `Vital: ${label}`}
                    />
                    <ReferenceLine x={0} stroke="var(--color-border-strong)" />
                    <Bar dataKey="value" radius={[4, 4, 4, 4]} isAnimationActive={false}>
                      {shapData.map((entry) => (
                        <Cell key={entry.feature} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="text-caption-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
                Red bars push risk up · green bars push risk down (protective).
              </p>
            </div>
          )}

          {trendData.length > 1 && (
            <div className="mt-6">
              <h2 className="text-title-md text-[var(--color-ink)] mb-[var(--space-sm)]">
                Risk trend
              </h2>
              <div style={{ width: '100%', height: 200 }}>
                <ResponsiveContainer>
                  <LineChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hairline)" />
                    <XAxis dataKey="date" stroke="var(--color-muted)" fontSize={12} />
                    <YAxis stroke="var(--color-muted)" fontSize={12} domain={[0, 100]} />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="score"
                      stroke="var(--color-primary)"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {result.explanation && (
            <p className="text-body-sm text-[var(--color-body)] mt-[var(--space-lg)]">
              {result.explanation}
            </p>
          )}
        </Card>
      )}
    </>
  );
}

export default function SepsisPage({
  params,
}: {
  params: { patient_id: string };
}) {
  return (
    <AuthenticatedShell>
      <SepsisBody patientId={params.patient_id} />
    </AuthenticatedShell>
  );
}
