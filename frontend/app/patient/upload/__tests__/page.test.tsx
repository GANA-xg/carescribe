import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import UploadPage from '../page';
import { useAuthStore } from '../../../../store/auth';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/patient/upload',
}));

function renderUpload() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UploadPage />
    </QueryClientProvider>
  );
}

const patient = {
  id: 'p1',
  name: 'Ananya Rao',
  email: 'patient@example.com',
  role: 'patient' as const,
};

let calls: { url: string; init?: RequestInit }[] = [];

function mockFetchSequence(responses: Array<{ status: number; body: unknown }>) {
  calls = [];
  let i = 0;
  const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const r = responses[Math.min(i, responses.length - 1)];
    i++;
    return Promise.resolve({
      ok: r.status >= 200 && r.status < 300,
      status: r.status,
      json: () => Promise.resolve(r.body),
    } as Response);
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

beforeEach(() => {
  push.mockClear();
  localStorage.clear();
  useAuthStore.setState({ user: patient, hydrated: true });
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('upload flow', () => {
  it('shows the three steps in the indicator', () => {
    renderUpload();
    expect(screen.getByText('Capture')).toBeInTheDocument();
    expect(screen.getByText('Processing')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
  });

  it('shows the drop zone with camera icon and take photo action', () => {
    renderUpload();
    expect(screen.getByText('Drag prescription here')).toBeInTheDocument();
    expect(screen.getByText('or')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Take photo' })).toBeInTheDocument();
  });

  it('shows a preview after picking a file', async () => {
    mockFetchSequence([{ status: 200, body: {} }]);
    renderUpload();
    const input = screen.getByLabelText('Prescription photo') as HTMLInputElement;
    const file = new File(['img'], 'rx.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByAltText('Prescription preview')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Use this photo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retake photo' })).toBeInTheDocument();
  });

  it('moves to processing, polls, and lands on review with OCR fields', async () => {
    const doneBody = {
      status: 'done',
      result: {
        raw_text: 'Rx Paracetamol 500mg',
        structured: {
          drugs: ['Paracetamol', 'Amoxicillin'],
          diagnosis: 'Fever',
          date: '2026-09-01',
        },
        model_used: 'chandra',
        confidence: 0.85,
      },
    };
    mockFetchSequence([
      { status: 202, body: { job_id: 'job-1', status: 'queued' } },
      { status: 200, body: { status: 'processing' } },
      { status: 200, body: doneBody },
    ]);

    renderUpload();
    const input = screen.getByLabelText('Prescription photo') as HTMLInputElement;
    const file = new File(['img'], 'rx.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Use this photo' }));

    await waitFor(() => expect(screen.getByText('Reading your prescription…')).toBeInTheDocument());

    await vi.advanceTimersByTimeAsync(2100);
    await vi.advanceTimersByTimeAsync(2100);

    expect(await screen.findByLabelText('Diagnosis')).toBeInTheDocument();
    expect((screen.getByLabelText('Diagnosis') as HTMLInputElement).value).toBe('Fever');
    expect(screen.getByText('Paracetamol')).toBeInTheDocument();
    expect(screen.getByText('Amoxicillin')).toBeInTheDocument();
  });

  it('removes a drug chip when × is clicked', async () => {
    renderUpload();
    // Jump straight to review via the flow
    const doneBody = {
      status: 'done',
      result: {
        raw_text: 'Rx',
        structured: { drugs: ['Paracetamol'], diagnosis: '', date: '' },
        model_used: 'donut',
        confidence: 0.8,
      },
    };
    mockFetchSequence([
      { status: 202, body: { job_id: 'j', status: 'queued' } },
      { status: 200, body: doneBody },
    ]);
    const input = screen.getByLabelText('Prescription photo') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'rx.png', { type: 'image/png' })] } });
    fireEvent.click(screen.getByRole('button', { name: 'Use this photo' }));
    await vi.advanceTimersByTimeAsync(2100);
    expect(await screen.findByText('Paracetamol')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove Paracetamol' }));
    expect(screen.queryByText('Paracetamol')).not.toBeInTheDocument();
  });

  it('shows the failure state and lets the user try again', async () => {
    mockFetchSequence([
      { status: 202, body: { job_id: 'j', status: 'queued' } },
      { status: 200, body: { status: 'failed', error: 'blurry' } },
    ]);
    renderUpload();
    const input = screen.getByLabelText('Prescription photo') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'rx.png', { type: 'image/png' })] } });
    fireEvent.click(screen.getByRole('button', { name: 'Use this photo' }));
    await vi.advanceTimersByTimeAsync(2100);
    expect(await screen.findByText("Couldn't read this prescription.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(screen.getByText('Drag prescription here')).toBeInTheDocument();
  });

  it('saves to passport and shows the toast', async () => {
    const doneBody = {
      status: 'done',
      result: {
        raw_text: 'Rx',
        structured: { drugs: ['Paracetamol'], diagnosis: 'Fever', date: '2026-09-01' },
        model_used: 'donut',
        confidence: 0.8,
      },
    };
    mockFetchSequence([
      { status: 202, body: { job_id: 'j', status: 'queued' } },
      { status: 200, body: doneBody },
      { status: 201, body: { record: { id: 'r1' } } },
    ]);
    renderUpload();
    const input = screen.getByLabelText('Prescription photo') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'rx.png', { type: 'image/png' })] } });
    fireEvent.click(screen.getByRole('button', { name: 'Use this photo' }));
    await vi.advanceTimersByTimeAsync(2100);
    await screen.findByLabelText('Diagnosis');

    fireEvent.click(screen.getByRole('button', { name: 'Save to Health Passport' }));
    await vi.advanceTimersByTimeAsync(1300);

    const saveCall = calls.find((c) => c.url.includes('/passport/p1/records'));
    expect(saveCall).toBeTruthy();
    expect(JSON.parse(String(saveCall!.init!.body))).toMatchObject({
      type: 'prescription',
      source: 'ocr',
    });
    expect(await screen.findByText('Saved ✓')).toBeInTheDocument();
  });
});
