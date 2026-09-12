'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Badge, Button, Card, LoadingSpinner } from '../../../../components/ui';
import AuthenticatedShell from '../../../../components/shared/AuthenticatedShell';
import { api } from '../../../../lib/api';
import type { Study, TumorScanResponse } from '../../../../lib/types';

const OHIF_URL = 'http://localhost:3001';

function formatDate(date: string | null): string {
  if (!date) return '—';
  const iso = date.length === 8 ? `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}` : date;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? date : d.toLocaleDateString();
}

function TumorAiCard() {
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [result, setResult] = useState<TumorScanResponse | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const runAnalysis = async (file: File) => {
    setState('loading');
    setFileName(file.name);
    try {
      const data = await api.imaging.tumorScan(file);
      setResult(data);
      setState('done');
    } catch {
      setState('error');
    }
  };

  return (
    <Card padding="lg" className="flex flex-col gap-[var(--space-sm)]">
      <div className="flex items-center justify-between">
        <h2 className="text-title-md text-[var(--color-ink)]">🧠 Tumor AI</h2>
        <Badge>Reference only</Badge>
      </div>

      <p className="text-caption-sm text-[var(--color-muted)]">
        ⚠️ AI result is for clinical reference only — not a diagnosis.
      </p>

      <p className="text-body-sm text-[var(--color-muted)]">
        Upload the DICOM slice to run the tumor classifier alongside the viewer.
      </p>

      {state === 'idle' && (
        <label>
          <input
            type="file"
            accept=".dcm,application/dicom"
            hidden
            aria-label="DICOM file for AI analysis"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void runAnalysis(f);
            }}
          />
          <span className="inline-flex">
            <Button aria-label="Run AI analysis">Run AI Analysis</Button>
          </span>
        </label>
      )}
      {state === 'loading' && (
        <div className="flex items-center gap-[var(--space-sm)]">
          <LoadingSpinner />
          <span className="text-body-md text-[var(--color-muted)]">
            Analyzing {fileName ?? 'scan'}…
          </span>
        </div>
      )}
      {state === 'error' && (
        <div role="alert" className="flex flex-col gap-[var(--space-sm)]">
          <p className="text-body-sm text-[var(--color-error)]">
            Analysis failed — the model service may be busy.
          </p>
          <label>
            <input
              type="file"
              accept=".dcm,application/dicom"
              hidden
              aria-label="DICOM file for AI analysis retry"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void runAnalysis(f);
              }}
            />
            <span className="inline-flex">
              <Button variant="secondary" aria-label="Try AI analysis again">
                Try again
              </Button>
            </span>
          </label>
        </div>
      )}
      {state === 'done' && result && (
        <div className="flex flex-col gap-[var(--space-sm)]">
          <p className="text-[20px] font-bold text-[var(--color-ink)]">{result.prediction}</p>
          <div>
            <div className="flex justify-between text-caption-sm text-[var(--color-muted)] mb-[var(--space-xxs)]">
              <span>Confidence</span>
              <span>{Math.round(result.confidence * 100)}%</span>
            </div>
            <div
              className="h-2 w-full rounded-full bg-[var(--color-surface-strong)] overflow-hidden"
              role="progressbar"
              aria-valuenow={Math.round(result.confidence * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="AI confidence"
            >
              <div
                className="h-full bg-[var(--color-primary)]"
                style={{ width: `${Math.round(result.confidence * 100)}%` }}
              />
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function ImagingBody({ patientId }: { patientId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['studies', patientId],
    queryFn: () => api.imaging.getStudies(patientId),
  });

  const studies = data?.studies ?? [];
  const [selected, setSelected] = useState<Study | null>(null);

  return (
    <>
      <h1 className="text-[28px] font-bold text-[var(--color-ink)] mt-8">Imaging</h1>
      <p className="text-body-sm text-[var(--color-muted)] mt-[var(--space-xxs)]">
        Studies for this patient. Select one to open it in the OHIF viewer.
      </p>

      {isLoading ? (
        <div className="mt-6 grid grid-cols-1 gap-3 min-[744px]:grid-cols-2">
          <Card padding="md">
            <div className="skeleton h-4 w-1/2 mb-[var(--space-sm)]" />
            <div className="skeleton h-3 w-1/3" />
          </Card>
          <Card padding="md">
            <div className="skeleton h-4 w-1/2 mb-[var(--space-sm)]" />
            <div className="skeleton h-3 w-1/3" />
          </Card>
        </div>
      ) : error ? (
        <Card padding="lg" className="mt-6 text-center">
          <p className="text-body-md text-[var(--color-error)]" role="alert">
            Couldn&apos;t load studies. Please refresh.
          </p>
        </Card>
      ) : studies.length === 0 ? (
        <Card padding="lg" className="mt-6 text-center">
          <p className="text-body-md text-[var(--color-muted)]">
            No imaging studies for this patient yet.
          </p>
        </Card>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-3 min-[744px]:grid-cols-2">
          {studies.map((study) => (
            <Card
              key={study.orthanc_study_id}
              padding="md"
              className={`cursor-pointer ${
                selected?.orthanc_study_id === study.orthanc_study_id
                  ? 'border-2 border-[var(--color-primary)]'
                  : ''
              }`}
              onClick={() => setSelected(study)}
              role="button"
              aria-label={`Open study ${study.description ?? study.study_instance_uid ?? ''}`}
            >
              <div className="flex items-center gap-[var(--space-sm)]">
                <Badge>{study.date ? `Study` : 'Study'}</Badge>
                <span className="text-body-sm text-[var(--color-muted)]">
                  {formatDate(study.date)}
                </span>
              </div>
              <p className="text-title-sm text-[var(--color-ink)] mt-[var(--space-sm)] truncate">
                {study.description ?? 'Unnamed study'}
              </p>
              <p className="text-caption-sm text-[var(--color-muted)] mt-[var(--space-xxs)] truncate">
                {study.series_count ?? 0} series · {study.study_instance_uid ?? 'no UID'}
              </p>
            </Card>
          ))}
        </div>
      )}

      {selected && (
        <div className="mt-8 flex flex-col gap-[var(--space-base)]">
          <TumorAiCard />
          <iframe
            src={`${OHIF_URL}/viewer?StudyInstanceUIDs=${selected.study_instance_uid}`}
            title={`OHIF viewer for ${selected.description ?? 'study'}`}
            width="100%"
            height="600px"
            className="w-full rounded-[var(--rounded-md)] border-0"
            allow="clipboard-write"
          />
        </div>
      )}
    </>
  );
}

export default function ImagingPage({
  params,
}: {
  params: { patient_id: string };
}) {
  const patientId = params.patient_id;
  return (
    <AuthenticatedShell>
      <ImagingBody patientId={patientId} />
    </AuthenticatedShell>
  );
}
