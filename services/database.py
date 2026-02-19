"""
MongoDB Database Service - Fixed to store table in submissions
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, PyMongoError
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId
import json
from config import Config
from services.models import (
    ScanDocument, RescanDocument, SubmissionDocument,
    DocumentType, ScanStatus, SubmissionStatus
)

class DatabaseService:
    def __init__(self):
        try:
            self.client = MongoClient(Config.MONGODB_URI)
            self.db = self.client[Config.MONGODB_DATABASE]
            
            # Collections
            self.scans = self.db.scans
            self.rescans = self.db.rescans
            self.submissions = self.db.submissions
            self.edits = self.db.edits          
            # Create indexes for better performance
            self._create_indexes()
            
            # Test connection
            self.client.admin.command('ping')
            print("✅ MongoDB connected successfully")
            
        except ConnectionFailure as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise
    
    def _create_indexes(self):
        """Create database indexes INCLUDING user_id"""
        try:
            # Scans collection indexes
            self.scans.create_index([("scan_id", ASCENDING)], unique=True)
            self.scans.create_index([("user_id", ASCENDING)])  # 🆕 NEW: User index
            self.scans.create_index([("document_type", ASCENDING)])
            self.scans.create_index([("created_at", DESCENDING)])
            self.scans.create_index([("status", ASCENDING)])
            
            # Rescans collection indexes
            self.rescans.create_index([("rescan_id", ASCENDING)], unique=True)
            self.rescans.create_index([("original_scan_id", ASCENDING)])
            self.rescans.create_index([("user_id", ASCENDING)])  # 🆕 NEW: User index
            self.rescans.create_index([("created_at", DESCENDING)])
            
            # Submissions collection indexes
            self.submissions.create_index([("submission_id", ASCENDING)], unique=True)
            self.submissions.create_index([("scan_id", ASCENDING)])
            self.submissions.create_index([("user_id", ASCENDING)])
            self.submissions.create_index([("edit_id", ASCENDING)])  
            self.submissions.create_index([("created_at", DESCENDING)])
            self.submissions.create_index([("status", ASCENDING)])

            # Edits collection indexes
            self.edits.create_index([("edit_id", ASCENDING)], unique=True)
            self.edits.create_index([("scan_id", ASCENDING)])
            self.edits.create_index([("user_id", ASCENDING)])
            self.edits.create_index([("created_at", DESCENDING)])

            print("✅ Database indexes created (with user_id support)")
            
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")
    
    
    # ==================== SCAN OPERATIONS ====================
    
    def save_scan(self, scan_data: Dict[str, Any], user_id: str = "0000") -> str:
        """
        🆕 UPDATED: Save initial scan result with user_id
        
        Args:
            scan_data: Extraction result dict
            user_id: User ID from JWT (default: "0000" for anonymous)
        
        Returns: scan_id
        """
        try:
            from uuid import uuid4
            scan_id = str(uuid4())
            
            # 🆕 Create ScanDocument with user_id
            scan_doc = ScanDocument.from_extraction(scan_id, user_id, scan_data)
            
            # Convert to dict and insert
            self.scans.insert_one(scan_doc.to_dict())
            print(f"✅ Scan saved: {scan_id} (user: {user_id})")
            return scan_id
            
        except PyMongoError as e:
            print(f"❌ Error saving scan: {e}")
            raise
    
    def get_scan(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """Get scan by ID"""
        try:
            scan = self.scans.find_one({"scan_id": scan_id})
            if scan:
                scan['_id'] = str(scan['_id'])
            return scan
        except PyMongoError as e:
            print(f"❌ Error retrieving scan: {e}")
            return None
    
    def get_all_scans(self, limit: int = 100, skip: int = 0, 
            document_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all scans with pagination and filtering"""
        try:
            query = {}
            if document_type:
                query['document_type'] = document_type
            
            scans = list(self.scans.find(query)
                        .sort("created_at", DESCENDING)
                        .skip(skip)
                        .limit(limit))
            
            for scan in scans:
                scan['_id'] = str(scan['_id'])
            
            return scans
        except PyMongoError as e:
            print(f"❌ Error retrieving scans: {e}")
            return []
    
    def get_user_scans(self, user_id: str, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        """
        🆕 NEW: Get all scans for specific user
        
        Args:
            user_id: User ID to filter by
            limit: Max results
            skip: Pagination offset
        
        Returns:
            List of user's scans
        """
        try:
            scans = list(self.scans.find({"user_id": user_id})
                        .sort("created_at", DESCENDING)
                        .skip(skip)
                        .limit(limit))
            
            for scan in scans:
                scan['_id'] = str(scan['_id'])
            
            print(f"📋 Retrieved {len(scans)} scans for user {user_id}")
            return scans
        except PyMongoError as e:
            print(f"❌ Error retrieving user scans: {e}")
            return []
    
    def update_scan(self, scan_id: str, update_data: Dict[str, Any]) -> bool:
        """Update scan data"""
        try:
            update_data['updated_at'] = datetime.utcnow()
            result = self.scans.update_one(
                {"scan_id": scan_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            print(f"❌ Error updating scan: {e}")
            return False
    
    def delete_scan(self, scan_id: str) -> bool:
        """Delete scan"""
        try:
            result = self.scans.delete_one({"scan_id": scan_id})
            return result.deleted_count > 0
        except PyMongoError as e:
            print(f"❌ Error deleting scan: {e}")
            return False
    
    # ==================== RESCAN OPERATIONS ====================
    
    def save_rescan(self, rescan_data: Dict[str, Any], original_scan_id: str, user_id: str = "0000") -> str:
        """
        🆕 UPDATED: Save rescan result with user_id
        
        Args:
            rescan_data: Extraction result dict
            original_scan_id: Original scan ID
            user_id: User ID from JWT (default: "0000")
        
        Returns: rescan_id
        """
        try:
            from uuid import uuid4
            rescan_id = str(uuid4())
            
            # 🆕 Create RescanDocument with user_id
            rescan_doc = RescanDocument.from_extraction(
                rescan_id, 
                original_scan_id,
                user_id,  # 🆕 Pass user_id
                rescan_data
            )
            
            # Convert to dict and insert
            self.rescans.insert_one(rescan_doc.to_dict())
            
            # Update original scan's rescan count
            self.scans.update_one(
                {"scan_id": original_scan_id},
                {
                    "$inc": {"rescan_count": 1},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            print(f"✅ Rescan saved: {rescan_id} (user: {user_id})")
            return rescan_id
            
        except PyMongoError as e:
            print(f"❌ Error saving rescan: {e}")
            raise
    
    def get_rescan(self, rescan_id: str) -> Optional[Dict[str, Any]]:
        """Get rescan by ID"""
        try:
            rescan = self.rescans.find_one({"rescan_id": rescan_id})
            if rescan:
                rescan['_id'] = str(rescan['_id'])
            return rescan
        except PyMongoError as e:
            print(f"❌ Error retrieving rescan: {e}")
            return None
    
    def get_rescans_by_scan(self, scan_id: str) -> List[Dict[str, Any]]:
        """Get all rescans for a specific scan"""
        try:
            rescans = list(self.rescans.find({"original_scan_id": scan_id})
                .sort("created_at", DESCENDING))
            
            for rescan in rescans:
                rescan['_id'] = str(rescan['_id'])
            
            return rescans
        except PyMongoError as e:
            print(f"❌ Error retrieving rescans: {e}")
            return []
    
    def get_user_rescans(self, user_id: str, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        """
        🆕 NEW: Get all rescans for specific user
        """
        try:
            rescans = list(self.rescans.find({"user_id": user_id})
                          .sort("created_at", DESCENDING)
                          .skip(skip)
                          .limit(limit))
            
            for rescan in rescans:
                rescan['_id'] = str(rescan['_id'])
            
            return rescans
        except PyMongoError as e:
            print(f"❌ Error retrieving user rescans: {e}")
            return []
    
    # ==================== SUBMISSION OPERATIONS ====================
    
    def save_submission(self, submission_data: Dict[str, Any]) -> str:
        """
    UPSERT LOGIC: Update existing submission or create new one
    - If submission exists for this scan_id + user_id → UPDATE it (NO duplicates)
    - If not → CREATE new submission
    
        Returns: submission_id
        """
        try:    
            from uuid import uuid4
        
            user_id = submission_data.get('user_id', '0000')
            scan_id = submission_data.get('scan_id')
        
        # Check if submission already exists
            existing_submission = self.submissions.find_one({
                "scan_id": scan_id,
                "user_id": user_id
            })
        
            if existing_submission:
                #UPDATE existing submission (REPLACE mode)
                submission_id = existing_submission['submission_id']
            
                update_data = {
                    "title": submission_data.get('title', existing_submission.get('title')),
                    "rescan_id": submission_data.get('rescan_id'),
                    "edit_id": submission_data.get('edit_id'),
                    "document_type": submission_data.get('document_type'),
                    "verified_fields": submission_data.get('verified_fields', {}),
                    "table": submission_data.get('table', []),
                    "user_corrections": submission_data.get('user_corrections', {}),
                    "final_confidence": submission_data.get('final_confidence', 0.0),
                    "extraction_summary": submission_data.get('extraction_summary', {}),
                    "status": SubmissionStatus.SUBMITTED.value,
                    "updated_at": datetime.utcnow()
                }
            
                self.submissions.update_one(
                    {"submission_id": submission_id},
                    {"$set": update_data}
                )
            
                print(f" Submission UPDATED: {submission_id} (user: {user_id}, {len(update_data.get('table', []))} table rows)")
        
            else:
                # âž• CREATE new submission
                submission_id = str(uuid4())
            
                submission_doc = {
                    "submission_id": submission_id,
                    "title": submission_data.get('title', None),
                    "scan_id": scan_id,
                    "user_id": user_id,
                    "rescan_id": submission_data.get('rescan_id'),
                    "edit_id": submission_data.get('edit_id'),
                    "document_type": submission_data.get('document_type'),
                    "verified_fields": submission_data.get('verified_fields', {}),
                    "table": submission_data.get('table', []),
                    "user_corrections": submission_data.get('user_corrections', {}),
                    "final_confidence": submission_data.get('final_confidence', 0.0),
                    "extraction_summary": submission_data.get('extraction_summary', {}),
                    "status": SubmissionStatus.SUBMITTED.value,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            
                self.submissions.insert_one(submission_doc)
                print(f" Submission CREATED: {submission_id} (user: {user_id}, {len(submission_doc.get('table', []))} table rows)")
        
            # Update scan status
            if scan_id:
                self.scans.update_one(
                    {"scan_id": scan_id},
                    {
                        "$set": {
                            "status": ScanStatus.SUBMITTED.value, 
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
        
            return submission_id
        
        except PyMongoError as e:
            print(f"❌ Error saving submission: {e}")
            raise
    def get_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """Get submission by ID"""
        try:
            submission = self.submissions.find_one({"submission_id": submission_id})
            if submission:
                submission['_id'] = str(submission['_id'])
            return submission
        except PyMongoError as e:
            print(f"❌ Error retrieving submission: {e}")
            return None
    
    def get_submissions_by_scan(self, scan_id: str, user_id: str = None) -> List[Dict[str, Any]]:
        """
        🆕 UPDATED: Get all submissions for a specific scan (for title auto-increment)

        Args:
            scan_id: Scan ID
            user_id: Optional user ID to filter by user

        Returns:
            List of submission documents ordered by creation time
        """
        try:
            submissions = list(self.submissions.find({
                "scan_id": scan_id,
                "user_id": user_id  # ✅ Filter by BOTH scan_id AND user_id
            }).sort("created_at", ASCENDING))
    
            for submission in submissions:
                submission['_id'] = str(submission['_id'])
    
            print(f"📊 Found {len(submissions)} submissions for scan={scan_id}, user={user_id}")
            return submissions
        
        except PyMongoError as e:
            print(f"❌ Error retrieving submissions by scan: {e}")
            return []

    def get_all_submissions(self, limit: int = 100, skip: int = 0,
                        status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all submissions with pagination and filtering"""
        try:
            query = {}
            if status:
                query['status'] = status
            
            submissions = list(self.submissions.find(query)
                    .sort("created_at", DESCENDING)
                    .skip(skip)
                    .limit(limit))
            
            for submission in submissions:
                submission['_id'] = str(submission['_id'])
            
            return submissions
        except PyMongoError as e:
            print(f"❌ Error retrieving submissions: {e}")
            return []
    
    def get_user_submissions(self, user_id: str, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        """
        🆕 NEW: Get all submissions for specific user
        """
        try:
            submissions = list(self.submissions.find({"user_id": user_id})
                              .sort("created_at", DESCENDING)
                              .skip(skip)
                              .limit(limit))
            
            for submission in submissions:
                submission['_id'] = str(submission['_id'])
            
            return submissions
        except PyMongoError as e:
            print(f"❌ Error retrieving user submissions: {e}")
            return []
    
    def update_submission_title(self, scan_id: str, user_id: str, title: str) -> bool:
        """
        Update submission title by scan_id
    
        Args:
            scan_id: Scan ID to find submission
            user_id: User ID for ownership verification
            title: New title to set
    
        Returns:
            True if updated, False otherwise
        """
        try:
            # Find submission by scan_id and user_id
            result = self.submissions.update_one(
                {
                    "scan_id": scan_id,
                    "user_id": user_id
                },
                {
                    "$set": {
                        "title": title,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                print(f"✅ Title updated for scan {scan_id}: '{title}'")
                return True
            else:
                print(f"❌ No submission found for scan {scan_id} and user {user_id}")
                return False
            
        except PyMongoError as e:
            print(f"❌  Error updating title: {e}")
            return False

    def get_submission_by_scan(self, scan_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
    Get submission by scan_id and user_id
    
    Args:
        scan_id: Scan ID
        user_id: User ID
    
    Returns:
        Submission document or None
        """
        try:
            submission = self.submissions.find_one({
                "scan_id": scan_id,
                "user_id": user_id
            })

            if submission:
                submission['_id'] = str(submission['_id'])

            return submission
        
        except PyMongoError as e:
            print(f"❌ Error retrieving submission: {e}")
            return None

    # ==================== EDIT OPERATIONS ====================

    def save_or_update_edit(self, scan_id: str, user_id: str, edit_data: Dict[str, Any]) -> str:
        """
        Save or update edit (PUT behavior - replaces existing)
        """
        try:
            from uuid import uuid4
        
            # Check if edit already exists for this scan
            existing = self.edits.find_one({"scan_id": scan_id, "user_id": user_id})
        
            if existing:
                # Update existing edit
                edit_id = existing['edit_id']
                self.edits.update_one(
                    {"edit_id": edit_id},
                    {"$set": {
                        "edited_fields": edit_data.get('edited_fields', {}),
                        "table": edit_data.get('table', []),
                        "user_corrections": edit_data.get('user_corrections', {}),
                        "updated_at": datetime.utcnow()
                    }}
                )
                print(f"✅ Edit updated: {edit_id} (user: {user_id})")
            else:
                # Create new edit
                edit_id = str(uuid4())
                edit_doc = {
                    "edit_id": edit_id,
                    "scan_id": scan_id,
                    "user_id": user_id,
                    "document_type": edit_data.get('document_type'),
                    "edited_fields": edit_data.get('edited_fields', {}),
                    "table": edit_data.get('table', []),
                    "user_corrections": edit_data.get('user_corrections', {}),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                self.edits.insert_one(edit_doc)
                print(f"✅ Edit created: {edit_id} (user: {user_id})")
        
            return edit_id

        except PyMongoError as e:
            print(f"❌ Error saving edit: {e}")
            raise
    
    def get_edit(self, edit_id: str) -> Optional[Dict[str, Any]]:
        """Get edit by ID"""
        try:
            edit = self.edits.find_one({"edit_id": edit_id})
            if edit:
                edit['_id'] = str(edit['_id'])
            return edit
        except PyMongoError as e:
            print(f"❌ Error retrieving edit: {e}")
            return None

    def get_edit_by_scan(self, scan_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's edit for a specific scan"""
        try:
            edit = self.edits.find_one({"scan_id": scan_id, "user_id": user_id})
            if edit:
                edit['_id'] = str(edit['_id'])
            return edit
        except PyMongoError as e:
            print(f"❌ Error retrieving edit: {e}")
            return None

    def delete_edit(self, edit_id: str) -> bool:
        """Delete edit"""
        try:
            result = self.edits.delete_one({"edit_id": edit_id})
            return result.deleted_count > 0
        except PyMongoError as e:
            print(f"❌ Error deleting edit: {e}")
            return False

     # ==================== STATISTICS ====================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            stats = {
                "total_scans": self.scans.count_documents({}),
                "total_rescans": self.rescans.count_documents({}),
                "total_submissions": self.submissions.count_documents({}),
                "scans_by_type": {},
                "submissions_by_status": {},
                "recent_activity": []
            }
            
            # Scans by document type
            pipeline = [
                {"$group": {"_id": "$document_type", "count": {"$sum": 1}}}
            ]
            for doc in self.scans.aggregate(pipeline):
                stats['scans_by_type'][doc['_id']] = doc['count']
            
            # Submissions by status
            pipeline = [
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ]
            for doc in self.submissions.aggregate(pipeline):
                stats['submissions_by_status'][doc['_id']] = doc['count']
            
            # Recent activity (last 10 scans)
            recent = list(self.scans.find()
                        .sort("created_at", DESCENDING)
                        .limit(10))
            for item in recent:
                stats['recent_activity'].append({
                    "scan_id": item['scan_id'],
                    "user_id": item.get('user_id', '0000'),  # 🆕 Include user_id
                    "document_type": item['document_type'],
                    "created_at": item['created_at'].isoformat()
                })
            
            return stats
        except PyMongoError as e:
            print(f"❌ Error getting statistics: {e}")
            return {}
    
    def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        🆕 NEW: Get statistics for specific user
        """
        try:
            stats = {
                "user_id": user_id,
                "total_scans": self.scans.count_documents({"user_id": user_id}),
                "total_rescans": self.rescans.count_documents({"user_id": user_id}),
                "total_edits": self.edits.count_documents({}),
                "total_submissions": self.submissions.count_documents({"user_id": user_id}),
                "scans_by_type": {}
            }
            
            # User's scans by document type
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$group": {"_id": "$document_type", "count": {"$sum": 1}}}
            ]
            for doc in self.scans.aggregate(pipeline):
                stats['scans_by_type'][doc['_id']] = doc['count']
            
            return stats
        except PyMongoError as e:
            print(f"❌ Error getting user statistics: {e}")
            return {}
    
    # ==================== UTILITY ====================
    
    def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            print("✅ MongoDB connection closed")

# Singleton instance
_db_service = None

def get_db() -> DatabaseService:
    """Get database service instance"""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service


if __name__ == "__main__":
    # Test database connection
    db = get_db()
    print("Database service initialized successfully with user_id support")
    stats = db.get_statistics()
    print(f"Statistics: {json.dumps(stats, indent=2)}")

