"""
MongoDB Document Models/Schemas - WITH Field Normalization Built-in
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


# ==================== FIELD SCHEMA (Built into models.py) ====================

DOCUMENT_FIELD_SCHEMA = {
    "PAN": ["pan", "name", "father_name", "dob"],
    "Aadhaar": ["aadhaar_number", "name", "dob", "gender", "father_name", "address", "mobile"],
    "Voter ID": ["voter_id", "name", "father_name", "husband_name", "dob", "gender"],
    "Driving Licence": ["dl_number", "name", "dob", "issue_date", "valid_till", "father_name", "address"],
    "Marksheet": ["student_name", "father_name", "mother_name", "school_name", "dob", "roll_no", "year", "cgpa"]
}


def normalize_fields(fields: Dict[str, Any], document_type: str) -> Dict[str, Any]:
    """
    Ensure all expected fields are present in the response (even if null)
    
    Args:
        fields: Extracted fields (may have confidence annotation)
        document_type: Type of document
    
    Returns:
        Normalized fields dict with all expected fields
    """
    expected_fields = DOCUMENT_FIELD_SCHEMA.get(document_type, [])
    
    if not expected_fields:
        return fields
    
    normalized = {}
    
    # Ensure all expected fields are present
    for field_name in expected_fields:
        if field_name in fields:
            field_data = fields[field_name]
            
            # Ensure it has confidence structure
            if isinstance(field_data, dict):
                normalized[field_name] = field_data
            else:
                normalized[field_name] = {
                    "value": field_data,
                    "confidence": 0
                }
        else:
            # Field missing - add empty structure
            normalized[field_name] = {
                "value": None,
                "confidence": 0
            }
    
    # Keep any extra fields not in schema
    for field_name, field_value in fields.items():
        if field_name not in normalized:
            if isinstance(field_value, dict):
                normalized[field_name] = field_value
            else:
                normalized[field_name] = {
                    "value": field_value,
                    "confidence": 0
                }
    
    return normalized


# ==================== ENUMS ====================

class DocumentType(str, Enum):
    """Supported document types"""
    PAN = "PAN"
    AADHAAR = "Aadhaar"
    VOTER_ID = "Voter ID"
    DRIVING_LICENCE = "Driving Licence"
    MARKSHEET = "Marksheet"
    UNKNOWN = "Unknown"


class ScanStatus(str, Enum):
    """Scan processing status"""
    SCANNED = "scanned"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    FAILED = "failed"


class SubmissionStatus(str, Enum):
    """Submission status"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"


# ==================== FIELD MODELS ====================

@dataclass
class FieldValue:
    """Individual field with confidence score"""
    value: Any
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "confidence": self.confidence
        }


@dataclass
class PanFields:
    """PAN Card fields"""
    pan: Optional[str] = None
    name: Optional[str] = None
    father_name: Optional[str] = None
    dob: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class AadhaarFields:
    """Aadhaar Card fields"""
    aadhaar_number: Optional[str] = None
    name: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    father_name: Optional[str] = None
    address: Optional[str] = None
    mobile: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class VoterIdFields:
    """Voter ID fields"""
    voter_id: Optional[str] = None
    name: Optional[str] = None
    father_name: Optional[str] = None
    husband_name: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class DrivingLicenceFields:
    """Driving Licence fields"""
    dl_number: Optional[str] = None
    name: Optional[str] = None
    dob: Optional[str] = None
    issue_date: Optional[str] = None
    valid_till: Optional[str] = None
    father_name: Optional[str] = None
    address: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class MarksheetFields:
    """Marksheet fields"""
    student_name: Optional[str] = None
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    school_name: Optional[str] = None
    dob: Optional[str] = None
    roll_no: Optional[str] = None
    year: Optional[str] = None
    cgpa: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SubjectGrade:
    """Subject with grade and marks"""
    subject: Optional[str] = None
    grade: Optional[str] = None
    marks: Optional[str] = None
    max_marks: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# ==================== MAIN DOCUMENT MODELS ====================

@dataclass
class ScanDocument:
    """
    Main Scan Document Model - WITH USER_ID
    Stored in 'scans' collection
    """
    scan_id: str
    user_id: str
    filename: str
    document_type: str
    fields: Dict[str, Any]
    confidence: float
    status: str = ScanStatus.SCANNED.value
    table: List[Dict[str, Any]] = field(default_factory=list)
    raw_text_preview: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    extraction_summary: Dict[str, Any] = field(default_factory=dict)
    rescan_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MongoDB document"""
        return {
            "scan_id": self.scan_id,
            "user_id": self.user_id,
            "filename": self.filename,
            "document_type": self.document_type,
            "fields": self.fields,
            "table": self.table,
            "confidence": self.confidence,
            "raw_text_preview": self.raw_text_preview,
            "meta": self.meta,
            "extraction_summary": self.extraction_summary,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "rescan_count": self.rescan_count
        }
    
    @classmethod
    def from_extraction(cls, scan_id: str, user_id: str, extraction_result: Dict[str, Any]) -> 'ScanDocument':
        """Create ScanDocument from extraction result"""
        return cls(
            scan_id=scan_id,
            user_id=user_id,
            filename=extraction_result.get('filename', ''),
            document_type=extraction_result.get('document_type', DocumentType.UNKNOWN.value),
            fields=extraction_result.get('fields', {}),
            table=extraction_result.get('table', []),
            confidence=extraction_result.get('confidence', 0.0),
            raw_text_preview=extraction_result.get('raw_text_preview', ''),
            meta=extraction_result.get('meta', {}),
            extraction_summary=extraction_result.get('extraction_summary', {})
        )


@dataclass
class RescanDocument:
    """
    Rescan Document Model - WITH USER_ID
    Stored in 'rescans' collection
    """
    rescan_id: str
    original_scan_id: str
    user_id: str
    filename: str
    document_type: str
    fields: Dict[str, Any]
    confidence: float
    table: List[Dict[str, Any]] = field(default_factory=list)
    raw_text_preview: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    extraction_summary: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MongoDB document"""
        return {
            "rescan_id": self.rescan_id,
            "original_scan_id": self.original_scan_id,
            "user_id": self.user_id,
            "filename": self.filename,
            "document_type": self.document_type,
            "fields": self.fields,
            "table": self.table,
            "confidence": self.confidence,
            "raw_text_preview": self.raw_text_preview,
            "meta": self.meta,
            "extraction_summary": self.extraction_summary,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_extraction(cls, rescan_id: str, original_scan_id: str, user_id: str,
                       extraction_result: Dict[str, Any]) -> 'RescanDocument':
        """Create RescanDocument from extraction result"""
        return cls(
            rescan_id=rescan_id,
            original_scan_id=original_scan_id,
            user_id=user_id,
            filename=extraction_result.get('filename', ''),
            document_type=extraction_result.get('document_type', DocumentType.UNKNOWN.value),
            fields=extraction_result.get('fields', {}),
            table=extraction_result.get('table', []),
            confidence=extraction_result.get('confidence', 0.0),
            raw_text_preview=extraction_result.get('raw_text_preview', ''),
            meta=extraction_result.get('meta', {}),
            extraction_summary=extraction_result.get('extraction_summary', {})
        )
    
@dataclass
class EditDocument:
    """
    Edit Document Model - User's edited fields
    Stored in 'edits' collection
    """
    edit_id: str
    scan_id: str
    user_id: str
    document_type: str
    edited_fields: Dict[str, Any]
    table: List[Dict[str, Any]] = field(default_factory=list)
    user_corrections: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "edit_id": self.edit_id,
            "scan_id": self.scan_id,
            "user_id": self.user_id,
            "document_type": self.document_type,
            "edited_fields": self.edited_fields,
            "table": self.table,
            "user_corrections": self.user_corrections,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class SubmissionDocument:
    """
    Submission Document Model - WITH USER_ID
    Stored in 'submissions' collection
    """
    submission_id: str
    scan_id: str
    user_id: str
    document_type: str
    verified_fields: Dict[str, Any]
    final_confidence: float
    title: Optional[str] = None
    rescan_id: Optional[str] = None
    edit_id: Optional[str] = None
    table: List[Dict[str, Any]] = field(default_factory=list)
    user_corrections: Dict[str, Any] = field(default_factory=dict)
    extraction_summary: Dict[str, Any] = field(default_factory=dict)
    status: str = SubmissionStatus.SUBMITTED.value
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MongoDB document"""
        return {
            "submission_id": self.submission_id,
            "scan_id": self.scan_id,
            "user_id": self.user_id,
            "title": self.title,
            "rescan_id": self.rescan_id,
            "edit_id": self.edit_id,
            "document_type": self.document_type,
            "verified_fields": self.verified_fields,
            "table": self.table,
            "user_corrections": self.user_corrections,
            "final_confidence": self.final_confidence,
            "extraction_summary": self.extraction_summary,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_submission_data(cls, submission_id: str, submission_data: Dict[str, Any]) -> 'SubmissionDocument':
        """Create SubmissionDocument from submission data"""
        return cls(
            submission_id=submission_id,
            scan_id=submission_data.get('scan_id'),
            user_id=submission_data.get('user_id', '0000'),
            rescan_id=submission_data.get('rescan_id'),
            document_type=submission_data.get('document_type'),
            verified_fields=submission_data.get('verified_fields', {}),
            table=submission_data.get('table', []),
            user_corrections=submission_data.get('user_corrections', {}),
            final_confidence=submission_data.get('final_confidence', 0.0),
            extraction_summary=submission_data.get('extraction_summary', {})
        )

# ==================== RESPONSE MODELS (ORDERED) ====================

@dataclass
class ScanResponse:
    """API Response for scan operation - ORDERED FIELDS"""
    success: bool
    scan_id: Optional[str] = None
    user_id: Optional[str] = None
    filename: Optional[str] = None
    document_type: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    table: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float] = None
    extraction_summary: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    submission_id: Optional[str] = None
    auto_submitted: bool = False
    meta: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with ORDERED fields (IDs first, confidence last)"""
        result = {}
    
    # 1️⃣ TOP: Identifiers (most important)
        if self.scan_id:
            result["scan_id"] = self.scan_id
        if self.user_id:
            result["user_id"] = self.user_id
    
    # 2️⃣ Status
        result["success"] = self.success
    
    # 3️⃣ Document Info
        if self.document_type:
            result["document_type"] = self.document_type
        if self.filename:
            result["filename"] = self.filename
    
    # 4️⃣ Data (fields and table) - NORMALIZED
        if self.fields is not None:
            normalized_fields = normalize_fields(self.fields, self.document_type or "Unknown")
            result["fields"] = normalized_fields
    
        if self.table is not None:
            result["table"] = self.table
    
    # 5️⃣ Message
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
    
    # 6️⃣ BOTTOM: Confidence scores (details last)
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.extraction_summary is not None:
            result["extraction_summary"] = self.extraction_summary

        if self.meta is not None:
            result["meta"] = self.meta
    
    # 7️⃣ Submission info (if any)
        if self.submission_id:
            result["submission_id"] = self.submission_id
        if self.auto_submitted:
            result["auto_submitted"] = self.auto_submitted
    
        return result

@dataclass
class RescanResponse:
    """API Response for rescan operation - ORDERED FIELDS"""
    success: bool
    rescan_id: Optional[str] = None
    scan_id: Optional[str] = None
    user_id: Optional[str] = None
    filename: Optional[str] = None
    document_type: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    table: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float] = None
    extraction_summary: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    submission_id: Optional[str] = None
    auto_submitted: bool = False
    meta: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with ORDERED fields"""
        result = {}
        
        # 1️⃣ TOP: Identifiers
        if self.rescan_id:
            result["rescan_id"] = self.rescan_id
        if self.scan_id:
            result["scan_id"] = self.scan_id
        if self.user_id:
            result["user_id"] = self.user_id
        
        # 2️⃣ Status
        result["success"] = self.success
        
        # 3️⃣ Document Info
        if self.document_type:
            result["document_type"] = self.document_type
        if self.filename:
            result["filename"] = self.filename
        
        # 4️⃣ Data - NORMALIZED
        if self.fields is not None:
            normalized_fields = normalize_fields(self.fields, self.document_type or "Unknown")
            result["fields"] = normalized_fields
        
        if self.table is not None:
            result["table"] = self.table
        
        # 5️⃣ Message
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
        
        # 6️⃣ BOTTOM: Confidence
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.extraction_summary is not None:
            result["extraction_summary"] = self.extraction_summary

        if self.meta is not None:
            result["meta"] = self.meta
        
        # 7️⃣ Submission info
        if self.submission_id:
            result["submission_id"] = self.submission_id
        if self.auto_submitted:
            result["auto_submitted"] = self.auto_submitted
        
        return result


@dataclass
class SubmissionResponse:
    """API Response for submission operation - ORDERED FIELDS"""
    success: bool
    submission_id: Optional[str] = None
    scan_id: Optional[str] = None
    user_id: Optional[str] = None
    status: Optional[str] = None
    verified_fields: Optional[Dict[str, Any]] = None
    table: Optional[List[Dict[str, Any]]] = None
    document_type: Optional[str] = None
    extraction_summary: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with ORDERED fields"""
        result = {}
        
        # 1️⃣ TOP: Identifiers
        if self.submission_id:
            result["submission_id"] = self.submission_id
        if self.scan_id:
            result["scan_id"] = self.scan_id
        if self.user_id:
            result["user_id"] = self.user_id
        
        # 2️⃣ Status
        result["success"] = self.success
        if self.status:
            result["status"] = self.status
        
        # 3️⃣ Document Info
        if self.document_type:
            result["document_type"] = self.document_type
        
        # 4️⃣ Data - NORMALIZED
        if self.verified_fields is not None:
            normalized_fields = normalize_fields(self.verified_fields, self.document_type or "Unknown")
            result["verified_fields"] = normalized_fields
        
        if self.table is not None:
            result["table"] = self.table
        
        # 5️⃣ Message
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
        
        # 6️⃣ BOTTOM: Summary
        if self.extraction_summary is not None:
            result["extraction_summary"] = self.extraction_summary
        
        return result


# ==================== UTILITY FUNCTIONS ====================

def validate_document_type(doc_type: str) -> bool:
    """Validate if document type is supported"""
    return doc_type in [t.value for t in DocumentType]


def get_field_schema(doc_type: str) -> Dict[str, type]:
    """Get field schema for document type"""
    schemas = {
        DocumentType.PAN.value: PanFields,
        DocumentType.AADHAAR.value: AadhaarFields,
        DocumentType.VOTER_ID.value: VoterIdFields,
        DocumentType.DRIVING_LICENCE.value: DrivingLicenceFields,
        DocumentType.MARKSHEET.value: MarksheetFields
    }
    return schemas.get(doc_type)


if __name__ == "__main__":
    print("✅ Models loaded with:")
    print("   - User ID support")
    print("   - Ordered response fields (IDs first, confidence last)")
    print("   - Field normalization (all expected fields present)")