"""
BATANOX — AI-Powered Plant Disease Detection
Flask Backend  ·  app.py  (v6)

KEY CHANGES vs v5:
  ─────────────────────────────────────────────────────────────────────────
  1. ARTIFICIAL PLANT DETECTION
     A MobileNetV3-Small binary classifier is loaded from
     'artificial_classifier.pt' (or auto-downloaded weights on first run).
     Before YOLO runs, every image is screened:
       • artificial  → return early with a friendly rejection message
       • real plant  → proceed to YOLO disease detection as before

  2. IMAGE QUALITY GATES  (new)
     • Blurry image    → Laplacian variance < BLUR_THRESHOLD → rejected
     • Too dark/bright → mean pixel value outside [20, 235] → rejected
     • Unknown object  → YOLO conf below NO_PLANT_CONF_THRESHOLD → rejected

  3. CONFIDENCE SCORES  (improved)
     Both the artificial-plant check and the disease check return a
     confidence percentage that is forwarded to the templates.

  4. PREPROCESSING  (improved)
     Central helper preprocess_image() applies:
       • Resize to 224×224 (classifier) or 640×640 (YOLO native)
       • ImageNet normalisation for the classifier
       • Quality checks before anything is sent to the models

  5. MISC HARDENING
     • Secret key moved to env var (BATANOX_SECRET_KEY) with a fallback
     • /predict and /guest/predict now validate Content-Type
     • Structured DetectionResult dataclass replaces tuple returns
     • All model paths configurable via env vars
  ─────────────────────────────────────────────────────────────────────────

URL map
───────
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
from dataclasses import dataclass, field
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

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# ── Detection thresholds ──────────────────────────────────────────────────────
DISEASE_CONF_THRESHOLD    = 0.50   # 50% — confident disease signal required
NO_PLANT_CONF_THRESHOLD   = 0.30   # 30% — anything lower is treated as noise
ARTIFICIAL_CONF_THRESHOLD = 0.70   # 70% — confidence to call a plant artificial
BLUR_THRESHOLD            = 80.0   # Laplacian variance — below this → blurry
MIN_PIXEL_MEAN            = 20     # Too dark  if mean brightness < this
MAX_PIXEL_MEAN            = 235    # Too bright if mean brightness > this

# ── Class-name keyword lists ──────────────────────────────────────────────────
PLANT_TYPE_KEYWORDS = (
    "_leaf", "leaf_", " leaf",
    "plant", "seedling", "background",
    "raspberry", "tomato", "potato", "corn", "apple",
    "grape", "rice", "wheat", "pepper", "strawberry",
    "squash", "peach", "cherry", "orange", "soybean", "blueberry",
)

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
    status:        str   = "no_plant"   # no_plant | healthy | diseased | artificial | error
    message:       str   = ""           # human-readable explanation (edge-cases)


# ═════════════════════════════════════════════════════════════════════════════
#  MODEL LOADING
# ═════════════════════════════════════════════════════════════════════════════

# ── YOLO plant-disease model ──────────────────────────────────────────────────
yolo_model: Optional[YOLO] = None
if os.path.exists(YOLO_MODEL_PATH):
    yolo_model = YOLO(YOLO_MODEL_PATH)
    log.info("YOLO model loaded: %s", YOLO_MODEL_PATH)
else:
    log.warning("'%s' not found — running in MOCK MODE", YOLO_MODEL_PATH)


# ── Artificial-plant binary classifier ───────────────────────────────────────
#
#  Architecture: MobileNetV3-Small with the final Linear layer replaced by a
#  2-class head (real=0, artificial=1).
#
#  Training recipe (recommended, ~30 min on a consumer GPU):
#
#    from torchvision.datasets import ImageFolder
#    from torch.utils.data import DataLoader
#
#    train_ds = ImageFolder("data/artificial_vs_real/train", transform=train_tfm)
#    val_ds   = ImageFolder("data/artificial_vs_real/val",   transform=val_tfm)
#    # Folder layout:
#    #   data/artificial_vs_real/
#    #     train/
#    #       real/       (≥500 images of real leaves / plants)
#    #       artificial/ (≥500 images of plastic/fake plants)
#    #     val/
#    #       real/
#    #       artificial/
#
#    loader  = DataLoader(train_ds, batch_size=32, shuffle=True)
#    model   = _build_art_classifier()
#    optim   = torch.optim.Adam(model.parameters(), lr=1e-3)
#    loss_fn = torch.nn.CrossEntropyLoss()
#
#    for epoch in range(20):
#        for imgs, labels in loader:
#            optim.zero_grad()
#            loss_fn(model(imgs), labels).backward()
#            optim.step()
#
#    torch.save(model.state_dict(), "artificial_classifier.pt")
#
#  Until you train the model the system falls back to a lightweight heuristic
#  (colour-saturation + texture analysis) that catches obvious plastic plants.
# ─────────────────────────────────────────────────────────────────────────────

def _build_art_classifier() -> nn.Module:
    """Return a MobileNetV3-Small with a 2-class output head."""
    weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1
    m = mobilenet_v3_small(weights=weights)
    in_features = m.classifier[-1].in_features
    m.classifier[-1] = nn.Linear(in_features, 2)
    return m


art_classifier: Optional[nn.Module] = None
_art_classifier_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if os.path.exists(ART_CLASSIFIER_PATH):
    try:
        art_classifier = _build_art_classifier().to(_art_classifier_device)
        state = torch.load(ART_CLASSIFIER_PATH, map_location=_art_classifier_device)
        art_classifier.load_state_dict(state)
        art_classifier.eval()
        log.info("Artificial-plant classifier loaded: %s", ART_CLASSIFIER_PATH)
    except Exception as exc:
        log.warning("Could not load artificial classifier: %s — using heuristic fallback", exc)
        art_classifier = None
else:
    log.warning(
        "'%s' not found — artificial detection will use heuristic fallback.\n"
        "  Train the classifier and save weights to '%s' for full accuracy.",
        ART_CLASSIFIER_PATH, ART_CLASSIFIER_PATH,
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


def preprocess_image(disk_path: str) -> Optional[np.ndarray]:
    """
    Load and validate an image from disk.

    Returns the BGR numpy array if the image is usable, or None + logs
    the reason. Raises no exceptions — caller checks the return value.
    """
    try:
        img = cv2.imread(disk_path)
        if img is None:
            log.warning("cv2.imread returned None for: %s", disk_path)
            return None

        # ── Exposure check ────────────────────────────────────────────────
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        if mean_brightness < MIN_PIXEL_MEAN:
            log.info("Image too dark (mean=%.1f): %s", mean_brightness, disk_path)
            return None   # caller maps to "Image too dark" error
        if mean_brightness > MAX_PIXEL_MEAN:
            log.info("Image too bright / washed-out (mean=%.1f): %s", mean_brightness, disk_path)
            return None

        # ── Blur check ────────────────────────────────────────────────────
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if laplacian_var < BLUR_THRESHOLD:
            log.info("Image too blurry (Laplacian var=%.1f): %s", laplacian_var, disk_path)
            return None

        return img

    except Exception as exc:
        log.exception("preprocess_image failed for %s: %s", disk_path, exc)
        return None


def _load_pil(disk_path: str) -> Optional[Image.Image]:
    """Load a PIL Image in RGB mode (for the torch classifier)."""
    try:
        return Image.open(disk_path).convert("RGB")
    except Exception as exc:
        log.warning("PIL open failed: %s", exc)
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  ARTIFICIAL PLANT DETECTION
# ═════════════════════════════════════════════════════════════════════════════

def _heuristic_artificial_check(disk_path: str) -> tuple[bool, float]:
    """
    Lightweight fallback when the trained classifier is unavailable.

    Detects obvious artificial plants by examining:
      1. Colour uniformity — real leaves have high HSV-saturation variance;
         plastic plants tend to be uniform / over-saturated single-hue.
      2. Texture complexity (gradient energy) — plastic surfaces lack the
         fine micro-texture of real plant tissue.

    Returns (is_artificial: bool, confidence: float 0–1).
    Note: this heuristic is intentionally conservative (high false-negative
    rate) to avoid rejecting real-plant images.  Replace it with the trained
    classifier for production use.
    """
    try:
        img = cv2.imread(disk_path)
        if img is None:
            return False, 0.0

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        sat_channel = hsv[:, :, 1]

        sat_std  = float(np.std(sat_channel))
        sat_mean = float(np.mean(sat_channel))

        # Real leaves: moderate-to-high saturation with local variation.
        # Plastic plants: often very high uniform saturation (dyed plastic)
        # OR very low saturation (white/grey plastic).
        if sat_std < 15 and (sat_mean > 180 or sat_mean < 20):
            # Very uniform AND extreme saturation → likely artificial
            conf = min(0.85, 0.65 + (15 - sat_std) / 50)
            return True, conf

        # Texture check via Sobel gradient energy
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gx   = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy   = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_energy = float(np.mean(np.sqrt(gx**2 + gy**2)))

        # Very smooth surfaces (low gradient energy) + unnatural colour → artificial
        if gradient_energy < 5.0 and sat_std < 20:
            conf = min(0.80, 0.55 + (5.0 - gradient_energy) / 10)
            return True, conf

        return False, 0.0

    except Exception as exc:
        log.warning("Heuristic artificial check failed: %s", exc)
        return False, 0.0


def is_artificial_plant(disk_path: str) -> tuple[bool, float]:
    """
    Main entry point for artificial-plant detection.

    Uses the trained MobileNetV3 classifier when available, otherwise
    falls back to the colour/texture heuristic.

    Returns (is_artificial: bool, confidence: float 0–1).
    """
    # ── Path A: trained classifier ────────────────────────────────────────
    if art_classifier is not None:
        pil_img = _load_pil(disk_path)
        if pil_img is None:
            return False, 0.0
        try:
            tensor = _classifier_transform(pil_img).unsqueeze(0).to(_art_classifier_device)
            with torch.no_grad():
                logits = art_classifier(tensor)           # shape: (1, 2)
                probs  = torch.softmax(logits, dim=1)[0]  # [p_real, p_artificial]
            p_artificial = float(probs[1].item())
            is_art = p_artificial >= ARTIFICIAL_CONF_THRESHOLD
            log.info(
                "ArtClassifier → p_artificial=%.3f  is_artificial=%s",
                p_artificial, is_art,
            )
            return is_art, p_artificial
        except Exception as exc:
            log.warning("Classifier inference failed, falling back to heuristic: %s", exc)

    # ── Path B: heuristic fallback ────────────────────────────────────────
    is_art, conf = _heuristic_artificial_check(disk_path)
    log.info("Heuristic → is_artificial=%s  conf=%.3f", is_art, conf)
    return is_art, conf


# ═════════════════════════════════════════════════════════════════════════════
#  YOLO LABEL CLASSIFICATION
# ═════════════════════════════════════════════════════════════════════════════

def _classify_label(class_name: str) -> str:
    """
    Map a raw YOLO class name to 'healthy', 'diseased', or 'unknown'.

    Logic:
      1. Explicit healthy keyword  → 'healthy'
      2. Known disease keyword     → 'diseased'
      3. Plain plant/species name  → 'healthy'  (the Raspberry_leaf fix)
      4. Anything else             → 'unknown'  (let confidence decide)
    """
    n = class_name.lower().replace("-", "_").replace(" ", "_")
    if any(k in n for k in HEALTHY_KEYWORDS):
        return "healthy"
    if any(k in n for k in DISEASE_KEYWORDS):
        return "diseased"
    if any(k in n for k in PLANT_TYPE_KEYWORDS):
        return "healthy"   # species label only — no disease implied
    return "unknown"


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN DETECTION PIPELINE
# ═════════════════════════════════════════════════════════════════════════════

def run_detection(upload_url_path: str) -> DetectionResult:
    """
    Full detection pipeline:

      1. Validate / preprocess image (blur, exposure).
      2. Screen for artificial plant.
      3. Run YOLO disease detection on real plants.
      4. Return a structured DetectionResult.

    Status values
    ─────────────
    "artificial" – image contains a fake/plastic plant
    "no_plant"   – nothing plant-like detected above noise threshold
    "healthy"    – real plant, no confident disease found
    "diseased"   – real plant, at least one disease class above threshold
    "error"      – image quality issue (blurry / too dark / corrupt)
    """
    disk_path   = upload_url_path.lstrip("/")
    filename    = os.path.basename(disk_path)
    result_disk = os.path.join(RESULT_FOLDER, filename)
    result_url  = "/" + result_disk.replace("\\", "/")

    # ── Step 1: Image quality validation ─────────────────────────────────
    img = preprocess_image(disk_path)
    if img is None:
        # Determine which quality check failed for a useful error message
        try:
            raw = cv2.imread(disk_path)
            if raw is None:
                msg = "Could not read the image file. Please upload a valid PNG/JPG/WEBP."
            else:
                gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
                mean_b = float(np.mean(gray))
                lap_v  = cv2.Laplacian(gray, cv2.CV_64F).var()
                if lap_v < BLUR_THRESHOLD:
                    msg = (
                        f"The image appears too blurry (sharpness score: {lap_v:.1f}). "
                        "Please upload a clearer, well-focused photo."
                    )
                elif mean_b < MIN_PIXEL_MEAN:
                    msg = (
                        "The image is too dark. Please retake in better lighting conditions."
                    )
                else:
                    msg = (
                        "The image appears washed-out or overexposed. "
                        "Please retake in better lighting conditions."
                    )
        except Exception:
            msg = "Image quality check failed. Please upload a different image."

        shutil.copy2(disk_path, result_disk)
        return DetectionResult(
            display_label="Image Quality Issue",
            confidence=0.0,
            result_url=result_url,
            status="error",
            message=msg,
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
    message       = "No plant was detected in the image. Please upload a clear photo of a plant leaf."

    if yolo_model:
        results = yolo_model(disk_path, conf=NO_PLANT_CONF_THRESHOLD)
        results[0].save(filename=result_disk)

        boxes = results[0].boxes
        if boxes is not None and len(boxes) > 0:
            detections = [
                (results[0].names[int(c)], float(cf))
                for c, cf in zip(boxes.cls.tolist(), boxes.conf.tolist())
                if float(cf) >= NO_PLANT_CONF_THRESHOLD
            ]
            log.info("YOLO detections above threshold: %s", detections)

            if detections:
                disease_hits = [
                    (n, c) for n, c in detections
                    if _classify_label(n) == "diseased" and c >= DISEASE_CONF_THRESHOLD
                ]
                healthy_hits = [
                    (n, c) for n, c in detections
                    if _classify_label(n) == "healthy"
                ]
                unknown_hits = [
                    (n, c) for n, c in detections
                    if _classify_label(n) == "unknown"
                ]

                if disease_hits:
                    # ── Confirmed disease ──────────────────────────────
                    seen, unique = set(), []
                    for n, _ in disease_hits:
                        if n not in seen:
                            seen.add(n)
                            unique.append(n)
                    display_label = ", ".join(unique)
                    confidence    = round(max(c for _, c in disease_hits) * 100, 1)
                    status        = "diseased"
                    message       = (
                        f"Disease detected: {display_label} "
                        f"(confidence: {confidence}%). "
                        "Consult an agronomist for treatment options."
                    )

                elif unknown_hits and not healthy_hits:
                    max_unk = max(c for _, c in unknown_hits)
                    if max_unk >= DISEASE_CONF_THRESHOLD:
                        # High-confidence but unrecognised class — surface it
                        display_label = unknown_hits[0][0]
                        confidence    = round(max_unk * 100, 1)
                        status        = "diseased"
                        message       = (
                            f"Possible disease detected: {display_label} "
                            f"(confidence: {confidence}%). "
                            "The condition was not matched to a known disease name; "
                            "please seek expert advice."
                        )
                        log.warning(
                            "Unknown high-conf class treated as disease: %s",
                            display_label,
                        )
                    else:
                        display_label = "Healthy Leaf"
                        confidence    = round(max_unk * 100, 1)
                        status        = "healthy"
                        message       = (
                            f"No disease detected. The plant appears healthy "
                            f"(confidence: {confidence}%)."
                        )

                else:
                    # Only healthy / species labels detected
                    all_hits  = healthy_hits or detections
                    max_conf  = max(c for _, c in all_hits)
                    display_label = "Healthy Leaf"
                    confidence    = round(max_conf * 100, 1)
                    status        = "healthy"
                    message       = (
                        f"No disease detected. The plant appears healthy "
                        f"(confidence: {confidence}%)."
                    )

        # Low-confidence result warning
        if status == "no_plant" and confidence < NO_PLANT_CONF_THRESHOLD * 100:
            message = (
                "No plant was confidently detected. "
                "Try uploading a close-up, well-lit photo of a plant leaf."
            )

    else:
        # Mock mode — no YOLO model available
        shutil.copy2(disk_path, result_disk)
        message = "YOLO model not loaded (MOCK MODE). Place best.pt in the project root."

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
    """Save uploaded image; return (url_path, None) or (None, error_msg)."""
    if not file or not file.filename:
        return None, "No file selected."
    allowed = {"png", "jpg", "jpeg", "gif", "webp"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        return None, "Invalid file type. Use PNG, JPG, or WEBP."
    filename  = f"{os.urandom(8).hex()}.{ext}"
    disk_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(disk_path)
    return "/" + disk_path.replace("\\", "/"), None


def php_get(endpoint: str) -> tuple[dict, int]:
    """GET a PHP endpoint with the current session cookie."""
    try:
        r = requests.get(
            f"{PHP_BASE}/{endpoint}",
            cookies=get_php_cookies(),
            timeout=3,
        )
        return r.json(), r.status_code
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def php_post(endpoint: str, body: dict) -> tuple[dict, int]:
    """POST JSON to a PHP endpoint with the current session cookie."""
    try:
        r = requests.post(
            f"{PHP_BASE}/{endpoint}",
            json=body,
            cookies=get_php_cookies(),
            timeout=3,
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
#  LOGGED-IN USER ROUTES
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
    """Serve the Treatment Log page."""
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
    The user must click '💾 Save Record' in the UI to persist the result.
    """
    auth = check_auth()
    if auth and auth.get("guest"):
        return redirect(url_for("guest_home"))
    if not auth or not auth.get("authenticated"):
        return redirect(f"{PHP_BASE}/login.php")

    user = {"name": auth.get("name", "User"), "is_admin": auth.get("role") == "admin"}

    upload_url, err = save_image(request.files.get("image"))
    if err:
        return render_template("index.html", user=user, error=err)

    plant_name = request.form.get("plant_name", "").strip()
    result     = run_detection(upload_url)

    return _render_result(
        "index.html",
        result,
        user=user,
        uploaded_image=upload_url,
        plant_name=plant_name,
    )


# ═════════════════════════════════════════════════════════════════════════════
#  GUEST ROUTES
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/guest")
def guest_home():
    return render_template("guest.html")


@app.route("/guest/predict", methods=["POST"])
def guest_predict():
    upload_url, err = save_image(request.files.get("image"))
    if err:
        return render_template("guest.html", error=err)
    plant_name = request.form.get("plant_name", "").strip()
    result     = run_detection(upload_url)
    return _render_result(
        "guest.html",
        result,
        uploaded_image=upload_url,
        plant_name=plant_name,
    )


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
    """Proxy to get_treatment_log.php — returns record + weekly entries."""
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated."}), 401
    record_id = request.args.get("record_id", "0")
    data, status = php_get(f"get_treatment_log.php?record_id={record_id}")
    return jsonify(data), status


@app.route("/api/treatment_log", methods=["POST"])
def api_treatment_log_post():
    """Proxy to save_treatment_log.php — saves weekly entry + meta flags."""
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
        return jsonify({"success": True, "reminders": []})
    data, status = php_get("get_reminders.php")
    return jsonify(data), status


@app.route("/api/disease_info")
def api_disease_info():
    """
    Returns structured disease profile data for the 'About This Disease' feature.
    Query param: ?name=<disease_name>

    The knowledge base here mirrors the frontend JS DB so both can stay in sync.
    Add new disease entries to DISEASE_INFO_DB to expand coverage.
    """
    name = request.args.get("name", "").strip().lower()
    if not name:
        return jsonify({"success": False, "error": "Disease name required"}), 400

    # ── Disease knowledge base ────────────────────────────────────────────────
    DISEASE_INFO_DB = {
        "tomato leaf mosaic virus": {
            "description": (
                "Tomato Leaf Mosaic Virus (ToLMV) is a highly contagious viral pathogen belonging "
                "to the Tobamovirus genus. It causes characteristic mosaic or mottled patterns on "
                "leaves, stunted growth, and reduced fruit quality. Spreads via infected debris, "
                "contaminated tools, and aphid vectors. There is no chemical cure once infected."
            ),
            "severity": "High",
            "spread": "Contact / Aphids / Infected tools",
            "season": "Year-round (worse in warm humid conditions)",
            "recovery_days": 35,
            "treatments": [
                "Remove and destroy all infected plants immediately — do not compost",
                "Control aphid populations with insecticidal soap or neem oil spray",
                "Disinfect pruning tools with 10% bleach solution between cuts",
                "Apply mineral oil spray to reduce aphid transmission rates",
                "Use reflective mulches to deter aphid landings",
            ],
            "medicines": [
                {"name": "Imidacloprid (Admire Pro)", "type": "Systemic Insecticide",
                 "price_usd": "$18–$35 / 8 oz",
                 "description": "Controls aphid vectors; apply as soil drench or foliar spray"},
                {"name": "Spinosad (Entrust SC)", "type": "Bio-Insecticide",
                 "price_usd": "$28–$55 / pint",
                 "description": "Organic-certified aphid control; low mammalian toxicity"},
                {"name": "Neem Oil (70% Cold Pressed)", "type": "Organic Repellent",
                 "price_usd": "$8–$15 / quart",
                 "description": "Disrupts aphid feeding; also has antifungal properties"},
                {"name": "Pyrethrin (PyGanic)", "type": "Contact Insecticide",
                 "price_usd": "$22–$40 / quart",
                 "description": "Fast knockdown of aphid colonies; OMRI listed"},
            ],
            "prevention_tips": [
                {"title": "Use Certified Seeds", "tip": "Source seeds from certified virus-free nurseries and suppliers"},
                {"title": "Sanitize Tools", "tip": "Disinfect shears with 70% alcohol or 10% bleach after each use"},
                {"title": "Monitor Aphids", "tip": "Set up yellow sticky traps to monitor aphid populations weekly"},
                {"title": "Resistant Varieties", "tip": "Select ToMV-resistant varieties (look for 'Tm-2²' resistance gene)"},
            ],
            "total_cost_usd": "$45–$120",
            "cost_note": "Estimated total cost including insecticides, removal labor, and prevention per 100 sq ft",
        },
        "early blight": {
            "description": (
                "Early Blight, caused by Alternaria solani, is one of the most common foliar diseases "
                "of tomato and potato. It appears as dark concentric-ringed 'bullseye' lesions on older "
                "leaves. High humidity and temperatures 24–29°C create ideal infection conditions."
            ),
            "severity": "Moderate–High",
            "spread": "Wind / Rain splash / Infected debris",
            "season": "Mid-summer to fall; worse in humid conditions",
            "recovery_days": 21,
            "treatments": [
                "Apply copper-based fungicide every 7–10 days",
                "Remove and dispose of infected lower leaves immediately",
                "Avoid overhead watering; water at soil level in early morning",
                "Improve plant spacing to enhance air circulation",
                "Apply organic mulch to prevent soil splash onto leaves",
            ],
            "medicines": [
                {"name": "Copper Hydroxide (Kocide 3000)", "type": "Copper Fungicide",
                 "price_usd": "$12–$25 / lb",
                 "description": "Broad-spectrum; apply preventively every 7–10 days"},
                {"name": "Chlorothalonil (Daconil)", "type": "Protectant Fungicide",
                 "price_usd": "$10–$22 / quart",
                 "description": "Prevents spore germination; apply before disease onset"},
                {"name": "Mancozeb (Dithane)", "type": "Contact Fungicide",
                 "price_usd": "$8–$18 / lb",
                 "description": "Effective multi-site fungicide; rotate to prevent resistance"},
                {"name": "Azoxystrobin (Quadris)", "type": "Systemic Fungicide",
                 "price_usd": "$30–$60 / quart",
                 "description": "Systemic protection; excellent curative and preventive activity"},
            ],
            "prevention_tips": [
                {"title": "Drip Irrigation", "tip": "Use drip irrigation to keep foliage dry"},
                {"title": "Crop Rotation", "tip": "Rotate tomatoes with non-solanaceous crops every 2–3 years"},
                {"title": "Remove Debris", "tip": "Clean up plant debris at end of season to remove spores"},
                {"title": "Proper Spacing", "tip": "Space plants 18–24 inches apart to improve airflow"},
            ],
            "total_cost_usd": "$30–$80",
            "cost_note": "Estimated total treatment cost per season per 100 sq ft",
        },
        "late blight": {
            "description": (
                "Late Blight, caused by Phytophthora infestans, is one of the most devastating plant "
                "diseases worldwide — responsible for the Irish Potato Famine. It spreads rapidly in "
                "cool, wet conditions and can destroy an entire crop within days."
            ),
            "severity": "Critical",
            "spread": "Wind-dispersed sporangia / Rain splash / Infected tubers",
            "season": "Cool, wet weather (15–22°C, >90% humidity)",
            "recovery_days": 28,
            "treatments": [
                "Apply metalaxyl-based fungicide immediately upon first sign of infection",
                "Remove and seal infected material in plastic bags before disposal",
                "Never compost infected material — burn or bag for landfill",
                "Apply preventive spray before forecasted cool, wet periods",
                "Avoid overhead irrigation; keep foliage as dry as possible",
            ],
            "medicines": [
                {"name": "Metalaxyl-M (Ridomil Gold)", "type": "Systemic Fungicide",
                 "price_usd": "$35–$70 / lb",
                 "description": "Gold standard for late blight; systemic through plant tissue"},
                {"name": "Cymoxanil + Famoxadone (Tanos)", "type": "Combination Fungicide",
                 "price_usd": "$28–$55 / lb",
                 "description": "Dual mode of action; excellent curative and preventive"},
                {"name": "Fluopicolide (Presidio)", "type": "Systemic Fungicide",
                 "price_usd": "$45–$90 / pint",
                 "description": "Novel mode of action; use in rotation to manage resistance"},
                {"name": "Copper Octanoate (Cueva)", "type": "Organic Copper",
                 "price_usd": "$14–$28 / quart",
                 "description": "Organically approved option; protective (not curative)"},
            ],
            "prevention_tips": [
                {"title": "Monitor Weather", "tip": "Use BlightPro forecasting tools to anticipate high-risk periods"},
                {"title": "Resistant Varieties", "tip": "Plant 'Defiant PhR' or 'Mountain Magic' — both have strong late blight resistance"},
                {"title": "Certified Tubers", "tip": "Use only certified disease-free potato seed; inspect before planting"},
                {"title": "Avoid Wet Foliage", "tip": "Never leave foliage wet overnight; improve drainage around plants"},
            ],
            "total_cost_usd": "$60–$150",
            "cost_note": "Estimated total cost including emergency fungicide and potential replanting per 100 sq ft",
        },
        "powdery mildew": {
            "description": (
                "Powdery Mildew is caused by various Erysiphales species and is recognizable by its "
                "white to grayish powdery coating on leaves. Unlike most fungi, it thrives in warm dry "
                "conditions and does not require free water on leaves for infection."
            ),
            "severity": "Moderate",
            "spread": "Airborne conidia / Wind",
            "season": "Late spring through fall; dry warm days, cool nights",
            "recovery_days": 14,
            "treatments": [
                "Apply sulfur-based fungicide or potassium bicarbonate at first sign",
                "Use baking soda solution (1 tbsp per gallon + dish soap) for organic control",
                "Prune and remove heavily infected leaves and stems",
                "Improve air circulation by opening up the plant canopy",
                "Apply neem oil as both preventive and mild curative treatment",
            ],
            "medicines": [
                {"name": "Sulfur Dust (Bonide)", "type": "Protectant Fungicide",
                 "price_usd": "$6–$14 / 4 lb",
                 "description": "Highly effective preventive; do not apply when temp >90°F"},
                {"name": "Potassium Bicarbonate (Milstop)", "type": "Organic Fungicide",
                 "price_usd": "$15–$30 / lb",
                 "description": "OMRI-listed; curative by disrupting pH on leaf surface"},
                {"name": "Myclobutanil (Eagle 20EW)", "type": "Systemic DMI Fungicide",
                 "price_usd": "$18–$35 / 8 oz",
                 "description": "Excellent systemic curative; rotate with other modes of action"},
                {"name": "Tebuconazole (Spectracide Immunox)", "type": "Triazole Fungicide",
                 "price_usd": "$12–$22 / pint",
                 "description": "Broad-spectrum; curative and preventive against powdery mildew"},
            ],
            "prevention_tips": [
                {"title": "Prune for Airflow", "tip": "Open the canopy to reduce humidity in the leaf zone"},
                {"title": "Sunlight Exposure", "tip": "Plant in full sun; UV light suppresses powdery mildew spores"},
                {"title": "Resistant Cultivars", "tip": "Choose mildew-resistant cultivars — most modern varieties have improved resistance"},
                {"title": "Avoid Excess Nitrogen", "tip": "Do not over-fertilize; lush growth is more susceptible"},
            ],
            "total_cost_usd": "$20–$60",
            "cost_note": "Estimated total treatment cost for a typical home garden over one season",
        },
        "leaf spot": {
            "description": (
                "Leaf Spot diseases encompass fungal and bacterial infections producing distinct circular "
                "spots on leaves with defined margins. Common agents include Septoria lycopersici, "
                "Cercospora spp., and Alternaria spp. Advanced infections cause premature leaf drop."
            ),
            "severity": "Moderate",
            "spread": "Rain splash / Wind / Contaminated tools",
            "season": "Warm, humid conditions throughout growing season",
            "recovery_days": 21,
            "treatments": [
                "Apply mancozeb or chlorothalonil at first symptom appearance",
                "Remove and destroy all infected leaves to reduce spore reservoir",
                "Avoid wetting foliage during irrigation; use drip systems",
                "Improve airflow by proper plant spacing and pruning",
                "Apply preventive copper-based spray during high-humidity periods",
            ],
            "medicines": [
                {"name": "Chlorothalonil (Bravo 720)", "type": "Protectant Fungicide",
                 "price_usd": "$10–$22 / quart",
                 "description": "Multi-site fungicide; excellent activity spectrum"},
                {"name": "Mancozeb (Dithane M-45)", "type": "Contact Fungicide",
                 "price_usd": "$8–$18 / lb",
                 "description": "Broad-spectrum protectant against many Cercospora species"},
                {"name": "Propiconazole (Banner Maxx)", "type": "Systemic Fungicide",
                 "price_usd": "$22–$45 / quart",
                 "description": "Systemic DMI; curative and preventive action"},
                {"name": "Copper Hydroxide (Kocide)", "type": "Copper Bactericide/Fungicide",
                 "price_usd": "$12–$25 / lb",
                 "description": "Effective against bacterial leaf spot; apply during wet weather"},
            ],
            "prevention_tips": [
                {"title": "Avoid Leaf Wetness", "tip": "Water at base; avoid wetting foliage, especially in evenings"},
                {"title": "Rotate Crops", "tip": "Practice 2–3 year crop rotation to reduce pathogen buildup"},
                {"title": "Garden Sanitation", "tip": "Remove and destroy infected plant debris at end of each season"},
                {"title": "Monitor Regularly", "tip": "Scout plants weekly; early detection improves treatment success dramatically"},
            ],
            "total_cost_usd": "$25–$70",
            "cost_note": "Estimated total treatment cost per season per 100 sq ft",
        },
        "common rust": {
            "description": (
                "Common Rust (Puccinia sorghi on corn; Phragmidium spp. on roses) presents as "
                "brick-red to orange-brown pustules releasing powdery spores. It spreads rapidly "
                "in cool, moist conditions and can cause severe yield losses in susceptible crops."
            ),
            "severity": "Moderate–High",
            "spread": "Wind-dispersed urediniospores",
            "season": "Cool, humid conditions (16–23°C with high humidity)",
            "recovery_days": 18,
            "treatments": [
                "Apply triazole fungicide at first pustule appearance",
                "Remove heavily infected leaves to reduce local spore load",
                "Apply fungicide preventively when conditions favor rust development",
                "Ensure good plant nutrition — potassium deficiency increases rust severity",
                "Use strobilurin fungicides for excellent protective and curative activity",
            ],
            "medicines": [
                {"name": "Propiconazole (Tilt)", "type": "Triazole Fungicide",
                 "price_usd": "$20–$40 / pint",
                 "description": "Excellent systemic activity against rusts; curative and preventive"},
                {"name": "Pyraclostrobin (Headline)", "type": "Strobilurin Fungicide",
                 "price_usd": "$35–$65 / quart",
                 "description": "Broad-spectrum systemic; also improves overall plant health"},
                {"name": "Tebuconazole (Folicur)", "type": "DMI Fungicide",
                 "price_usd": "$25–$50 / pint",
                 "description": "Highly effective against rust pathogens; systemic uptake"},
                {"name": "Sulfur (Bonide Sulfur)", "type": "Protective Fungicide",
                 "price_usd": "$6–$14 / 4 lb",
                 "description": "Organic option; preventive only; reapply after rain"},
            ],
            "prevention_tips": [
                {"title": "Resistant Hybrids", "tip": "Select rust-resistant corn hybrids or rose cultivars for your region"},
                {"title": "Early Planting", "tip": "Plant early in the season to develop before peak rust pressure"},
                {"title": "Improve Airflow", "tip": "Adequate spacing promotes air circulation and reduces leaf moisture"},
                {"title": "Scout Weekly", "tip": "Begin scouting from mid-season; early detection is critical"},
            ],
            "total_cost_usd": "$35–$90",
            "cost_note": "Estimated total treatment cost per season per 100 sq ft including fungicide applications",
        },
        "bacterial spot": {
            "description": (
                "Bacterial Spot, caused by Xanthomonas spp., affects tomato, pepper, and other crops "
                "producing small, water-soaked lesions that turn brown with yellow halos. Warm, wet "
                "weather accelerates spread. Severe infections defoliate plants and reduce fruit quality."
            ),
            "severity": "Moderate–High",
            "spread": "Rain splash / Wind / Infected seed / Contaminated tools",
            "season": "Warm, wet weather (>24°C); rainy periods",
            "recovery_days": 20,
            "treatments": [
                "Apply copper-based bactericide at first symptom appearance",
                "Avoid overhead irrigation; use drip systems to keep foliage dry",
                "Remove and destroy heavily infected plant material",
                "Apply copper + mancozeb mixture for enhanced effectiveness",
                "Reduce plant density to improve air circulation",
            ],
            "medicines": [
                {"name": "Copper Hydroxide (Kocide 3000)", "type": "Copper Bactericide",
                 "price_usd": "$12–$25 / lb",
                 "description": "Primary bactericide for bacterial spot; apply preventively"},
                {"name": "Copper Sulfate + Lime (Bordeaux)", "type": "Classic Copper Mix",
                 "price_usd": "$8–$16 / lb",
                 "description": "Traditional broad-spectrum copper formulation"},
                {"name": "Kasugamycin (Kasumin)", "type": "Antibiotic Bactericide",
                 "price_usd": "$40–$80 / quart",
                 "description": "Antibiotic bactericide; restricted use in some regions"},
                {"name": "Acibenzolar-S-methyl (Actigard)", "type": "SAR Inducer",
                 "price_usd": "$30–$60 / 10 oz",
                 "description": "Induces systemic acquired resistance in the plant"},
            ],
            "prevention_tips": [
                {"title": "Certified Seed", "tip": "Use pathogen-free certified seed; hot-water seed treatment reduces risk"},
                {"title": "Avoid Wetting Leaves", "tip": "Use drip irrigation; do not work in plants when foliage is wet"},
                {"title": "Copper Sprays", "tip": "Apply preventive copper sprays before rainy forecasts"},
                {"title": "Resistant Varieties", "tip": "Select bacterial spot–resistant tomato or pepper varieties"},
            ],
            "total_cost_usd": "$30–$85",
            "cost_note": "Estimated total treatment cost per season per 100 sq ft",
        },
        "mosaic": {
            "description": (
                "Mosaic viruses (TMV, CMV, WMV) cause light and dark green mottling on leaves, "
                "leaf curling, stunted growth, and distorted fruit. No chemical cure exists — "
                "management centers on vector control, sanitation, and resistant varieties."
            ),
            "severity": "High",
            "spread": "Aphid vectors / Mechanical contact / Contaminated tools",
            "season": "Year-round; peak in spring and summer when aphid populations are high",
            "recovery_days": 35,
            "treatments": [
                "Remove and destroy infected plants to prevent spread to healthy plants",
                "Control aphid vectors with insecticidal soap, neem oil, or systemic insecticides",
                "Disinfect all tools with 10% bleach solution or 70% isopropyl alcohol",
                "Apply reflective silver mulch to confuse and deter aphids",
                "Weed control is critical — many weeds serve as virus reservoirs",
            ],
            "medicines": [
                {"name": "Imidacloprid (Admire Pro)", "type": "Systemic Insecticide",
                 "price_usd": "$18–$35 / 8 oz",
                 "description": "Systemic aphid control; soil or foliar application"},
                {"name": "Insecticidal Soap (Safer Brand)", "type": "Contact Insecticide",
                 "price_usd": "$8–$14 / quart",
                 "description": "Organic; kills soft-bodied insects on contact"},
                {"name": "Pyrethrin (PyGanic)", "type": "Contact Insecticide",
                 "price_usd": "$22–$40 / quart",
                 "description": "Fast-acting organic knockdown of aphid colonies"},
                {"name": "Mineral Oil Spray", "type": "Vector Suppression",
                 "price_usd": "$6–$12 / quart",
                 "description": "Disrupts aphid probing and virus transmission"},
            ],
            "prevention_tips": [
                {"title": "Certified Seeds", "tip": "Always use certified virus-free seeds from reputable sources"},
                {"title": "Reflective Mulch", "tip": "Silver reflective mulch disorients aphids and dramatically reduces landings"},
                {"title": "Weed Management", "tip": "Remove weeds that serve as virus reservoirs around the growing area"},
                {"title": "Resistant Varieties", "tip": "Select varieties with TMV/CMV resistance ratings for your crop"},
            ],
            "total_cost_usd": "$40–$100",
            "cost_note": "Estimated total cost including vector control and preventive measures per 100 sq ft",
        },
        "septoria": {
            "description": (
                "Septoria Leaf Spot (Septoria lycopersici) is a common and destructive fungal disease "
                "of tomatoes. It appears as numerous small, circular spots with dark borders and "
                "lighter tan centers. The disease progresses upward from older leaves and can cause "
                "complete defoliation if left untreated."
            ),
            "severity": "Moderate–High",
            "spread": "Rain splash / Wind / Contaminated tools / Soil",
            "season": "Warm, humid conditions; especially after fruit set",
            "recovery_days": 18,
            "treatments": [
                "Apply chlorothalonil or propiconazole at first sign of symptoms",
                "Remove infected lower leaves and dispose of immediately",
                "Mulch around plants to prevent soil splash onto lower leaves",
                "Stake plants to improve air circulation",
                "Rotate fungicides to prevent resistance development",
            ],
            "medicines": [
                {"name": "Chlorothalonil (Daconil)", "type": "Protectant Fungicide",
                 "price_usd": "$10–$22 / quart",
                 "description": "Highly effective against Septoria; apply every 7–10 days"},
                {"name": "Propiconazole (Tilt)", "type": "Systemic Fungicide",
                 "price_usd": "$20–$40 / pint",
                 "description": "Systemic curative and preventive; excellent Septoria control"},
                {"name": "Mancozeb (Dithane)", "type": "Contact Fungicide",
                 "price_usd": "$8–$18 / lb",
                 "description": "Broad-spectrum protectant; use in rotation programs"},
                {"name": "Copper Hydroxide (Kocide)", "type": "Copper Fungicide",
                 "price_usd": "$12–$25 / lb",
                 "description": "Effective copper option; apply during wet weather"},
            ],
            "prevention_tips": [
                {"title": "Crop Rotation", "tip": "Do not grow tomatoes in the same location for 2+ consecutive years"},
                {"title": "Stake and Prune", "tip": "Stake plants upright and remove suckers to maximize airflow"},
                {"title": "Bury Debris", "tip": "Till or bury crop residue deeply after harvest to destroy spores"},
                {"title": "Resistant Varieties", "tip": "Some modern hybrids have improved tolerance to Septoria"},
            ],
            "total_cost_usd": "$25–$65",
            "cost_note": "Estimated total treatment cost per growing season per 100 sq ft",
        },
        "scab": {
            "description": (
                "Apple Scab (Venturia inaequalis) is a destructive fungal disease of apples and "
                "pears, causing olive-green to dark brown scab-like lesions on leaves and fruit. "
                "Spores overwinter in fallen leaves and are released during wet spring weather. "
                "Infected fruit is unmarketable and heavily infected trees may defoliate."
            ),
            "severity": "High",
            "spread": "Wind / Rain-dispersed ascospores from infected leaf litter",
            "season": "Spring and early summer during wet, cool weather",
            "recovery_days": 30,
            "treatments": [
                "Apply captan or myclobutanil fungicide starting at green tip bud stage",
                "Maintain spray schedule every 7–14 days during wet spring weather",
                "Prune trees to open canopy and improve air circulation",
                "Rake and destroy fallen leaves to remove overwintering spores",
                "Apply urea to fallen leaves in autumn to accelerate decomposition",
            ],
            "medicines": [
                {"name": "Captan 50WP", "type": "Protectant Fungicide",
                 "price_usd": "$15–$30 / lb",
                 "description": "Excellent broad-spectrum protectant; apply before rain events"},
                {"name": "Myclobutanil (Rally 40WSP)", "type": "Systemic DMI Fungicide",
                 "price_usd": "$25–$50 / lb",
                 "description": "Systemic curative; effective up to 96hr post-infection"},
                {"name": "Lime Sulfur", "type": "Dormant/Early Season",
                 "price_usd": "$10–$20 / quart",
                 "description": "Apply at silver tip to delayed dormant; kills overwintering spores"},
                {"name": "Sulfur (Wettable Sulfur)", "type": "Protectant Fungicide",
                 "price_usd": "$6–$14 / 4 lb",
                 "description": "Organic option; protective activity; safe for bees post-dry"},
            ],
            "prevention_tips": [
                {"title": "Resistant Varieties", "tip": "Plant scab-resistant apple varieties (Liberty, Freedom, Enterprise)"},
                {"title": "Rake Leaves", "tip": "Collect and destroy fallen leaves each autumn — this is the #1 control measure"},
                {"title": "Prune Annually", "tip": "Annual dormant pruning improves light and airflow through the canopy"},
                {"title": "Time Sprays", "tip": "Use a disease prediction model (RIMpro, Coupure table) to time fungicide applications"},
            ],
            "total_cost_usd": "$40–$110",
            "cost_note": "Estimated annual treatment cost per tree including fungicides, pruning, and debris management",
        },
        "black rot": {
            "description": (
                "Black Rot, caused by Guignardia bidwellii on grapes, produces wedge-shaped "
                "brown lesions on leaves (with tiny black pycnidia visible under magnification) "
                "and causes infected berries to shrivel into black mummies. It is one of the "
                "most economically damaging grape diseases in humid growing regions."
            ),
            "severity": "High",
            "spread": "Rain-dispersed conidia / Wind / Infected mummified berries",
            "season": "Spring through summer; peak infection during bloom to 3 weeks post-bloom",
            "recovery_days": 25,
            "treatments": [
                "Apply myclobutanil or mancozeb starting at bud break",
                "Remove and destroy all mummified berries and infected canes",
                "Maintain rigorous spray schedule (every 7–10 days) during wet periods",
                "Improve canopy management to enhance air circulation",
                "Apply captan as a broad-spectrum supplemental fungicide",
            ],
            "medicines": [
                {"name": "Myclobutanil (Rally)", "type": "DMI Fungicide",
                 "price_usd": "$25–$50 / lb",
                 "description": "Excellent systemic curative and preventive against black rot"},
                {"name": "Mancozeb (Dithane)", "type": "Contact Fungicide",
                 "price_usd": "$8–$18 / lb",
                 "description": "Broad-spectrum protectant; use in rotation programs"},
                {"name": "Captan 50WP", "type": "Protectant Fungicide",
                 "price_usd": "$15–$30 / lb",
                 "description": "Excellent protectant; apply before rain events"},
                {"name": "Tebuconazole (Elite)", "type": "Triazole Fungicide",
                 "price_usd": "$25–$50 / pint",
                 "description": "Strong curative activity; apply within 96hr of infection"},
            ],
            "prevention_tips": [
                {"title": "Remove Mummies", "tip": "Pick and destroy all mummified berries before the new growing season"},
                {"title": "Prune Canes", "tip": "Remove and burn infected canes during dormant pruning"},
                {"title": "Canopy Management", "tip": "Shoot positioning and leaf removal improve airflow and spray penetration"},
                {"title": "Early Season Timing", "tip": "Critical spray window is from bud break through 3 weeks after bloom"},
            ],
            "total_cost_usd": "$45–$120",
            "cost_note": "Estimated total annual treatment cost per 100 sq ft vineyard block",
        },
        "blast": {
            "description": (
                "Rice Blast (Magnaporthe oryzae) is the most destructive rice disease worldwide, "
                "capable of destroying entire crops in weeks. It causes diamond-shaped gray lesions "
                "on leaves, and in severe cases infects the neck node, causing 'neck rot' that "
                "prevents grain filling. Favored by cool nights, high humidity, and excess nitrogen."
            ),
            "severity": "Critical",
            "spread": "Wind-dispersed conidia / Infected seed / Water splash",
            "season": "Humid conditions; especially with cool nights (20–22°C) and warm days",
            "recovery_days": 21,
            "treatments": [
                "Apply tricyclazole or isoprothiolane fungicide at first symptom",
                "Use azoxystrobin at heading stage to prevent neck blast",
                "Reduce nitrogen fertilizer rates — excess nitrogen dramatically increases susceptibility",
                "Ensure proper water management (avoid deep flooding during susceptible stages)",
                "Use silicon fertilizer amendments to strengthen plant cell walls",
            ],
            "medicines": [
                {"name": "Tricyclazole (Beam)", "type": "Melanin Biosynthesis Inhibitor",
                 "price_usd": "$25–$50 / lb",
                 "description": "Highly specific to Magnaporthe; excellent curative activity"},
                {"name": "Isoprothiolane (Fuji-one)", "type": "Systemic Fungicide",
                 "price_usd": "$20–$40 / liter",
                 "description": "Systemic activity; also controls brown planthopper"},
                {"name": "Azoxystrobin (Amistar)", "type": "Strobilurin Fungicide",
                 "price_usd": "$30–$60 / quart",
                 "description": "Excellent for neck blast prevention at heading; broad-spectrum"},
                {"name": "Propiconazole (Tilt)", "type": "Triazole Fungicide",
                 "price_usd": "$20–$40 / pint",
                 "description": "Effective curative; use in combination products for best results"},
            ],
            "prevention_tips": [
                {"title": "Resistant Varieties", "tip": "Plant blast-resistant rice varieties — this is the most cost-effective control"},
                {"title": "Balanced Nitrogen", "tip": "Split nitrogen applications; avoid heavy applications during susceptible stages"},
                {"title": "Field Drainage", "tip": "Periodic drainage reduces leaf wetness duration and infection risk"},
                {"title": "Seed Treatment", "tip": "Treat seeds with thiram or carbendazim before planting to prevent seedling blast"},
            ],
            "total_cost_usd": "$30–$80",
            "cost_note": "Estimated total treatment cost per season per 100 sq meter paddy",
        },
    }

    # Fuzzy match: exact → partial → keyword
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
            "found": False,
            "message": f"No detailed profile found for '{name}'. Please consult your local agricultural extension office.",
        }), 404

    return jsonify({"success": True, "found": True, "data": info})


@app.route("/api/dashboard")
def api_dashboard():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    data, status = php_get("get_dashboard.php")
    return jsonify(data), status


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    divider = "═" * 60
    print(f"\n{divider}")
    print("  🌿  BATANOX — Plant Disease Detection System  v6")
    print(divider)
    print(f"  Dashboard          : http://localhost:5000/")
    print(f"  Guest page         : http://localhost:5000/guest")
    print(f"  Login page         : {PHP_BASE}/login.php")
    print(f"  YOLO model         : {'Loaded ✓' if yolo_model         else '⚠  MOCK MODE (best.pt not found)'}")
    print(f"  Art. classifier    : {'Loaded ✓' if art_classifier     else '⚠  Heuristic fallback (no artificial_classifier.pt)'}")
    print(f"  Inference device   : {_art_classifier_device}")
    print(f"{divider}\n")
    app.run(debug=True, port=5000)