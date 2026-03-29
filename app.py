"""
BATANOX — AI-Powered Plant Disease Detection
Flask Backend  ·  app.py  (v5)

KEY CHANGE vs v3:
  - save_record_to_db() is NO LONGER called automatically after detection.
  - Records are saved ONLY when the user clicks the "Save Record" button
    in the frontend, which POSTs directly to PHP (same origin, no
    cross-port cookie issues).
  - Flask still exposes /api/records, /api/clear_records,
    /api/update_status, /api/reminders for the frontend to call.

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
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify
from ultralytics import YOLO
import os, shutil, requests

app = Flask(__name__)
app.secret_key = "batanox_secret_key_2024"

# ── Configuration ─────────────────────────────────────────────────────────────
MODEL_PATH    = "best.pt"
UPLOAD_FOLDER = "static/uploads"
RESULT_FOLDER = "static/results"
PHP_BASE      = "http://localhost/batanox"
PHP_AUTH_URL  = f"{PHP_BASE}/auth_check.php"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# ── Load YOLO model ───────────────────────────────────────────────────────────
model = None
if os.path.exists(MODEL_PATH):
    model = YOLO(MODEL_PATH)
    print(f"  [BATANOX] Model loaded: {MODEL_PATH}")
else:
    print(f"  [BATANOX] WARNING: '{MODEL_PATH}' not found — running in MOCK MODE")


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
    except Exception as e:
        print(f"  [BATANOX] auth_check failed: {e}")
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


# ── Classification thresholds ────────────────────────────────────────────────
#
#  DISEASE_CONF_THRESHOLD  – min confidence to call something a real disease.
#                            Below this the leaf is reported as Healthy Leaf.
#  NO_PLANT_CONF_THRESHOLD – min confidence to believe ANY plant is present.
#                            Below this → "No Plant Detected".
#
DISEASE_CONF_THRESHOLD  = 0.50   # 50 % — confident disease signal required
NO_PLANT_CONF_THRESHOLD = 0.30   # 30 % — anything lower is noise

# Substrings that mark a plain "species / plant-part" label, NOT a disease.
# KEY FIX: "Raspberry_leaf", "Tomato_leaf" etc. are just plant types.
# Your model fires these labels on healthy leaves → we treat them as healthy.
PLANT_TYPE_KEYWORDS = (
    "_leaf", "leaf_", " leaf",
    "plant", "seedling", "background",
    "raspberry", "tomato", "potato", "corn", "apple",
    "grape", "rice", "wheat", "pepper", "strawberry",
    "squash", "peach", "cherry", "orange", "soybean", "blueberry",
)

# Substrings that mark an explicitly-healthy label (PlantVillage convention).
HEALTHY_KEYWORDS = ("healthy",)

# Disease keywords — a class name containing any of these AND conf ≥ threshold
# is definitely a disease detection.
DISEASE_KEYWORDS = (
    "blight", "rust", "mold", "mildew", "scab", "rot", "spot",
    "mosaic", "wilt", "canker", "anthracnose", "blast", "smut",
    "lesion", "necrosis", "chlorosis", "disease", "infected",
    "bacterial", "fungal", "viral", "cercospora", "septoria",
    "alternaria", "powdery", "downy", "leaf_curl", "yellowing",
    "curl", "burn", "scorch",
)


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


def run_detection(upload_url_path: str) -> tuple[str, float, str, str]:
    """
    Run YOLO inference and return a reliable, labelled result.

    Returns
    -------
    (display_label, confidence_pct, result_url, status)

    status values
    -------------
    "no_plant"  – nothing plant-like detected above noise threshold
    "healthy"   – plant present, no confident disease class found
    "diseased"  – at least one disease class detected above threshold

    Root-cause of the Raspberry_leaf false-positive (and the fix)
    -------------------------------------------------------------
    The model was trained only on diseased samples.  When the input leaf is
    healthy, the model still outputs the nearest class it knows — often just
    the species label ("Raspberry_leaf") at high confidence.  The old code
    blindly used every detected class name as a disease name, so a healthy
    leaf was always reported as "Disease Detected".

    The fix: we inspect the class NAME through _classify_label().  A pure
    species / plant-type name is treated as healthy.  Only class names that
    contain known disease keywords AND exceed DISEASE_CONF_THRESHOLD are
    reported as diseases.
    """
    disk_path   = upload_url_path.lstrip("/")
    filename    = os.path.basename(disk_path)
    result_disk = os.path.join(RESULT_FOLDER, filename)
    result_url  = "/" + result_disk.replace("\\", "/")

    display_label = "No Plant Detected"
    confidence    = 0.0
    status        = "no_plant"

    if model:
        # Run with a low threshold so we see all candidates, then apply our
        # own smarter gates below.
        results = model(disk_path, conf=NO_PLANT_CONF_THRESHOLD)
        results[0].save(filename=result_disk)

        boxes = results[0].boxes
        if boxes is not None and len(boxes) > 0:
            detections = [
                (results[0].names[int(c)], float(cf))
                for c, cf in zip(boxes.cls.tolist(), boxes.conf.tolist())
                if float(cf) >= NO_PLANT_CONF_THRESHOLD
            ]
            print(f"  [BATANOX] detections above plant threshold: {detections}")

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
                    # ── Confirmed disease ─────────────────────────────────
                    seen, unique = set(), []
                    for n, _ in disease_hits:
                        if n not in seen:
                            seen.add(n); unique.append(n)
                    display_label = ", ".join(unique)
                    confidence    = round(max(c for _, c in disease_hits) * 100, 1)
                    status        = "diseased"

                elif unknown_hits and not healthy_hits:
                    # Unknown class name — use confidence to decide
                    max_unk = max(c for _, c in unknown_hits)
                    if max_unk >= DISEASE_CONF_THRESHOLD:
                        # High confidence but unrecognised → surface the raw name
                        display_label = unknown_hits[0][0]
                        confidence    = round(max_unk * 100, 1)
                        status        = "diseased"
                        print(f"  [BATANOX] Unrecognised high-conf class — treating as disease: {display_label}")
                    else:
                        display_label = "Healthy Leaf"
                        confidence    = round(max_unk * 100, 1)
                        status        = "healthy"

                else:
                    # Only healthy / species-type labels detected
                    all_hits  = healthy_hits or detections
                    max_conf  = max(c for _, c in all_hits)
                    display_label = "Healthy Leaf"
                    confidence    = round(max_conf * 100, 1)
                    status        = "healthy"
    else:
        shutil.copy2(disk_path, result_disk)

    print(f"  [BATANOX] Final → status={status!r}  label={display_label!r}  conf={confidence}%")
    return display_label, confidence, result_url, status


def php_get(endpoint: str) -> tuple[dict, int]:
    """GET a PHP endpoint with the current session cookie."""
    try:
        r = requests.get(f"{PHP_BASE}/{endpoint}", cookies=get_php_cookies(), timeout=3)
        return r.json(), r.status_code
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


def php_post(endpoint: str, body: dict) -> tuple[dict, int]:
    """POST JSON to a PHP endpoint with the current session cookie."""
    try:
        r = requests.post(f"{PHP_BASE}/{endpoint}", json=body, cookies=get_php_cookies(), timeout=3)
        return r.json(), r.status_code
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


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

    plant_name                                   = request.form.get("plant_name", "").strip()
    display_label, conf, result_url, det_status = run_detection(upload_url)

    # ── NO auto-save here. User must click Save Record. ──────────────────────

    return render_template(
        "index.html",
        user=user,
        uploaded_image=upload_url,
        result_image=result_url,
        disease_name=display_label,
        confidence=conf,
        plant_name=plant_name,
        detection_status=det_status,
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
    plant_name                                   = request.form.get("plant_name", "").strip()
    display_label, conf, result_url, det_status = run_detection(upload_url)
    return render_template(
        "guest.html",
        uploaded_image=upload_url,
        result_image=result_url,
        disease_name=display_label,
        confidence=conf,
        plant_name=plant_name,
        detection_status=det_status,
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


@app.route("/api/reminders")
def api_reminders():
    auth = check_auth()
    if not auth or not auth.get("authenticated"):
        return jsonify({"success": True, "reminders": []})
    data, status = php_get("get_reminders.php")
    return jsonify(data), status


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
    print("\n" + "═" * 56)
    print("  🌿  BATANOX — Plant Disease Detection System  v4")
    print("═" * 56)
    print(f"  Dashboard   : http://localhost:5000/")
    print(f"  Guest page  : http://localhost:5000/guest")
    print(f"  Login page  : {PHP_BASE}/login.php")
    print(f"  Admin panel : {PHP_BASE}/admin.php")
    print(f"  Model       : {'Loaded ✓' if model else '⚠  MOCK MODE (best.pt not found)'}")
    print("═" * 56 + "\n")
    app.run(debug=True, port=5000)