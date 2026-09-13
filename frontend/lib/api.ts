// CareScribe API client — single fetch surface for the whole app.
// Components never call fetch directly; they go through `api.*`.

import type {
  AuthResponse,
  ChatRequest,
  ChatResponse,
  DiagnosisCompareRequest,
  DiagnosisCompareResponse,
  DoctorPatient,
  DrugCompareResponse,
  FaceIdResponse,
  HealthRecord,
  LoginRequest,
  OcrJobResponse,
  OcrStatusResponse,
  PassportResponse,
  RecordIn,
  RegisterRequest,
  SepsisRiskResponse,
  Study,
  SymptomCheckResponse,
  TumorScanResponse,
  User,
  Vitals,
  VoiceResponse,
} from './types';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const TOKEN_KEY = 'cs_token';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string | null) {
  if (typeof window === 'undefined') return;
  if (token === null) localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, token);
}

function handle401(path: string, detail?: string): never {
  setToken(null);
  // A 401 on the auth screens themselves is a wrong-password case —
  // surface the server's message inline instead of bouncing the user
  // to the login page they are already on.
  const isAuthPath = path.startsWith('/auth/login') || path.startsWith('/auth/register');
  if (!isAuthPath && typeof window !== 'undefined') {
    window.location.href = '/auth/login';
  }
  throw new ApiError(401, detail ?? 'Unauthorized');
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 401) {
    const body401 = (await res.json().catch(() => ({}))) as { detail?: string };
    handle401(path, body401.detail);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(res.status, body.detail ?? 'Request failed');
  }
  return (await res.json()) as T;
}

async function upload<T>(path: string, formData: FormData): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { method: 'POST', headers, body: formData });

  if (res.status === 401) {
    const body401 = (await res.json().catch(() => ({}))) as { detail?: string };
    handle401(path, body401.detail);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(res.status, body.detail ?? 'Upload failed');
  }
  return (await res.json()) as T;
}

function toFile(field: string, file: Blob | File, filename?: string): FormData {
  const fd = new FormData();
  fd.append(field, file, filename ?? (file instanceof File ? file.name : 'upload.bin'));
  return fd;
}

export const api = {
  auth: {
    register: (body: RegisterRequest) =>
      request<AuthResponse>('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
    login: (body: LoginRequest) =>
      request<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
    me: () => request<User>('/auth/me'),
    refresh: () =>
      request<{ token: string; user: User }>('/auth/refresh', { method: 'POST' }),
  },

  ocr: {
    // Backend reads multipart field "file"
    process: (file: File) => upload<OcrJobResponse>('/ocr/process', toFile('file', file)),
    getStatus: (jobId: string) => request<OcrStatusResponse>(`/ocr/status/${jobId}`),
  },

  passport: {
    get: (patientId: string) => request<PassportResponse>(`/passport/${patientId}`),
    // Backend wraps the record: { record: HealthRecord }
    addRecord: (patientId: string, body: RecordIn) =>
      request<{ record: HealthRecord }>(`/passport/${patientId}/records`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    getRecord: (patientId: string, recordId: string) =>
      request<{ record: HealthRecord }>(`/passport/${patientId}/records/${recordId}`),
  },

  drugs: {
    compare: (names: string[]) =>
      request<DrugCompareResponse>('/drugs/compare', {
        method: 'POST',
        body: JSON.stringify({ drug_names: names }),
      }),
    getGenerics: (name: string) =>
      request<{ generics: unknown[] }>(`/drugs/generics/${encodeURIComponent(name)}`),
  },

  imaging: {
    getStudies: (patientId: string) =>
      request<{ studies: Study[] }>(`/imaging/studies/${patientId}`),
    // Backend reads multipart field "dicom_file"
    tumorScan: (file: File) =>
      upload<TumorScanResponse>('/imaging/tumor-scan', toFile('dicom_file', file)),
  },

  symptoms: {
    check: (symptoms: string[]) =>
      request<SymptomCheckResponse>('/symptoms/check', {
        method: 'POST',
        body: JSON.stringify({ symptoms }),
      }),
  },

  clinical: {
    sepsisRisk: (patientId: string, vitals: Vitals) =>
      request<SepsisRiskResponse>('/clinical/sepsis-risk', {
        method: 'POST',
        body: JSON.stringify({ patient_id: patientId, vitals }),
      }),
  },

  assistant: {
    chat: (body: ChatRequest) =>
      request<ChatResponse>('/assistant/chat', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    // Backend requires patient_id form field + audio_file
    voice: (audio: Blob, patientId: string) => {
      const fd = new FormData();
      fd.append('audio_file', audio, 'voice.wav');
      fd.append('patient_id', patientId);
      return upload<VoiceResponse>('/assistant/voice', fd);
    },
  },

  faceid: {
    // Enroll is patient-only; backend derives patient from the token.
    enroll: (image: File) =>
      upload<{ enrolled: boolean }>('/faceid/enroll', toFile('file', image)),
    identify: (image: File) =>
      upload<FaceIdResponse>('/faceid/identify', toFile('file', image)),
    unenroll: (patientId: string) =>
      request<{ success: boolean }>(`/faceid/unenroll/${patientId}`, {
        method: 'DELETE',
      }),
  },

  diagnosis: {
    compare: (body: DiagnosisCompareRequest) =>
      request<DiagnosisCompareResponse>('/diagnosis/compare', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  },

  doctor: {
    // Doctor-only: every patient with name/email/last_visit
    listPatients: () =>
      request<{ patients: DoctorPatient[] }>('/patients'),
  },
};

export { BASE, getToken, setToken };
