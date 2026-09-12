import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, BASE } from '../api';

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
  vi.stubGlobal('fetch', fn);
  return fn;
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('cs_token', 'test-token');
});

describe('api client', () => {
  it('uses the dev base URL by default', () => {
    expect(BASE).toBe('http://localhost:8000');
  });

  it('sends the bearer token from localStorage', async () => {
    const fn = mockFetch(200, { user: { id: '1', name: 'A', email: 'a@b.c', role: 'patient' } });
    await api.auth.me();
    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-token');
  });

  it('includes JSON content type on requests', async () => {
    const fn = mockFetch(200, { reply: 'ok', sources: [], citations: [] });
    await api.assistant.chat({ patient_id: 'p1', message: 'hi', history: [] });
    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    expect(init.method).toBe('POST');
    expect(String(fn.mock.calls[0][0])).toContain('/assistant/chat');
  });

  it('throws ApiError with detail message on error status', async () => {
    mockFetch(404, { detail: 'Patient not found' });
    await expect(api.passport.get('missing')).rejects.toSatisfy((e: unknown) => {
      return e instanceof ApiError && e.status === 404 && e.message === 'Patient not found';
    });
  });

  it('falls back to a generic message when body has no detail', async () => {
    mockFetch(500, {});
    await expect(api.auth.me()).rejects.toSatisfy((e: unknown) => {
      return e instanceof ApiError && e.message === 'Request failed';
    });
  });

  it('clears token and redirects to login on 401', async () => {
    mockFetch(401, { detail: 'Unauthorized' });
    await expect(api.auth.me()).rejects.toBeInstanceOf(ApiError);
    expect(localStorage.getItem('cs_token')).toBeNull();
  });

  it('keeps 401 on login inline (no redirect loop)', async () => {
    localStorage.setItem('cs_token', 'stale');
    mockFetch(401, { detail: 'Invalid credentials' });
    await expect(api.auth.login({ email: 'a@b.c', password: 'x' })).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && e.message === 'Invalid credentials'
    );
    // Auth-path 401 still clears the stale token but never navigates.
    expect(localStorage.getItem('cs_token')).toBeNull();
  });

  it('posts drug names under drug_names key', async () => {
    const fn = mockFetch(200, { drugs: [] });
    await api.drugs.compare(['Paracetamol']);
    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ drug_names: ['Paracetamol'] });
  });

  it('uploads tumor scan under dicom_file field', async () => {
    const fn = mockFetch(200, { prediction: 'no_tumor', confidence: 0.9 });
    const file = new File(['x'], 'scan.dcm', { type: 'application/dicom' });
    await api.imaging.tumorScan(file);
    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    const fd = init.body as FormData;
    expect(fd.get('dicom_file')).toBeInstanceOf(File);
    expect((fd.get('dicom_file') as File).name).toBe('scan.dcm');
  });

  it('uploads voice with audio_file + patient_id form fields', async () => {
    const fn = mockFetch(200, { transcript: 'hi', reply: 'hello', audio_reply_url: null });
    const blob = new Blob(['audio'], { type: 'audio/wav' });
    await api.assistant.voice(blob, 'patient-1');
    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    const fd = init.body as FormData;
    expect(fd.get('audio_file')).toBeInstanceOf(File);
    expect(fd.get('patient_id')).toBe('patient-1');
  });

  it('uploads face enroll under file field (no patient_id)', async () => {
    const fn = mockFetch(200, { enrolled: true });
    const file = new File(['img'], 'face.jpg', { type: 'image/jpeg' });
    await api.faceid.enroll(file);
    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    const fd = init.body as FormData;
    expect(fd.get('file')).toBeInstanceOf(File);
    expect(fd.has('patient_id')).toBe(false);
  });

  it('sends sepsis vitals wrapped with patient_id', async () => {
    const fn = mockFetch(200, { risk_score: 10, risk_level: 'low', shap_explanation: [], trend: [], explanation: '' });
    const vitals = { temp: 37, hr: 80, rr: 16, wbc: 6, lactate: 1.2 };
    await api.clinical.sepsisRisk('p1', vitals);
    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ patient_id: 'p1', vitals });
  });
});
