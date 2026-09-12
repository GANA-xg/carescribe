// CareScribe API types — mirrored from backend/schemas.py + backend/routes/*.
// Every request/response shape used by the frontend lives here.

// ---------- Auth ----------

export type Role = 'patient' | 'doctor';

export type User = {
  id: string;
  name: string;
  email: string;
  role: Role;
  created_at?: string;
  // Profile row ids — patient_id is what every patient-scoped
  // endpoint (/passport, /assistant, /imaging) expects in its path.
  patient_id?: string | null;
  doctor_id?: string | null;
};

// Resolve the id to use for patient-scoped routes.
export function patientIdOf(user: User): string {
  if (user.patient_id) return user.patient_id;
  // Fallback for sessions created before the contract change.
  return user.id;
}

export type RegisterRequest = {
  name: string;
  email: string;
  password: string;
  role: Role;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type AuthResponse = {
  user: User;
  token: string;
};

// ---------- OCR ----------

export type OcrJobResponse = {
  job_id: string;
  status: 'queued';
};

export type StructuredPrescription = {
  drugs: string[];
  diagnosis: string;
  date: string;
};

export type OcrResult = {
  raw_text: string;
  structured: Partial<StructuredPrescription>;
  model_used: string;
  confidence: number;
  engines?: Record<string, string>;
};

// Backend terminal statuses: queued | processing | done | failed
export type OcrStatusResponse = {
  status: 'queued' | 'processing' | 'done' | 'failed';
  result?: OcrResult;
  error?: string;
};

// ---------- Passport ----------

export type HealthRecord = {
  id: string;
  type: string; // prescription | diagnosis | sepsis_score | imaging | lab | ...
  data: Record<string, unknown>;
  source: 'ocr' | 'manual';
  created_at: string | null;
};

export type FhirResource = Record<string, unknown> & { resourceType?: string };

export type PassportSummary = {
  total: number;
  last_updated: string | null;
  conditions: string[];
  medications: string[];
};

export type PassportResponse = {
  records: HealthRecord[];
  fhir_resources: FhirResource[];
  summary: PassportSummary;
};

export type RecordIn = {
  type: string;
  data: Record<string, unknown>;
  source: 'ocr' | 'manual';
};

// ---------- Drugs ----------

export type DrugComparison = {
  name: string;
  found: boolean;
  brand_name?: string;
  brand_price?: number;
  generic_name?: string;
  generic_price?: number;
  saving?: number;
  saving_pct?: number;
  formulation?: string;
};

export type DrugCompareResponse = {
  drugs: DrugComparison[];
};

export type GenericOption = {
  generic_name: string;
  generic_name_price?: number;
  formulation?: string;
};

// ---------- Imaging ----------

export type Study = {
  study_instance_uid: string | null;
  orthanc_study_id: string;
  date: string | null;
  description: string | null;
  accession_number?: string | null;
  series_count?: number;
  ohif_url: string;
};

export type TumorScanResponse = {
  prediction: string;
  confidence: number;
  heatmap_url?: string | null;
  probabilities?: Record<string, number> | null;
  orthanc_instance_id?: string | null;
};

// ---------- Symptoms ----------

export type PossibleCondition = {
  name: string;
  score: number | null;
};

export type SymptomCheckResponse = {
  possible_conditions: PossibleCondition[];
  severity: 'low' | 'medium' | 'high';
  see_doctor: boolean;
  disclaimer?: string;
};

// ---------- Sepsis ----------

export type Vitals = {
  temp: number;
  hr: number;
  rr: number;
  wbc: number;
  lactate: number;
};

export type ShapItem = {
  feature: string;
  value: number;
};

export type SepsisRiskResponse = {
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high';
  shap_explanation: ShapItem[];
  trend: { date: string; score: number }[];
  explanation: string;
  record_id: string | null;
};

// ---------- Assistant ----------

export type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
};

export type ChatRequest = {
  patient_id: string;
  message: string;
  history: ChatMessage[];
};

export type Citation = {
  source: string;
  text: string;
  similarity: number;
};

export type ChatResponse = {
  reply: string;
  sources: string[];
  citations: Citation[];
};

export type VoiceResponse = {
  transcript: string;
  reply: string;
  audio_reply_url: string | null;
  sources?: string[];
};

// ---------- FaceID ----------

export type FaceIdResponse = {
  patient_id: string | null;
  name: string | null;
  confidence: number;
  liveness_passed: boolean;
};

// ---------- Diagnosis ----------

export type DiagnosisCompareRequest = {
  diagnosis_a: string;
  diagnosis_b: string;
  date_a?: string | null;
  date_b?: string | null;
};

export type DiagnosisCompareResponse = {
  agreement: boolean;
  conflict_details: string | null;
  icd_codes: string[];
  explanation: string;
  similarity?: number;
};

// ---------- Doctor dashboard ----------

export type DoctorPatient = {
  id: string;
  name: string;
  email: string;
  last_visit: string | null;
};
