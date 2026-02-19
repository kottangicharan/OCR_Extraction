"""
OCR Routes - HEAVY PRIORITY WITH LIGHT FALLBACK
Strategy: Try Heavy API first (143s timeout), fallback to Light if fails
"""
import requests
import os
import time
from flask import Blueprint, request, jsonify, g
from werkzeug.utils import secure_filename
from services.extractor import process_document
from services.database import get_db
from services.file_storage import get_storage
from services.confidence_calculator import process_with_confidence, add_extraction_summary
from services.models import ScanResponse, RescanResponse, SubmissionResponse
from services.auth import optional_auth, check_document_ownership
from typing import List, Dict, Any, Tuple
from config import Config

ocr_blueprint = Blueprint("ocr", __name__)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

# Heavy API configuration
def validate_heavy_api_url(url):
    """Validate Heavy API URL format"""
    if url and not url.startswith(('http://', 'https://')):
        print(f"⚠️ WARNING: Invalid HEAVY_API_URL format: {url}")
        return None
    return url

HEAVY_API_URL = validate_heavy_api_url(os.getenv('HEAVY_API_URL', None))
APP_MODE = os.getenv('APP_MODE', 'light')
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '70'))

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def call_heavy_api(file_bytes, filename, auto_submit=False, retry_count=0, max_retries=1):
    """
    Call Heavy API with 143s timeout and retry logic
    Returns: dict or None
    """
    if not HEAVY_API_URL:
        print("⚠️ Heavy API URL not configured")
        return None
    
    attempt_num = retry_count + 1
    retry_label = f" (Attempt {attempt_num}/{max_retries + 1})" if retry_count > 0 else ""
    
    try:
        print(f"🔵 [Heavy API] Starting{retry_label}: {HEAVY_API_URL}")
        start_time = time.time()
        
        files = {'file': (filename, file_bytes, 'application/pdf')}
        data = {'auto_submit': 'true' if auto_submit else 'false'}
        
        response = requests.post(
            f"{HEAVY_API_URL}/api/scan",
            files=files,
            data=data,
            timeout=143  # 143 second timeout
        )
        
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ [Heavy API] Success in {elapsed:.2f}s{retry_label}")
            
            # Debug: Check Heavy API response
            if result and isinstance(result, dict):
                has_meta = 'meta' in result and result['meta']
                has_fields = 'fields' in result and result['fields']
                print(f"   Heavy API meta: {'✅' if has_meta else '❌'}")
                print(f"   Heavy API fields: {len(result.get('fields', {}))} fields")
            
            return result
        else:
            print(f"❌ [Heavy API] HTTP {response.status_code} in {elapsed:.2f}s{retry_label}")
            
            # Retry on server errors (5xx)
            if retry_count < max_retries and response.status_code >= 500:
                print(f"🔄 Retrying Heavy API...")
                time.sleep(2)
                return call_heavy_api(file_bytes, filename, auto_submit, retry_count + 1, max_retries)
            
            return None
            
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"⏱️ [Heavy API] Timeout after {elapsed:.2f}s{retry_label}")
        
        # Retry on timeout
        if retry_count < max_retries:
            print(f"🔄 Retrying Heavy API after timeout...")
            time.sleep(2)
            return call_heavy_api(file_bytes, filename, auto_submit, retry_count + 1, max_retries)
        
        print(f"❌ [Heavy API] Failed after {max_retries + 1} attempts (timeout)")
        return None
    
    except requests.exceptions.ConnectionError as e:
        print(f"❌ [Heavy API] Connection failed{retry_label}: {e}")
        
        if retry_count < max_retries:
            print(f"🔄 Retrying Heavy API after connection error...")
            time.sleep(2)
            return call_heavy_api(file_bytes, filename, auto_submit, retry_count + 1, max_retries)
        
        return None
    
    except Exception as e:
        print(f"❌ [Heavy API] Error{retry_label}: {e}")
        return None


def run_light_api(file_bytes, filename):
    """
    Run Light API (local Tesseract processing)
    Returns: dict or None
    """
    try:
        print("🟢 [Light API] Starting...")
        start = time.time()
        
        # Process with local Tesseract
        result = process_document(filename, file_bytes)
        elapsed = time.time() - start
        
        if not isinstance(result, dict):
            raise TypeError(f"process_document returned {type(result)}, expected dict")
        
        if 'fields' not in result:
            result['fields'] = {}
        
        if not isinstance(result['fields'], dict):
            raise TypeError(f"result['fields'] is {type(result['fields'])}, expected dict")
        
        # Extract quality metrics
        field_ocr_confs = result.get('field_ocr_confidences', {})
        image_quality_info = result.get('image_quality', {})
        img_quality_score = image_quality_info.get('quality_score', 75.0)
        
        # Enhanced confidence
        result = process_with_confidence(
            result,
            ocr_confidences=field_ocr_confs,
            image_quality=img_quality_score
        )
        result = add_extraction_summary(result)
        
        print(f"✅ [Light API] Completed in {elapsed:.2f}s")
        return result
        
    except Exception as e:
        print(f"❌ [Light API] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==================== SCAN ENDPOINT (HEAVY PRIORITY) ====================
@ocr_blueprint.route("/scan", methods=["POST"])
@optional_auth
def scan_document():
    """
    📄 Scan document with HEAVY PRIORITY, Light Fallback
    
    Strategy:
    1. Try Heavy API first (143s timeout)
    2. If Heavy fails/times out → Use Light API
    3. Return whichever succeeds
    """
    endpoint_start = time.time()
    
    try:
        # Get user_id from auth
        user_id = g.user_id
        is_authenticated = g.is_authenticated
        auth_message = g.auth_message
        
        print(f"\n{'='*70}")
        print(f"📄 NEW SCAN REQUEST (Heavy Priority)")
        print(f"   User ID: {user_id}")
        print(f"   Authenticated: {is_authenticated}")
        if auth_message:
            print(f"   ⚠️  {auth_message}")
        print(f"{'='*70}\n")
        
        if "file" not in request.files:
            response = ScanResponse(success=False, error="No file uploaded")
            return jsonify(response.to_dict()), 400
        
        file = request.files["file"]
        
        if file.filename == "":
            response = ScanResponse(success=False, error="Empty filename")
            return jsonify(response.to_dict()), 400
        
        if not allowed_file(file.filename):
            response = ScanResponse(success=False, error=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
            return jsonify(response.to_dict()), 400
        
        auto_submit = request.form.get('auto_submit', 'false').lower() == 'true'
        
        # Read file bytes
        filename = secure_filename(file.filename)
        file_bytes = file.read()
        
        # Validate file size
        if len(file_bytes) > Config.MAX_CONTENT_LENGTH:
            response = ScanResponse(success=False, error="File too large")
            return jsonify(response.to_dict()), 413
        
        if len(file_bytes) == 0:
            response = ScanResponse(success=False, error="Empty file")
            return jsonify(response.to_dict()), 400
        
        print(f"📄 Processing scan: {filename} ({len(file_bytes)} bytes)")
        print(f"📄 Mode: HEAVY PRIORITY → Light Fallback")
        
        # ============================================
        # 🔥 HEAVY PRIORITY STRATEGY
        # ============================================
        
        final_result = None
        strategy = "unknown"
        processing_time = 0
        
        # STEP 1: Try Heavy API first
        heavy_start = time.time()
        heavy_result = call_heavy_api(file_bytes, filename, auto_submit)
        heavy_time = time.time() - heavy_start
        
        if heavy_result and heavy_result.get('success'):
            # Heavy API succeeded
            print(f"\n✅ Using Heavy API result")
            final_result = heavy_result
            strategy = "heavy_only"
            processing_time = heavy_time
            
            # Ensure meta exists (Heavy API should provide it)
            if 'meta' not in final_result:
                final_result['meta'] = {}
            
        else:
            # Heavy API failed - Fallback to Light
            print(f"\n⚠️  Heavy API failed/timeout - Falling back to Light API...")
            
            light_start = time.time()
            light_result = run_light_api(file_bytes, filename)
            light_time = time.time() - light_start
            
            if light_result:
                print(f"✅ Using Light API fallback")
                final_result = light_result
                strategy = "light_fallback"
                processing_time = heavy_time + light_time
            else:
                print(f"\n❌ Both Heavy and Light APIs failed!")
                response = ScanResponse(
                    success=False, 
                    error="Both Heavy API and Light API failed to process document"
                )
                return jsonify(response.to_dict()), 500
        
        # Safety checks
        if not isinstance(final_result, dict) or 'fields' not in final_result:
            raise ValueError("Invalid result structure")
        
        confidence = final_result.get("overall_confidence") or final_result.get("confidence", 0.0)
        
        # Save to database WITH USER_ID
        try:
            db = get_db()
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            response = ScanResponse(success=False, error="Database connection failed")
            return jsonify(response.to_dict()), 500
        
        scan_id = db.save_scan(final_result, user_id=user_id)
         
        # Save file for rescan (if enabled)
        storage_metadata = {}
        if Config.ENABLE_FILE_STORAGE:
            try:
                storage = get_storage()
                storage_metadata = storage.save_file(scan_id, file_bytes, filename)
                db.update_scan(scan_id, {'storage_metadata': storage_metadata})
                print(f"💾 File stored: {storage_metadata.get('storage_mode')}")
            except Exception as e:
                print(f"⚠️ File storage failed: {e}")
        
        # Build response message
        message = f"Document scanned successfully (Strategy: {strategy})"
        
        if auth_message:
            message = f"{message} - {auth_message}"
        
        image_quality_info = final_result.get('image_quality', {})
        quality_issues = image_quality_info.get('issues', [])
        if quality_issues:
            warnings = "; ".join(quality_issues[:2])
            message = f"Scan complete with warnings: {warnings}"
        
        metadata = final_result.get("metadata", {})
        if metadata.get("suggest_rescan", False):
            low_count = metadata.get("low_confidence_count", 0)
            message += f" | ⚠️ Rescan suggested ({low_count} fields below threshold)"
        
        # Build response with user_id
        response = ScanResponse(
            success=True,
            scan_id=scan_id,
            user_id=user_id,
            filename=final_result.get("filename"),
            document_type=final_result.get("document_type"),
            fields=final_result.get("fields", {}),
            table=final_result.get("table", []),
            confidence=confidence,
            extraction_summary=final_result.get("extraction_summary", {}),
            message=message,
            meta=final_result.get("meta", {})
        )
        
        # Auto-submit if requested
        if auto_submit and final_result.get("fields"):
            submission_data = {
                'scan_id': scan_id,
                'user_id': user_id,
                'document_type': final_result.get("document_type"),
                'verified_fields': final_result.get("fields", {}),
                'table': final_result.get('table', []),
                'user_corrections': {},
                'final_confidence': confidence,
                'extraction_summary': final_result.get("extraction_summary", {})
            }
            submission_id = db.save_submission(submission_data)
            response.submission_id = submission_id
            response.auto_submitted = True
            response.message = f"Document scanned and submitted automatically ({strategy})"
        
        # Performance summary
        total_time = time.time() - endpoint_start
        print(f"\n⏱️  PERFORMANCE SUMMARY:")
        print(f"   Processing Time: {processing_time:.2f}s")
        print(f"   Strategy: {strategy}")
        print(f"   Table Rows: {len(final_result.get('table', []))}")
        print(f"   User ID: {user_id}")
        print(f"   ✅ TOTAL ENDPOINT TIME: {total_time:.2f}s")
        
        if total_time > 150:
            print(f"   ⚠️ WARNING: Close to timeout!")
        
        return jsonify(response.to_dict()), 200
    
    except TypeError as e:
        print(f"❌ Type error in scan: {e}")
        import traceback
        traceback.print_exc()
        response = ScanResponse(success=False, error=f"Data type error: {str(e)}")
        return jsonify(response.to_dict()), 500
    
    except Exception as e:
        print(f"❌ Scan error: {e}")
        import traceback
        traceback.print_exc()
        response = ScanResponse(success=False, error=str(e))
        return jsonify(response.to_dict()), 500


# ==================== RESCAN ENDPOINT (UPDATED) ====================
@ocr_blueprint.route("/rescan/<scan_id>", methods=["POST"])
@optional_auth
def rescan_document(scan_id: str):
    """
    🔄 Rescan document with SAME strategy as /scan
    Heavy API (60s, single attempt) → Light fallback
    """
    endpoint_start = time.time()
    
    try:
        # Get user_id from auth
        user_id = g.user_id
        is_authenticated = g.is_authenticated
        
        print(f"\n{'='*70}")
        print(f"🔄 RESCAN REQUEST")
        print(f"   Scan ID: {scan_id}")
        print(f"   User ID: {user_id}")
        print(f"{'='*70}\n")
        
        try:
            db = get_db()
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            response = RescanResponse(success=False, error="Database connection failed")
            return jsonify(response.to_dict()), 500
        
        scan = db.get_scan(scan_id)
        if not scan:
            response = RescanResponse(success=False, error="Original scan not found")
            return jsonify(response.to_dict()), 404
        
        # CHECK OWNERSHIP
        if not check_document_ownership(scan, user_id):
            print(f"❌ Permission denied: User {user_id} cannot access scan {scan_id}")
            response = RescanResponse(
                success=False, 
                error="Permission denied - you can only rescan your own documents"
            )
            return jsonify(response.to_dict()), 403
        
        storage_metadata = scan.get('storage_metadata', {})
        
        # Get stored file or new upload
        if storage_metadata.get('stored') and "file" not in request.files:
            print(f"📄 Rescanning using stored file for: {scan_id}")
            storage = get_storage()
            file_bytes = storage.get_file(scan_id, storage_metadata)
            
            if not file_bytes:
                response = RescanResponse(
                    success=False, 
                    error="Stored file not found. Please upload file again."
                )
                return jsonify(response.to_dict()), 404
            
            filename = storage_metadata.get('filename', 'stored_file.pdf')
        
        elif "file" in request.files:
            print(f"📄 Rescanning with new uploaded file")
            file = request.files["file"]
            
            if file.filename == "":
                response = RescanResponse(success=False, error="Empty filename")
                return jsonify(response.to_dict()), 400
                
            if not allowed_file(file.filename):
                response = RescanResponse(success=False, error="Invalid file type")
                return jsonify(response.to_dict()), 400
            
            filename = secure_filename(file.filename)
            file_bytes = file.read()
            
            if len(file_bytes) > Config.MAX_CONTENT_LENGTH:
                response = RescanResponse(success=False, error="File too large")
                return jsonify(response.to_dict()), 413
        
        else:
            response = RescanResponse(
                success=False,
                error="No file available. Original file not stored or no new file uploaded."
            )
            return jsonify(response.to_dict()), 400
        
        auto_submit = request.form.get('auto_submit', 'false').lower() == 'true'
        
        # ============================================
        # 🔥 SAME STRATEGY AS /scan
        # Heavy API (60s, single attempt) → Light fallback
        # ============================================
        
        print(f"📄 Processing rescan: {filename} ({len(file_bytes)} bytes)")
        print(f"📄 Mode: Heavy (60s, 1 attempt) → Light fallback")
        
        final_result = None
        strategy = "unknown"
        processing_time = 0
        
        # STEP 1: Try Heavy API (60s timeout, NO RETRY)
        heavy_start = time.time()
        heavy_result = call_heavy_api(file_bytes, filename, auto_submit=False, retry_count=0, max_retries=0)
        heavy_time = time.time() - heavy_start
        
        if heavy_result and heavy_result.get('success'):
            print(f"\n✅ Using Heavy API result")
            final_result = heavy_result
            strategy = "heavy_only"
            processing_time = heavy_time
            
            if 'meta' not in final_result:
                final_result['meta'] = {}
            
        else:
            # Heavy API failed - Fallback to Light
            print(f"\n⚠️ Heavy API failed - Falling back to Light API...")
            
            light_start = time.time()
            light_result = run_light_api(file_bytes, filename)
            light_time = time.time() - light_start
            
            if light_result:
                print(f"✅ Using Light API fallback")
                final_result = light_result
                strategy = "light_fallback"
                processing_time = heavy_time + light_time
            else:
                print(f"\n❌ Both Heavy and Light APIs failed!")
                response = RescanResponse(
                    success=False, 
                    error="Both Heavy API and Light API failed to rescan document"
                )
                return jsonify(response.to_dict()), 500
        
        # Safety checks
        if not isinstance(final_result, dict) or 'fields' not in final_result:
            raise ValueError("Invalid result structure after rescan")
        
        confidence = final_result.get("overall_confidence") or final_result.get("confidence", 0.0)
        
        # Save rescan WITH USER_ID
        rescan_id = db.save_rescan(final_result, scan_id, user_id=user_id)
    
        # Build response message
        message = f"Document rescanned successfully (Strategy: {strategy})"
        
        if hasattr(g, 'auth_message') and g.auth_message:
            message = f"{message} - {g.auth_message}"
        
        image_quality_info = final_result.get('image_quality', {})
        quality_issues = image_quality_info.get('issues', [])
        if quality_issues:
            warnings = "; ".join(quality_issues[:2])
            message = f"Rescan complete with warnings: {warnings}"
        
        metadata = final_result.get("metadata", {})
        if metadata.get("suggest_rescan", False):
            low_count = metadata.get("low_confidence_count", 0)
            message += f" | ⚠️ Another rescan suggested ({low_count} fields still below threshold)"
        
        # Build response with user_id
        response = RescanResponse(
            success=True,
            rescan_id=rescan_id,
            scan_id=scan_id,
            user_id=user_id,
            filename=final_result.get("filename"),
            document_type=final_result.get("document_type"),
            fields=final_result.get("fields", {}),
            table=final_result.get("table", []),
            confidence=confidence,
            extraction_summary=final_result.get("extraction_summary", {}),
            message=message,
            meta=final_result.get("meta", {})
        )        
        
        # Auto-submit if requested
        if auto_submit and final_result.get("fields"):
            submission_data = {
                'scan_id': scan_id,
                'rescan_id': rescan_id,
                'user_id': user_id,
                'document_type': final_result.get("document_type"),
                'verified_fields': final_result.get("fields", {}),
                'table': final_result.get('table', []),
                'user_corrections': {},
                'final_confidence': confidence,
                'extraction_summary': final_result.get("extraction_summary", {})
            }
            submission_id = db.save_submission(submission_data)
            response.submission_id = submission_id
            response.auto_submitted = True
            response.message = f"Document rescanned and submitted automatically ({strategy})"
        
        # Performance summary
        total_time = time.time() - endpoint_start
        print(f"\n⏱️ RESCAN PERFORMANCE:")
        print(f"   Processing Time: {processing_time:.2f}s")
        print(f"   Strategy: {strategy}")
        print(f"   Table Rows: {len(final_result.get('table', []))}")
        print(f"   User ID: {user_id}")
        print(f"   ✅ TOTAL TIME: {total_time:.2f}s")
        
        return jsonify(response.to_dict()), 200
    
    except TypeError as e:
        print(f"❌ Type error in rescan: {e}")
        import traceback
        traceback.print_exc()
        response = RescanResponse(success=False, error=f"Data type error: {str(e)}")
        return jsonify(response.to_dict()), 500
    
    except Exception as e:
        print(f"❌ Rescan error: {e}")
        import traceback
        traceback.print_exc()
        response = RescanResponse(success=False, error=str(e))
        return jsonify(response.to_dict()), 500

# ==================== EDIT ENDPOINT ====================

@ocr_blueprint.route("/edit/<scan_id>", methods=["PUT", "OPTIONS"])  
@optional_auth
def edit_scan(scan_id: str):
    """
    📝 Save user's edited fields (PUT - replaces existing edit)
    
    Request body:
    {
        "edited_fields": {...},
        "table": [...],
        "user_corrections": {...}
    }
    """
    try:
        user_id = g.user_id
        
        print(f"\n{'='*70}")
        print(f"📝 EDIT REQUEST")
        print(f"   Scan ID: {scan_id}")
        print(f"   User ID: {user_id}")
        print(f"{'='*70}\n")
        
        # Get database
        try:
            db = get_db()
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return jsonify({
                "success": False,
                "error": "Database connection failed"
            }), 500
        
        # Check if scan exists
        scan = db.get_scan(scan_id)
        if not scan:
            return jsonify({
                "success": False,
                "error": "Scan not found"
            }), 404
        
        # CHECK OWNERSHIP
        if not check_document_ownership(scan, user_id):
            print(f"❌ Permission denied: User {user_id} cannot edit scan {scan_id}")
            return jsonify({
                "success": False,
                "error": "Permission denied - you can only edit your own documents"
            }), 403
        
        # Get request data
        data = request.get_json()
        
        if not data or 'edited_fields' not in data:
            return jsonify({
                "success": False,
                "error": "edited_fields is required"
            }), 400
        
        print(f"\n📦 Received edit data:")
        print(f"   Fields: {len(data.get('edited_fields', {}))} fields")
        print(f"   Table: {len(data.get('table', []))} rows")
        print(f"   Corrections: {len(data.get('user_corrections', {}))} corrections")
        
        # Prepare edit data
        edit_data = {
            "document_type": scan.get('document_type'),
            "edited_fields": data.get('edited_fields', {}),
            "table": data.get('table', scan.get('table', [])),
            "user_corrections": data.get('user_corrections', {})
        }
        
        # Save or update edit (PUT behavior)
        edit_id = db.save_or_update_edit(scan_id, user_id, edit_data)
        
        # Get the saved edit
        saved_edit = db.get_edit(edit_id)
        
        print(f"✅ Edit saved: {edit_id}")
        
        return jsonify({
            "success": True,
            "edit_id": edit_id,
            "scan_id": scan_id,
            "user_id": user_id,
            "document_type": saved_edit.get('document_type'),
            "edited_fields": saved_edit.get('edited_fields'),
            "table": saved_edit.get('table'),
            "user_corrections": saved_edit.get('user_corrections'),
            "created_at": saved_edit.get('created_at').isoformat(),
            "updated_at": saved_edit.get('updated_at').isoformat(),
            "message": "Edits saved successfully"
        }), 200
    
    except Exception as e:
        print(f"❌ Edit error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ocr_blueprint.route("/edit/<scan_id>", methods=["GET", "OPTIONS"]) 
@optional_auth
def get_edit(scan_id: str):
    """
    📖 Get user's edit for a scan
    """
    try:
        user_id = g.user_id
        
        db = get_db()
        
        # Check scan ownership
        scan = db.get_scan(scan_id)
        if not scan:
            return jsonify({
                "success": False,
                "error": "Scan not found"
            }), 404
        
        if not check_document_ownership(scan, user_id):
            return jsonify({
                "success": False,
                "error": "Permission denied"
            }), 403
        
        # Get edit
        edit = db.get_edit_by_scan(scan_id, user_id)
        
        if not edit:
            return jsonify({
                "success": False,
                "error": "No edit found for this scan"
            }), 404
        
        return jsonify({
            "success": True,
            "edit_id": edit.get('edit_id'),
            "scan_id": edit.get('scan_id'),
            "user_id": edit.get('user_id'),
            "document_type": edit.get('document_type'),
            "edited_fields": edit.get('edited_fields'),
            "table": edit.get('table'),
            "user_corrections": edit.get('user_corrections'),
            "created_at": edit.get('created_at').isoformat(),
            "updated_at": edit.get('updated_at').isoformat()
        }), 200
    
    except Exception as e:
        print(f"❌ Get edit error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== HELPER FUNCTION ====================

def normalize_verified_fields(verified_fields: Dict[str, Any], original_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize verified fields to handle both plain values and confidence structure"""
    if not verified_fields:
        return original_fields
    
    normalized = {}
    
    for field_name, field_value in verified_fields.items():
        if isinstance(field_value, dict) and 'value' in field_value:
            normalized[field_name] = field_value
        else:
            original_conf = 0
            if field_name in original_fields:
                orig_field = original_fields[field_name]
                if isinstance(orig_field, dict):
                    original_conf = orig_field.get('confidence', 0)
            
            normalized[field_name] = {
                "value": field_value,
                "confidence": original_conf if original_conf > 0 else 50
            }
    
    return normalized


# ==================== SUBMIT ENDPOINT (UPDATED) ====================
@ocr_blueprint.route("/submit/<scan_id>", methods=["POST"])
@optional_auth
def submit_document(scan_id: str):
    """✅ Submit document with authentication, edit support, and AUTO-INCREMENT TITLE"""
    try:
        user_id = g.user_id
        
        print(f"\n✅ SUBMIT REQUEST")
        print(f"   Scan ID: {scan_id}")
        print(f"   User ID: {user_id}")
        
        try:
            db = get_db()
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            response = SubmissionResponse(success=False, error="Database connection failed")
            return jsonify(response.to_dict()), 500
        
        scan = db.get_scan(scan_id)
        
        if not scan:
            response = SubmissionResponse(success=False, error="Scan not found")
            return jsonify(response.to_dict()), 404
        
        # CHECK OWNERSHIP
        if not check_document_ownership(scan, user_id):
            print(f"❌ Permission denied: User {user_id} cannot submit scan {scan_id}")
            response = SubmissionResponse(
                success=False,
                error="Permission denied - you can only submit your own documents"
            )
            return jsonify(response.to_dict()), 403
        
        data = request.get_json() or {}
        
        print(f"\n📦 Received submit data:")
        print(f"   Has verified_fields: {'verified_fields' in data}")
        print(f"   Has edit_id: {'edit_id' in data}")
        print(f"   Has table: {'table' in data}")
        print(f"   Has title: {'title' in data}")
        
        # 🆕 NEW: Check if there's an edit_id
        edit_id = data.get('edit_id')
        edit = None
        
        if edit_id:
            print(f"\n📝 Checking for edit_id: {edit_id}")
            edit = db.get_edit(edit_id)
            
            if edit:
                # Verify edit belongs to this user and scan
                if edit.get('user_id') != user_id:
                    print(f"❌ Edit ownership mismatch: edit user {edit.get('user_id')} != current user {user_id}")
                    response = SubmissionResponse(
                        success=False,
                        error="Permission denied - edit belongs to different user"
                    )
                    return jsonify(response.to_dict()), 403
                
                if edit.get('scan_id') != scan_id:
                    print(f"❌ Edit scan mismatch: edit scan {edit.get('scan_id')} != requested scan {scan_id}")
                    response = SubmissionResponse(
                        success=False,
                        error="Edit does not belong to this scan"
                    )
                    return jsonify(response.to_dict()), 400
                
                print(f"✅ Using edited fields from edit_id: {edit_id}")
                verified_fields_raw = edit.get('edited_fields')
                table = edit.get('table', [])
                user_corrections = edit.get('user_corrections', {})
                
            else:
                print(f"⚠️ edit_id provided but edit not found: {edit_id}")
                response = SubmissionResponse(
                    success=False,
                    error=f"Edit not found: {edit_id}"
                )
                return jsonify(response.to_dict()), 404
        
        else:
            # No edit_id - use original flow
            print(f"ℹ️ No edit_id provided - using data from request or original scan")
            
            original_fields = scan.get('fields', {})
            verified_fields_raw = data.get('verified_fields')
            
            if verified_fields_raw:
                print(f"   ✅ Using verified_fields from request (user edited inline)")
            else:
                print(f"   ⚠️ No verified_fields sent - using original scan fields")
                verified_fields_raw = original_fields
            
            table = data.get('table')
            if table is None:
                table = scan.get('table', [])
            
            user_corrections = data.get('user_corrections', {})
        
        # Normalize verified fields
        original_fields = scan.get('fields', {})
        verified_fields = normalize_verified_fields(verified_fields_raw, original_fields)
        
        extraction_summary = data.get('extraction_summary') or scan.get('extraction_summary', {})
        
        # ============================================
        # 🆕 AUTO-INCREMENT TITLE LOGIC
        # ============================================# 

        title = data.get('title', None)

# Use provided title or keep existing/default
        if not title:
            # Check if there's an existing submission to get its title
            existing_submission = db.get_submission_by_scan(scan_id, user_id)
            if existing_submission:
                title = existing_submission.get('title')  # Keep existing title
    
        # If still no title, use document type as default
            if not title:
                title = scan.get('document_type', 'Document')

        print(f"Title: '{title}'")

        # ============================================
        # END AUTO-INCREMENT TITLE LOGIC
        # ============================================
        
        print(f"\n📊 Final submission data:")
        print(f"   Title: '{title}'")
        print(f"   Fields: {len(verified_fields)} fields")
        print(f"   Table: {len(table)} rows")
        print(f"   User corrections: {len(user_corrections)}")
        print(f"   Source: {'edit' if edit else 'direct/scan'}")
        
        submission_data = {
            'scan_id': scan_id,
            'user_id': user_id,
            'title': title,  
            'rescan_id': data.get('rescan_id'),
            'edit_id': edit_id,
            'document_type': data.get('document_type') or scan.get('document_type'),
            'verified_fields': verified_fields,
            'table': table,
            'user_corrections': user_corrections,
            'final_confidence': data.get('confidence') or scan.get('overall_confidence') or scan.get('confidence', 0.0),
            'extraction_summary': extraction_summary
        }
        
        submission_id = db.save_submission(submission_data)
        
        cleanup = request.args.get('cleanup', 'true').lower() == 'true'
        if cleanup:
            storage_metadata = scan.get('storage_metadata', {})
            if storage_metadata.get('stored'):
                try:
                    storage = get_storage()
                    if storage.delete_file(scan_id, storage_metadata):
                        print(f"🗑️ Cleaned up stored file for: {scan_id}")
                except Exception as e:
                    print(f"⚠️ File cleanup failed: {e}")
            
            # 🆕 NEW: Also delete edit if it exists
            if edit:
                try:
                    db.delete_edit(edit_id)
                    print(f"🗑️ Cleaned up edit: {edit_id}")
                except Exception as e:
                    print(f"⚠️ Edit cleanup failed: {e}")
        
        print(f"✅ Submission saved: {submission_id} (user: {user_id}, title: '{title}')")
        
        response_data = {
            "scan_id": scan_id,
            "submission_id": submission_id,
            "user_id": user_id,
            "edit_id": edit_id,
            "title": title,  # 🆕 Include title in response
            "success": True,
            "status": "submitted",
            "document_type": submission_data['document_type'],
            "verified_fields": verified_fields,
            "table": table,
            "extraction_summary": extraction_summary,
            "message": f"Document submitted successfully{' (from edited version)' if edit else ''}"
        }
        
        return jsonify(response_data), 200
    
    except Exception as e:
        print(f"❌ Submit error: {e}")
        import traceback
        traceback.print_exc()
        response = SubmissionResponse(success=False, error=str(e))
        return jsonify(response.to_dict()), 500
    

# ==================== TITLE ENDPOINT ========================

@ocr_blueprint.route("/title/<scan_id>", methods=["POST", "OPTIONS"])
@optional_auth
def set_document_title(scan_id: str):
    """
    🏷️ Set/Update title for a submitted document
    
    URL: POST /api/title/abc123
    
    Request body:
    {
        "title": "My PAN Card"
    }
    
    Response:
    {
        "success": true,
        "scan_id": "abc123",
        "submission_id": "sub456",
        "title": "My PAN Card",
        "message": "Title updated successfully"
    }
    """
    try:
        # Get user_id from auth
        user_id = g.user_id
        
        print(f"\n TITLE UPDATE REQUEST")
        print(f"   User ID: {user_id}")
        print(f"   Scan ID: {scan_id}")  # ← From URL
        
        # Get request data
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "Request body is required"
            }), 400
        
        # Get title from body (scan_id from URL)
        title = data.get('title')
        
        if not title:
            return jsonify({
                "success": False,
                "error": "title is required"
            }), 400
        
        # Validate title length
        title = title.strip()
        if len(title) < 1:
            return jsonify({
                "success": False,
                "error": "Title cannot be empty"
            }), 400
        
        if len(title) > 100:
            return jsonify({
                "success": False,
                "error": "Title too long (max 100 characters)"
            }), 400
        
        print(f"   Title: '{title}'")
        
        # Get database
        try:
            db = get_db()
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return jsonify({
                "success": False,
                "error": "Database connection failed"
            }), 500
        
        # Check if scan exists and belongs to user
        scan = db.get_scan(scan_id)
        if not scan:
            return jsonify({
                "success": False,
                "error": "Scan not found"
            }), 404
        
        # Check ownership
        if not check_document_ownership(scan, user_id):
            print(f"❌ Permission denied: User {user_id} cannot update scan {scan_id}")
            return jsonify({
                "success": False,
                "error": "Permission denied - you can only update your own documents"
            }), 403
        
        # Check if submission exists
        submission = db.get_submission_by_scan(scan_id, user_id)
        if not submission:
            return jsonify({
                "success": False,
                "error": "Submission not found. Please submit the document first."
            }), 404
        
        # Update title
        success = db.update_submission_title(scan_id, user_id, title)
        
        if not success:
            return jsonify({
                "success": False,
                "error": "Failed to update title"
            }), 500
        
        print(f"✅ Title updated successfully")
        
        # Return success response
        return jsonify({
            "success": True,
            "scan_id": scan_id,
            "submission_id": submission.get('submission_id'),
            "title": title,
            "message": "Title updated successfully"
        }), 200
    
    except Exception as e:
        print(f"❌ Title update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ocr_blueprint.route("/title/<scan_id>", methods=["GET", "OPTIONS"])
@optional_auth
def get_document_title(scan_id: str):  
    """
    📖 Get title for a document
    
    URL: GET /api/title/abc123
    
    Response:
    {
        "success": true,
        "scan_id": "abc123",
        "title": "My PAN Card"
    }
    """
    try:
        user_id = g.user_id
        
        # Get database
        db = get_db()
        
        # Check scan ownership
        scan = db.get_scan(scan_id)
        if not scan:
            return jsonify({
                "success": False,
                "error": "Scan not found"
            }), 404
        
        if not check_document_ownership(scan, user_id):
            return jsonify({
                "success": False,
                "error": "Permission denied"
            }), 403
        
        # Get submission
        submission = db.get_submission_by_scan(scan_id, user_id)
        if not submission:
            return jsonify({
                "success": False,
                "error": "Submission not found"
            }), 404
        
        title = submission.get('title', '')
        
        return jsonify({
            "success": True,
            "scan_id": scan_id,
            "submission_id": submission.get('submission_id'),
            "title": title
        }), 200
    
    except Exception as e:
        print(f"❌ Get title error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ==================== USER SCANS ENDPOINT ====================

@ocr_blueprint.route("/my-scans", methods=["GET"])
@optional_auth
def get_my_scans():
    """📋 Get all scans for current user"""
    try:
        user_id = g.user_id
        
        limit = int(request.args.get('limit', 100))
        skip = int(request.args.get('skip', 0))
        
        print(f"\n📋 GET MY SCANS")
        print(f"   User ID: {user_id}")
        print(f"   Limit: {limit}, Skip: {skip}")
        
        db = get_db()
        scans = db.get_user_scans(user_id, limit=limit, skip=skip)
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "count": len(scans),
            "scans": scans
        }), 200
    
    except Exception as e:
        print(f"❌ Error getting user scans: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== DOCUMENTATION ====================

@ocr_blueprint.route("/docs", methods=["GET"])
def docs():
    """API Documentation"""
    return jsonify({
        "api_version": "6.0.0 - Heavy Priority with Light Fallback",
        "description": "OCR API with Heavy API priority and automatic Light API fallback",
        "strategy": {
            "description": "Heavy API first, Light API if Heavy fails/times out",
            "heavy_timeout": "143 seconds",
            "fallback": "Automatic to Light API on Heavy failure"
        },
        "authentication": {
            "type": "JWT Bearer Token",
            "header": "Authorization: Bearer <token>",
            "anonymous_access": "Yes (user_id='0000')"
        },
        "mode": "heavy_priority",
        "heavy_api_configured": HEAVY_API_URL is not None,
        "endpoints": {
            "/api/scan": {
                "method": "POST",
                "auth": "Optional (JWT)",
                "description": "Scan document (Heavy priority → Light fallback)",
                "strategy": "Try Heavy API (143s timeout), fallback to Light if fails"
            },
            "/api/rescan/<scan_id>": {
                "method": "POST",
                "auth": "Optional (JWT)",
                "description": "Rescan document (Heavy priority → Light fallback)"
            },
            "/api/edit/<scan_id>": {  # 🆕 NEW
                "method": "PUT",
                "auth": "Optional (JWT)",
                "description": "Save user's edited fields (replaces existing edit)"
            },
            "/api/edit/<scan_id>": {  # 🆕 NEW
                "method": "GET",
                "auth": "Optional (JWT)",
                "description": "Get user's saved edit for a scan"
            },
            "/api/submit/<scan_id>": {
                "method": "POST",
                "auth": "Optional (JWT)",
                "description": "Submit verified data (supports edit_id in body)"
            },
            "/api/my-scans": {
                "method": "GET",
                "auth": "Optional (JWT)",
                "description": "Get all scans for current user"
            },
            # Inside /api/docs endpoint, add these entries to the "endpoints" dict:

            "/api/title": {
            "method": "POST",
            "auth": "Optional (JWT)",
            "description": "Set/Update title for submitted document",
            "body": {
                "scan_id": "string (required)",
                "title": "string (required, max 100 chars)"
            }
        },
        "/api/title/<scan_id>": {
            "method": "GET",
            "auth": "Optional (JWT)",
            "description": "Get title for a document"
        }
            }
    }), 200

# ==================== HEALTH CHECK ====================

@ocr_blueprint.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        db = get_db()
        stats = db.get_statistics()
        
        return jsonify({
            "status": "healthy",
            "service": "OCR API",
            "version": "6.0.0 - Heavy Priority",
            "mode": "heavy_priority",
            "strategy": "Heavy first (143s timeout) → Light fallback",
            "heavy_api": "configured" if HEAVY_API_URL else "not_configured",
            "database": {
                "status": "connected",
                "total_scans": stats.get('total_scans', 0),
                "total_submissions": stats.get('total_submissions', 0)
            },
            "features": {
                "heavy_priority": True,
                "light_fallback": True,
                "jwt_auth": True,
                "user_tracking": True,
                "file_storage": Config.ENABLE_FILE_STORAGE
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500
    
    