# CareScribe — Model Service

Internal model-serving microservice for CareScribe. **FreeBuff's component**: every
model, every inference pipeline, every data-science artefact lives here.

FastAPI on `0.0.0.0:9000`. **Not exposed to the frontend** and deliberately absent
from the public port map in `docker-compose` — the backend proxies to it over the
private network.

---

## Quickstart

```bash
cd models
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt      # core only, ~300 MB
.venv/bin/python -m pytest                     # 146 pass, 9 skip; no GPU, no downloads
.venv/bin/uvicorn main:app --port 9000
curl -s localhost:9000/health | python3 -m json.tool
```

That is enough to run every endpoint. See
[Graceful degradation](#graceful-degradation) for what each one returns before the
real models are installed.

To add the real models:

```bash
.venv/bin/pip install -r requirements-models.txt
.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install git+https://github.com/datalab-to/chandra.git
```

---

## Repository layout

This service lives at **`models/`** in the repo root, alongside `backend/`,
`frontend/` and `infra/` — matching `docker-compose.yml`'s `build: ./models`.

> It was originally scaffolded at `carescribe/models/` with a placeholder
> `service.py`. That placeholder has been replaced by this implementation, and the
> tree was flattened to the repo root by the infra work, so root-level `models/`
> is the canonical location. Nothing else needs moving.

## Architecture

```
main.py                 FastAPI app, lifespan warmup, typed error handling
catalog.py              single source of truth for model ids and versions
config.py               env-driven settings
architectures.py        torch models shared by training and serving
schemas.py              pydantic request/response contracts
routers/                thin HTTP layer — one module per model group
services/               model logic, one module per model group
utils/                  images, audio, text, confidence, heatmap, transport, registry,
                        loader, log
scripts/                download / train / evaluate / report
tests/                  pytest suite
```

Layering is strictly one-way: `routers → services → utils`. `services/` never
imports `routers/`, so every backend is swappable without touching HTTP.

**Models load once, never per request.** `utils/loader.py` holds a `LazyModel`
that resolves on first use under a lock and caches the result. `ENABLE_HEAVY_MODELS=true`
plus `WARMUP_ON_STARTUP=true` resolves everything at boot on a background thread,
so `/health` answers immediately and reports each model as it becomes ready.

---

## Graceful degradation

The central design decision, and the one worth reviewing first.

Every model has a **primary backend** and, where a meaningful answer exists
without it, a **fallback**. The fallback is never a random number:

| Endpoint | Primary | Fallback | Fallback is… |
| --- | --- | --- | --- |
| `/ocr` | Donut + Chandra | — | empty text, `confidence 0`, `degraded: true` |
| `/ner` | medspaCy | lexicon + regex parser | **real extraction** — ~350 drugs, dose/frequency regexes |
| `/tumor-predict` | EfficientNet-B0 | — | **503** — a fabricated tumour class is unacceptable |
| `/symptoms` | RandomForest | curated rules KB | **real triage** — 45 conditions, red-flag override |
| `/sepsis-risk` | XGBoost + TreeSHAP | transparent logistic | real scoring, contributions labelled `linear-contribution` |
| `/embed` | MiniLM | signed hashing | deterministic 384-dim, lexical only |
| `/stt` | Whisper | — | empty transcript, `confidence 0`, `degraded: true` |
| `/tts` | Coqui | gTTS → silence | valid WAV/MP3 container; silence, never a tone |
| `/faceid/embed` | UniFace | — | **503** — a wrong patient match is unacceptable |

Three endpoints refuse to answer rather than guess: **tumour classification, face
identity, and (partially) speech**. In each case a plausible-looking wrong answer
would flow into a clinical record, which is worse than an error. They return
`503 model_unavailable` naming the exact command that fixes it.

Every endpoint returns `degraded: bool`. A caller can always tell "the model said
X" from "the model isn't installed". `/health` reports each model's `status`
(`loaded` / `degraded` / `failed`) with the reason, so an orchestrator can
distinguish *up but running on fallbacks* from *fully warm*.

---

## Internal API

Base URL `http://localhost:9000` (dev). All endpoints are internal.

| Method | Endpoint | Body | Response |
| --- | --- | --- | --- |
| GET | `/health` | — | `{status, models_loaded[], models[], degraded_models[], gpu, device, service_version}` |
| POST | `/ocr` | `{image_b64}` | `{donut, chandra, merged, agreement, engines, timings, model_version, inference_time_ms}` |
| POST | `/ner` | `{text}` | `{drugs[], dosages[], frequencies[], diagnosis, engine, confidence, ...}` |
| POST | `/tumor-predict` | `{image_b64, with_heatmap?}` | `{prediction, confidence, class_probabilities{}, heatmap_b64?, ...}` |
| POST | `/symptoms` | `{symptoms[]}` | `{conditions[], condition_scores[], severity, see_doctor, disclaimer, ...}` |
| POST | `/sepsis-risk` | `{vitals{temp,hr,rr,wbc,lactate}}` | `{risk_score, risk_level, shap_values[], explanation, ...}` |
| POST | `/embed` | `{texts[]}` | `{embeddings[][], model, dim, ...}` |
| POST | `/stt` | `{audio_b64, language?}` | `{transcript, language_detected, confidence, duration_s, ...}` |
| POST | `/tts` | `{text, language?}` | `{audio_b64, audio_format, duration_s, engine, ...}` |
| POST | `/faceid/embed` | `{image_b64}` | `{embedding[], dim, liveness_score, liveness_passed, ...}` |

Every response carries `model_version` and `inference_time_ms` (rule 5 — the paper
reports both). Errors use `{error, message}` with stable codes: `invalid_image`,
`invalid_audio`, `no_face_detected` (422), `batch_too_large` (422),
`missing_payload` (422), `model_unavailable` (503).

**Two transports.** The file endpoints (`/ocr`, `/tumor-predict`,
`/faceid/embed`, `/stt`) accept **both** base64 JSON — the canonical internal
contract — and `multipart/form-data` uploads, so the backend can call them either
way without changes. Multipart field names are accepted generously (`file`,
`image`, `dicom_file`, `audio_file`, …); uploaded bytes are base64-encoded at the
transport boundary so no service or model code sees a difference. The OpenAPI
schema advertises both content types.

Interactive docs: <http://localhost:9000/docs>.

---

## Training

Three checks are needed for the real models.

```bash
# FB-05 brain tumour — Kaggle credentials required
.venv/bin/python scripts/download_data.py
.venv/bin/python scripts/train_tumor.py --epochs 8            # -> weights/tumor_model.pth

# FB-06 symptom checker — public dataset, no credentials
.venv/bin/python scripts/train_symptoms.py --csv data/symptoms.csv   # -> weights/symptom_model.pkl

# FB-07 sepsis — MIMIC/eICU credentials required
.venv/bin/python scripts/train_sepsis.py --csv data/sepsis.csv       # -> weights/sepsis_model.pkl
```

All three run standalone on CPU or GPU. `train_symptoms.py` auto-detects three
CSV layouts (wide flags, packed delimiters, one-symptom-per-row) and needs no
pandas. `train_sepsis.py --synthetic N` produces a loadable checkpoint for smoke
tests — it prints a warning and records `synthetic: true` in the bundle, because
its accuracy is an artefact of the generator and must not be quoted.

Once trained, restart the service and `/health` flips those models from `degraded`
to `loaded`.

---

## Evaluation (FB-11)

```bash
# OCR: CER, WER, drug accuracy, per-engine latency
.venv/bin/python scripts/evaluate_ocr.py \
    --images data/ocr_test/images --truth data/ocr_test/truth \
    --truth-drugs data/ocr_test/drugs.json --out reports

# Tumour: confusion matrix, per-class P/R/F1, macro AUC
.venv/bin/python scripts/evaluate_tumor.py --out reports
```

Both write a markdown table plus CSV to `reports/`. Reproducible: same inputs,
same installed engines, same numbers.

---

## Inference logging (FB-12)

Every call is appended to a SQLite database (`logs/inference.db` by default) with
model, version, endpoint, latency, input size, confidence, degraded flag and any
error. **No patient data**: sizes and numbers only, never images, transcripts or
record contents.

```bash
.venv/bin/python scripts/inference_report.py --csv reports/inference_summary.csv
```

Prints call counts, mean latency and degradation share per model and per endpoint,
plus the slowest calls. This is the source of the report's latency table.

---

## Docker

```bash
docker build -t carescribe-models ./models                             # core image
docker build -t carescribe-models:full ./models --build-arg INSTALL_HEAVY=true
docker run -p 9000:9000 -v "$PWD/models/weights:/app/weights" carescribe-models
```

Multi-stage: a builder compiles a virtualenv, the runtime image carries no
compiler and runs as a non-root user. `torch` is pulled from the CPU-only index.

**Integration notes for OpenCode.** `docker-compose.yml` already wires this
service correctly — `build: ./models` and `expose: "9000"` (not `ports:`), with
`MODEL_SERVICE_URL: http://models:9000` for the backend. Two additions worth
making:

1. **Mount the weights directory** so trained checkpoints survive a rebuild:
   `volumes: ["./models/weights:/app/weights"]`. Without it, `/tumor-predict`,
   `/sepsis-risk` and `/faceid/embed` keep returning `503` inside Docker even
after you train the models on the host.
2. **`REDIS_URL` is passed to this service but unused** — the model service is
   stateless by design (no cache, no queue, no session). Harmless, but safe to
   drop from the `models` service environment if you prefer a tidy file.

Do not add a `ports:` mapping. Only the backend should reach port 9000.

---

## Configuration

All settings are environment variables with working defaults — see `.env.example`.
The ones that change behaviour most:

| Variable | Default | Effect |
| --- | --- | --- |
| `ENABLE_HEAVY_MODELS` | `true` | `false` skips every heavy backend and serves fallbacks immediately |
| `WARMUP_ON_STARTUP` | `true` | `false` resolves models on first request instead |
| `DEVICE` | `auto` | `auto`/`cpu`/`cuda`/`mps`. CPU always works |
| `LIVENESS_THRESHOLD` | `0.5` | Face liveness pass mark |
| `MAX_EMBED_BATCH` | `100` | `/embed` cap per call |
| `WHISPER_MODEL` | `openai/whisper-base` | Swap for a Hindi checkpoint |

---

## Task status

| Task | Scope | Status |
| --- | --- | --- |
| FB-01 | Model service scaffold, `/health`, Dockerfile | ✅ Done |
| FB-02 | Dual OCR pipeline (Donut + Chandra + merge by CER) | ✅ Done |
| FB-03 | medspaCy NER + lexicon/regex fallback | ✅ Done |
| FB-04 | Face-ID embeddings (UniFace) + liveness | ✅ Done |
| FB-05 | Brain tumour CNN, Grad-CAM, train + download scripts | ✅ Done |
| FB-06 | Symptom checker, rules fallback, training script | ✅ Done |
| FB-07 | Sepsis XGBoost + SHAP, logistic fallback, training script | ✅ Done |
| FB-08 | Embeddings service (MiniLM + hashing fallback) | ✅ Done |
| FB-09 | Whisper STT (faster-whisper → transformers) | ✅ Done |
| FB-10 | TTS (Coqui → gTTS → silent placeholder) | ✅ Done |
| FB-11 | `evaluate_ocr.py`, `evaluate_tumor.py` | ✅ Done |
| FB-12 | Model versioning, `/health` detail, SQLite inference log, `inference_report.py` | ✅ Done |

Code is complete and tested for every task. What remains is **data and weights**,
which need credentials this environment does not have:

- Donut + Chandra weights — downloaded on first load once the packages are installed.
- `tumor_model.pth` — needs Kaggle credentials, then `train_tumor.py`.
- `symptom_model.pkl` — needs the public dataset CSV, then `train_symptoms.py`.
- `sepsis_model.pkl` — needs MIMIC/eICU credentialed access, then `train_sepsis.py`.

---

## Decisions and deviations from the brief

Worth a look before the paper is written.

1. **Three endpoints hard-fail instead of degrading** — `/tumor-predict`,
   `/faceid/embed`, and the tumour/face paths. The brief asks for fallbacks
   everywhere; a fabricated tumour class or patient identity is worse than an
   error, so these return `503` naming the fix. The brief's intent (keep serving)
   is met everywhere a fallback can be *honest*.
2. **`liveness` is a heuristic, not a PAD model.** UniFace ships detection and
   recognition, not presentation-attack detection. The service uses Laplacian
   texture energy discounted by blown-out highlights, reports
   `liveness_method: "texture-heuristic"`, and says in the module docstring that a
   real PAD model (e.g. MiniFASNet) is required before production.
3. **`/tts` can return MP3.** gTTS produces MP3 only; converting needs ffmpeg. The
   response adds `audio_format` and the note says so, rather than claiming WAV.
4. **`explanation_method` distinguishes SHAP from linear attribution.** The sepsis
   fallback's contributions are `coefficient × deviation`, not SHAP. Labelling
   them alike would be a research-integrity problem.
5. **Inference log is `logs/inference.db`, not `inference.log`.** The brief says
   "local SQLite log at `/models/logs/inference.log`"; a `.log` extension on a
   SQLite database misleads anyone who opens it. Path is configurable via
   `INFERENCE_DB`.
6. **The tumour dataset's split is slice-level, not patient-level.** Consecutive
   slices of one scan can appear in both Training and Testing, which inflates
   accuracy. `evaluate_tumor.py` states this in its output and recommends macro
   AUC over raw accuracy when comparing to published baselines. Any paper using
   these numbers must say so.
7. **`see_doctor` is true for `medium` as well as `high`.** The brief requires it
   for `high`; `medium` advising a consultation is the clinically safer default.
   `low` returns `false` so the field carries information.
8. **`/ocr` returns an empty result rather than failing** when neither engine is
   installed — consistent with `/stt`. The backend can show "couldn't read that,
   try again" without treating it as a service outage.
9. **`/embed` rejects oversize batches with `422`** rather than chunking silently,
   per the 100-text cap in the internal contract.
10. **Notion was not updated.** The Notion workspace was unreachable from this
    environment, so the task board was not moved. The table above is the status to
    paste in.

---

## Testing

```bash
.venv/bin/python -m pytest                  # everything; ~0.7s
.venv/bin/python -m pytest -m heavy         # real backends only, if installed
.venv/bin/python -m pytest tests/test_ocr.py -v
```

The suite forces `ENABLE_HEAVY_MODELS=false` in `tests/conftest.py` before anything
imports `config`, so it runs offline in about a second and asserts the **degraded
contract** — which is the path a fresh clone actually takes. The 9 tests marked
`heavy` exercise real backends and skip when those packages are absent.
