# SmartFill — Technical Project Documentation

> **Version:** 6.0.0  
> **API Type:** REST  
> **Stack:** Python · Flask · FastAPI · MongoDB · Docker · Hugging Face Spaces

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Flow](#2-architecture--flow)
3. [File / Module Breakdown](#3-file--module-breakdown)
4. [Database Schema](#4-database-schema)
5. [Confidence Scoring Logic](#5-confidence-scoring-logic)
6. [API Reference](#6-api-reference)
7. [Setup & Deployment](#7-setup--deployment)

---

## 1. Project Overview

SmartFill is an OCR-based document extraction backend that reads Indian identity and academic documents and returns structured JSON with per-field confidence scores. It supports Aadhaar Card, PAN Card, Voter ID, Driving Licence, and Marksheet. The system is split into two independent APIs — a Light API (Flask, Docker) for fast Tesseract-based extraction, and a Heavy API (FastAPI, Hugging Face Spaces) that uses YOLO, docTR, and Tesseract in a 3-tier fallback chain for high-accuracy extraction on difficult documents.

**Key characteristics:**

- Heavy API is always tried first (143s timeout); Light API is the automatic fallback.
- JWT authentication is optional — unauthenticated requests are processed as `user_id = "0000"`.
- Every field in the response carries a confidence score, a PASS/REVIEW/FAIL status, and a breakdown of how the score was calculated.
- MongoDB stores four collections: `scans`, `rescans`, `submissions`, `edits`.

---

## 2. Architecture & Flow

### 2.1 System Architecture

```
Client (Frontend / curl)
        │
        │  POST /api/scan (multipart file)
        ▼
┌─────────────────────────────┐
│     Flask Light API          │   ← Main server (Docker, port 8000)
│     ocr_routes.py            │
│                             │
│  1. Validate file + JWT     │
│  2. Call Heavy API (143s)   │──────────────────────────────────────────►  Hugging Face Space
│     ├─ Success → use result │                                             FastAPI Heavy API
│     └─ Fail/Timeout         │◄──────────────────────────────────────────  (YOLO + docTR + Tesseract)
│  3. Fallback: Light (Tess.) │
│  4. Add confidence scores   │
│  5. Save to MongoDB         │
│  6. Return JSON response    │
└─────────────────────────────┘
        │
        ▼
   MongoDB Atlas
   (scans / rescans / submissions / edits)
```

### 2.2 Request Processing Flow (Scan)

```
File Upload
    │
    ├─► File Validation (extension, size, not empty)
    │
    ├─► Auth Check (JWT optional → user_id or "0000")
    │
    ├─► [HEAVY API ATTEMPT]
    │       POST {HEAVY_API_URL}/api/scan
    │       Timeout: 143s, Retry on 5xx: 1 time
    │       ├─ 200 OK → use Heavy result
    │       └─ Fail / Timeout → fallback
    │
    ├─► [LIGHT API FALLBACK]
    │       extractor.process_document()
    │           ├─ PDF? → pdf2image + pdfplumber
    │           └─ Image? → pytesseract + OpenCV preprocess
    │       → classify_document_smart()
    │       → extract_{doc_type}_fields()
    │       → process_with_confidence()
    │
    ├─► add_extraction_summary()
    │
    ├─► db.save_scan(result, user_id)
    │
    ├─► file_storage.save_file() (if ENABLE_FILE_STORAGE=True)
    │
    └─► Return ScanResponse JSON
```

### 2.3 Heavy API Internal Flow (Hugging Face)

```
File Upload to /api/scan
    │
    ├─► YOLO (YOLOv8) — detect and crop document region from image
    │
    ├─► docTR — deep learning OCR on cropped region
    │       └─ If DOCTR_AVAILABLE=False → skip
    │
    ├─► Tesseract — fallback OCR (always runs)
    │       └─ Config: --oem 3 --psm 6
    │
    ├─► pdfplumber — PDF table extraction (Marksheet)
    │       └─ 3-tier fallback: camelot → lattice → stream
    │
    ├─► classify_document_smart(full_text)
    │
    ├─► extract_{doc_type}_fields(full_text)
    │
    ├─► process_with_confidence(result, ocr_confidences, image_quality)
    │
    └─► Return JSON response
```

### 2.4 Document Classification Logic

Classification happens in `extractor.py → classify_document_smart()`. It uses keyword pattern matching on the raw OCR text:

| Document | Primary Keywords |
|---|---|
| Aadhaar | "aadhaar", "uid", "unique identification", 12-digit number pattern |
| PAN | "income tax", "permanent account", 10-char alphanumeric pattern |
| Voter ID | "election commission", "elector", "epic" |
| Driving Licence | "driving licence", "motor vehicles", "transport" |
| Marksheet | "board of education", "cbse", "icse", "marks obtained", "roll no" |

---

## 3. File / Module Breakdown

### Light API (Main Server)

| File | Purpose |
|---|---|
| `server_production.py` | Entry point. Creates Flask app, registers `ocr_blueprint`, starts Waitress WSGI server on port 8000. |
| `config.py` | Central config using `python-dotenv`. Auto-detects Docker vs local. Sets Tesseract path, MongoDB URI, JWT secrets, file storage mode. |
| `ocr_routes.py` | All API route handlers. Heavy-priority scan strategy, rescan, edit, submit, title, my-scans, health, docs endpoints. Registers as Flask Blueprint at `/api`. |
| `extractor.py` | Core document processor. Handles image preprocessing, OCR (Tesseract + optional docTR), document classification, and field extraction for all 5 document types. |
| `confidence_calculator.py` | Hybrid confidence engine. Calculates per-field confidence using Tesseract OCR score + regex pattern match + image quality + business rules. Applies cross-field validation. |
| `extraction_summary.py` | Generates `extraction_summary` block: counts fields into High (≥85%), Medium (68–84%), Low (<68%) confidence buckets. Adds table count for Marksheet. |
| `models.py` | Dataclass models for all MongoDB documents (`ScanDocument`, `RescanDocument`, `SubmissionDocument`) and API responses (`ScanResponse`, `RescanResponse`, `SubmissionResponse`). Contains `DOCUMENT_FIELD_SCHEMA` and `normalize_fields()`. |
| `database.py` | MongoDB service singleton. All CRUD operations for scans, rescans, submissions, edits. Creates indexes on startup. |
| `auth.py` | JWT auth decorator (`@optional_auth`). Extracts `user_id` from Bearer token into `flask.g`. Falls back to `user_id = "0000"` for anonymous requests. |
| `image_preprocessor.py` | OpenCV-based image quality checker and preprocessor. Detects blur, low contrast, skew. Applies adaptive thresholding, denoising, deskewing before OCR. |
| `tesseract_confidence.py` | Single-pass Tesseract data extractor. Returns full text, per-word confidence, and overall stats (`average`, `min`, `max`) in one `pytesseract.image_to_data()` call. |
| `accuracy_metrics.py` | Accuracy and metrics utilities (used internally for evaluation). |
| `merge.py` | Merges OCR results from multiple passes (Tesseract + docTR) using field-level confidence comparison. |
| `file_storage.py` | Handles original file storage for rescan. Supports `filesystem` mode and `database` (GridFS) mode, controlled by `FILE_STORAGE_MODE` env var. |
| `heavy_api.py` | Thin client wrapper for calling Heavy API. Used internally (not the primary caller — `ocr_routes.py` handles the main Heavy API call logic directly). |

### Heavy API (Hugging Face Space)

| File | Purpose |
|---|---|
| `app.py` | Self-contained FastAPI app. Contains all extraction logic, confidence calculator, YOLO crops, docTR OCR, Tesseract fallback, and all 3 table extraction methods for Marksheet. Exposes `/api/scan`, `/health`, `/api/docs`. |

---

## 4. Database Schema

MongoDB Atlas. Database name: `smart_form_db` (configurable via `MONGODB_DATABASE`).

### 4.1 Collections Overview

| Collection | Purpose | Primary Key |
|---|---|---|
| `scans` | Initial scan results | `scan_id` (UUID) |
| `rescans` | Rescan results linked to original scan | `rescan_id` (UUID) |
| `submissions` | User-verified and submitted data | `submission_id` (UUID) |
| `edits` | User field edits (draft, not yet submitted) | `edit_id` (UUID) |

---

### 4.2 `scans` Collection

```json
{
  "scan_id": "uuid-string",
  "user_id": "string",              // JWT user_id or "0000" for anonymous
  "filename": "aadhaar.jpg",
  "document_type": "Aadhaar",       // PAN | Aadhaar | Voter ID | Driving Licence | Marksheet
  "fields": {
    "name": {
      "value": "Rahul Sharma",
      "confidence": 88,
      "breakdown": { "tesseract_ocr": 85, "pattern_match": 88, "image_quality": 90, "business_rules": 90 },
      "threshold": 75,
      "status": "PASS"              // PASS | REVIEW | FAIL
    }
    // ... all document fields
  },
  "table": [],                      // Subject rows for Marksheet, empty for others
  "confidence": 87.4,               // Overall weighted confidence
  "raw_text_preview": "...",        // First 30 lines of raw OCR text
  "meta": {
    "raw_ocr_data": {
      "tesseract_text": "...",
      "text_length": 450,
      "tesseract_confidence": { "overall_stats": { "average": 82.1, "min": 30, "max": 96 } }
    },
    "image_quality": {
      "quality_score": 78.5,
      "issues": [],
      "needs_preprocessing": false
    },
    "processing_info": {
      "is_pdf": false,
      "filename": "aadhaar.jpg",
      "classification_method": "smart_v2"
    }
  },
  "extraction_summary": {
    "overall_confidence": 87.4,
    "high_confidence": { "count": 5 },
    "medium_confidence": { "count": 1 },
    "low_confidence": { "count": 0 }
  },
  "status": "scanned",              // scanned | submitted | processing | failed
  "rescan_count": 0,
  "storage_metadata": {
    "stored": true,
    "storage_mode": "filesystem",   // filesystem | database
    "filename": "aadhaar.jpg"
  },
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**Indexes:** `scan_id` (unique), `user_id`, `document_type`, `created_at` (desc), `status`

---

### 4.3 `rescans` Collection

```json
{
  "rescan_id": "uuid-string",
  "original_scan_id": "uuid-string",    // Reference to parent scan
  "user_id": "string",
  "filename": "aadhaar.jpg",
  "document_type": "Aadhaar",
  "fields": { /* same structure as scans */ },
  "table": [],
  "confidence": 91.2,
  "raw_text_preview": "...",
  "meta": { /* same structure as scans */ },
  "extraction_summary": { /* same structure */ },
  "status": "scanned",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**Indexes:** `rescan_id` (unique), `original_scan_id`, `user_id`, `created_at` (desc)

---

### 4.4 `submissions` Collection

```json
{
  "submission_id": "uuid-string",
  "scan_id": "uuid-string",
  "rescan_id": "uuid-string | null",    // Set if submitted after a rescan
  "edit_id": "uuid-string | null",      // Set if submitted from an edit
  "user_id": "string",
  "document_type": "Aadhaar",
  "verified_fields": {
    "name": { "value": "Rahul Sharma", "confidence": 88 }
    // user-corrected or as-extracted fields
  },
  "table": [],
  "user_corrections": {
    "name": { "original": "Rahul Sharms", "corrected": "Rahul Sharma" }
  },
  "final_confidence": 91.2,
  "extraction_summary": { /* same structure */ },
  "title": "My Aadhaar Card",           // User-set document title (optional)
  "status": "submitted",                // pending | submitted | verified | rejected
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**Indexes:** `submission_id` (unique), `scan_id`, `user_id`, `edit_id`, `created_at` (desc), `status`

---

### 4.5 `edits` Collection

Draft edits saved before the user confirms submission.

```json
{
  "edit_id": "uuid-string",
  "scan_id": "uuid-string",
  "user_id": "string",
  "document_type": "PAN",
  "edited_fields": {
    "name": { "value": "Corrected Name", "confidence": 88 }
  },
  "table": [],
  "user_corrections": {
    "name": { "original": "Wrong Name", "corrected": "Corrected Name" }
  },
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**Indexes:** `edit_id` (unique), `scan_id`, `user_id`, `created_at` (desc)  
**Behavior:** `save_or_update_edit()` is a PUT operation — only one edit per `(scan_id, user_id)` pair exists at any time.

---

### 4.6 Document Field Schemas (from `models.py`)

```python
DOCUMENT_FIELD_SCHEMA = {
    "PAN":              ["pan", "name", "father_name", "dob"],
    "Aadhaar":          ["aadhaar_number", "name", "dob", "gender", "father_name", "address", "mobile"],
    "Voter ID":         ["voter_id", "name", "father_name", "husband_name", "dob", "gender", "address"],
    "Driving Licence":  ["dl_number", "name", "dob", "issue_date", "valid_till", "father_name", "address"],
    "Marksheet":        ["student_name", "father_name", "mother_name", "school_name", "dob", "roll_no", "year", "cgpa"]
}
```

`normalize_fields()` ensures every field in the schema is present in the API response, setting missing ones to `{"value": null, "confidence": 0}`.

---

## 5. Confidence Scoring Logic

Confidence is calculated at two levels: **per field** and **overall document**.

### 5.1 Per-Field Hybrid Confidence (`confidence_calculator.py`)

Each field's final confidence is a weighted combination of four components:

| Component | Weight | Description |
|---|---|---|
| `tesseract_ocr` | 30% | Raw Tesseract word-level confidence from `image_to_data()` |
| `pattern_match` | 40% | Regex validation score — how well the extracted value matches the expected format |
| `image_quality` | 15% | Image quality score from `image_preprocessor.check_image_quality()` |
| `business_rules` | 15% | Domain-specific validation (date ranges, name character ratios, etc.) |

```
final_confidence = (tesseract * 0.30) + (pattern * 0.40) + (quality * 0.15) + (business * 0.15)
```

**Pattern match confidence examples:**

| Field | Full match | Partial match | No match |
|---|---|---|---|
| `aadhaar_number` | 98% (12 digits exact) | 75% (10–14 digits) | 40% |
| `pan` | 98% (`[A-Z]{5}[0-9]{4}[A-Z]`) | 70% (10 chars alphanumeric) | 35% |
| `dob` | 95% (valid DD/MM/YYYY) | 40% | — |
| `gender` | 99% (male/female/transgender) | 50% | — |
| `name` | 88% (2–5 words, 90%+ alpha ratio) | 60–75% | 30–35% |

**Cross-field validation** is applied after the base confidence is calculated. Mismatches (e.g., DOB in the future, gender/name inconsistency) apply a `confidence_adjustment` penalty to the relevant fields.

---

### 5.2 Field Thresholds and Status

Each field has an individual threshold from `FIELD_THRESHOLDS`:

```
PASS    → confidence >= threshold
REVIEW  → confidence >= (threshold - 10)
FAIL    → confidence < (threshold - 10)
```

Key thresholds (post-lowering to reduce false FAILs):

| Field | Threshold |
|---|---|
| ID fields (aadhaar, pan, voter_id, dl_number) | 75 |
| name, father_name | 75 |
| dob, issue_date, valid_till, cgpa | 70 |
| mobile | 80 |
| gender, school_name, year, roll_no | 75 |

---

### 5.3 Overall Document Confidence

The overall confidence is a **weighted average** of per-field confidences, where higher-importance fields carry more weight:

```python
importance_weights = {
    "aadhaar_number": 1.5,  "pan": 1.5,  "voter_id": 1.5,  "dl_number": 1.5,
    "name": 1.3,  "student_name": 1.3,  "dob": 1.2,
    "father_name": 1.0,  "mobile": 1.0,  "roll_no": 1.0,
    "address": 0.9,  "mother_name": 0.9,
    "school_name": 0.8,  "issue_date": 0.8,  "valid_till": 0.8,  "year": 0.8,
    "gender": 0.7,  "cgpa": 0.7
}
```

Only fields that **have a value** are included in the weighted sum. Empty fields contribute 0 but do not drag down the average.

---

### 5.4 Marksheet Table Penalty

For Marksheet documents, a subject table penalty is applied to the overall confidence if the table extraction is insufficient:

| Subjects extracted | Multiplier applied |
|---|---|
| 0 | × 0.60 (−40%) |
| 1–2 | × 0.75 (−25%) |
| 3–4 | × 0.90 (−10%) |
| 5+ | No penalty |

---

### 5.5 Confidence Categories

| Category | Range |
|---|---|
| High | ≥ 85% |
| Medium | 68% – 84% |
| Low | < 68% |

The `suggest_rescan` flag is set to `true` in `metadata` if: `overall_confidence < 70` OR 3+ fields are FAIL/REVIEW.

---

### 5.6 Heavy API Confidence (app.py)

The Heavy API uses a slightly different formula: `(tesseract_ocr * 0.40) + (pattern_match * 0.60)`, with an `+8` boost applied to fields where `overall_conf > 68`. It also applies a `+10–15` extraction rate boost based on how many fields were successfully extracted, and a `−20` penalty per missing critical field (e.g., `aadhaar_number`, `name`).

---

## 6. API Reference

**Base URL:** `http://localhost:8000/api`  
**Authentication:** `Authorization: Bearer <JWT>` (optional on all endpoints)  
**Content-Type:** `multipart/form-data` for file uploads, `application/json` for JSON body endpoints

---

### `POST /api/scan`

Scan a document. Tries Heavy API first (143s timeout, 1 retry on 5xx), falls back to Light API automatically.

**Request (multipart/form-data):**

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File | Yes | `jpg`, `jpeg`, `png`, or `pdf`. Max 16MB. |
| `auto_submit` | string | No | `"true"` to auto-submit after scan. Default `"false"`. |

**Response (200):**

```json
{
  "scan_id": "uuid",
  "user_id": "string",
  "success": true,
  "document_type": "Aadhaar",
  "filename": "aadhaar.jpg",
  "fields": {
    "aadhaar_number": { "value": "9876 5432 1012", "confidence": 95, "breakdown": {...}, "threshold": 75, "status": "PASS" },
    "name": { "value": "Rahul Sharma", "confidence": 88, "breakdown": {...}, "threshold": 75, "status": "PASS" },
    "dob": { "value": "12/08/1995", "confidence": 91, "breakdown": {...}, "threshold": 70, "status": "PASS" },
    "gender": { "value": "Male", "confidence": 99, "breakdown": {...}, "threshold": 75, "status": "PASS" },
    "father_name": { "value": "Suresh Sharma", "confidence": 80, "breakdown": {...}, "threshold": 75, "status": "PASS" },
    "address": { "value": "123, MG Road, Pune - 411001", "confidence": 72, "breakdown": {...}, "threshold": 75, "status": "REVIEW" },
    "mobile": { "value": null, "confidence": 0, "breakdown": {...}, "threshold": 80, "status": "FAIL" }
  },
  "table": [],
  "message": "Document scanned successfully (Strategy: heavy_only)",
  "confidence": 87.4,
  "extraction_summary": {
    "overall_confidence": 87.4,
    "high_confidence": { "count": 4 },
    "medium_confidence": { "count": 2 },
    "low_confidence": { "count": 1 }
  },
  "meta": { ... }
}
```

**Error responses:**

| Code | Reason |
|---|---|
| 400 | No file / empty file / empty filename |
| 400 | Invalid file type (not jpg/jpeg/png/pdf) |
| 413 | File too large (>16MB) |
| 500 | Both Heavy and Light APIs failed |

---

### `POST /api/rescan/<scan_id>`

Re-process a previously scanned document. Uses the stored file if `ENABLE_FILE_STORAGE=true`; otherwise requires a new file upload. Ownership check: only the original user (or anonymous `"0000"`) can rescan.

**URL param:** `scan_id` — the UUID from the original scan.

**Request (multipart/form-data):**

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File | Conditional | Required only if original file was not stored. |
| `auto_submit` | string | No | `"true"` to auto-submit. |

**Response (200):**

```json
{
  "rescan_id": "uuid",
  "scan_id": "original-uuid",
  "user_id": "string",
  "success": true,
  "document_type": "PAN",
  "filename": "pan.jpg",
  "fields": { ... },
  "table": [],
  "confidence": 91.2,
  "extraction_summary": { ... },
  "message": "Document rescanned successfully (Strategy: heavy_only)",
  "meta": { ... }
}
```

**Error responses:** 403 (not owner), 404 (scan not found / stored file missing)

---

### `PUT /api/edit/<scan_id>`

Save user's edited fields as a draft. Only one edit per `(scan_id, user_id)` is stored — subsequent PUTs overwrite the previous edit.

**Request body (JSON):**

```json
{
  "document_type": "Aadhaar",
  "edited_fields": {
    "name": { "value": "Corrected Name", "confidence": 88 }
  },
  "table": [],
  "user_corrections": {
    "name": { "original": "Wrong Name", "corrected": "Corrected Name" }
  }
}
```

**Response (200):**

```json
{
  "success": true,
  "edit_id": "uuid",
  "scan_id": "uuid",
  "message": "Edit saved successfully"
}
```

---

### `GET /api/edit/<scan_id>`

Retrieve the current draft edit for a scan.

**Response (200):**

```json
{
  "success": true,
  "edit_id": "uuid",
  "scan_id": "uuid",
  "document_type": "Aadhaar",
  "edited_fields": { ... },
  "table": [],
  "user_corrections": { ... },
  "created_at": "ISO date",
  "updated_at": "ISO date"
}
```

**Error:** 404 if no edit exists for this scan.

---

### `POST /api/submit/<scan_id>`

Submit verified data permanently. Can optionally reference an `edit_id` to submit from a saved edit.

**Request body (JSON):**

```json
{
  "document_type": "Aadhaar",
  "verified_fields": { ... },
  "table": [],
  "user_corrections": { ... },
  "final_confidence": 91.2,
  "edit_id": "uuid (optional)"
}
```

**Response (200):**

```json
{
  "submission_id": "uuid",
  "scan_id": "uuid",
  "user_id": "string",
  "success": true,
  "status": "submitted",
  "document_type": "Aadhaar",
  "verified_fields": { ... },
  "table": [],
  "message": "Document submitted successfully",
  "extraction_summary": { ... }
}
```

---

### `POST /api/title`

Set or update a custom title for a submitted document.

**Request body (JSON):**

```json
{
  "scan_id": "uuid",
  "title": "My Aadhaar Card"
}
```

**Response (200):**

```json
{
  "success": true,
  "scan_id": "uuid",
  "submission_id": "uuid",
  "title": "My Aadhaar Card",
  "message": "Title updated successfully"
}
```

---

### `GET /api/title/<scan_id>`

Retrieve the title for a submitted document.

**Response (200):**

```json
{
  "success": true,
  "scan_id": "uuid",
  "submission_id": "uuid",
  "title": "My Aadhaar Card"
}
```

---

### `GET /api/my-scans`

Get all scans for the authenticated user. Anonymous users (`user_id="0000"`) get all anonymous scans.

**Query params:** `limit` (default 100), `skip` (default 0)

**Response (200):**

```json
{
  "success": true,
  "user_id": "string",
  "count": 5,
  "scans": [ { /* scan documents */ } ]
}
```

---

### `GET /api/health`

Returns server health and statistics.

**Response (200):**

```json
{
  "status": "healthy",
  "service": "OCR API",
  "version": "6.0.0 - Heavy Priority",
  "mode": "heavy_priority",
  "strategy": "Heavy first (143s timeout) → Light fallback",
  "heavy_api": "configured",
  "database": {
    "status": "connected",
    "total_scans": 120,
    "total_submissions": 45
  },
  "features": {
    "heavy_priority": true,
    "light_fallback": true,
    "jwt_auth": true,
    "user_tracking": true,
    "file_storage": true
  }
}
```

---

### `GET /api/docs`

Returns full API documentation as JSON (auto-generated from route handlers).

---

### Heavy API Endpoints (Hugging Face Space)

#### `POST /api/scan`

Same interface as Light API scan. Accepts `file`, `auto_submit`, `rawdata` (optional — include raw OCR text in response).

#### `GET /health`

```json
{
  "status": "healthy",
  "service": "Complete OCR API",
  "version": "2.0.0",
  "models": {
    "yolo": true,
    "doctr": true,
    "tesseract": true
  }
}
```

#### `GET /api/docs`

Returns supported documents, endpoint descriptions, and parameter docs.

---

## 7. Setup & Deployment

### 7.1 Environment Variables

Create a `.env` file (copy from `.env.docker`):

```env
# MongoDB
MONGODB_URI=mongodb+srv://<user>:<pass>@cluster.mongodb.net/smart_form_db?retryWrites=true&w=majority
MONGODB_DATABASE=smart_form_db

# Flask
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ALGORITHM=HS256
JWT_TOKEN_EXPIRY_DAYS=7

# OCR
TESSERACT_PATH=/usr/bin/tesseract      # Linux/Docker
# TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe  # Windows
OCR_DPI=300
OCR_CONFIDENCE_THRESHOLD=0.2

# Heavy API
HEAVY_API_URL=https://your-hf-space.hf.space
CONFIDENCE_THRESHOLD=70

# File Storage
ENABLE_FILE_STORAGE=True
FILE_STORAGE_MODE=database             # filesystem | database
FILE_RETENTION_DAYS=1

# Server
HOST=0.0.0.0
PORT=8000
FLASK_ENV=production

# YOLO (disabled by default to save memory on Light API)
ENABLE_YOLO=False
```

---

### 7.2 Tesseract Installation

**Windows:**

```bash
# 1. Download installer from:
#    https://github.com/UB-Mannheim/tesseract/wiki
# 2. Install and note the path
# 3. Set in .env:
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
```

**Linux (Ubuntu/Debian):**

```bash
sudo apt update
sudo apt install tesseract-ocr -y
sudo apt install tesseract-ocr-eng -y
tesseract --version   # verify
# Path auto-detected as /usr/bin/tesseract — no .env change needed
```

**Docker:**

Tesseract is installed inside the container via `Dockerfile`. Path is hardcoded to `/usr/bin/tesseract` when `IN_DOCKER=True` is detected. No manual config needed.

---

### 7.3 Run with Docker

```bash
# Build
docker build -t smartfill .

# Run
docker run -p 8000:8000 --env-file .env smartfill

# Or with inline env vars
docker run -p 8000:8000 \
  -e MONGODB_URI="..." \
  -e HEAVY_API_URL="..." \
  smartfill
```

---

### 7.4 Run Locally (Without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Install spaCy model
python -m spacy download en_core_web_sm

# Run
python server_production.py
```

Server starts at `http://localhost:8000`.

---

### 7.5 Python Dependencies (Key)

| Package | Purpose |
|---|---|
| `Flask`, `flask-cors`, `Waitress` | Web framework and WSGI server |
| `pytesseract`, `Pillow` | OCR and image handling |
| `opencv-python-headless` | Image preprocessing (blur detection, deskew) |
| `pdf2image`, `pdfplumber` | PDF to image conversion and table extraction |
| `pymongo` | MongoDB driver |
| `PyJWT` | JWT token handling |
| `spacy` | NLP for name/field extraction |
| `python-dotenv` | `.env` file loading |
| `camelot-py[cv]` | PDF table extraction (fallback) |

Heavy API additionally uses `fastapi`, `uvicorn`, `ultralytics` (YOLO), `python-doctr`, `torch`, `torchvision`.

---

### 7.6 Important Config Notes

- `ENABLE_YOLO=False` by default on the Light API to avoid the 1.6GB `ultralytics` dependency in Docker. YOLO runs only on the Hugging Face Heavy API.
- `FILE_STORAGE_MODE=database` stores original files in MongoDB GridFS — preferred for Docker as it avoids filesystem mount issues. `filesystem` mode saves to `./uploads/`.
- `FILE_RETENTION_DAYS=1` in production to avoid accumulating uploaded files.
- The Heavy API cold start on Hugging Face can take **30–60 seconds** on the first request after inactivity. This is normal for HF Spaces on the free tier.