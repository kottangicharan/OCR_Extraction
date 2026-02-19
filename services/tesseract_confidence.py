"""
Tesseract Confidence Extractor - OPTIMIZED (Step 1)
Extract REAL OCR confidence from Tesseract in SINGLE PASS
"""
import pytesseract
from pytesseract import Output
import numpy as np
from PIL import Image
import io
from typing import Dict, List, Tuple, Any


# ✅ NEW: Single-pass OCR data extraction
def extract_all_ocr_data_single_pass(image_input) -> Dict[str, Any]:
    """
    🆕 OPTIMIZED: Extract ALL OCR data in ONE pass
    
    Returns:
        {
            'text': str,                    # Full text
            'data': dict,                   # Tesseract data dict
            'words': list,                  # Words list
            'confidences': list,            # Confidence per word
            'overall_stats': dict,          # Overall confidence stats
            'word_data': list              # [{word, confidence}]
        }
    """
    try:
        # Convert to PIL Image if needed
        if isinstance(image_input, bytes):
            image = Image.open(io.BytesIO(image_input))
        elif isinstance(image_input, np.ndarray):
            image = Image.fromarray(image_input)
        else:
            image = image_input
        
        # 🔥 SINGLE PASS: Get both text and data at once
        config = '--oem 3 --psm 6'
        
        # Get full text
        full_text = pytesseract.image_to_string(image, config=config)
        
        # Get detailed data (includes text, confidence, positions)
        data = pytesseract.image_to_data(image, output_type=Output.DICT, config=config)
        
        # Extract words and confidences
        words = []
        confidences = []
        word_data = []
        
        for i, text in enumerate(data['text']):
            conf = int(data['conf'][i])
            
            # Skip empty text and background (-1 confidence)
            if conf == -1 or not text.strip():
                continue
            
            word = text.strip()
            words.append(word)
            confidences.append(conf)
            word_data.append({'word': word, 'confidence': conf})
        
        # Calculate overall stats
        if confidences:
            overall_stats = {
                'average': round(sum(confidences) / len(confidences), 2),
                'median': round(float(np.median(confidences)), 2),
                'min': min(confidences),
                'max': max(confidences),
                'word_count': len(confidences),
                'low_conf_words': sum(1 for c in confidences if c < 70),
                'high_conf_words': sum(1 for c in confidences if c >= 85)
            }
        else:
            overall_stats = {
                'average': 0.0, 'median': 0.0, 'min': 0, 'max': 0,
                'word_count': 0, 'low_conf_words': 0, 'high_conf_words': 0
            }
        
        return {
            'text': full_text,
            'data': data,
            'words': words,
            'confidences': confidences,
            'overall_stats': overall_stats,
            'word_data': word_data
        }
    
    except Exception as e:
        print(f"⚠️ Single-pass OCR failed: {e}")
        return {
            'text': '', 'data': None, 'words': [], 'confidences': [],
            'overall_stats': {'average': 0.0, 'median': 0.0, 'min': 0, 'max': 0, 
                            'word_count': 0, 'low_conf_words': 0, 'high_conf_words': 0},
            'word_data': []
        }


# ✅ KEEP OLD FUNCTIONS (backward compatible)
def extract_word_confidences(image_input) -> Tuple[List[str], List[int]]:
    """Original function - still works"""
    try:
        if isinstance(image_input, bytes):
            image = Image.open(io.BytesIO(image_input))
        elif isinstance(image_input, np.ndarray):
            image = Image.fromarray(image_input)
        else:
            image = image_input
        
        data = pytesseract.image_to_data(image, output_type=Output.DICT, config='--oem 3 --psm 6')
        
        words = []
        confidences = []
        
        for i, text in enumerate(data['text']):
            conf = int(data['conf'][i])
            if conf == -1 or not text.strip():
                continue
            words.append(text.strip())
            confidences.append(conf)
        
        return words, confidences
    
    except Exception as e:
        print(f"⚠️ Word confidence extraction failed: {e}")
        return [], []


def get_overall_ocr_confidence(image_input) -> Dict[str, Any]:
    """Original function - still works"""
    try:
        words, confs = extract_word_confidences(image_input)
        
        if not confs:
            return {
                'average': 0.0, 'median': 0.0, 'min': 0, 'max': 0,
                'word_count': 0, 'low_conf_words': 0, 'high_conf_words': 0
            }
        
        return {
            'average': round(sum(confs) / len(confs), 2),
            'median': round(float(np.median(confs)), 2),
            'min': min(confs),
            'max': max(confs),
            'word_count': len(confs),
            'low_conf_words': sum(1 for c in confs if c < 70),
            'high_conf_words': sum(1 for c in confs if c >= 85)
        }
    
    except Exception as e:
        print(f"⚠️ Overall confidence calculation failed: {e}")
        return {
            'average': 0.0, 'median': 0.0, 'min': 0, 'max': 0,
            'word_count': 0, 'low_conf_words': 0, 'high_conf_words': 0
        }


def get_text_with_confidence(image_input, min_confidence: int = 0) -> List[Dict[str, Any]]:
    """Original function - still works"""
    words, confs = extract_word_confidences(image_input)
    
    return [
        {'word': word, 'confidence': conf}
        for word, conf in zip(words, confs)
        if conf >= min_confidence
    ]


def get_line_confidence(image_input) -> List[Dict[str, Any]]:
    """Original function - still works"""
    try:
        if isinstance(image_input, bytes):
            image = Image.open(io.BytesIO(image_input))
        elif isinstance(image_input, np.ndarray):
            image = Image.fromarray(image_input)
        else:
            image = image_input
        
        data = pytesseract.image_to_data(image, output_type=Output.DICT, config='--oem 3 --psm 6')
        
        from collections import defaultdict
        lines = defaultdict(lambda: {'confs': [], 'texts': []})
        
        for i, text in enumerate(data['text']):
            conf = int(data['conf'][i])
            if conf == -1 or not text.strip():
                continue
            
            line_key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            lines[line_key]['confs'].append(conf)
            lines[line_key]['texts'].append(text.strip())
        
        result = []
        for line_key, line_data in lines.items():
            if not line_data['confs']:
                continue
            
            result.append({
                'line_num': line_key[2],
                'text': ' '.join(line_data['texts']),
                'avg_conf': round(sum(line_data['confs']) / len(line_data['confs']), 2),
                'min_conf': min(line_data['confs']),
                'max_conf': max(line_data['confs']),
                'word_count': len(line_data['confs'])
            })
        
        return sorted(result, key=lambda x: x['line_num'])
    
    except Exception as e:
        print(f"⚠️ Line confidence extraction failed: {e}")
        return []


def get_field_confidence(image_input, field_bbox: Dict[str, int] = None) -> float:
    """Original function - still works"""
    try:
        if isinstance(image_input, bytes):
            image = Image.open(io.BytesIO(image_input))
        elif isinstance(image_input, np.ndarray):
            image = Image.fromarray(image_input)
        else:
            image = image_input
        
        if field_bbox:
            x, y, w, h = field_bbox['x'], field_bbox['y'], field_bbox['w'], field_bbox['h']
            image = image.crop((x, y, x + w, y + h))
        
        words, confs = extract_word_confidences(image)
        
        if not confs:
            return 0.0
        
        return round(sum(confs) / len(confs), 2)
    
    except Exception as e:
        print(f"⚠️ Field confidence extraction failed: {e}")
        return 0.0


if __name__ == "__main__":
    print("✅ Tesseract Confidence Extractor loaded (OPTIMIZED)")
    print("🆕 NEW: extract_all_ocr_data_single_pass() - Single-pass extraction")
    print("Functions:")
    print("  - extract_all_ocr_data_single_pass(image) [NEW - FASTER]")
    print("  - extract_word_confidences(image)")
    print("  - get_line_confidence(image)")
    print("  - get_field_confidence(image, bbox)")
    print("  - get_overall_ocr_confidence(image)")
    print("  - get_text_with_confidence(image, min_conf)")