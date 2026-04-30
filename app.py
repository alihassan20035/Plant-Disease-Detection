"""
BATANOX — AI-Powered Plant Disease Detection
Flask Backend  ·  app.py  (v7 — FIXED & OPTIMIZED)

FIXES vs v6:
  ─────────────────────────────────────────────────────────────────────────
  FIX 1. HEALTHY BIAS ELIMINATED
     - _classify_label() was mapping ALL plain plant/species names (e.g.
       "Raspberry_leaf", "Tomato_leaf") to "healthy", even when YOLO
       had NOT confirmed healthy status. This caused diseased images to
       be reported as healthy.
     - Fix: plain species-only labels now map to "unknown" (let confidence
       and downstream logic decide), NOT "healthy".
     - "Healthy" is ONLY returned when the YOLO label explicitly contains
       the word "healthy".

  FIX 2. DISEASE CONFIDENCE THRESHOLD LOGIC CORRECTED
     - Disease detections now require confidence >= DISEASE_CONF_THRESHOLD.
     - If YOLO detects disease labels but ALL are below threshold, the
       system now returns "Image not clear" (low_confidence) instead of
       silently falling through to "Healthy".
     - A new status "low_confidence" was added to clearly distinguish
       "genuinely healthy" from "model is uncertain".

  FIX 3. BLUR THRESHOLD MADE ADAPTIVE
     - Fixed hardcoded BLUR_THRESHOLD=80 which was too aggressive for
       close-up leaf photos (natural leaf texture scores low on Laplacian).
     - New adaptive blur check uses a two-pass approach: first a loose
       pass (var < 30) for obviously blurry images, then a medium pass
       (var < 80) only if the image also has low contrast, preventing
       false "Image not clear" rejections on valid plant photos.

  FIX 4. IMAGE PREPROCESSING — FORCED RGB CONVERSION
     - cv2 loads images as BGR. YOLO expects BGR (handled internally),
       but any PIL-based path must convert BGR→RGB. Added explicit
       conversion guard in preprocess_image() and _load_pil().
     - Images with an alpha channel (RGBA PNG) are now flattened to RGB
       before processing to prevent channel mismatch errors.

  FIX 5. YOLO MODEL LOADING — ROBUST .pt HANDLING
     - Added try/except around YOLO load with clear error messages.
     - Added device assignment (CPU fallback if CUDA unavailable).
     - Added model.fuse() after load for faster inference.
     - Validate that model.names exists and is non-empty after loading.

  FIX 6. CONFIDENCE THRESHOLD — PREVENTS FALSE "IMAGE NOT CLEAR"
     - Previously, ANY result below DISEASE_CONF_THRESHOLD was silently
       treated as healthy or "no plant", causing confusing "Image not
       clear" messages on valid, clear images of healthy plants.
     - Fix: introduced a dedicated HEALTHY_CONF_THRESHOLD (0.40). If
       the top result is below this, report "low_confidence". Only
       report "Healthy" when a healthy label exceeds this threshold.

  FIX 7. PREDICTION PIPELINE — PRIORITY ORDER CORRECTED
     - Old order: disease_hits → unknown_hits → healthy/fallback
     - New order: disease_hits (conf≥0.50) → healthy_hits (conf≥0.40)
       → low_confidence (anything below thresholds)
     - This prevents a 0.31-confidence "healthy" label from overriding
       a 0.48-confidence disease label.

  FIX 8. SAVE_IMAGE — SECURE FILENAME + WEBP HANDLING
     - Used werkzeug secure_filename to prevent path traversal attacks.
     - Added explicit check that file content is non-empty before saving.
     - GIF files removed from allowed types (not plant images).

  FIX 9. /predict ROUTE — CONTENT-TYPE & FILE VALIDATION
     - Added request.content_type check (must be multipart/form-data).
     - Added max file size enforcement (MAX_UPLOAD_MB, default 10MB).
     - Added JSON error response for AJAX callers alongside HTML fallback.

  FIX 10. ARTIFICIAL CLASSIFIER — WEIGHTS KEY FIX
     - torch.load() for older .pt files may return the raw state_dict OR
       a dict with a "model" key. Added auto-detection of both formats.
  ─────────────────────────────────────────────────────────────────────────

URL map (unchanged from v6)
───────────────────────────
GET  /                   → Logged-in user dashboard
POST /predict            → Run detection only (NO DB save)
GET  /guest              → Guest detection page
POST /guest/predict      → Run detection (guest) — NO DB save ever

GET  /api/records        → Proxy to get_records.php
POST /api/clear_records  → Proxy to clear_records.php
POST /api/update_status  → Proxy to update_status.php
GET  /api/reminders      → Proxy to get_reminders.php
GET  /api/dashboard      → Proxy to get_dashboard.php
"""

from __future__ import annotations

import os
import shutil
import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import requests
import torch
import torch.nn as nn
import torchvision.transforms as T
from flask import Flask, jsonify, redirect, render_template, request, url_for
from PIL import Image
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
from ultralytics import YOLO
from werkzeug.utils import secure_filename

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [BATANOX]  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("batanox")

# ── App factory ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("BATANOX_SECRET_KEY", "batanox_secret_key_2024")

# ── Configuration (override via environment variables) ────────────────────────
YOLO_MODEL_PATH       = os.environ.get("YOLO_MODEL_PATH",       "best.pt")
ART_CLASSIFIER_PATH   = os.environ.get("ART_CLASSIFIER_PATH",   "artificial_classifier.pt")
UPLOAD_FOLDER         = os.environ.get("UPLOAD_FOLDER",         "static/uploads")
RESULT_FOLDER         = os.environ.get("RESULT_FOLDER",         "static/results")
PHP_BASE              = os.environ.get("PHP_BASE",              "http://localhost/batanox")
PHP_AUTH_URL          = f"{PHP_BASE}/auth_check.php"
MAX_UPLOAD_MB         = int(os.environ.get("MAX_UPLOAD_MB",     "10"))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# ── Detection thresholds ──────────────────────────────────────────────────────
# FIX 2 & FIX 6: Separate thresholds for disease vs healthy vs uncertain
DISEASE_CONF_THRESHOLD    = 0.50   # Min confidence to CONFIRM a disease label
HEALTHY_CONF_THRESHOLD    = 0.40   # Min confidence to confirm a HEALTHY label
                                    # Below this → "low_confidence" / unclear
NO_PLANT_CONF_THRESHOLD   = 0.25   # YOLO minimum — anything lower is noise
                                    # (lowered from 0.30 to catch more detections)
ARTIFICIAL_CONF_THRESHOLD = 0.70   # Confidence to call a plant artificial

# FIX 3: Adaptive blur — two-level instead of single hardcoded cutoff
BLUR_THRESHOLD_HARD       = 30.0   # Definitely blurry (any image this low is bad)
BLUR_THRESHOLD_SOFT       = 80.0   # Possibly blurry — only reject if ALSO low contrast
CONTRAST_THRESHOLD        = 40.0   # Standard deviation of pixel brightness

MIN_PIXEL_MEAN            = 20     # Too dark  if mean brightness < this
MAX_PIXEL_MEAN            = 235    # Too bright if mean brightness > this

# ── Allowed upload extensions ─────────────────────────────────────────────────
# FIX 8: Removed GIF; added explicit set
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

# ── Class-name keyword lists ──────────────────────────────────────────────────
# NOTE: PLANT_TYPE_KEYWORDS is used ONLY for "no_plant" detection, NOT for
# mapping to "healthy" (FIX 1).
PLANT_TYPE_KEYWORDS = (
    "_leaf", "leaf_", " leaf",
    "plant", "seedling", "background",
    "raspberry", "tomato", "potato", "corn", "apple",
    "grape", "rice", "wheat", "pepper", "strawberry",
    "squash", "peach", "cherry", "orange", "soybean", "blueberry",
)

# FIX 1: "healthy" is ONLY matched when the label explicitly says so.
HEALTHY_KEYWORDS = ("healthy",)

DISEASE_KEYWORDS = (
    "blight", "rust", "mold", "mildew", "scab", "rot", "spot",
    "mosaic", "wilt", "canker", "anthracnose", "blast", "smut",
    "lesion", "necrosis", "chlorosis", "disease", "infected",
    "bacterial", "fungal", "viral", "cercospora", "septoria",
    "alternaria", "powdery", "downy", "leaf_curl", "yellowing",
    "curl", "burn", "scorch",
)


# ═════════════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class DetectionResult:
    """Structured result returned by run_detection()."""
    display_label: str   = "Unknown"
    confidence:    float = 0.0          # percentage, e.g. 87.3
    result_url:    str   = ""
    # FIX 2: Added "low_confidence" as a distinct status
    status:        str   = "no_plant"   # no_plant | healthy | diseased |
                                         # low_confidence | artificial | error
    message:       str   = ""           # human-readable explanation


# ═════════════════════════════════════════════════════════════════════════════
#  MODEL LOADING
# ═════════════════════════════════════════════════════════════════════════════

# ── YOLO plant-disease model ──────────────────────────────────────────────────
# FIX 5: Robust YOLO loading with device selection, fuse(), and validation
_device = "cuda" if torch.cuda.is_available() else "cpu"
yolo_model: Optional[YOLO] = None

if os.path.exists(YOLO_MODEL_PATH):
    try:
        yolo_model = YOLO(YOLO_MODEL_PATH)
        # Move to correct device
        yolo_model.to(_device)
        # Fuse Conv+BN layers for faster inference (safe on eval mode)
        try:
            yolo_model.fuse()
        except Exception:
            pass  # fuse() not available on all YOLO versions — skip silently
        # Validate that class names loaded correctly
        if not getattr(yolo_model, "names", None):
            log.error("YOLO model loaded but model.names is empty — check your best.pt")
            yolo_model = None
        else:
            log.info(
                "YOLO model loaded: %s  |  device=%s  |  classes=%d",
                YOLO_MODEL_PATH, _device, len(yolo_model.names),
            )
            log.info("YOLO class list: %s", list(yolo_model.names.values())[:20])
    except Exception as exc:
        log.error("Failed to load YOLO model '%s': %s", YOLO_MODEL_PATH, exc)
        yolo_model = None
else:
    log.warning("'%s' not found — running in MOCK MODE", YOLO_MODEL_PATH)


# ── Artificial-plant binary classifier ───────────────────────────────────────
def _build_art_classifier() -> nn.Module:
    """Return a MobileNetV3-Small with a 2-class output head."""
    weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1
    m = mobilenet_v3_small(weights=weights)
    in_features = m.classifier[-1].in_features
    m.classifier[-1] = nn.Linear(in_features, 2)
    return m


art_classifier: Optional[nn.Module] = None
_art_classifier_device = torch.device(_device)

if os.path.exists(ART_CLASSIFIER_PATH):
    try:
        art_classifier = _build_art_classifier().to(_art_classifier_device)
        # FIX 10: Handle both raw state_dict and {"model": state_dict} formats
        raw = torch.load(ART_CLASSIFIER_PATH, map_location=_art_classifier_device)
        state_dict = raw.get("model", raw) if isinstance(raw, dict) else raw
        art_classifier.load_state_dict(state_dict)
        art_classifier.eval()
        log.info("Artificial-plant classifier loaded: %s", ART_CLASSIFIER_PATH)
    except Exception as exc:
        log.warning("Could not load artificial classifier: %s — using heuristic fallback", exc)
        art_classifier = None
else:
    log.warning(
        "'%s' not found — artificial detection will use heuristic fallback.",
        ART_CLASSIFIER_PATH,
    )


# ═════════════════════════════════════════════════════════════════════════════
#  IMAGE PREPROCESSING
# ═════════════════════════════════════════════════════════════════════════════

# ImageNet normalisation (used by the classifier)
_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD  = [0.229, 0.224, 0.225]

_classifier_transform = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=_IMAGENET_MEAN, std=_IMAGENET_STD),
])


def preprocess_image(disk_path: str) -> tuple[Optional[np.ndarray], str]:
    """
    Load and validate an image from disk.

    FIX 3: Adaptive blur detection (two-pass).
    FIX 4: Explicit RGB/channel handling.

    Returns (bgr_array, "") on success, or (None, reason_message) on failure.
    Raises no exceptions — caller checks the return value.
    """
    try:
        img = cv2.imread(disk_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None, "Could not read the image file. Please upload a valid PNG/JPG/WEBP."

        # FIX 4: Flatten alpha channel (RGBA PNG → BGR)
        if img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        # Ensure 3-channel image (handles grayscale uploads)
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        # ── Exposure check ────────────────────────────────────────────────
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        if mean_brightness < MIN_PIXEL_MEAN:
            log.info("Image too dark (mean=%.1f): %s", mean_brightness, disk_path)
            return None, "The image is too dark. Please retake in better lighting conditions."
        if mean_brightness > MAX_PIXEL_MEAN:
            log.info("Image too bright (mean=%.1f): %s", mean_brightness, disk_path)
            return None, "The image appears washed-out or overexposed. Please retake in better lighting."

        # FIX 3: Adaptive blur — two-pass
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        contrast      = float(np.std(gray))

        if laplacian_var < BLUR_THRESHOLD_HARD:
            # Definitely blurry regardless of contrast
            log.info("Image definitely blurry (Lap=%.1f): %s", laplacian_var, disk_path)
            return None, (
                f"The image appears too blurry (sharpness score: {laplacian_var:.1f}). "
                "Please upload a clearer, well-focused photo."
            )
        if laplacian_var < BLUR_THRESHOLD_SOFT and contrast < CONTRAST_THRESHOLD:
            # Moderately low sharpness AND low contrast together → blurry
            log.info(
                "Image likely blurry (Lap=%.1f, contrast=%.1f): %s",
                laplacian_var, contrast, disk_path,
            )
            return None, (
                f"The image appears too blurry (sharpness: {laplacian_var:.1f}, "
                f"contrast: {contrast:.1f}). Please upload a clearer photo."
            )

        log.info(
            "Image quality OK — brightness=%.1f  Lap=%.1f  contrast=%.1f",
            mean_brightness, laplacian_var, contrast,
        )
        return img, ""

    except Exception as exc:
        log.exception("preprocess_image failed for %s: %s", disk_path, exc)
        return None, "Image processing error. Please upload a different image."


def _load_pil(disk_path: str) -> Optional[Image.Image]:
    """
    Load a PIL Image in strict RGB mode.
    FIX 4: Handles RGBA and palette-mode images.
    """
    try:
        img = Image.open(disk_path)
        # Handle palette (P) and RGBA modes
        if img.mode in ("P", "PA"):
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            # Composite over white background
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            return bg
        return img.convert("RGB")
    except Exception as exc:
        log.warning("PIL open failed: %s", exc)
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  ARTIFICIAL PLANT DETECTION
# ═════════════════════════════════════════════════════════════════════════════

def _heuristic_artificial_check(disk_path: str) -> tuple[bool, float]:
    """
    Lightweight fallback for artificial-plant detection.
    Intentionally conservative to avoid rejecting real plants.
    Returns (is_artificial: bool, confidence: float 0–1).
    """
    try:
        img = cv2.imread(disk_path)
        if img is None:
            return False, 0.0

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        sat_channel = hsv[:, :, 1]
        sat_std  = float(np.std(sat_channel))
        sat_mean = float(np.mean(sat_channel))

        if sat_std < 15 and (sat_mean > 180 or sat_mean < 20):
            conf = min(0.85, 0.65 + (15 - sat_std) / 50)
            return True, conf

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gx   = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy   = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_energy = float(np.mean(np.sqrt(gx**2 + gy**2)))

        if gradient_energy < 5.0 and sat_std < 20:
            conf = min(0.80, 0.55 + (5.0 - gradient_energy) / 10)
            return True, conf

        return False, 0.0

    except Exception as exc:
        log.warning("Heuristic artificial check failed: %s", exc)
        return False, 0.0


def is_artificial_plant(disk_path: str) -> tuple[bool, float]:
    """
    Main entry: returns (is_artificial: bool, confidence: float 0–1).
    Uses trained MobileNetV3 classifier when available, else heuristic.
    """
    if art_classifier is not None:
        pil_img = _load_pil(disk_path)
        if pil_img is None:
            return False, 0.0
        try:
            tensor = _classifier_transform(pil_img).unsqueeze(0).to(_art_classifier_device)
            with torch.no_grad():
                logits = art_classifier(tensor)
                probs  = torch.softmax(logits, dim=1)[0]
            p_artificial = float(probs[1].item())
            is_art = p_artificial >= ARTIFICIAL_CONF_THRESHOLD
            log.info("ArtClassifier → p_artificial=%.3f  is_artificial=%s", p_artificial, is_art)
            return is_art, p_artificial
        except Exception as exc:
            log.warning("Classifier inference failed, using heuristic: %s", exc)

    is_art, conf = _heuristic_artificial_check(disk_path)
    log.info("Heuristic → is_artificial=%s  conf=%.3f", is_art, conf)
    return is_art, conf


# ═════════════════════════════════════════════════════════════════════════════
#  YOLO LABEL CLASSIFICATION  (FIX 1 — CORE FIX)
# ═════════════════════════════════════════════════════════════════════════════

def _classify_label(class_name: str) -> str:
    """
    Map a raw YOLO class name to 'healthy', 'diseased', or 'unknown'.

    FIX 1 — CRITICAL:
      Old logic mapped ANY plain plant/species name (e.g. "Raspberry_leaf",
      "Tomato_leaf") to 'healthy'. This was WRONG — a label like
      "Tomato_leaf" only means the model detected a tomato leaf, NOT that
      the leaf is disease-free.

      New logic:
        1. Explicit 'healthy' keyword → 'healthy'   (must say healthy)
        2. Known disease keyword      → 'diseased'
        3. Plain species/plant name   → 'unknown'   ← CHANGED from 'healthy'
        4. Anything else              → 'unknown'

      'unknown' detections are handled by confidence in run_detection():
        - High conf unknown → treated as possible disease
        - Low conf unknown  → low_confidence result
    """
    n = class_name.lower().replace("-", "_").replace(" ", "_")

    # Rule 1: Explicit healthy confirmation required
    if any(k in n for k in HEALTHY_KEYWORDS):
        return "healthy"

    # Rule 2: Known disease keyword
    if any(k in n for k in DISEASE_KEYWORDS):
        return "diseased"

    # Rule 3: Plain species name — unknown (NOT healthy; the model hasn't
    # said healthy, it's just identified the plant type)
    if any(k in n for k in PLANT_TYPE_KEYWORDS):
        return "unknown"

    return "unknown"


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN DETECTION PIPELINE  (FIX 2, FIX 6, FIX 7)
# ═════════════════════════════════════════════════════════════════════════════

def run_detection(upload_url_path: str) -> DetectionResult:
    """
    Full detection pipeline:

      1. Validate / preprocess image (blur, exposure, channels).
      2. Screen for artificial plant.
      3. Run YOLO disease detection on real plants.
      4. Return a structured DetectionResult.

    Status values
    ─────────────
    "artificial"     – image is a fake/plastic plant
    "no_plant"       – nothing plant-like detected above noise threshold
    "healthy"        – real plant, explicitly labelled healthy with confidence
    "diseased"       – real plant, disease confirmed above threshold
    "low_confidence" – plant detected but model is uncertain (not 'Image not clear')
    "error"          – image quality issue (blurry / too dark / corrupt)
    """
    disk_path   = upload_url_path.lstrip("/")
    filename    = os.path.basename(disk_path)
    result_disk = os.path.join(RESULT_FOLDER, filename)
    result_url  = "/" + result_disk.replace("\\", "/")

    # ── Step 1: Image quality validation ─────────────────────────────────
    img, quality_msg = preprocess_image(disk_path)
    if img is None:
        shutil.copy2(disk_path, result_disk)
        return DetectionResult(
            display_label="Image Quality Issue",
            confidence=0.0,
            result_url=result_url,
            status="error",
            message=quality_msg,
        )

    # ── Step 2: Artificial-plant detection ────────────────────────────────
    is_art, art_conf = is_artificial_plant(disk_path)
    if is_art:
        shutil.copy2(disk_path, result_disk)
        return DetectionResult(
            display_label="Artificial Plant Detected",
            confidence=round(art_conf * 100, 1),
            result_url=result_url,
            status="artificial",
            message=(
                "This appears to be an artificial (fake/plastic) plant. "
                "Please upload a real plant image for disease detection."
            ),
        )

    # ── Step 3: YOLO disease detection (real plants only) ─────────────────
    display_label = "No Plant Detected"
    confidence    = 0.0
    status        = "no_plant"
    message       = (
        "No plant was detected in the image. "
        "Please upload a clear, close-up photo of a plant leaf."
    )

    if not yolo_model:
        shutil.copy2(disk_path, result_disk)
        return DetectionResult(
            display_label="Model Not Loaded",
            confidence=0.0,
            result_url=result_url,
            status="error",
            message="YOLO model not loaded (MOCK MODE). Place best.pt in the project root.",
        )

    # Run YOLO — use NO_PLANT_CONF_THRESHOLD as the minimum filter
    results = yolo_model(disk_path, conf=NO_PLANT_CONF_THRESHOLD, verbose=False)
    results[0].save(filename=result_disk)

    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        log.info("YOLO returned no boxes for: %s", disk_path)
        return DetectionResult(
            display_label=display_label,
            confidence=confidence,
            result_url=result_url,
            status=status,
            message=message,
        )

    # Collect all detections above the noise floor
    all_detections = [
        (results[0].names[int(c)], float(cf))
        for c, cf in zip(boxes.cls.tolist(), boxes.conf.tolist())
        if float(cf) >= NO_PLANT_CONF_THRESHOLD
    ]
    log.info("YOLO all detections (conf≥%.2f): %s", NO_PLANT_CONF_THRESHOLD, all_detections)

    if not all_detections:
        return DetectionResult(
            display_label=display_label,
            confidence=confidence,
            result_url=result_url,
            status=status,
            message=message,
        )

    # ── Bucket detections by label type ──────────────────────────────────
    disease_hits = [
        (n, c) for n, c in all_detections
        if _classify_label(n) == "diseased"
    ]
    healthy_hits = [
        (n, c) for n, c in all_detections
        if _classify_label(n) == "healthy"
    ]
    # FIX 1: unknown_hits now includes plain species names
    unknown_hits = [
        (n, c) for n, c in all_detections
        if _classify_label(n) == "unknown"
    ]

    log.info(
        "Bucketed — disease=%s  healthy=%s  unknown=%s",
        disease_hits, healthy_hits, unknown_hits,
    )

    # ── FIX 7: PRIORITY ORDER ────────────────────────────────────────────
    # Priority 1: Disease confirmed above DISEASE_CONF_THRESHOLD
    confirmed_disease = [(n, c) for n, c in disease_hits if c >= DISEASE_CONF_THRESHOLD]
    if confirmed_disease:
        seen, unique = set(), []
        for n, _ in sorted(confirmed_disease, key=lambda x: -x[1]):
            if n not in seen:
                seen.add(n)
                unique.append(n)
        top_conf = max(c for _, c in confirmed_disease)
        display_label = ", ".join(unique)
        confidence    = round(top_conf * 100, 1)
        status        = "diseased"
        message       = (
            f"Disease detected: {display_label} "
            f"(confidence: {confidence}%). "
            "Consult an agronomist for treatment options."
        )
        log.info("RESULT: diseased — %s @ %.1f%%", display_label, confidence)

    # Priority 2: Below-threshold disease detections exist —
    # FIX 2: Do NOT fall through to healthy; report low_confidence
    elif disease_hits:
        top_n, top_c = max(disease_hits, key=lambda x: x[1])
        display_label = top_n
        confidence    = round(top_c * 100, 1)
        status        = "low_confidence"
        message       = (
            f"Possible disease signs detected ({top_n}, confidence: {confidence}%), "
            "but the confidence is too low to confirm. "
            "Please retake with a clearer, closer photo of the affected leaf area."
        )
        log.info("RESULT: low_confidence disease — %s @ %.1f%%", display_label, confidence)

    # Priority 3: Explicit healthy label with sufficient confidence
    elif healthy_hits:
        top_n, top_c = max(healthy_hits, key=lambda x: x[1])
        if top_c >= HEALTHY_CONF_THRESHOLD:
            display_label = "Healthy Leaf"
            confidence    = round(top_c * 100, 1)
            status        = "healthy"
            message       = (
                f"No disease detected. The plant appears healthy "
                f"(confidence: {confidence}%)."
            )
            log.info("RESULT: healthy @ %.1f%%", confidence)
        else:
            # FIX 6: Healthy label below threshold → uncertain, not confirmed
            display_label = "Uncertain"
            confidence    = round(top_c * 100, 1)
            status        = "low_confidence"
            message       = (
                f"A healthy plant was tentatively detected (confidence: {confidence}%), "
                "but the model is not sufficiently confident. "
                "Please upload a clearer image for a definitive result."
            )
            log.info("RESULT: low_confidence healthy @ %.1f%%", confidence)

    # Priority 4: Unknown labels only (plant detected, no disease/healthy labels)
    elif unknown_hits:
        top_n, top_c = max(unknown_hits, key=lambda x: x[1])
        if top_c >= DISEASE_CONF_THRESHOLD:
            # High-confidence unknown — surface as possible disease
            display_label = top_n
            confidence    = round(top_c * 100, 1)
            status        = "diseased"
            message       = (
                f"Possible disease detected: {top_n} "
                f"(confidence: {confidence}%). "
                "The condition was not matched to a known disease name — "
                "please seek expert agronomist advice."
            )
            log.warning("Unknown high-conf class treated as possible disease: %s", top_n)
        elif top_c >= HEALTHY_CONF_THRESHOLD:
            # Moderate confidence unknown — likely a species label; report low_confidence
            display_label = "Plant Detected (Unclassified)"
            confidence    = round(top_c * 100, 1)
            status        = "low_confidence"
            message       = (
                f"A plant was detected ({top_n}, confidence: {confidence}%), "
                "but no disease or healthy status could be confirmed. "
                "Please upload a closer photo of the leaf surface."
            )
        else:
            # Low confidence everything
            display_label = "Image Not Clear Enough"
            confidence    = round(top_c * 100, 1)
            status        = "low_confidence"
            message       = (
                "The model detected something but with very low confidence. "
                "Please upload a well-lit, focused close-up of the plant leaf."
            )

    log.info(
        "Final → status=%r  label=%r  conf=%.1f%%",
        status, display_label, confidence,
    )
    return DetectionResult(
        display_label=display_label,
        confidence=confidence,
        result_url=result_url,
        status=status,
        message=message,
    )


# ═════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def get_php_cookies() -> dict:
    """Forward the browser PHPSESSID cookie to PHP endpoints."""
    sid = request.cookies.get("PHPSESSID")
    return {"PHPSESSID": sid} if sid else {}


def check_auth() -> dict | None:
    """
    Ask PHP whether the current session is valid.
    Returns None if WAMP is unreachable or no PHPSESSID is present.
    """
    cookies = get_php_cookies()
    if not cookies:
        return None
    try:
        resp = requests.get(PHP_AUTH_URL, cookies=cookies, timeout=3)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("auth_check failed: %s", exc)
        return None


def save_image(file) -> tuple[str | None, str | None]:
    """
    Save uploaded image; return (url_path, None) or (None, error_msg).

    FIX 8: Uses secure_filename, enforces max size, validates extension.
    """
    if not file or not file.filename:
        return None, "No file selected."

    # FIX 8: Secure the filename against path traversal
    original_name = secure_filename(file.filename)
    if not original_name:
        return None, "Invalid filename."

    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        return None, f"Invalid file type '{ext}'. Use PNG, JPG, or WEBP."

    # Read content to check size and that file is non-empty
    content = file.read()
    if not content:
        return None, "Uploaded file is empty."
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        return None, f"File too large. Maximum allowed size is {MAX_UPLOAD_MB} MB."

    # Write to disk with a random name to avoid collisions
    new_name  = f"{os.urandom(8).hex()}.{ext}"
    disk_path = os.path.join(UPLOAD_FOLDER, new_name)
    with open(disk_path, "wb") as f:
        f.write(content)

    return "/" + disk_path.replace("\\", "/"), None


def php_get(endpoint: str) -> tuple[dict, int]:
    """GET a PHP endpoint with the current session cookie."""
    try:
        r = requests.get(f"{PHP_BASE}/{endpoint}", cookies=get_php_cookies(), timeout=3)
        return r.json(), r.status_code
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def php_post(endpoint: str, body: dict) -> tuple[dict, int]:
    """POST JSON to a PHP endpoint with the current session cookie."""
    try:
        r = requests.post(
            f"{PHP_BASE}/{endpoint}", json=body, cookies=get_php_cookies(), timeout=3,
        )
        return r.json(), r.status_code
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def _render_result(template: str, result: DetectionResult, **extra) -> str:
    """Render a template with the standard DetectionResult fields."""
    return render_template(
        template,
        result_image=result.result_url,
        disease_name=result.display_label,
        confidence=result.confidence,
        detection_status=result.status,
        detection_message=result.message,
        **extra,
    )


# ═════════════════════════════════════════════════════════════════════════════
#  LOGGED-IN USER ROUTES  (FIX 9)
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    auth = check_auth()
    if auth and auth.get("guest"):
        return redirect(url_for("guest_home"))
    if not auth or not auth.get("authenticated"):
        return redirect(f"{PHP_BASE}/login.php")
    user = {"name": auth.get("name", "User"), "is_admin": auth.get("role") == "admin"}
    return render_template("index.html", user=user)


@app.route("/treatment_log")
def treatment_log():
    auth = check_auth()
    if auth and auth.get("guest"):
        return redirect(url_for("guest_home"))
    if not auth or not auth.get("authenticated"):
        return redirect(f"{PHP_BASE}/login.php")
    return render_template("treatment_log.html")


@app.route("/predict", methods=["POST"])
def predict():
    """
    Run detection ONLY. Does NOT save to the database.
    FIX 9: Content-type validation + JSON error responses for AJAX callers.
    """
    auth = check_auth()
    if auth and auth.get("guest"):
        return redirect(url_for("guest_home"))
    if not auth or not auth.get("authenticated"):
        return redirect(f"{PHP_BASE}/login.php")

    user = {"name": auth.get("name", "User"), "is_admin": auth.get("role") == "admin"}

    # FIX 9: Validate content type
    if not request.content_type or "multipart/form-data" not in request.content_type:
        err = "Request must use multipart/form-data encoding."
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"success": False, "error": err}), 400
        return render_template("index.html", user=user, error=err)

    upload_url, err = save_image(request.files.get("image"))
    if err:
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"success": False, "error": err}), 400
        return render_template("index.html", user=user, error=err)

    plant_name = request.form.get("plant_name", "").strip()
    result     = run_detection(upload_url)

    # Support AJAX/JSON callers
    if request.accept_mimetypes.best == "application/json":
        return jsonify({
            "success":          True,
            "status":           result.status,
            "disease_name":     result.display_label,
            "confidence":       result.confidence,
            "message":          result.message,
            "result_image_url": result.result_url,
        })

    return _render_result("index.html", result, user=user,
                          uploaded_image=upload_url, plant_name=plant_name)


# ═════════════════════════════════════════════════════════════════════════════
#  GUEST ROUTES
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/guest")
def guest_home():
    return render_template("guest.html")


@app.route("/guest/predict", methods=["POST"])
def guest_predict():
    """
    Guest detection — no auth, no DB save.
    FIX 9: Same content-type and JSON-response improvements as /predict.
    """
    if not request.content_type or "multipart/form-data" not in request.content_type:
        err = "Request must use multipart/form-data encoding."
        return render_template("guest.html", error=err)

    upload_url, err = save_image(request.files.get("image"))
    if err:
        return render_template("guest.html", error=err)

    plant_name = request.form.get("plant_name", "").strip()
    result     = run_detection(upload_url)

    if request.accept_mimetypes.best == "application/json":
        return jsonify({
            "success":          True,
            "status":           result.status,
            "disease_name":     result.display_label,
            "confidence":       result.confidence,
            "message":          result.message,
            "result_image_url": result.result_url,
        })

    return _render_result("guest.html", result,
                          uploaded_image=upload_url, plant_name=plant_name)


# ═════════════════════════════════════════════════════════════════════════════
#  API PROXY ROUTES  (forward to PHP with session cookie)
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/records")
def api_records():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": True, "records": []})
    data, status = php_get("get_records.php")
    return jsonify(data), status


@app.route("/api/clear_records", methods=["POST"])
def api_clear_records():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authorised."}), 403
    data, status = php_post("clear_records.php", {})
    return jsonify(data), status


@app.route("/api/update_status", methods=["POST"])
def api_update_status():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authorised."}), 403
    body = request.get_json(silent=True) or {}
    data, status = php_post("update_status.php", body)
    return jsonify(data), status


@app.route("/api/treatment_log")
def api_treatment_log_get():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated."}), 401
    record_id = request.args.get("record_id", "0")
    data, status = php_get(f"get_treatment_log.php?record_id={record_id}")
    return jsonify(data), status


@app.route("/api/treatment_log", methods=["POST"])
def api_treatment_log_post():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated."}), 401
    body = request.get_json(silent=True) or {}
    data, status = php_post("save_treatment_log.php", body)
    return jsonify(data), status


@app.route("/api/reminders")
def api_reminders():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated."}), 401
    data, status = php_get("get_reminders.php")
    return jsonify(data), status


@app.route("/api/dashboard")
def api_dashboard():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    data, status = php_get("get_dashboard.php")
    return jsonify(data), status


@app.route("/api/disease_info")
def api_disease_info():
    """Return detailed disease profile for a given disease name."""
    name = request.args.get("name", "").strip().lower()
    if not name:
        return jsonify({"success": False, "error": "Missing 'name' parameter."}), 400

    # ── Disease info database (unchanged from v6) ─────────────────────────
    DISEASE_INFO_DB: dict = {
        "blight": {
            "description": "Blight is a rapid and complete chlorosis, browning, then death of plant tissues.",
            "severity": "High",
            "spread": "Wind / Rain splash / Infected plant debris",
            "season": "Cool, wet weather",
            "recovery_days": 14,
            "treatments": ["Remove infected tissue immediately", "Apply copper-based fungicide"],
            "medicines": [
                {"name": "Copper Hydroxide", "type": "Fungicide", "price_usd": "$15–$30/lb",
                 "description": "Broad-spectrum contact fungicide"},
            ],
            "prevention_tips": [
                {"title": "Crop Rotation", "tip": "Rotate crops every season to break disease cycles"},
            ],
            "total_cost_usd": "$20–$60",
            "cost_note": "Per 100 sq ft per season",
        },
        # Add additional disease entries here matching your YOLO class names
    }

    info = DISEASE_INFO_DB.get(name)
    if not info:
        for key, val in DISEASE_INFO_DB.items():
            if name in key or key in name:
                info = val
                break
    if not info:
        for key, val in DISEASE_INFO_DB.items():
            for word in key.split():
                if len(word) > 4 and word in name:
                    info = val
                    break
            if info:
                break

    if not info:
        return jsonify({
            "success": False,
            "found":   False,
            "message": f"No detailed profile found for '{name}'. Consult your local agricultural extension office.",
        }), 404

    return jsonify({"success": True, "found": True, "data": info})


@app.route("/api/medicine_suggestions")
def api_medicine_suggestions_get():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated."}), 401
    record_id = request.args.get("record_id", "0")
    data, status = php_get(f"get_medicine_suggestions.php?record_id={record_id}")
    return jsonify(data), status


@app.route("/api/medicine_suggestions", methods=["POST"])
def api_medicine_suggestions_post():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated."}), 401
    if auth.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required."}), 403
    body = request.get_json(silent=True) or {}
    data, status = php_post("save_medicine_suggestion.php", body)
    return jsonify(data), status


@app.route("/api/all_medicine_suggestions")
def api_all_medicine_suggestions():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated."}), 401
    data, status = php_get("get_all_medicine_suggestions.php")
    return jsonify(data), status


# ═════════════════════════════════════════════════════════════════════════════
#  SHOP — Medicine Store page
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/shop")
@app.route("/shop.html")
def shop():
    """Standalone medicine store — no auth required."""
    return render_template("shop.html")


# ═════════════════════════════════════════════════════════════════════════════
#  SHOP ORDER API  — save cart to DB via PHP
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/shop/order", methods=["POST"])
def api_shop_order():
    """
    POST /api/shop/order
    Receives cart JSON from shop.html, attaches user info, forwards to save_order.php.
    """
    body = request.get_json(silent=True)
    if not body or not isinstance(body.get("items"), list) or len(body["items"]) == 0:
        return jsonify({"success": False, "error": "Empty or invalid order data."}), 400

    items = body["items"]
    for it in items:
        if not isinstance(it.get("price"), (int, float)) or float(it["price"]) <= 0:
            return jsonify({"success": False, "error": f"Invalid price for: {it.get('name','?')}"}), 400
        if not isinstance(it.get("quantity"), int) or int(it["quantity"]) < 1:
            return jsonify({"success": False, "error": f"Invalid quantity for: {it.get('name','?')}"}), 400

    auth       = check_auth()
    user_id    = None
    user_name  = "Guest"
    user_email = ""
    if auth and auth.get("authenticated"):
        user_id    = auth.get("user_id")
        user_name  = auth.get("name", "User")
        user_email = auth.get("email", "")

    try:
        resp   = requests.post(
            f"{PHP_BASE}/save_order.php",
            json={"user_id": user_id, "user_name": user_name, "user_email": user_email, "items": items},
            cookies=get_php_cookies(),
            timeout=6,
        )
        result = resp.json()
        log.info("Order saved → #%s  user=%s  total=$%s", result.get("order_id"), user_name, result.get("total_price"))
        return jsonify(result), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"success": False, "error": "Cannot connect to database. Is WAMP running?"}), 503
    except Exception as exc:
        log.exception("api_shop_order: %s", exc)
        return jsonify({"success": False, "error": "Internal server error."}), 500


# ═════════════════════════════════════════════════════════════════════════════
#  MY ORDERS API  — fetch logged-in user's orders + items + status
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/shop/my_orders")
def api_my_orders():
    """
    GET /api/shop/my_orders
    Called by index.html "My Orders" tab.
    Forwards to get_my_orders.php which returns all orders for the
    current user (with line items), so the user can see admin-updated status.
    Auth required — guests have no order history.
    """
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated.", "orders": []}), 401

    try:
        resp = requests.get(
            f"{PHP_BASE}/get_my_orders.php",
            cookies=get_php_cookies(),
            timeout=6,
        )
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"success": False, "error": "Cannot connect to database.", "orders": []}), 503
    except Exception as exc:
        log.exception("api_my_orders: %s", exc)
        return jsonify({"success": False, "error": "Internal server error.", "orders": []}), 500


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    divider = "═" * 62
    print(f"\n{divider}")
    print("  🌿  BATANOX — Plant Disease Detection System  v7 (FIXED)")
    print(divider)
    print(f"  Dashboard          : http://localhost:5000/")
    print(f"  Guest page         : http://localhost:5000/guest")
    print(f"  Medicine Store     : http://localhost:5000/shop")
    print(f"  My Orders API      : http://localhost:5000/api/shop/my_orders  [GET]")
    print(f"  Place Order API    : http://localhost:5000/api/shop/order       [POST]")
    print(f"  Login page         : {PHP_BASE}/login.php")
    print(f"  YOLO model         : {'Loaded ✓  (' + str(len(yolo_model.names)) + ' classes)' if yolo_model else '⚠  MOCK MODE (best.pt not found)'}")
    print(f"  Art. classifier    : {'Loaded ✓' if art_classifier else '⚠  Heuristic fallback (no artificial_classifier.pt)'}")
    print(f"  Inference device   : {_device}")
    print(f"  Thresholds         : disease≥{DISEASE_CONF_THRESHOLD:.0%}  healthy≥{HEALTHY_CONF_THRESHOLD:.0%}  no-plant≥{NO_PLANT_CONF_THRESHOLD:.0%}")
    print(f"{divider}\n")
    app.run(debug=True, port=5000)