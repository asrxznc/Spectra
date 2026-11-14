# SPECTRA

### AI media assessment workstation

SPECTRA is an experimental digital-forensics workspace for inspecting images, checking file integrity, and reviewing an AI-generated versus human-created classification estimate.

It is designed to feel like a focused investigation console: register an exhibit, seal its exact bytes with SHA-256, inspect basic image signals, review the model output, and export a readable investigation record.

> **Important:** SPECTRA is decision-support software, not proof of authenticity, authorship, or provenance. Model results can be wrong and should never be the sole basis for legal, disciplinary, financial, journalistic, or other high-impact decisions.

---

## What SPECTRA does

| Capability | Purpose |
|---|---|
| **Image intake** | Accepts JPG, JPEG, PNG, and WebP files up to 20 MB |
| **Integrity sealing** | Calculates a SHA-256 digest for the uploaded byte stream |
| **Image inspection** | Reads dimensions, format, orientation, and limited metadata markers |
| **AI assessment** | Produces an AI-generated, human-created, or inconclusive estimate |
| **Investigation history** | Keeps a short-lived record of the current session |
| **Report export** | Downloads a plain-text investigation record |

The interface includes the home console, investigation overview, media intake, live analysis, findings, and investigation-record screens. The existing visual language, motion system, and interaction design are intentionally preserved.

## How it works

```text
Browser
   │
   │  Upload + job polling
   ▼
Node.js / Express
   │
   │  Hashing, validation, metadata, reports
   ▼
Python / FastAPI
   │
   │  Image preprocessing + model inference
   ▼
Ateeqq/ai-vs-human-image-detector
```

The Node.js service serves the workstation and owns the public application API. The Python service loads the Hugging Face model and performs inference. They can run locally as two processes or be packaged as separate containers.

## Quick start

### Requirements

- Node.js 22+
- Python 3.11+
- Internet access for the first model download
- Enough memory for PyTorch and the Hugging Face model

### 1. Install JavaScript dependencies

```bash
npm install
```

The repository also contains `bun.lock` for Bun-based installs.

### 2. Install Python dependencies

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Configure the services

Copy `.env.example` to `.env` and use:

```dotenv
PORT=3000
PYTHON_BACKEND_URL=http://127.0.0.1:8000
```

`CORS_ORIGINS` is optional. Leave it empty for same-origin local use, or provide a comma-separated list when the browser and API use different origins.

### 4. Start the inference service

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

Wait for the model to finish loading:

```text
http://127.0.0.1:8000/api/health
```

### 5. Start the workstation

In a second terminal:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Useful commands

| Command | Use |
|---|---|
| `npm run dev` | Start the Node.js service with watch mode |
| `npm run build` | Run the TypeScript check |
| `npm start` | Start the Node.js service |
| `py -m py_compile server.py` | Check Python syntax |

## Application routes

| Route | Screen |
|---|---|
| `/` | Home console |
| `/overview` | Investigation overview |
| `/analyze` | Media intake |
| `/progress` | Analysis progress |
| `/results` | Findings |
| `/reports` | Investigation records |

## API surface

### Node.js application API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Application and classifier readiness |
| `POST` | `/api/analyze` | Create an image-analysis job |
| `GET` | `/api/jobs/:id` | Read job status and findings |
| `GET` | `/api/jobs/:id/image` | View the temporary image payload |
| `POST` | `/api/jobs/:id/retry` | Retry a failed job |
| `GET` | `/api/history` | Read current-session history |
| `GET` | `/api/reports/:id` | Download a completed report |

### Python inference API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Model readiness |
| `POST` | `/api/classify` | Run image classification |

## Reading the result

SPECTRA uses a deliberately conservative decision rule:

- **AI-Generated** — AI score is at least 70% and leads by at least 20 percentage points.
- **Human-Created** — human score is at least 70% and leads by at least 20 percentage points.
- **Inconclusive** — the model is not sufficiently separated or confident.

These are statistical model estimates, not calibrated probabilities. Performance can change across cameras, editing workflows, compression levels, image sources, and newer generative systems.

The SHA-256 value proves the identity of the uploaded bytes at the time of processing. It does not prove who created the image or whether the image itself is authentic.

## Privacy and retention

- Uploaded image bytes are held in server memory for processing.
- Jobs expire from server memory after approximately 24 hours.
- Browser history stores sanitized metadata in `localStorage`, not image bytes.
- Restarting the Node.js service clears its in-memory jobs.
- The default application has no login or user-level authorization.

Do not expose an unprotected instance to sensitive or hostile traffic without adding authentication, authorization, rate limiting, persistent storage controls, and an explicit data-retention policy.

## Technical safeguards

The application currently includes:

- Extension, media-type, signature, and dimension validation.
- A 20 MB upload limit and a 40-million-pixel safety limit.
- A bounded in-memory job store.
- Configurable CORS origins.
- Basic security response headers.
- Non-root Docker execution.
- Structured upload errors and degraded classifier health reporting.

## Repository map

```text
server.ts                              Node.js application and API
server.py                              FastAPI inference service
home/                                  Home console
investigation_overview/                Overview screen
analyze_media/                         Media intake screen
analysis_in_progress_scientific_.../   Progress screen
analysis_results/                      Findings screen
investigation_reports/                 Records and exports screen
public/vendor/                         Shared client-side utilities
Dockerfile                             Python inference container
Dockerfile.web                         Node.js web/API container
deploy-cloud-run.ps1                   Optional Cloud Run deployment helper
```

## Containers and deployment files

Deployment is intentionally **not required** for local development.

The repository keeps two optional container definitions:

- `Dockerfile` packages the Python inference service.
- `Dockerfile.web` packages the Node.js workstation/API service.

`deploy-cloud-run.ps1` contains an optional Google Cloud Run workflow for teams that later want a hosted deployment. It is not executed automatically and does not change the local development flow.

## Current boundaries

SPECTRA is an experimental workstation. It does not currently provide:

- A complete metadata-forensics engine.
- Sensor-level PRNU analysis.
- C2PA or other provenance verification.
- An independently validated accuracy benchmark.
- Persistent multi-user storage.
- Authentication or role-based access control.
- A distributed inference queue.

Those limitations are intentional and should remain visible whenever model output is presented.

## License

No license file is currently included. Until one is added, reuse and redistribution permissions should not be assumed.
