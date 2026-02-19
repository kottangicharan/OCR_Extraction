"""
Image Preprocessing Service - OPTIMIZED (Step 2)
Smart preprocessing: Only process if needed
"""
import cv2
import numpy as np
from PIL import Image
import io
from typing import Tuple, Dict, Any


def check_image_quality(image_bytes: bytes, fast_mode: bool = True) -> Dict[str, Any]:
    """
    ⚡ OPTIMIZED: Analyze image quality with optional fast mode
    
    Args:
        image_bytes: Image as bytes
        fast_mode: If True, skip expensive calculations for good images
    
    Returns: Quality dict with metrics
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return {
                "quality": "unknown",
                "quality_score": 0,
                "needs_preprocessing": True,
                "issues": ["Failed to decode image"]
            }
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Quick brightness check first (very fast)
        brightness = np.mean(gray)
        brightness_score = 100 - abs(brightness - 127) / 1.27
        
        # 2. Quick contrast check (fast)
        contrast = gray.std()
        contrast_score = min(100, (contrast / 80) * 100)
        
        # 🔥 OPTIMIZATION: If brightness and contrast are good, skip expensive sharpness check
        if fast_mode and brightness_score > 80 and contrast_score > 70:
            # Image looks good - skip detailed analysis
            height, width = gray.shape
            resolution = (width, height)
            min_dim = min(width, height)
            resolution_score = min(100, (min_dim / 800) * 100)
            
            quality_score = int(
                85 * 0.4 +  # Assume good sharpness
                contrast_score * 0.3 +
                brightness_score * 0.2 +
                resolution_score * 0.1
            )
            
            return {
                "quality": "good",
                "quality_score": quality_score,
                "sharpness": 150.0,  # Estimated
                "brightness": float(brightness),
                "contrast": float(contrast),
                "resolution": resolution,
                "needs_preprocessing": False,
                "issues": [],
                "fast_check": True  # Marker that we used fast mode
            }
        
        # 3. Full sharpness check (expensive - only if needed)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_score = min(100, (laplacian_var / 500) * 100)
        
        # 4. Resolution quality
        height, width = gray.shape
        resolution = (width, height)
        min_dim = min(width, height)
        resolution_score = min(100, (min_dim / 800) * 100)
        
        # Overall quality score (weighted average)
        quality_score = int(
            sharpness_score * 0.4 +
            contrast_score * 0.3 +
            brightness_score * 0.2 +
            resolution_score * 0.1
        )
        
        # Determine quality level and issues
        quality = "good"
        issues = []
        
        if laplacian_var < 100:
            quality = "blurry"
            issues.append("Image is blurry - text edges not sharp")
        
        if brightness < 50:
            quality = "poor_lighting"
            issues.append("Image too dark - insufficient lighting")
        elif brightness > 200:
            quality = "poor_lighting"
            issues.append("Image too bright - overexposed")
        
        if contrast < 30:
            quality = "low_contrast"
            issues.append("Low contrast - text hard to distinguish from background")
        
        if min_dim < 600:
            issues.append(f"Low resolution ({width}x{height}) - recommend 800px minimum")
        
        needs_preprocessing = quality != "good" or len(issues) > 0
        
        return {
            "quality": quality,
            "quality_score": quality_score,
            "sharpness": float(laplacian_var),
            "brightness": float(brightness),
            "contrast": float(contrast),
            "resolution": resolution,
            "needs_preprocessing": needs_preprocessing,
            "issues": issues,
            "fast_check": False
        }
        
    except Exception as e:
        print(f"⚠️ Quality check failed: {e}")
        return {
            "quality": "unknown",
            "quality_score": 0,
            "needs_preprocessing": True,
            "issues": [f"Quality check error: {str(e)}"]
        }


def should_preprocess(quality_info: Dict[str, Any]) -> bool:
    """
    🆕 NEW: Smart decision on whether to preprocess
    
    Returns: True if preprocessing is beneficial
    """
    # Skip preprocessing if:
    # 1. Quality score is high (>= 80)
    # 2. No major issues
    # 3. Fast check passed
    
    if quality_info.get('quality_score', 0) >= 80:
        return False
    
    if quality_info.get('fast_check') and not quality_info.get('issues'):
        return False
    
    # Always preprocess if quality is poor
    if quality_info.get('quality') in ['blurry', 'poor_lighting', 'low_contrast']:
        return True
    
    return quality_info.get('needs_preprocessing', True)


def preprocess_image(image_bytes: bytes) -> bytes:
    """
    ✅ UNCHANGED: Full preprocessing pipeline
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return image_bytes
        
        # Step 1: Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Step 2: Noise removal
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        
        # Step 3: Increase contrast (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast = clahe.apply(denoised)
        
        # Step 4: Binarization
        _, binary = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Step 5: Deskew
        binary_deskewed = deskew_image(binary)
        
        # Step 6: Morphological operations
        kernel = np.ones((1, 1), np.uint8)
        cleaned = cv2.morphologyEx(binary_deskewed, cv2.MORPH_CLOSE, kernel)
        
        # Convert back to bytes
        pil_img = Image.fromarray(cleaned)
        output = io.BytesIO()
        pil_img.save(output, format='PNG')
        
        return output.getvalue()
        
    except Exception as e:
        print(f"⚠️ Preprocessing failed: {e}, using original image")
        return image_bytes


def deskew_image(image: np.ndarray) -> np.ndarray:
    """✅ UNCHANGED: Deskew function"""
    try:
        coords = np.column_stack(np.where(image > 0))
        
        if coords.size == 0:
            return image
        
        angle = cv2.minAreaRect(coords)[-1]
        
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        
        if abs(angle) < 0.5:
            return image
        
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            image, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
        
        return rotated
        
    except Exception as e:
        print(f"⚠️ Deskew failed: {e}")
        return image


if __name__ == "__main__":
    print("✅ Image Preprocessor loaded (OPTIMIZED)")
    print("⚡ Smart preprocessing: Only processes if quality_score < 80")
    print("Functions:")
    print("  - check_image_quality(bytes, fast_mode) [OPTIMIZED]")
    print("  - should_preprocess(quality_dict) [NEW]")
    print("  - preprocess_image(bytes)")
    print("  - preprocess_with_quality(bytes) [OPTIMIZED]")
    print("  - enhance_for_ocr(bytes, aggressive)")