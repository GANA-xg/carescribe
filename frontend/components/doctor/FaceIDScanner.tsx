'use client';

import { useEffect, useRef, useState } from 'react';
import { Camera } from 'lucide-react';
import { Button, Input, Modal } from '../ui';
import { api } from '../../lib/api';
import type { FaceIdResponse } from '../../lib/types';

type ScannerState =
  | { mode: 'idle' }
  | { mode: 'scanning' }
  | { mode: 'result'; result: FaceIdResponse }
  | { mode: 'no-match' }
  | { mode: 'liveness-failed' }
  | { mode: 'error'; message: string };

export default function FaceIDScanner({
  isOpen,
  onClose,
  onPatientSelected,
}: {
  isOpen: boolean;
  onClose: () => void;
  onPatientSelected: (patient: { id: string; name: string }) => void;
}) {
  const [state, setState] = useState<ScannerState>({ mode: 'idle' });
  const [search, setSearch] = useState('');
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [capturing, setCapturing] = useState(false);

  // Stop the camera whenever the modal closes or state leaves scanning.
  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  useEffect(() => {
    if (!isOpen) {
      stopCamera();
      setState({ mode: 'idle' });
      setSearch('');
    }
    return stopCamera;
  }, [isOpen]);

  const startScan = async () => {
    setState({ mode: 'scanning' });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: 640, height: 640 },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
    } catch {
      setState({ mode: 'error', message: 'Camera access was denied.' });
    }
  };

  const capture = async () => {
    setCapturing(true);
    const video = videoRef.current;
    if (!video) {
      setCapturing(false);
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 640;
    canvas.getContext('2d')?.drawImage(video, 0, 0);
    stopCamera();

    canvas.toBlob(async (blob) => {
      if (!blob) {
        setCapturing(false);
        setState({ mode: 'error', message: 'Could not capture a frame.' });
        return;
      }
      try {
        const file = new File([blob], 'face.jpg', { type: 'image/jpeg' });
        const result = await api.faceid.identify(file);
        if (result.patient_id && result.liveness_passed) {
          setState({ mode: 'result', result });
        } else if (!result.liveness_passed && result.confidence === 0) {
          setState({ mode: 'liveness-failed' });
        } else if (!result.patient_id) {
          setState({ mode: 'no-match' });
        } else {
          setState({ mode: 'liveness-failed' });
        }
      } catch (e) {
        setState({
          mode: 'error',
          message: e instanceof Error && e.message ? e.message : 'Face scan failed.',
        });
      } finally {
        setCapturing(false);
      }
    }, 'image/jpeg');
  };

  const submitSearch = () => {
    const name = search.trim();
    if (!name) return;
    // Name search routes through the doctor's patient list — the parent
    // screen owns lookup. We surface the chosen name immediately.
    onPatientSelected({ id: '', name });
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Scan Patient" aria-label="Face ID scanner">
      <div className="flex flex-col items-center gap-[var(--space-lg)]">
        {state.mode === 'idle' && (
          <>
            <Camera className="h-16 w-16 text-[var(--color-muted)]" aria-hidden="true" />
            <Button aria-label="Start face scan" onClick={startScan}>
              Scan Patient
            </Button>
            <button
              onClick={submitSearch}
              disabled={!search.trim()}
              className="text-body-sm text-[var(--color-primary)] underline disabled:opacity-40"
              aria-label="Search by name instead"
            >
              Search by name instead
            </button>
            <div className="w-full">
              <Input
                label="Name"
                placeholder="Type a patient name…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    submitSearch();
                  }
                }}
              />
            </div>
          </>
        )}

        {state.mode === 'scanning' && (
          <>
            <div className="relative h-[280px] w-[280px] overflow-hidden rounded-full border-4 border-dashed border-white shadow-card bg-black">
              <video
                ref={videoRef}
                playsInline
                muted
                className="h-full w-full object-cover"
                aria-label="Camera preview"
              />
            </div>
            <Button aria-label="Capture face photo" loading={capturing} onClick={capture}>
              Capture
            </Button>
          </>
        )}

        {state.mode === 'result' && (
          <>
            <p className="text-[20px] font-bold text-[var(--color-ink)]">
              {state.result.name ?? 'Matched patient'}
            </p>
            <span className="inline-flex items-center rounded-full bg-[#22c55e] px-[10px] py-[4px] text-badge font-semibold text-white">
              {Math.round(state.result.confidence * 100)}% match
            </span>
            <div className="flex gap-[var(--space-base)]">
              <Button
                aria-label="Open records"
                onClick={() => {
                  onPatientSelected({
                    id: state.result.patient_id ?? '',
                    name: state.result.name ?? '',
                  });
                  onClose();
                }}
              >
                Open Records
              </Button>
              <Button variant="secondary" aria-label="Dismiss match" onClick={() => setState({ mode: 'idle' })}>
                Dismiss
              </Button>
            </div>
          </>
        )}

        {state.mode === 'no-match' && (
          <>
            <p className="text-body-md text-[var(--color-muted)]">No match found</p>
            <div className="w-full">
              <Input
                label="Name"
                placeholder="Type a patient name…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    submitSearch();
                  }
                }}
                autoFocus
              />
            </div>
            <Button aria-label="Search by name" onClick={submitSearch} disabled={!search.trim()}>
              Search
            </Button>
          </>
        )}

        {state.mode === 'liveness-failed' && (
          <>
            <p className="text-body-sm text-[var(--color-error)]">
              Please face the camera directly.
            </p>
            <Button variant="secondary" aria-label="Try face scan again" onClick={startScan}>
              Try again
            </Button>
          </>
        )}

        {state.mode === 'error' && (
          <>
            <p className="text-body-sm text-[var(--color-error)]" role="alert">
              {state.message}
            </p>
            <Button variant="secondary" aria-label="Retry face scan" onClick={startScan}>
              Try again
            </Button>
          </>
        )}
      </div>
    </Modal>
  );
}
