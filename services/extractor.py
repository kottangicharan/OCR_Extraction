"""
Complete OCR Extractor Service - Enhanced with Improved Classification
Backward compatible: Old classify_document_type() unchanged, new v2 added
"""
from services.image_preprocessor import preprocess_image, check_image_quality
import io
import re
import os
import tempfile
from typing import List, Dict, Any, Tuple, Optional
import pytesseract
from PIL import Image
import numpy as np
from config import Config

TESSERACT_CONFIGS = {
    'default': r'--oem 3 --psm 6',
    'single_line': r'--oem 3 --psm 7',
    'single_word': r'--oem 3 --psm 8',
    'number_only': r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789',
    'alphanum': r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
}

pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH

# ==================== OPTIONAL IMPORTS ====================
try:
    from pdf2image import convert_from_bytes
    HAVE_PDF2IMAGE = True
except ImportError:
    HAVE_PDF2IMAGE = False

try:
    import pdfplumber
    HAVE_PDFPLUMBER = True
except ImportError:
    HAVE_PDFPLUMBER = False

try:
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    ocr_model = ocr_predictor(pretrained=True).to("cpu")
    HAVE_DOCTR = True
except ImportError:
    HAVE_DOCTR = False
    ocr_model = None

try:
    from ultralytics import YOLO
    HAVE_YOLO = Config.ENABLE_YOLO
    if HAVE_YOLO:
        yolo_model = YOLO(Config.YOLO_WEIGHTS)
    else:
        yolo_model = None
except ImportError:
    HAVE_YOLO = False
    yolo_model = None

try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False


# ==================== NEW: IMPROVED CLASSIFICATION V2 ====================

def classify_document_type_v2(text: str) -> Dict[str, Any]:
    """
    Improved classification with confidence scoring
    Returns: {"document_type": "PAN", "confidence": 95, "scores": {...}}
    """
    if not text or len(text.strip()) == 0:
        return {"document_type": "Unknown", "confidence": 0, "scores": {}}
    
    txt = text.upper()
    scores = {
        "PAN": 0,
        "Aadhaar": 0,
        "Voter ID": 0,
        "Driving Licence": 0,
        "Marksheet": 0
    }
    
    # ========== PAN SCORING ==========
    if re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", txt):
        scores["PAN"] += 50
    if "INCOME TAX" in txt[:500]:
        scores["PAN"] += 40
    if "PERMANENT ACCOUNT" in txt[:500]:
        scores["PAN"] += 30
    if "GOVT. OF INDIA INCOME TAX" in txt:
        scores["PAN"] += 20
    if re.search(r"\bFATHER'?S? NAME\b", txt):
        scores["PAN"] += 15
    if re.search(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b", txt):
        scores["PAN"] += 10
    # Penalties
    if "AADHAAR" in txt or "ELECTION" in txt or "DRIVING" in txt:
        scores["PAN"] -= 30
    if "APPLICATION" in txt or "FORM" in txt[:300]:
        scores["PAN"] -= 20
    
    # ========== AADHAAR SCORING ==========
    if re.search(r"\b\d{4}\s*\d{4}\s*\d{4}\b", txt):
        scores["Aadhaar"] += 50
    if "UIDAI" in txt[:500]:
        scores["Aadhaar"] += 40
    if "AADHAAR" in txt or "AADHAR" in txt:
        scores["Aadhaar"] += 30
    if "UNIQUE IDENTIFICATION" in txt:
        scores["Aadhaar"] += 25
    if "GOVERNMENT OF INDIA" in txt:
        scores["Aadhaar"] += 20
    if re.search(r"\b(S/O|D/O|C/O)\b", txt):
        scores["Aadhaar"] += 15
    if "VID" in txt:
        scores["Aadhaar"] += 10
    # Penalties
    if "INCOME TAX" in txt or "ELECTION" in txt:
        scores["Aadhaar"] -= 30
    if "ENROLMENT" in txt or "APPLICATION" in txt[:300]:
        scores["Aadhaar"] -= 25
    
    # ========== VOTER ID SCORING ==========
    if re.search(r"\b[A-Z]{3,4}[0-9]{6,10}\b", txt):
        scores["Voter ID"] += 50
    if "ELECTION COMMISSION" in txt[:500]:
        scores["Voter ID"] += 40
    if "ELECTORAL" in txt[:500]:
        scores["Voter ID"] += 30
    if "ELECTOR" in txt:
        scores["Voter ID"] += 25
    if re.search(r"\bEPIC\s*NO\b", txt):
        scores["Voter ID"] += 20
    if re.search(r"\bPART\s*NO\b", txt):
        scores["Voter ID"] += 15
    # Penalties
    if "AADHAAR" in txt or "INCOME TAX" in txt or "DRIVING" in txt:
        scores["Voter ID"] -= 30
    
    # ========== DRIVING LICENCE SCORING ==========
    if re.search(r"\b[A-Z]{2}[0-9O]{6,20}\b", txt):
        scores["Driving Licence"] += 50
    if "DRIVING LICENCE" in txt[:500] or "DRIVING LICENSE" in txt[:500]:
        scores["Driving Licence"] += 40
    if "TRANSPORT" in txt[:500]:
        scores["Driving Licence"] += 30
    if re.search(r"\bVALID\s*(TILL|UPTO)\b", txt):
        scores["Driving Licence"] += 25
    if "MOTOR VEHICLE" in txt:
        scores["Driving Licence"] += 20
    if re.search(r"\b(LMV|MCWG|TRANS)\b", txt):
        scores["Driving Licence"] += 15
    # Penalties
    if "AADHAAR" in txt or "INCOME TAX" in txt or "ELECTION" in txt:
        scores["Driving Licence"] -= 30
    if "LEARNER" in txt or "APPLICATION" in txt[:300]:
        scores["Driving Licence"] -= 25
    
    # ========== MARKSHEET SCORING ==========
    if re.search(r"\b(A1|A2|B1|B2|C1|C2|GRADE|CGPA)\b", txt):
        scores["Marksheet"] += 50
    if "BOARD OF" in txt[:500]:
        scores["Marksheet"] += 40
    if "EXAMINATION" in txt[:500]:
        scores["Marksheet"] += 35
    if "MARKS" in txt:
        scores["Marksheet"] += 30
    if "MARKSHEET" in txt:
        scores["Marksheet"] += 25
    if re.search(r"\b(SCHOOL|COLLEGE|INSTITUTE)\b", txt):
        scores["Marksheet"] += 20
    if re.search(r"\bROLL\s*NO\b", txt):
        scores["Marksheet"] += 20
    if "SUBJECT" in txt:
        scores["Marksheet"] += 15
    # Penalties
    if "SAMPLE PAPER" in txt or "PRACTICE" in txt:
        scores["Marksheet"] -= 30
    
    # Ensure no negative scores
    scores = {k: max(0, v) for k, v in scores.items()}
    
    # Find best match
    if max(scores.values()) == 0:
        return {"document_type": "Unknown", "confidence": 0, "scores": scores}
    
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    
    # Convert score to confidence (0-100)
    if best_score >= 100:
        confidence = min(95, 70 + (best_score - 70) * 0.5)
    elif best_score >= 70:
        confidence = best_score
    elif best_score >= 50:
        confidence = 50 + (best_score - 50) * 0.5
    else:
        confidence = best_score
    
    return {
        "document_type": best_type,
        "confidence": int(confidence),
        "scores": scores
    }


# ==================== OLD CLASSIFICATION (UNCHANGED) ====================

def classify_document_type(text: str) -> str:
    """OLD METHOD - UNCHANGED for backward compatibility"""
    if not text or len(text.strip()) == 0:
        return "Unknown"
    
    txt = text.upper()
    
    if re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", txt):
        return "PAN"
    if any(keyword in txt for keyword in ["INCOME TAX", "PERMANENT ACCOUNT"]):
        return "PAN"
    
    if re.search(r"\b\d{4}\s*\d{4}\s*\d{4}\b", txt):
        if any(keyword in txt for keyword in ["AADHAAR", "AADHAR", "UNIQUE IDENTIFICATION", "UIDAI"]):
            return "Aadhaar"
    
    if any(keyword in txt for keyword in ["DRIVING LICENCE", "DRIVING LICENSE", "TRANSPORT AUTHORITY"]):
        return "Driving Licence"
    
    if any(keyword in txt for keyword in ["ELECTION COMMISSION", "ELECTOR", "EPIC NO"]):
        return "Voter ID"
    
    if any(keyword in txt for keyword in ["MARKSHEET", "MARKS MEMO", "GRADE POINT", "CGPA", "BOARD OF"]):
        return "Marksheet"
    
    return "Unknown"


# ==================== SMART CLASSIFICATION (MAIN ENTRY POINT) ====================

def classify_document_smart(text: str) -> str:
    """
    Smart classification: Use v2 if confident (>=70%), else fallback to v1
    THIS IS CALLED BY process_document()
    """
    v2_result = classify_document_type_v2(text)
    
    if v2_result["confidence"] >= 70:
        print(f"✅ V2 Classification: {v2_result['document_type']} ({v2_result['confidence']}%)")
        return v2_result["document_type"]
    
    old_result = classify_document_type(text)
    print(f"⚠️ V1 Fallback: {old_result} (V2 was {v2_result['confidence']}% confident)")
    
    if old_result == "Unknown" and v2_result["confidence"] >= 50:
        print(f"   → Using V2 result: {v2_result['document_type']}")
        return v2_result["document_type"]
    
    return old_result


# ==================== HELPER FUNCTIONS ====================

def clean_extracted_fields(fields: dict) -> dict:
    """Remove None and empty values"""
    if not isinstance(fields, dict):
        return {}
    return {k: v.strip() if isinstance(v, str) else v 
            for k, v in fields.items() 
            if v is not None and (not isinstance(v, str) or v.strip())}

def safe_split_lines(text: str) -> List[str]:
    return [ln.strip() for ln in re.split(r"[\r\n]+", text or "") if ln.strip()]

def clean_value(val: str) -> Optional[str]:
    if not val:
        return None
    return re.sub(r"^[\s,.:;_\-]+|[\s,.:;_\-]+$", "", val).strip()

def flatten_doctr_blocks(blocks: List[List[str]]) -> List[str]:
    out = []
    for block in blocks or []:
        if isinstance(block, (list, tuple)):
            out.extend([line.strip() for line in block if line and isinstance(line, str)])
        elif isinstance(block, str):
            out.append(block.strip())
    return out

def is_probable_name(text: str) -> bool:
    """Check if text looks like a real name"""
    if not text or re.fullmatch(r"[-——]+", text) or len(text.strip(" .'-")) < 3:
        return False
    return (
        bool(re.fullmatch(r"[A-Za-z .'-]+", text)) and
        3 < len(text) < 50 and
        not any(kw in text.lower() for kw in ['government', 'india', 'authority', 
                'unique', 'identification', 'number', 'aadhaar', 'address', 
                'pin', 'code', 'signature', 'enrolment', 'mobile'])
    )

def is_probable_address_line(text: str) -> bool:
    """Check if text looks like address"""
    if not text or len(text) <= 4:
        return False
    return (
        re.search(r'[A-Za-z]', text) and
        not re.fullmatch(r'[0-9 /:,.-]+', text) and
        not any(kw in text.lower() for kw in ['aadhaar', 'signature', 'mobile', 
                'government', 'unique', 'identification', 'enrolment', 
                'your aadhaar no', 'vid', 'pin code'])
    )

def get_right_text(box, boxes, max_y_diff=40) -> Optional[str]:
    """Find text to right of label box"""
    x1, y1, x2, y2 = box['box']
    right_texts = []
    for other in boxes:
        if 'text' in other:
            ox1, oy1, ox2, oy2 = other['box']
            if ox1 > x1 and abs(oy1 - y1) < max_y_diff:
                right_texts.append((ox1, other['text']))
    right_texts.sort(key=lambda x: x[0])
    if right_texts:
        val = right_texts[0][1]
        return re.sub(r"^[\s,.:;_\-]+|[\s,.:;_\-]+$", "", val).strip() if val else None
    return None

def normalize_name(s: str) -> Optional[str]:
    """Normalize name"""
    if not s: return None
    s = re.sub(r'\s+', ' ', s).strip()
    return re.sub(r'[:\-]+$', '', s).strip()


# ==================== OCR FUNCTIONS ====================

def extract_image_ocr(img_bytes: bytes) -> Tuple[str, Optional[dict], Image.Image, List[str]]:
    """Extract OCR from original image"""
    
    # OCR on ORIGINAL image first
    img_original = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    
    try:
        original_tess_text = pytesseract.image_to_string(img_original, config=TESSERACT_CONFIGS['default'])
        original_tess_data = pytesseract.image_to_data(img_original, output_type=pytesseract.Output.DICT, 
                                               config=TESSERACT_CONFIGS['default'])
    except Exception as e:
        original_tess_text, original_tess_data = "", None
    
    # Check quality
    quality_info = check_image_quality(img_bytes)
    
    # Preprocess if needed
    if quality_info.get('needs_preprocessing', True):
        img_bytes_preprocessed = preprocess_image(img_bytes)
        img = Image.open(io.BytesIO(img_bytes_preprocessed)).convert("RGB")
    else:
        img = img_original
    
    # Use original text for extraction
    tess_text = original_tess_text
    tess_data = original_tess_data

    # docTR OCR (optional)
    doctr_lines = []
    if HAVE_DOCTR and ocr_model is not None:
        try:
            from doctr.io import DocumentFile
            doc = DocumentFile.from_images([img_bytes])  # Use original bytes
            result = ocr_model(doc)
            blocks = []
            for page in result.pages:
                for block in page.blocks:
                    blocks.append([" ".join([w.value for w in line.words]) for line in block.lines])
            doctr_lines = flatten_doctr_blocks(blocks)
        except Exception as e:
            print(f"docTR error: {e}")

    # ✅ CRITICAL: Must return 4-tuple
    return tess_text, tess_data, img, doctr_lines

def pdf_bytes_to_images(pdf_bytes: bytes, dpi=300) -> List[Tuple[bytes, int]]:
    if not HAVE_PDF2IMAGE:
        raise RuntimeError("pdf2image not installed")
    
    images = []
    pil_pages = convert_from_bytes(pdf_bytes, dpi=dpi)
    for i, pil in enumerate(pil_pages):
        bio = io.BytesIO()
        pil.save(bio, format='PNG')
        images.append((bio.getvalue(), i + 1))
    return images

def extract_pdf_content(pdf_bytes: bytes) -> Tuple[str, List[List[str]]]:
    if not HAVE_PDFPLUMBER:
        return "", []
    
    tempf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        tempf.write(pdf_bytes)
        tempf.flush()
        tempf.close()
        
        text = ""
        tables = []
        with pdfplumber.open(tempf.name) as pdf:
            page_texts = []
            for page in pdf.pages:
                page_texts.append(page.extract_text() or "")
                try:
                    for pt in page.extract_tables():
                        tables.append(pt)
                except:
                    continue
            text = "\n".join(page_texts)
        return text, tables
    finally:
        try:
            os.unlink(tempf.name)
        except:
            pass




# ==================== FIELD EXTRACTORS  ==============================================def extract_aadhaar_fields(text: str, yolo_output: dict = None, rawdata: bool = False) -> dict:
def extract_aadhaar_fields(text: str, yolo_output: dict = None, rawdata: bool = False) -> dict:
    """Extract Aadhaar card fields - FIXED VERSION"""
    import re
    import string

    fields = {
        "aadhaar_number": None,
        "name": None,
        "dob": None,
        "gender": None,
        "father_name": None,
        "address": None,
        "mobile": None,
    }

    def clean_candidate(s):
        return re.sub(r'[^A-Za-z\s\.\-]', ' ', s).strip()
    
    def clean_address(s):
        return re.sub(r'\s+', ' ', s).strip(' ,.-')

    # Combine all text sources
    combined_text = text or ''
    lines = [ln.strip() for ln in combined_text.splitlines() if ln.strip()]

    if not lines:
        return fields

    # 1. AADHAAR NUMBER
    for line in lines:
        m = re.search(r'\b(\d{4})\s*(\d{4})\s*(\d{4})\b', line)
        if m:
            fields['aadhaar_number'] = ''.join(m.groups())
            break

    # 2. DOB
    for line in lines:
        m = re.search(r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})\b', line)
        if m:
            fields['dob'] = m.group(1)
            break

    # 3. GENDER
    for line in lines:
        if re.search(r'\b(male|female|transgender)\b', line, re.I):
            m = re.search(r'\b(male|female|transgender)\b', line, re.I)
            fields['gender'] = m.group(1).title()
            break

    # 4. MOBILE
    for line in lines:
        m = re.search(r'(?:^|[^\d])([6-9]\d{9})(?:[^\d]|$)', line)
        if m:
            fields['mobile'] = m.group(1)
            break

    # 5. CRITICAL FIX: NAME AND FATHER NAME EXTRACTION
    # Look for C/O, D/O patterns
    for i, line in enumerate(lines):
        line_clean = re.sub(r'[^A-Za-z\s/]', ' ', line).strip()
        
        # Pattern 1: "KOTTANGI CHARAN C/O: Kottangi Satya Ramakrishna"
        match = re.search(r'^([A-Z\s]{5,30})\s+(C/O|D/O|S/O|W/O)[^\w]*([A-Za-z\s]{5,50})$', line, re.I)
        if match:
            name_part = match.group(1).strip()
            father_part = match.group(3).strip()
            
            # Clean names
            name_part = re.sub(r'\s+', ' ', name_part)
            father_part = re.sub(r'\s+', ' ', father_part)
            
            if len(name_part) > 3:
                fields['name'] = name_part.title()
            if len(father_part) > 3:
                fields['father_name'] = father_part.title()
            break
        
        # Pattern 2: Name on one line, C/O on next line
        if i + 1 < len(lines):
            current_line_clean = re.sub(r'[^A-Za-z\s]', ' ', lines[i]).strip()
            next_line_clean = re.sub(r'[^A-Za-z\s]', ' ', lines[i+1]).strip()
            
            # Check if current line looks like a name and next line has C/O
            if (re.match(r'^[A-Z\s]{5,30}$', current_line_clean) and 
                re.search(r'(C/O|D/O|S/O|W/O)', next_line_clean, re.I)):
                
                # Extract name from current line
                fields['name'] = current_line_clean.title()
                
                # Extract father name from next line
                match = re.search(r'(?:C/O|D/O|S/O|W/O)[^\w]*([A-Za-z\s]{5,50})', lines[i+1], re.I)
                if match:
                    father_name = match.group(1).strip()
                    fields['father_name'] = re.sub(r'\s+', ' ', father_name).title()
                break

    # 6. FIXED ADDRESS EXTRACTION
    address_lines = []
    address_started = False
    
    # Look for address markers
    address_markers = ['road', 'street', 'flat', 'house', 'building', 'apartment', 'near', 'opposite']
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Start collecting address when we find address markers or house numbers
        if (any(marker in line_lower for marker in address_markers) or
            re.search(r'\d+[-/]\d+', line) or
            re.search(r'flat no|house no|building', line_lower)):
            address_started = True
        
        # Stop when we hit VTC, PO, or other non-address content
        if address_started and (re.search(r'\b(VTC|PO|District|State|PIN|Mobile|Aadhaar|VID)\b', line, re.I) or
                               'government' in line_lower or 'unique identification' in line_lower):
            break
            
        if address_started:
            # Clean the line and remove name/father name if present
            clean_line = re.sub(r'[^A-Za-z0-9\s,\-\./]', ' ', line).strip()
            clean_line = re.sub(r'\s+', ' ', clean_line)
            
            # Remove name and father name if they appear in the address
            if fields['name']:
                clean_line = re.sub(fields['name'], '', clean_line, flags=re.IGNORECASE)
            if fields['father_name']:
                clean_line = re.sub(fields['father_name'], '', clean_line, flags=re.IGNORECASE)
            
            clean_line = clean_line.strip(' ,.-')
            
            if len(clean_line) > 5 and clean_line not in address_lines:
                address_lines.append(clean_line)

    # If no address found with markers, try between name and VTC
    if not address_lines:
        name_index = None
        vtc_index = None
        
        for i, line in enumerate(lines):
            if fields['name'] and fields['name'].upper() in line.upper():
                name_index = i
            if re.search(r'\bVTC\b', line, re.I):
                vtc_index = i
                break
        
        if name_index is not None and vtc_index is not None:
            for i in range(name_index + 1, vtc_index):
                line_clean = re.sub(r'[^A-Za-z0-9\s,\-\./]', ' ', lines[i]).strip()
                line_clean = re.sub(r'\s+', ' ', line_clean)
                
                # Skip if it contains name or father name
                if (fields['name'] and fields['name'].upper() in line_clean.upper()) or \
                   (fields['father_name'] and fields['father_name'].upper() in line_clean.upper()):
                    continue
                    
                if len(line_clean) > 5 and line_clean not in address_lines:
                    address_lines.append(line_clean)

    if address_lines:
        fields['address'] = ', '.join(address_lines)

    return fields

def extract_voter_fields(text: str, yolo_output: dict = None, rawdata: bool = False) -> dict:
    """Voter ID with YOLO label detection"""
    fields = {"voter_id": None, "name": None, "father_name": None, "husband_name": None,
              "dob": None, "gender": None}
    
    if yolo_output:
        yolo_boxes = []
        for page in yolo_output.get("pages", []):
            if 'crops' in page:
                yolo_boxes.extend(page['crops'])
        
        if yolo_boxes:
            for box in yolo_boxes:
                txt = box.get('text', '').lower()
                if not txt: continue
                if 'name' in txt and 'father' not in txt and 'husband' not in txt:
                    fields['name'] = fields['name'] or get_right_text(box, yolo_boxes)
                elif 'father' in txt:
                    fields['father_name'] = fields['father_name'] or get_right_text(box, yolo_boxes)
                elif 'husband' in txt:
                    fields['husband_name'] = fields['husband_name'] or get_right_text(box, yolo_boxes)
                elif 'birth' in txt:
                    fields['dob'] = fields['dob'] or get_right_text(box, yolo_boxes)
                elif 'gender' in txt:
                    fields['gender'] = fields['gender'] or get_right_text(box, yolo_boxes)
                elif 'epic no' in txt or ('epic' in txt and 'no' in txt):
                    fields['voter_id'] = fields['voter_id'] or get_right_text(box, yolo_boxes)
            
            if any(fields.values()):
                if rawdata:
                    fields['rawdata'] = [box.get('text', '') for box in yolo_boxes]
                return fields
    
    # Regex fallback
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    m = re.search(r"\b([A-Z]{3,4}[0-9]{6,10})\b", text) or \
        re.search(r"Epic no\.?\s*[:\-]?\s*([A-Z0-9]{6,20})", text, re.I)
    if m: fields["voter_id"] = m.group(1)
    
    m = re.search(r"Name[ ,:/-]*([A-Za-z .'-]+)", text, re.I)
    if m: fields["name"] = normalize_name(m.group(1))
    
    for ln in lines:
        m = re.search(r"Father'?s Name\s*[:;+\-_]*\s*([A-Za-z .'-]+)", ln, re.I)
        if m:
            words = [w for w in m.group(1).split() if w.isalpha() and len(w) > 1]
            if words:
                fields["father_name"] = normalize_name(" ".join(words[:3]))
                break
    
    for pat in [r"Date of Birth[ /:]*([0-9]{2}[-/][0-9]{2}[-/][0-9]{4})", 
                r"([0-9]{2}[-/][0-9]{2}[-/][0-9]{4})"]:
        m = re.search(pat, text, re.I)
        if m:
            fields["dob"] = m.group(1)
            break
    
    m = re.search(r"(Sex|Gender)\s*[:;+\-_]*\s*(Male|Female|Other)", text, re.I)
    if m: fields["gender"] = m.group(2).capitalize()
    
    if rawdata: fields['rawdata'] = lines
    return fields

def extract_dl_fields(text: str) -> Dict[str, Any]:
    """DL with improved date extraction"""
    fields = {"dl_number": None, "name": None, "dob": None, "issue_date": None,
              "valid_till": None, "father_name": None, "address": None}
    if not text: return fields
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    
    # DL Number
    for ln in lines:
        m = re.search(r"\b([A-Z]{2}[0O]?\d{6,20})\b", ln.replace(" ", ""))
        if m:
            fields["dl_number"] = m.group(1)
            break
    if not fields["dl_number"]:
        m = re.search(r"\b([A-Z]{2}[0O]?\s*\d[\d\s]{5,20})\b", " ".join(lines))
        if m: fields["dl_number"] = m.group(1).replace(" ", "")
    
    # Name
    for ln in lines:
        if re.search(r"\bNAME\b", ln, re.I):
            m = re.search(r"Name\s*[:\-]?\s*(.+)", ln, re.I)
            if m:
                fields["name"] = normalize_name(re.sub(r"Holder.?s Signature", "", m.group(1), flags=re.I))
                break
    
    # Father
    for ln in lines:
        if re.search(r"\b(S/O|D/O|W/O|FATHER)\b", ln, re.I):
            m = re.search(r"(?:S/O|D/O|W/O|FATHER['']S NAME)[:\-]?\s*(.+)", ln, re.I)
            if m:
                fields["father_name"] = normalize_name(m.group(1))
                break
    
    # Address
    addr_lines = []
    addr_idx = -1
    for i, ln in enumerate(lines):
        if "ADDRESS" in ln.upper():
            addr_idx = i
            part = re.sub(r".*ADDRESS\s*[:\-]?\s*", "", ln, flags=re.I).strip()
            if part: addr_lines.append(part)
            break
    if addr_idx != -1:
        for i in range(addr_idx + 1, len(lines)):
            if lines[i].strip():
                addr_lines.append(lines[i].strip())
            elif addr_lines:
                break
    if addr_lines: fields["address"] = ", ".join(addr_lines)
    
    # Dates - improved logic
    all_dates = re.findall(r"(\d{2}[/-]\d{2}[/-]\d{4})", text)
    unique_dates = sorted(set(all_dates), key=all_dates.index)
    
    for label, field in [("(?:Date of Birth|DOB)", "dob"), 
                         ("(?:Issue Date|Date of First Issue)", "issue_date"),
                         ("(?:Validity|Valid Till)", "valid_till")]:
        m = re.search(f"{label}[\\s:]*(\d{{2}}[/-]\d{{2}}[/-]\d{{4}})", text, re.I)
        if m:
            fields[field] = m.group(1)
            if m.group(1) in unique_dates:
                unique_dates.remove(m.group(1))
    
    if not fields["issue_date"] and unique_dates:
        fields["issue_date"] = unique_dates.pop(0)
    if not fields["valid_till"] and unique_dates:
        fields["valid_till"] = unique_dates.pop(0)
    
    return fields

def extract_marksheet_fields(text: str, filename: str = None, meta: Dict[str, Any] = None) -> Dict[str, Any]:
    """Marksheet extraction"""
    fields = {"student_name": None, "father_name": None, "mother_name": None,
              "school_name": None, "dob": None, "roll_no": None, "year": None, "cgpa": None}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    
    # School
    for ln in lines:
        m = re.match(r"SCHOOL\s*[:\-——]?\s*(.+)", ln, re.I)
        if m:
            fields["school_name"] = m.group(0).strip()
            break
    if not fields["school_name"]:
        for ln in lines:
            if re.search(r'\b(SCHOOL|INSTITUTE|COLLEGE)\b', ln, re.I):
                fields["school_name"] = ln.strip()
                break
    
    # Roll
    for i, ln in enumerate(lines):
        if re.search(r"\bROLL\b", ln, re.I):
            m = re.search(r"\bROLL\s*(?:NO)?\.?\s*[:\-——]?\s*([0-9]{7,12})\b", ln, re.I)
            if m and "/" not in m.group(1):
                fields["roll_no"] = m.group(1)
                break
            elif i+1 < len(lines) and re.match(r"^[0-9]{7,12}$", lines[i+1].strip()):
                fields["roll_no"] = lines[i+1].strip()
                break
    
    # DOB
    for pat in [r"\b(?:DOB|DATE\s*OF\s*BIRTH)[\s:\-——]*([0-3]?\d[\/\-.][01]?\d[\/\-.]\d{4})\b",
                r"\b([0-3]?\d[\/\-.][01]?\d[\/\-.]\d{4})\b"]:
        m = re.search(pat, text, re.I)
        if m:
            fields["dob"] = m.group(1)
            break
    
    # Year
    for ln in lines:
        m = re.search(r"EXAMINATION\s+held\s+in\s+\w+-?(20\d{2})", ln, re.I)
        if m:
            fields["year"] = m.group(1)
            break
    
    # CGPA
    m = re.search(r"(CGPA|GPA|GRADE\s*POINT)[\s\.:;\-——]*([0-9]{1,2}\.[0-9]{1,2})", text, re.I)
    if m: fields["cgpa"] = m.group(2)
    
    # Names
    for i, line in enumerate(lines):
        if re.search(r"\b(REGULAR|ROLL|PC\/)\b", line, re.I):
            if i+1 < len(lines):
                m = re.search(r"CERTIFIED\s+THAT\s+([A-Z\s]+)", lines[i+1], re.I)
                fields["student_name"] = m.group(1).strip() if m else lines[i+1].strip()
            if i+2 < len(lines):
                m = re.search(r"FATHER'?S\s+NAME\s+([A-Z\s]+)", lines[i+2], re.I)
                fields["father_name"] = m.group(1).strip() if m else lines[i+2].strip()
            if i+3 < len(lines):
                m = re.search(r"MOTHER'?S\s+NAME\s+([A-Z\s]+)", lines[i+3], re.I)
                fields["mother_name"] = m.group(1).strip() if m else lines[i+3].strip()
            break
    
    return fields

def extract_pan_fields(text: str, rawdata: bool = False) -> dict:
    """PAN extraction"""
    fields = {"pan": None, "name": None, "father_name": None, "dob": None}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    upper_lines = [ln.upper() for ln in lines]
    
    m = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text.upper())
    if m: fields["pan"] = m.group(1)
    
    m = re.search(r"(DOB|DATE OF BIRTH)[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})", text.upper())
    if m:
        fields["dob"] = m.group(2)
    else:
        m = re.search(r"\b[0-9]{2}[/-][0-9]{2}[/-][0-9]{4}\b", text)
        if m: fields["dob"] = m.group(0)
    
    for i, ln in enumerate(upper_lines):
        if "NAME" in ln and not fields["name"]:
            m = re.search(r"NAME\s*[:\-]?\s*(.+)", lines[i], re.I)
            fields["name"] = normalize_name(m.group(1)) if m else (normalize_name(lines[i+1]) if i+1 < len(lines) else None)
        if "FATHER" in ln and not fields["father_name"]:
            m = re.search(r"FATHER'?S?\s*NAME\s*[:\-]?\s*(.+)", lines[i], re.I)
            fields["father_name"] = normalize_name(m.group(1)) if m else (normalize_name(lines[i+1]) if i+1 < len(lines) else None)
    
    if rawdata: fields['rawdata'] = lines
    return fields

def clean_subject(subj: str) -> str:
    """Clean subject name from marksheet"""
    if not subj:
        return None
    s = subj.upper()
    s = re.sub(r"\b(FIRST|SECOND|THIRD|FOURTH|FIFTH|LANGUAGE|CURRICULAR|CO-CURRICULAR|AREA|VALUE|EDUCATION|WORK|&|AND|THE|SUBJECT|SUBJECTS|GRADE|POINT|CODE)\b", ' ', s)
    s = re.sub(r"[\(\)\:\-\|,\.\\/]", ' ', s)
    s = re.sub(r"\s+", ' ', s).strip()
    tokens = [t for t in s.split(' ') if t]
    for tok in reversed(tokens):
        if len(tok) >= 3 and tok.isalpha():
            return tok.title()
    return s.title() if s else None


def parse_table_from_pdf_tables(pdf_tables: List[List[List[str]]]) -> List[Dict[str, Any]]:
    """Parse subject tables from PDF tables"""
    results = []
    if not pdf_tables:
        return results
    
    for tbl in pdf_tables:
        if not tbl or not isinstance(tbl, list):
            continue
        
        header_idx = None
        for i, row in enumerate(tbl[:5]):
            joined = " ".join([str(c).upper() for c in row if c])
            if any(h in joined for h in ['SUBJECT', 'GRADE', 'MARKS', 'POINT', 'SCORE', 'GRADE POINT']):
                header_idx = i
                break
        
        if header_idx is not None:
            headers = [str(c).strip().lower() for c in tbl[header_idx]]
            col_map = {}
            for ci, h in enumerate(headers):
                if 'subject' in h or 'course' in h or 'paper' in h:
                    col_map['subject'] = ci
                elif 'grade' in h:
                    col_map['grade'] = ci
                elif 'point' in h or 'marks' in h or 'score' in h or 'total' in h:
                    col_map['marks'] = ci
                elif 'max' in h and 'marks' not in col_map:
                    col_map['max_marks'] = ci
            
            for row in tbl[header_idx+1:]:
                try:
                    subj = row[col_map['subject']].strip() if 'subject' in col_map and len(row) > col_map['subject'] else ''
                    grade = row[col_map['grade']].strip() if 'grade' in col_map and len(row) > col_map['grade'] else ''
                    marks = row[col_map['marks']].strip() if 'marks' in col_map and len(row) > col_map['marks'] else ''
                    if subj or grade or marks:
                        results.append({
                            'subject': clean_subject(subj),
                            'grade': grade,
                            'marks': marks
                        })
                except:
                    continue
        else:
            for row in tbl:
                row_join = ' '.join([str(c) for c in row if c])
                grade_m = re.search(r"\bA[1-4]\b|\bA1\b|\bA2\b|\bB\b|\bC\b|\bD\b|\bE\b|\bF\b", row_join, re.I)
                marks_m = re.search(r"\b[0-9]{1,3}\b", row_join)
                if grade_m and marks_m:
                    subj = row_join[:grade_m.start()].strip()
                    results.append({
                        'subject': clean_subject(subj),
                        'grade': grade_m.group(0),
                        'marks': marks_m.group(0)
                    })
    
    return results


def parse_table_from_lines(lines: List[str]) -> List[Dict[str, Any]]:
    """Parse subject tables from text lines"""
    results = []
    if not lines:
        return results
    
    up_lines = [ln.upper() for ln in lines]
    grade_regex = re.compile(r"\bA[1-4]\b|\bA1\b|\bA2\b|\bB\b|\bC\b|\bD\b|\bE\b|\bF\b", re.I)
    marks_regex = re.compile(r"\b([0-9]{1,3})(?:\.\d+)?\b")
    used_indices = set()
    n = len(lines)
    
    for i in range(n):
        if i in used_indices:
            continue
        
        window = ' '.join([lines[j] for j in range(i, min(i+4, n))])
        up_window = window.upper()
        g = grade_regex.search(up_window)
        m = marks_regex.search(up_window)
        
        if g and m:
            subj_text = window[:g.start()].strip()
            subj_clean = clean_subject(subj_text)
            grade = g.group(0).strip()
            marks = m.group(1).strip()
            if subj_clean:
                results.append({
                    'subject': subj_clean,
                    'grade': grade,
                    'marks': marks
                })
                for k in range(i, min(i+4, n)):
                    used_indices.add(k)
                continue
        
        if i+2 < n:
            g2 = grade_regex.search(up_lines[i+1])
            m2 = marks_regex.search(up_lines[i+2])
            if g2 and m2:
                subj_clean = clean_subject(lines[i])
                grade = g2.group(0).strip()
                marks = m2.group(1).strip()
                if subj_clean:
                    results.append({
                        'subject': subj_clean,
                        'grade': grade,
                        'marks': marks
                    })
                    used_indices.update([i, i+1, i+2])
                    continue
    
    seen = set()
    dedup = []
    for r in results:
        key = (r.get('subject', '').upper(), r.get('grade', ''), r.get('marks', ''))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)
    
    return dedup



# ==================== MAIN PROCESSOR ====================


def process_document(filename: str, content_bytes: bytes) -> Dict[str, Any]:
    """Main processing function with complete meta population"""
    result = {
        'filename': filename,
        'document_type': None,
        'fields': {},
        'table': [],
        'raw_text_preview': "",
        'confidence': 0.0,
        'meta': {}
    }
    
    try:
        is_pdf = filename.lower().endswith('.pdf')
        
        # 🆕 Initialize meta containers
        field_ocr_confidences = {}
        image_quality_info = {}
        
        # Extract text with meta capture
        if is_pdf:
            full_text, pdf_tables = extract_pdf_content(content_bytes) if HAVE_PDFPLUMBER else ("", [])
            if HAVE_PDF2IMAGE:
                page_images = pdf_bytes_to_images(content_bytes, dpi=Config.OCR_DPI)
                all_text_pages = []
                for img_bytes, page_no in page_images:
                    # 🆕 Capture OCR data with meta
                    tess_text, tess_data, img, doctr_lines = extract_image_ocr(img_bytes)
                    all_text_pages.append(tess_text or "")
                    
                    # 🆕 Store Tesseract data for first page
                    if page_no == 1 and tess_data:
                        from services.tesseract_confidence import extract_all_ocr_data_single_pass
                        ocr_data = extract_all_ocr_data_single_pass(img_bytes)
                        field_ocr_confidences = {
                            'overall_stats': ocr_data.get('overall_stats', {}),
                            'word_count': len(ocr_data.get('words', []))
                        }
                        
                        # 🆕 Image quality check
                        from services.image_preprocessor import check_image_quality
                        image_quality_info = check_image_quality(img_bytes, fast_mode=True)
                
                ocr_text = "\n".join(all_text_pages)
                full_text = ocr_text if len(ocr_text) > len(full_text) else full_text
        else:
            # 🆕 For images - capture full OCR data
            tess_text, tess_data, img, doctr_lines = extract_image_ocr(content_bytes)
            full_text = tess_text or ""
            
            # 🆕 Extract comprehensive OCR data
            from services.tesseract_confidence import extract_all_ocr_data_single_pass
            ocr_data = extract_all_ocr_data_single_pass(content_bytes)
            
            field_ocr_confidences = {
                'overall_stats': ocr_data.get('overall_stats', {}),
                'word_data': ocr_data.get('word_data', []),
                'word_count': len(ocr_data.get('words', []))
            }
            
            # 🆕 Image quality check
            from services.image_preprocessor import check_image_quality
            image_quality_info = check_image_quality(content_bytes, fast_mode=True)
        
        # Classification
        doc_type = classify_document_smart(full_text)
        result['document_type'] = doc_type
        
        # Extract fields based on type
        if doc_type == "PAN":
            result['fields'] = extract_pan_fields(full_text)
        elif doc_type == "Aadhaar":
            result['fields'] = extract_aadhaar_fields(full_text, None)
        elif doc_type == "Voter ID":
            result['fields'] = extract_voter_fields(full_text, None)
        elif doc_type == "Driving Licence":
            result['fields'] = extract_dl_fields(full_text)
        elif doc_type == "Marksheet":
            result['fields'] = extract_marksheet_fields(full_text, filename, {})
        
        # Calculate confidence
        total_fields = len(result['fields'])
        filled_fields = sum(1 for v in result['fields'].values() if v)
        result['confidence'] = (filled_fields / total_fields * 100) if total_fields > 0 else 0
        
        result['raw_text_preview'] = "\n".join(full_text.splitlines()[:30])
        
        # 🆕 POPULATE META
        result['meta'] = {
            'raw_ocr_data': {
                'tesseract_text': full_text[:2812],  # First 1000 chars
                'text_length': len(full_text),
                'tesseract_confidence': field_ocr_confidences
            },
            'image_quality': image_quality_info,
            'field_ocr_confidences': field_ocr_confidences,
            'processing_info': {
                'is_pdf': is_pdf,
                'filename': filename,
                'classification_method': 'smart_v2'
            }
        }
        
        print(f"📦 Meta populated: {len(result['meta'])} keys")
        print(f"   - raw_ocr_data: ✅")
        print(f"   - image_quality: ✅ (score: {image_quality_info.get('quality_score', 0)})")
        print(f"   - field_ocr_confidences: ✅ ({field_ocr_confidences.get('word_count', 0)} words)")
        
        return result
    
    except Exception as e:
        print(f"❌ Processing error: {e}")
        import traceback
        traceback.print_exc()
        result['error'] = str(e)
        return result
    
if __name__ == "__main__":
    print("✅ Enhanced Extractor loaded with V2 classification")
    print("✅ Complete Extractor Service loaded successfully")
    print(f"   - PDF2Image: {'✅' if HAVE_PDF2IMAGE else '❌'}")
    print(f"   - PDFPlumber: {'✅' if HAVE_PDFPLUMBER else '❌'}")
    print(f"   - docTR: {'✅' if HAVE_DOCTR else '❌'}")
    print(f"   - YOLO: {'✅' if HAVE_YOLO else '❌'}")
    print(f"   - OpenCV: {'✅' if HAVE_CV2 else '❌'}")