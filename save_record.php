<?php
/**
 * BATANOX — save_record.php  (v5 — final fixed)
 *
 * FIX: Handles missing columns gracefully by detecting them first.
 *      Added verbose error logging.
 *      Proper CORS headers for Flask on :5000.
 */

session_start();
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: http://localhost:5000');
header('Access-Control-Allow-Credentials: true');
header('Access-Control-Allow-Headers: Content-Type');
header('Access-Control-Allow-Methods: POST, OPTIONS');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// ── Auth guard ───────────────────────────────────────────────────────────────
if (!isset($_SESSION['user_id'])) {
    http_response_code(401);
    echo json_encode(['success' => false, 'error' => 'Not authenticated. Please log in first.']);
    exit;
}

// ── Read JSON body ────────────────────────────────────────────────────────────
$raw  = file_get_contents('php://input');
$body = json_decode($raw, true);

if (!is_array($body)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Invalid JSON body.']);
    exit;
}

require_once __DIR__ . '/db_config.php';

// ── Sanitise inputs ───────────────────────────────────────────────────────────
$user_id      = (int)    $_SESSION['user_id'];
$plant_name   = trim((string) ($body['plant_name']   ?? ''));
$disease_name = trim((string) ($body['disease_name'] ?? ''));
$confidence   = (float)  ($body['confidence']  ?? 0.0);
$image_path   = trim((string) ($body['image_path']   ?? ''));
$result_path  = trim((string) ($body['result_path']  ?? ''));

if ($disease_name === '') {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'disease_name is required.']);
    exit;
}

// ── Treatment knowledge base ──────────────────────────────────────────────────
$kb = [
    'early blight'    => ['days' => 21, 'text' => 'Apply copper-based fungicide every 7–10 days. Remove infected leaves immediately. Avoid overhead watering and improve air circulation.'],
    'late blight'     => ['days' => 28, 'text' => 'Use metalaxyl-based fungicide immediately. Remove and destroy infected plants. Avoid overhead irrigation.'],
    'leaf mold'       => ['days' => 14, 'text' => 'Apply fungicide and reduce humidity. Ensure good ventilation. Remove infected foliage promptly.'],
    'common rust'     => ['days' => 18, 'text' => 'Apply triazole fungicide. Use resistant varieties. Plant early to avoid peak rust pressure.'],
    'powdery mildew'  => ['days' => 14, 'text' => 'Apply sulfur or potassium bicarbonate spray. Improve canopy airflow. Remove heavily infected parts.'],
    'blast'           => ['days' => 21, 'text' => 'Apply tricyclazole or isoprothiolane fungicide. Use disease-resistant varieties. Periodic field drainage helps.'],
    'scab'            => ['days' => 30, 'text' => 'Apply captan or myclobutanil. Prune trees for good air circulation. Rake and destroy fallen leaves.'],
    'black rot'       => ['days' => 25, 'text' => 'Remove infected fruit and canes. Apply copper fungicide. Improve canopy management.'],
    'bacterial spot'  => ['days' => 20, 'text' => 'Apply copper-based bactericide. Avoid overhead irrigation. Remove infected debris.'],
    'septoria'        => ['days' => 18, 'text' => 'Apply chlorothalonil or propiconazole. Use crop rotation. Bury infected residue after harvest.'],
    'mosaic'          => ['days' => 35, 'text' => 'Control aphid vectors. Remove infected plants immediately. Use certified virus-free seeds.'],
    'leaf spot'       => ['days' => 21, 'text' => 'Apply mancozeb or chlorothalonil fungicide. Remove and destroy infected leaves. Improve air circulation around plants.'],
    'healthy'         => ['days' => 0,  'text' => 'No treatment needed. Your plant appears healthy! Continue regular monitoring.'],
];
$default_plan = ['days' => 21, 'text' => 'Consult your local agricultural extension office. Remove infected leaves, improve air circulation, avoid overwatering, and apply an appropriate fungicide or bactericide.'];

$plan     = $default_plan;
$dn_lower = strtolower($disease_name);
foreach ($kb as $key => $p) {
    if (strpos($dn_lower, $key) !== false) {
        $plan = $p;
        break;
    }
}

$treatment     = $plan['text'];
$est_days      = ($plan['days'] > 0) ? (int) $plan['days'] : null;
$next_reminder = ($est_days !== null) ? date('Y-m-d H:i:s', strtotime('+3 days')) : null;
$reminder_note = ($est_days !== null) ? "Time to apply treatment — check your plant's progress." : null;

// ── Detect which columns actually exist in disease_records ────────────────────
try {
    $col_check = $pdo->query("SHOW COLUMNS FROM disease_records")->fetchAll(PDO::FETCH_COLUMN);
    $has = array_flip($col_check);

    // Build a flexible INSERT depending on what columns exist
    $cols   = ['user_id', 'disease_name'];
    $vals   = [$user_id, $disease_name];
    $places = ['?', '?'];

    if (isset($has['plant_name']))   { $cols[] = 'plant_name';   $vals[] = $plant_name;   $places[] = '?'; }
    if (isset($has['confidence']))   { $cols[] = 'confidence';   $vals[] = $confidence;   $places[] = '?'; }
    if (isset($has['image_path']))   { $cols[] = 'image_path';   $vals[] = $image_path;   $places[] = '?'; }
    if (isset($has['result_path']))  { $cols[] = 'result_path';  $vals[] = $result_path;  $places[] = '?'; }
    if (isset($has['treatment']))    { $cols[] = 'treatment';    $vals[] = $treatment;    $places[] = '?'; }
    if (isset($has['status']))       { $cols[] = 'status';       $vals[] = 'detected';    $places[] = '?'; }
    if (isset($has['estimated_days'])){ $cols[] = 'estimated_days'; $vals[] = $est_days;  $places[] = '?'; }
    if (isset($has['next_reminder'])){ $cols[] = 'next_reminder'; $vals[] = $next_reminder; $places[] = '?'; }
    if (isset($has['reminder_note'])){ $cols[] = 'reminder_note'; $vals[] = $reminder_note; $places[] = '?'; }

    $sql  = 'INSERT INTO disease_records (' . implode(', ', $cols) . ') VALUES (' . implode(', ', $places) . ')';
    $stmt = $pdo->prepare($sql);
    $stmt->execute($vals);

    $new_id = (int) $pdo->lastInsertId();

    echo json_encode([
        'success'   => true,
        'record_id' => $new_id,
        'user_id'   => $user_id,
        'disease'   => $disease_name,
        'treatment' => $treatment,
        'est_days'  => $est_days,
    ]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error'   => 'DB error: ' . $e->getMessage(),
    ]);
}