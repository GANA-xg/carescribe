'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import AuthenticatedShell from '../../../components/shared/AuthenticatedShell';
import { Button, Card, Input, StepIndicator } from '../../../components/ui';
import { api } from '../../../lib/api';
import { useAuthStore } from '../../../store/auth';
import type { OcrResult, StructuredPrescription } from '../../../lib/types';

type Step = 0 | 1 | 2;
type EditedRx = {
  drugs: string[];
  dosage: string;
  frequency: string;
  diagnosis: string;
  date: string;
};

type Reviewed = { edited: EditedRx; rawText: string } | null;

function drugListFromOcr(result: OcrResult): string[] {
  const structured = result.structured ?? {};
  const drugs = structured.drugs ?? [];
  return drugs.filter((d): d is string => typeof d === 'string' && d.trim().length > 0);
}

function UploadFlow() {
  const user = useAuthStore((s) => s.user)!;
  const router = useRouter();

  const [step, setStep] = useState<Step>(0);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState<Reviewed>(null);
  const [newDrug, setNewDrug] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showToast, setShowToast] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const pickFile = (f: File | null) => {
    if (!f) return;
    setOcrError(null);
    setSaveError(null);
    setFile(f);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(f));
  };

  const retake = () => {
    stopPolling();
    setStep(0);
    setFile(null);
    setReviewed(null);
    setOcrError(null);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
  };

  const beginProcessing = async () => {
    if (!file) return;
    setStep(1);
    setOcrError(null);
    try {
      const job = await api.ocr.process(file);
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.ocr.getStatus(job.job_id);
          if (status.status === 'done' && status.result) {
            stopPolling();
            const structured: Partial<StructuredPrescription> = status.result.structured ?? {};
            setReviewed({
              rawText: status.result.raw_text,
              edited: {
                drugs: drugListFromOcr(status.result),
                dosage: (structured as Record<string, unknown>).dosage as string ?? '',
                frequency: (structured as Record<string, unknown>).frequency as string ?? '',
                diagnosis: structured.diagnosis ?? '',
                date: structured.date ?? new Date().toISOString().slice(0, 10),
              },
            });
            setStep(2);
          } else if (status.status === 'failed') {
            stopPolling();
            setOcrError(status.error ?? 'The prescription could not be read.');
          }
        } catch {
          stopPolling();
          setOcrError('The prescription could not be read.');
        }
      }, 2000);
    } catch {
      setOcrError('Upload failed — please try again.');
    }
  };

  const addDrug = () => {
    const value = newDrug.trim();
    if (!value || !reviewed) return;
    if (reviewed.edited.drugs.includes(value)) {
      setNewDrug('');
      return;
    }
    setReviewed({ ...reviewed, edited: { ...reviewed.edited, drugs: [...reviewed.edited.drugs, value] } });
    setNewDrug('');
  };

  const removeDrug = (drug: string) => {
    if (!reviewed) return;
    setReviewed({
      ...reviewed,
      edited: { ...reviewed.edited, drugs: reviewed.edited.drugs.filter((d) => d !== drug) },
    });
  };

  const patchEdited = (patch: Partial<EditedRx>) => {
    if (!reviewed) return;
    setReviewed({ ...reviewed, edited: { ...reviewed.edited, ...patch } });
  };

  const saveToPassport = async () => {
    if (!reviewed) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.passport.addRecord(user.id, {
        type: 'prescription',
        data: {
          drugs: reviewed.edited.drugs,
          dosage: reviewed.edited.dosage,
          frequency: reviewed.edited.frequency,
          diagnosis: reviewed.edited.diagnosis,
          date: reviewed.edited.date,
          raw_text: reviewed.rawText,
        },
        source: 'ocr',
      });
      setShowToast(true);
      setTimeout(() => router.push('/patient/passport'), 1200);
    } catch (e) {
      setSaving(false);
      setSaveError(e instanceof Error && e.message ? e.message : 'Could not save.');
    }
  };

  return (
    <>
      <div className="mt-8">
        <StepIndicator steps={['Capture', 'Processing', 'Review']} current={step} />
      </div>

      {/* Step 1 — Capture */}
      {step === 0 && (
        <section aria-label="Capture prescription" className="mt-8">
          {!previewUrl ? (
            <div
              className="w-full min-h-64 rounded-[var(--rounded-md)] border-2 border-dashed border-[var(--color-hairline)] bg-[var(--color-surface-soft)] flex flex-col items-center justify-center gap-[var(--space-xxs)] p-[var(--space-lg)] text-center"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                pickFile(e.dataTransfer.files?.[0] ?? null);
              }}
            >
              <span className="text-[48px] leading-none" aria-hidden="true">📷</span>
              <p className="text-body-md text-[var(--color-muted)]">Drag prescription here</p>
              <p className="text-body-sm text-[var(--color-muted)]">or</p>
              <label className="mt-[var(--space-xxs)]">
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  hidden
                  onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                  aria-label="Prescription photo"
                />
                <span className="inline-flex">
                  <Button variant="secondary" aria-label="Take photo">
                    Take Photo
                  </Button>
                </span>
              </label>
            </div>
          ) : (
            <div className="flex flex-col gap-[var(--space-base)]">
              <Image
                src={previewUrl}
                alt="Prescription preview"
                width={0}
                height={0}
                sizes="100vw"
                unoptimized
                className="w-full rounded-[var(--rounded-md)] object-contain max-h-80 bg-[var(--color-surface-soft)]"
              />
              <div className="flex gap-[var(--space-base)]">
                <Button aria-label="Use this photo" onClick={beginProcessing}>
                  Use this photo
                </Button>
                <Button variant="secondary" aria-label="Retake photo" onClick={retake}>
                  Retake
                </Button>
              </div>
            </div>
          )}
        </section>
      )}

      {/* Step 2 — Processing */}
      {step === 1 && (
        <section aria-label="Processing prescription" className="mt-8">
          <Card padding="lg" className="flex flex-col items-center gap-[var(--space-base)] text-center">
            <div
              className="h-6 w-6 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin"
              role="status"
              aria-label="Reading prescription"
            />
            <p className="text-body-md text-[var(--color-muted)]">Reading your prescription…</p>
            {ocrError && (
              <div role="alert" className="flex flex-col items-center gap-[var(--space-sm)]">
                <p className="text-body-md text-[var(--color-error)]">Couldn&apos;t read this prescription.</p>
                <Button variant="secondary" aria-label="Try again" onClick={retake}>
                  Try again
                </Button>
              </div>
            )}
          </Card>
        </section>
      )}

      {/* Step 3 — Review */}
      {step === 2 && reviewed && (
        <section aria-label="Review prescription" className="mt-8 flex flex-col gap-[var(--space-base)]">
          <Card padding="lg" className="flex flex-col gap-[var(--space-base)]">
            <div>
              <p className="text-caption text-[var(--color-ink)] mb-[var(--space-sm)]">Drugs</p>
              <div className="flex flex-wrap gap-[var(--space-sm)]">
                {reviewed.edited.drugs.map((drug) => (
                  <span
                    key={drug}
                    className="inline-flex items-center gap-[var(--space-xxs)] rounded-full bg-[var(--color-surface-strong)] px-[var(--space-base)] py-[var(--space-xxs)] text-body-sm text-[var(--color-ink)]"
                  >
                    {drug}
                    <button
                      onClick={() => removeDrug(drug)}
                      aria-label={`Remove ${drug}`}
                      className="text-[var(--color-muted)] hover:text-[var(--color-error)]"
                    >
                      ×
                    </button>
                  </span>
                ))}
                {reviewed.edited.drugs.length === 0 && (
                  <p className="text-body-sm text-[var(--color-muted)]">No drugs detected — add below.</p>
                )}
              </div>
              <div className="flex gap-[var(--space-sm)] mt-[var(--space-sm)]">
                <div className="flex-1">
                  <Input
                    label="Add a drug"
                    placeholder="Drug name"
                    value={newDrug}
                    onChange={(e) => setNewDrug(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addDrug();
                      }
                    }}
                  />
                </div>
                <Button
                  variant="tertiary"
                  aria-label="Add drug"
                  onClick={addDrug}
                  disabled={!newDrug.trim()}
                  className="self-end"
                >
                  + Add drug
                </Button>
              </div>
            </div>

            <Input
              label="Dosage"
              value={reviewed.edited.dosage}
              onChange={(e) => patchEdited({ dosage: e.target.value })}
              placeholder="e.g. 500mg"
            />
            <Input
              label="Frequency"
              value={reviewed.edited.frequency}
              onChange={(e) => patchEdited({ frequency: e.target.value })}
              placeholder="e.g. twice a day"
            />
            <Input
              label="Diagnosis"
              value={reviewed.edited.diagnosis}
              onChange={(e) => patchEdited({ diagnosis: e.target.value })}
              placeholder="e.g. Fever"
            />

            {saveError && (
              <p role="alert" className="text-body-sm text-[var(--color-error)]">
                {saveError}
              </p>
            )}

            <div className="flex gap-[var(--space-base)]">
              <Button
                aria-label="Save to Health Passport"
                loading={saving}
                disabled={reviewed.edited.drugs.length === 0}
                onClick={saveToPassport}
              >
                Save to Health Passport
              </Button>
              <Button variant="secondary" aria-label="Retake photo" onClick={retake}>
                Retake
              </Button>
            </div>
          </Card>
        </section>
      )}

      {/* Success toast */}
      {showToast && (
        <div
          role="status"
          className="fixed bottom-[var(--space-lg)] left-1/2 -translate-x-1/2 rounded-[var(--rounded-md)] bg-[var(--color-ink)] px-[var(--space-base)] py-[var(--space-sm)] text-body-sm text-white shadow-card"
        >
          Saved ✓
        </div>
      )}
    </>
  );
}

export default function UploadPage() {
  return (
    <AuthenticatedShell>
      <UploadFlow />
    </AuthenticatedShell>
  );
}
