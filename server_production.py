"""
Production Server - Koyeb Docker Compatible
UPDATED: Increased timeout for Heavy API priority strategy
"""
import os
from waitress import serve
from flask import Flask, jsonify
from flask_cors import CORS
from routes.ocr_routes import ocr_blueprint
from config import Config
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

# Enable CORS
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://smart-form-frontend-gold.vercel.app", #(keep your frontend URL here)
        ],
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Register Blueprints
app.register_blueprint(ocr_blueprint, url_prefix="/api")

# Start background file cleanup scheduler
from services.file_storage import start_cleanup_scheduler
start_cleanup_scheduler()

# Root endpoints
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "name": "OCR API",
        "version": "6.0.0",
        "strategy": "Heavy Priority → Light Fallback",
        "status": "running",
        "mode": "production",
        "documentation": "/api/docs"
    })

@app.route("/health", methods=["GET"])
def health():
    try:
        from services.database import get_db
        db = get_db()
        stats = db.get_statistics()
        return jsonify({
            "status": "healthy",
            "service": "OCR API",
            "strategy": "Heavy Priority",
            "database": "connected",
            "total_scans": stats.get('total_scans', 0)
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({"success": False, "error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info("=" * 70)
    logger.info("🏭 OCR API - PRODUCTION SERVER (Heavy Priority)")
    logger.info("=" * 70)
    logger.info(f"Port: {port}")
    logger.info(f"Host: {host}")
    logger.info(f"Strategy: Heavy API first (143s) → Light fallback")
    logger.info(f"🚀 Server starting on http://{host}:{port}")
    logger.info(f"🏥 Health check: http://{host}:{port}/health")
    logger.info(f"MongoDB: {Config.MONGODB_URI[:50]}...")
    logger.info("=" * 70)
    
    print("\n" + "="*70)
    print(f"✅ SERVER READY → http://localhost:{port}")
    print(f"🏥 HEALTH CHECK → http://localhost:{port}/health")
    print(f"🗂️  MONGODB_URI → {Config.MONGODB_URI[:50]}...")
    print(f"📋 STRATEGY → Heavy Priority (143s timeout) → Light Fallback")
    print("="*70 + "\n")
    
    try:
        logger.info("⏳ Initializing Waitress server...")
        serve(
            app,
            host=host,
            port=port,
            threads=4,                # ✅ REDUCED: From 6 to 4 (less CPU load)
            channel_timeout=180,      # ✅ INCREASED: From 600 to 180s (3 minutes for Heavy API)
            url_scheme='http',
            ident='OCR-API/6.0.0',
            recv_bytes=131072,
            send_bytes=131072,
            connection_limit=50,      # ✅ REDUCED: From 100 to 50 (less memory)
            cleanup_interval=30,
            asyncore_use_poll=True
        )
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise

    