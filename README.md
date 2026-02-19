# SmartFill

> 🔗 **Project Link:** https://smart-form-frontend-gold.vercel.app/
> 🤗 **Hugging Face Space (Heavy API):** (https://huggingface.co/spaces/luffy140/Enhanced_OCR_API)
> 👨‍💻 **Built by:** Kottangi Charan — Intern at [Coursevita](https://coursevita.com), working on the OCR domain as part of the SmartFill project.

---

## What is SmartFill?

SmartFill is an intelligent OCR-powered document extraction system that automatically reads and extracts key information from Indian identity and academic documents. It uses a dual-API architecture — a lightweight Flask API for fast processing and a heavy AI-powered API hosted on Hugging Face for deeper, model-based extraction. The extracted data is returned in structured JSON format with confidence scores for every field.

---

## Supported Documents

| Document | Key Fields Extracted |
|---|---|
| 🪪 Aadhaar Card | Name, DOB, Gender, Aadhaar Number, Address, Father Name |
| 🗂️ PAN Card | Name, PAN Number, DOB, Father Name |
| 🗳️ Voter ID | Voter ID, Name, Father Name, DOB, Gender |
| 🚗 Driving Licence | DL Number, Name, DOB, Father Name, Address, Valid Till |
| 📄 Marksheet | Student Name, Roll No, School Name, Father Name, DOB, CGPA, Subjects Table |

---

## Architecture

### 🟢 Light API (Main Server — Flask)
The Light API runs on your own server via Docker using Flask. It handles document upload, Tesseract OCR, image preprocessing, field extraction using regex patterns, and confidence scoring. It is fast and suitable for most standard-quality document images.

### 🔴 Heavy API (Hugging Face Space — FastAPI)
The Heavy API is hosted separately on a Hugging Face Space and uses FastAPI. It runs YOLO for document region cropping, docTR for deep learning-based OCR, and Tesseract as a fallback — making it ideal for low-quality or complex documents. The Light API calls the Heavy API automatically when needed via `HEAVY_API_URL`.

---

## Models Used (Heavy API)

| Model | Purpose |
|---|---|
| **YOLO (YOLOv8)** | Detects and crops document regions from the image |
| **docTR** | Deep learning OCR engine for accurate text recognition |
| **Tesseract** | Fallback OCR engine when docTR is unavailable |
| **pdfplumber** | Extracts tables and text from PDF documents |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Light API | Python, Flask, Waitress, pytesseract, OpenCV, pdfplumber, pdf2image |
| Heavy API | Python, FastAPI, Uvicorn, YOLOv8, docTR, pytesseract, pdfplumber |
| Database | MongoDB Atlas |
| Auth | JWT (PyJWT) |
| Containerization | Docker |
| Heavy API Hosting | Hugging Face Spaces |

---

## Tesseract Setup

Tesseract is required for both local development and Docker. Follow the guide for your OS.

### 🪟 Windows

1. Download the installer from the official repo:  
   👉 https://github.com/UB-Mannheim/tesseract/wiki

2. Install it — default path will be:  
   `C:\Program Files\Tesseract-OCR\tesseract.exe`

3. Set the path in your `.env` file:
   ```env
   TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
   ```

4. Or update `config.py` directly for Windows:
   ```python
   TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
   ```

> ⚠️ The project default in `config.py` uses `E:\tesseract\tesseract.exe` — change this to match your install path.

---

### 🐧 Linux (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install tesseract-ocr -y
sudo apt install tesseract-ocr-eng -y   # English language pack

# Verify installation
tesseract --version
```

The path will automatically be `/usr/bin/tesseract` — no extra config needed.

---

### 🐳 Docker

Tesseract is installed automatically inside the Docker container via the `Dockerfile`. No manual setup is needed. The path is hardcoded to `/usr/bin/tesseract` when running in Docker.

```dockerfile
# Already handled in Dockerfile
RUN apt-get install -y tesseract-ocr
```

---

## Setup & Run

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd smartfill
```

### 2. Configure Environment

Copy the example env file and fill in your values:

```bash
cp .env.docker .env
```

Key variables to set in `.env`:

```env
MONGODB_URI=your_mongodb_connection_string
MONGODB_DATABASE=smart_form_db
TESSERACT_PATH=/usr/bin/tesseract
HEAVY_API_URL=https://your-hf-space-url.hf.space
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
```

### 3. Run with Docker

```bash
docker build -t smartfill .
docker run -p 8000:8000 --env-file .env smartfill
```

### 4. Run Locally (Without Docker)

```bash
pip install -r requirements.txt
python server_production.py
```

The server starts at `http://localhost:8000`

---

## How to Use

### API Endpoint

```
POST /api/scan
Content-Type: multipart/form-data
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file` | File | ✅ Yes | Image or PDF of the document |
| `auto_submit` | string | No | `true` / `false` |
| `rawdata` | string | No | `true` to include raw OCR text |

---

### Example — Aadhaar Card Scan

**Request (curl):**

```bash
curl -X POST http://localhost:8000/api/scan \
  -F "file=@aadhaar.jpg" \
  -F "auto_submit=false" \
  -F "rawdata=false"
```

**Response (JSON):**

```json
{
  "success": true,
  "scan_id": "a3f2c891-12d4-4b6e-9f3a-0c8e7d2b1a45",
  "filename": "aadhaar.jpg",
  "document_type": "Aadhaar",
  "confidence": 87.4,
  "confidence_category": "High",
  "fields": {
    "name": {
      "value": "Rahul Sharma",
      "confidence": 91.2,
      "confidence_category": "High",
      "breakdown": {
        "tesseract_ocr": 88.0,
        "pattern_match": 75.0
      },
      "threshold": 75,
      "status": "PASS"
    },
    "aadhaar_number": {
      "value": "9876 5432 1012",
      "confidence": 95.0,
      "confidence_category": "High",
      "breakdown": {
        "tesseract_ocr": 90.0,
        "pattern_match": 98.0
      },
      "threshold": 75,
      "status": "PASS"
    },
    "dob": {
      "value": "12/08/1995",
      "confidence": 88.6,
      "confidence_category": "High",
      "breakdown": {
        "tesseract_ocr": 85.0,
        "pattern_match": 90.0
      },
      "threshold": 75,
      "status": "PASS"
    },
    "gender": {
      "value": "Male",
      "confidence": 82.0,
      "confidence_category": "High",
      "breakdown": {
        "tesseract_ocr": 80.0,
        "pattern_match": 75.0
      },
      "threshold": 75,
      "status": "PASS"
    },
    "father_name": {
      "value": "Suresh Sharma",
      "confidence": 79.5,
      "confidence_category": "High",
      "breakdown": {
        "tesseract_ocr": 76.0,
        "pattern_match": 75.0
      },
      "threshold": 75,
      "status": "PASS"
    },
    "address": {
      "value": "123, MG Road, Pune, Maharashtra - 411001",
      "confidence": 72.3,
      "confidence_category": "Medium",
      "breakdown": {
        "tesseract_ocr": 70.0,
        "pattern_match": 75.0
      },
      "threshold": 75,
      "status": "FAIL"
    }
  },
  "extraction_summary": {
    "overall_confidence": 87.4,
    "high_confidence": { "count": 5 },
    "medium_confidence": { "count": 1 },
    "low_confidence": { "count": 0 }
  },
  "table": [],
  "message": "Document scanned (enhanced marksheet extraction)"
}
```

---

## Health Check

```bash
curl http://localhost:8000/health
```

---

## Notes

- The Heavy API on Hugging Face may take **30–60 seconds** on first call (cold start).
- Supported file formats: `jpg`, `jpeg`, `png`, `pdf`.
- Max file size: **16 MB**.
- If `HEAVY_API_URL` is not set in `.env`, the system falls back to the Light API automatically.