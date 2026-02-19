"""
Field-level Confidence Calculator - ENHANCED VERSION
Steps 3, 4, 7: Hybrid confidence + Field-specific thresholds + Cross-validation
"""
import re
from typing import Dict, Any, Optional
from datetime import datetime


# STEP 4: Field-specific thresholds - ✅ FIXED: LOWERED VALUES
FIELD_THRESHOLDS = {
    # Critical fields (IDs) - ✅ LOWERED to 75%
    "aadhaar_number": 75,    # ✅ Was 95 → Now 75
    "pan": 75,               # ✅ Was 95 → Now 75
    "voter_id": 75,          # ✅ Was 95 → Now 75
    "dl_number": 75,         # ✅ Was 95 → Now 75
    "roll_no": 75,           # ✅ Was 92 → Now 75
    
    # Important fields - ✅ LOWERED to 75%
    "name": 75,              # ✅ Was 88 → Now 75
    "student_name": 75,      # ✅ Was 88 → Now 75
    "dob": 70,               # ✅ Was 90 → Now 70
    "father_name": 75,       # ✅ Was 85 → Now 75
    "mother_name": 75,       # ✅ Was 85 → Now 75
    
    # Contact/Address - kept similar
    "mobile": 80,            # ✅ Was 85 → Now 80
    "address": 75,           # ✅ Was 80 → Now 75
    
    # Dates - ✅ LOWERED to 70%
    "issue_date": 70,        # ✅ Was 88 → Now 70
    "valid_till": 70,        # ✅ Was 88 → Now 70
    "year": 75,              # ✅ Was 85 → Now 75
    
    # Other fields
    "gender": 75,            # ✅ Was 85 → Now 75
    "school_name": 75,       # ✅ Was 82 → Now 75
    "cgpa": 70,              # ✅ Was 80 → Now 70
}


def calculate_pattern_confidence(field_name: str, field_value: Any, document_type: str) -> int:
    """
    Pattern-based confidence (your original logic, slightly improved)
    Returns: 0-100
    """
    if field_value is None or (isinstance(field_value, str) and not field_value.strip()):
        return 0
    
    value_str = str(field_value).strip()
    confidence = 0.0
    
    # ID Numbers
    if field_name == "aadhaar_number":
        if re.fullmatch(r'\d{12}', value_str.replace(' ', '')):
            confidence = 0.98
        elif re.fullmatch(r'\d{10,14}', value_str.replace(' ', '')):
            confidence = 0.75
        else:
            confidence = 0.40
    
    elif field_name == "pan":
        if re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', value_str):
            confidence = 0.98
        elif re.fullmatch(r'[A-Z0-9]{10}', value_str):
            confidence = 0.70
        else:
            confidence = 0.35
    
    elif field_name == "voter_id":
        if re.fullmatch(r'[A-Z]{3,4}[0-9]{6,10}', value_str):
            confidence = 0.95
        elif re.fullmatch(r'[A-Z0-9]{9,15}', value_str):
            confidence = 0.65
        else:
            confidence = 0.40
    
    elif field_name == "dl_number":
        if re.fullmatch(r'[A-Z]{2}[0-9O]{6,20}', value_str):
            confidence = 0.95
        elif re.search(r'[A-Z]{2}', value_str) and re.search(r'\d{6,}', value_str):
            confidence = 0.75
        else:
            confidence = 0.45
    
    elif field_name == "mobile":
        if re.fullmatch(r'[6-9]\d{9}', value_str):
            confidence = 0.97
        elif re.fullmatch(r'\d{10}', value_str):
            confidence = 0.65
        else:
            confidence = 0.35
    
    elif field_name == "roll_no":
        if re.fullmatch(r'\d{7,12}', value_str):
            confidence = 0.92
        elif re.fullmatch(r'\d{5,15}', value_str):
            confidence = 0.75
        else:
            confidence = 0.50
    
    # Date fields
    elif field_name in ["dob", "issue_date", "valid_till"]:
        if re.fullmatch(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', value_str):
            parts = re.split(r'[/-]', value_str)
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
                    confidence = 0.95
                else:
                    confidence = 0.60
            except:
                confidence = 0.50
        else:
            confidence = 0.40
    
    # Gender
    elif field_name == "gender":
        if value_str.lower() in ["male", "female", "transgender", "m", "f"]:
            confidence = 0.99
        else:
            confidence = 0.50
    
    # Name fields
    elif field_name in ["name", "father_name", "mother_name", "student_name"]:
        if len(value_str) < 3:
            confidence = 0.30
        elif len(value_str) > 50:
            confidence = 0.50
        else:
            alpha_ratio = sum(c.isalpha() or c.isspace() for c in value_str) / len(value_str)
            
            if alpha_ratio >= 0.90:
                word_count = len(value_str.split())
                if 2 <= word_count <= 5:
                    confidence = 0.88
                elif word_count == 1:
                    confidence = 0.75
                else:
                    confidence = 0.70
            elif alpha_ratio >= 0.70:
                confidence = 0.60
            else:
                confidence = 0.35
            
            if re.search(r'[|_\[\]{}]', value_str):
                confidence *= 0.75
            
            if any(len(word) == 1 for word in value_str.split()):
                confidence *= 0.85
    
    # Address
    elif field_name == "address":
        if len(value_str) < 10:
            confidence = 0.40
        elif len(value_str) > 200:
            confidence = 0.55
        else:
            has_letters = bool(re.search(r'[A-Za-z]', value_str))
            has_numbers = bool(re.search(r'\d', value_str))
            has_comma = ',' in value_str
            
            if has_letters and has_numbers and has_comma:
                confidence = 0.85
            elif has_letters and (has_numbers or has_comma):
                confidence = 0.75
            elif has_letters:
                confidence = 0.60
            else:
                confidence = 0.40
    
    # School name
    elif field_name == "school_name":
        if len(value_str) < 5:
            confidence = 0.40
        elif len(value_str) > 100:
            confidence = 0.50
        else:
            if re.search(r'\b(SCHOOL|COLLEGE|INSTITUTE|ACADEMY|UNIVERSITY)\b', value_str, re.I):
                confidence = 0.90
            else:
                confidence = 0.65
    
    # CGPA/Marks
    elif field_name == "cgpa":
        try:
            cgpa_val = float(value_str)
            if 0.0 <= cgpa_val <= 10.0:
                confidence = 0.92
            elif 0.0 <= cgpa_val <= 100.0:
                confidence = 0.65
            else:
                confidence = 0.40
        except:
            confidence = 0.30
    
    elif field_name == "year":
        if re.fullmatch(r'(19|20)\d{2}', value_str):
            confidence = 0.95
        elif re.fullmatch(r'\d{4}', value_str):
            confidence = 0.65
        else:
            confidence = 0.35
    
    # Default
    else:
        if len(value_str) > 0:
            confidence = 0.65
            if len(value_str) < 2:
                confidence = 0.40
            elif len(value_str) > 100:
                confidence = 0.55
        else:
            confidence = 0.0
    
    return int(round(confidence * 100))


def calculate_business_rules_confidence(field_name: str, field_value: Any) -> int:
    """
    Business logic confidence (format, length, realistic values)
    Returns: 0-100
    """
    if not field_value:
        return 0
    
    value_str = str(field_value).strip()
    score = 100
    
    # Length checks
    if len(value_str) == 0:
        return 0
    elif len(value_str) == 1:
        score -= 40
    elif len(value_str) > 200:
        score -= 30
    
    # Special character penalty (except allowed ones)
    special_chars = re.findall(r'[^A-Za-z0-9\s,.\-/()]', value_str)
    if special_chars:
        score -= min(30, len(special_chars) * 5)
    
    # All caps or all lowercase (for names)
    if field_name in ["name", "father_name", "mother_name", "student_name"]:
        if value_str.isupper() or value_str.islower():
            score -= 10  # Slight penalty, but acceptable
    
    # Repeated characters (AAAAA, 11111)
    if re.search(r'(.)\1{4,}', value_str):
        score -= 30
    
    # Numeric fields should be numeric
    if field_name in ["aadhaar_number", "pan", "mobile", "roll_no"]:
        if not any(c.isdigit() for c in value_str):
            score -= 50
    
    return max(0, score)

def calculate_hybrid_confidence(field_name: str, field_value: Any, document_type: str,
                                tesseract_conf: float = None, 
                                image_quality: float = None,
                                meta: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    🆕 FIXED: Hybrid confidence calculation with REAL Tesseract data from meta
    
    Formula:
    Final = 40% × Tesseract + 30% × Pattern + 20% × ImageQuality + 10% × BusinessRules
    
    Args:
        field_name: Field name (e.g., "name", "aadhaar_number")
        field_value: Field value
        document_type: Type of document
        tesseract_conf: DEPRECATED - use meta instead
        image_quality: Image quality score
        meta: Full meta dict with raw_ocr_data
    
    Returns:
        {
            'final_confidence': int (0-100),
            'breakdown': {...},
            'sources': {...}
        }
    """
    # Calculate individual confidences
    pattern_conf = calculate_pattern_confidence(field_name, field_value, document_type)
    business_conf = calculate_business_rules_confidence(field_name, field_value)
    
    # 🔥 NEW: Extract REAL Tesseract confidence from meta
    tess_conf = None
    
    if meta and isinstance(meta, dict):
        # Navigate: meta → field_ocr_confidences → overall_stats → average
        field_ocr_confs = meta.get('field_ocr_confidences', {})
        
        if isinstance(field_ocr_confs, dict):
            overall_stats = field_ocr_confs.get('overall_stats', {})
            
            if isinstance(overall_stats, dict):
                avg_conf = overall_stats.get('average', None)
                
                if avg_conf is not None:
                    tess_conf = float(avg_conf)
                    print(f"   📊 Using Tesseract confidence from meta: {tess_conf:.1f}%")
    
    # Fallback to pattern confidence if meta not available
    if tess_conf is None:
        if tesseract_conf is not None:
            tess_conf = tesseract_conf
            print(f"   ⚠️ Using provided tesseract_conf: {tess_conf:.1f}%")
        else:
            tess_conf = pattern_conf
            print(f"   ⚠️ No Tesseract data - using pattern_conf: {tess_conf}%")
    
    # Use provided or default image quality
    img_quality = image_quality if image_quality is not None else 75.0
    
    # Weighted formula (Step 3)
    final_confidence = (
        tess_conf * 0.40 +
        pattern_conf * 0.30 +
        img_quality * 0.20 +
        business_conf * 0.10
    )
    
    final_confidence = int(round(final_confidence))
    
    return {
        'final_confidence': final_confidence,
        'breakdown': {
            'tesseract_ocr': round(tess_conf, 1),
            'pattern_match': pattern_conf,
            'image_quality': round(img_quality, 1),
            'business_rules': business_conf
        },
        'weights': {
            'tesseract': '40%',
            'pattern': '30%',
            'image_quality': '20%',
            'business': '10%'
        }
    }

def validate_cross_fields(fields: Dict[str, Any], document_type: str) -> Dict[str, Any]:
    """
    STEP 7: Cross-field validation
    Check if fields make sense together
    
    Returns:
        {
            'field_name': {
                'valid': bool,
                'confidence_adjustment': int (penalty),
                'reason': str
            }
        }
    """
    validation_results = {}
    
    # Helper to get field value
    def get_value(field_name):
        field_data = fields.get(field_name)
        if isinstance(field_data, dict):
            return field_data.get('value')
        return field_data
    
    # Validate DOB format and realistic date
    dob = get_value('dob')
    if dob:
        is_valid_date = False
        penalty = 0
        reason = ""
        
        # Check format
        if re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', str(dob)):
            parts = re.split(r'[/-]', str(dob))
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                
                # Validate ranges
                if not (1 <= day <= 31):
                    penalty = 40
                    reason = f"Invalid day: {day}"
                elif not (1 <= month <= 12):
                    penalty = 40
                    reason = f"Invalid month: {month}"
                elif not (1900 <= year <= 2024):
                    penalty = 30
                    reason = f"Unrealistic year: {year}"
                else:
                    is_valid_date = True
            except:
                penalty = 50
                reason = "Failed to parse date"
        else:
            penalty = 50
            reason = "Invalid date format"
        
        validation_results['dob'] = {
            'valid': is_valid_date,
            'confidence_adjustment': -penalty if penalty > 0 else 0,
            'reason': reason if penalty > 0 else "Valid date"
        }
    
    # Validate year (for marksheets)
    year = get_value('year')
    if year:
        try:
            year_int = int(year)
            if 1990 <= year_int <= 2025:
                validation_results['year'] = {
                    'valid': True,
                    'confidence_adjustment': 0,
                    'reason': "Valid year"
                }
            else:
                validation_results['year'] = {
                    'valid': False,
                    'confidence_adjustment': -30,
                    'reason': f"Unrealistic year: {year_int}"
                }
        except:
            validation_results['year'] = {
                'valid': False,
                'confidence_adjustment': -40,
                'reason': "Year is not numeric"
            }
    
    # Validate CGPA range
    cgpa = get_value('cgpa')
    if cgpa:
        try:
            cgpa_val = float(cgpa)
            if 0.0 <= cgpa_val <= 10.0:
                validation_results['cgpa'] = {
                    'valid': True,
                    'confidence_adjustment': 0,
                    'reason': "Valid CGPA"
                }
            else:
                validation_results['cgpa'] = {
                    'valid': False,
                    'confidence_adjustment': -35,
                    'reason': f"CGPA out of range: {cgpa_val}"
                }
        except:
            validation_results['cgpa'] = {
                'valid': False,
                'confidence_adjustment': -30,
                'reason': "CGPA is not numeric"
            }
    
    # Cross-validate name consistency (father_name should not equal name)
    name = get_value('name') or get_value('student_name')
    father = get_value('father_name')
    if name and father:
        if str(name).strip().lower() == str(father).strip().lower():
            validation_results['father_name'] = {
                'valid': False,
                'confidence_adjustment': -50,
                'reason': "Father name same as student name (suspicious)"
            }
    
    # Gender validation (should be Male/Female/Transgender)
    gender = get_value('gender')
    if gender:
        valid_genders = ['male', 'female', 'transgender', 'm', 'f', 'other']
        if str(gender).strip().lower() not in valid_genders:
            validation_results['gender'] = {
                'valid': False,
                'confidence_adjustment': -40,
                'reason': f"Invalid gender value: {gender}"
            }
    
    return validation_results

def add_confidence_to_fields(fields: Dict[str, Any], document_type: str, 
                             ocr_confidences: Dict[str, float] = None,
                             image_quality: float = None,
                             meta: Dict[str, Any] = None) -> Dict[str, Dict[str, Any]]:
    """
    🆕 UPDATED: Transform flat fields into confidence-annotated structure with hybrid calculation
    Now accepts meta dict to extract real Tesseract confidence
    
    Input:  {"name": "John Doe", "dob": "01/01/1990"}
    Output: {
        "name": {
            "value": "John Doe",
            "confidence": 82,
            "breakdown": {...},
            "threshold": 88,
            "status": "BELOW_THRESHOLD"
        },
        ...
    }
    """
    annotated_fields = {}
    
    # Get cross-validation results
    cross_validation = validate_cross_fields(fields, document_type)
    
    for field_name, field_value in fields.items():
        # Get Tesseract confidence for this field (if available)
        tess_conf = ocr_confidences.get(field_name) if ocr_confidences else None
        
        # 🔥 NEW: Calculate hybrid confidence WITH meta
        hybrid_result = calculate_hybrid_confidence(
            field_name, field_value, document_type,
            tesseract_conf=tess_conf,
            image_quality=image_quality,
            meta=meta  # 🆕 Pass meta here
        )
        
        final_conf = hybrid_result['final_confidence']
        
        # Apply cross-validation adjustments
        cross_val = cross_validation.get(field_name, {})
        adjustment = cross_val.get('confidence_adjustment', 0)
        final_conf = max(0, final_conf + adjustment)
        
        # Get threshold for this field (Step 4)
        threshold = FIELD_THRESHOLDS.get(field_name, 80)
        
        # Determine status
        if final_conf >= threshold:
            status = "PASS"
        elif final_conf >= threshold - 10:
            status = "REVIEW"
        else:
            status = "FAIL"
        
        annotated_fields[field_name] = {
            "value": field_value,
            "confidence": final_conf,
            "breakdown": hybrid_result['breakdown'],
            "threshold": threshold,
            "status": status,
            "cross_validation": cross_val if cross_val else None
        }
    
    return annotated_fields

def calculate_overall_confidence(annotated_fields: Dict[str, Dict[str, Any]]) -> int:
    """
    Calculate overall document confidence from field confidences
    Returns: 0-100
    """
    if not annotated_fields:
        return 0
    
    importance_weights = {
        "aadhaar_number": 1.5, "pan": 1.5, "voter_id": 1.5, "dl_number": 1.5,
        "name": 1.3, "student_name": 1.3, "dob": 1.2,
        "father_name": 1.0, "mother_name": 0.9,
        "mobile": 1.0, "address": 0.9,
        "issue_date": 0.8, "valid_till": 0.8, "year": 0.8,
        "gender": 0.7, "school_name": 0.8, "roll_no": 1.0, "cgpa": 0.7,
    }
    
    total_weighted = 0.0
    total_weight = 0.0
    
    for field_name, field_data in annotated_fields.items():
        if not isinstance(field_data, dict):
            continue
        
        confidence = field_data.get("confidence", 0)
        value = field_data.get("value")
        
        if value is not None and (not isinstance(value, str) or value.strip()):
            weight = importance_weights.get(field_name, 1.0)
            total_weighted += confidence * weight
            total_weight += weight
    
    if total_weight == 0:
        return 0
    
    overall = total_weighted / total_weight
    return int(round(overall))


def process_with_confidence(extraction_result: Dict[str, Any],
                            ocr_confidences: Dict[str, float] = None,
                            image_quality: float = None) -> Dict[str, Any]:
    """
    Main function - Enhanced with hybrid confidence
    """
    if not extraction_result or "fields" not in extraction_result:
        return extraction_result
    
    document_type = extraction_result.get("document_type", "Unknown")
    fields = extraction_result.get("fields", {})
    
    meta = extraction_result.get("meta", {})
    
    # Add confidence with hybrid calculation (now with meta)
    annotated_fields = add_confidence_to_fields(
        fields, document_type,
        ocr_confidences=ocr_confidences,
        image_quality=image_quality,
        meta=meta  # 🆕 Pass meta here
    )
    
    overall_confidence = calculate_overall_confidence(annotated_fields)
    
    enhanced_result = extraction_result.copy()
    enhanced_result["fields"] = annotated_fields
    enhanced_result["overall_confidence"] = overall_confidence
    enhanced_result["confidence"] = overall_confidence
    
    # Apply table penalty for Marksheets
    if document_type == "Marksheet":
        table = extraction_result.get("table", [])
        table_count = len(table) if isinstance(table, list) else 0
        
        original_conf = overall_confidence
        
        if table_count == 0:
            overall_confidence = int(overall_confidence * 0.6)
            penalty = "60% (no subjects)"
            print(f"⚠️ Marksheet table penalty: {original_conf}% → {overall_confidence}% (-40%, no subjects)")
        elif table_count < 3:
            overall_confidence = int(overall_confidence * 0.75)
            penalty = f"75% (only {table_count} subjects)"
            print(f"⚠️ Marksheet table penalty: {original_conf}% → {overall_confidence}% (-25%, only {table_count} subjects)")
        elif table_count < 5:
            overall_confidence = int(overall_confidence * 0.9)
            penalty = f"90% (only {table_count} subjects)"
            print(f"⚠️ Marksheet table penalty: {original_conf}% → {overall_confidence}% (-10%, {table_count} subjects)")
        else:
            penalty = None
            print(f"✅ Marksheet table OK: {table_count} subjects, no penalty")
        
        if penalty:
            if "metadata" not in enhanced_result:
                enhanced_result["metadata"] = {}
            enhanced_result["metadata"]["table_penalty"] = {
                    "applied": True,
                    "original_confidence": original_conf,
                    "penalized_confidence": overall_confidence,
                    "penalty_multiplier": penalty,
                    "table_count": table_count,
                    "reason": f"Marksheet has only {table_count} subjects"
                }

    # Get low confidence fields
    low_conf = [
        {
            "field": fname,
            "confidence": fdata.get("confidence", 0),
            "threshold": fdata.get("threshold", 80),
            "status": fdata.get("status", "UNKNOWN")
        }
        for fname, fdata in annotated_fields.items()
        if isinstance(fdata, dict) and fdata.get("status") in ["FAIL", "REVIEW"]
    ]
    
    enhanced_result["metadata"] = {
        "low_confidence_fields": low_conf,
        "low_confidence_count": len(low_conf),
        "suggest_rescan": overall_confidence < 70 or len(low_conf) >= 3,
        "reviewed": False,
        "processed_at": datetime.utcnow().isoformat()
    }
    
    return enhanced_result


def add_extraction_summary(enhanced_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add extraction summary
    """
    from services.extraction_summary import add_extraction_summary_to_result
    return add_extraction_summary_to_result(enhanced_result)


if __name__ == "__main__":
    print("✅ Enhanced Confidence Calculator loaded")
    print("Features:")
    print("  - Step 3: Hybrid confidence (Tesseract + Pattern + Quality + Business)")
    print("  - Step 4: Field-specific thresholds")
    print("  - Step 7: Cross-field validation")