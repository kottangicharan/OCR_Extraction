"""
JWT Authentication Service
Handles token verification and user extraction
"""
import jwt
from functools import wraps
from flask import request, jsonify, g
from typing import Dict, Any, Optional, Tuple
from config import Config
from datetime import datetime, timezone


def extract_token_from_header() -> Optional[str]:
    """Extract JWT token from Authorization header"""
    auth_header = request.headers.get('Authorization', '')
    
    if not auth_header:
        return None
    
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:].strip()
    return token if token else None


def verify_jwt_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Verify JWT token and extract payload"""
    if not token:
        return False, None, "No token provided"
    
    try:
        payload = jwt.decode(
            token,
            Config.JWT_SECRET_KEY,
            algorithms=[Config.JWT_ALGORITHM]
        )
        
        exp = payload.get('exp')
        if exp:
            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
            if datetime.now(timezone.utc) > exp_datetime:
                return False, None, "Token has expired"
        
        return True, payload, None
    
    except jwt.ExpiredSignatureError:
        return False, None, "Token has expired"
    
    except jwt.InvalidTokenError:
        return False, None, "Invalid token"
    
    except Exception as e:
        print(f"⚠️ Token verification error: {e}")
        return False, None, f"Token verification failed: {str(e)}"


def extract_user_info(payload: Dict[str, Any]) -> Dict[str, str]:
    """Extract user information from JWT payload"""
    user_id = payload.get('user_id') or payload.get('sub', '0000')
    email = payload.get('email', '')
    
    return {
        "user_id": str(user_id),
        "email": email
    }


def optional_auth(f):
    """
    Decorator for optional authentication
    Allows both authenticated and anonymous users
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "OPTIONS":
            return "", 200
        token = extract_token_from_header()
        
        # No token → Anonymous user
        if not token:
            g.user_id = "0000"
            g.email = None
            g.is_authenticated = False
            g.auth_message = "user_id not received - processed as anonymous"
            print(f"⚠️ Anonymous request - user_id set to '0000'")
            return f(*args, **kwargs)
        
        # Token present → Verify it
        is_valid, payload, error = verify_jwt_token(token)
        
        # Invalid token → Reject
        if not is_valid:
            print(f"❌ Invalid token: {error}")
            return jsonify({
                "success": False,
                "error": "Invalid or expired token",
                "details": error
            }), 401
        
        # Valid token → Extract user
        user_info = extract_user_info(payload)
        g.user_id = user_info["user_id"]
        g.email = user_info["email"]
        g.is_authenticated = True
        g.auth_message = None
        
        print(f"✅ Authenticated user: {g.user_id} ({g.email})")
        return f(*args, **kwargs)
    
    return decorated_function


def check_document_ownership(document: Dict[str, Any], current_user_id: str) -> bool:
    """Check if current user owns the document"""
    doc_user_id = document.get('user_id', '0000')
    
    # Anonymous documents can be accessed by anyone
    if doc_user_id == '0000':
        return True
    
    # User can access their own documents
    if doc_user_id == current_user_id:
        return True
    
    return False


if __name__ == "__main__":
    print("✅ JWT Authentication Service loaded")