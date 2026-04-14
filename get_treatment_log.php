<?php
/**
 * BATANOX — get_treatment_log.php  (v2)
 *
 * - Regular users: can only access their own records
 * - Admin users:   can access ANY record (no user_id restriction)
 *
 * GET ?record_id=<int>
 */

session_start();
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: http://localhost:5000');
header('Access-Control-Allow-Credentials: true');
header('Access-Control-Allow-Headers: Content-Type');
header('Access-Control-Allow-Methods: GET, OPTIONS');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// Auth guard
if (!isset($_SESSION['user_id'])) {
    http_response_code(401);
    echo json_encode(['success' => false, 'error' => 'Not authenticated. Please log in first.']);
    exit;
}

$session_user_id = (int) $_SESSION['user_id'];
$session_role    = $_SESSION['role'] ?? $_SESSION['user_role'] ?? 'user';
$is_admin        = ($session_role === 'admin');
$record_id       = (int) ($_GET['record_id'] ?? 0);

if ($record_id <= 0) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'record_id is required.']);
    exit;
}

require_once __DIR__ . '/db_config.php';

try {
    // Detect optional columns
    $ecols    = $pdo->query("SHOW COLUMNS FROM disease_records")->fetchAll(PDO::FETCH_COLUMN);
    $has      = array_flip($ecols);
    $has_agri = isset($has['agri_contacted']);
    $has_dd   = isset($has['disease_detected']);

    $extra_cols = '';
    if ($has_agri) $extra_cols .= ', dr.agri_contacted';
    if ($has_dd)   $extra_cols .= ', dr.disease_detected';

    // Admin can view any record; regular users only their own
    if ($is_admin) {
        $sql = "
            SELECT dr.id, dr.user_id, dr.plant_name, dr.disease_name, dr.status,
                   dr.treatment, dr.estimated_days, dr.scanned_at,
                   u.name AS owner_name, u.email AS owner_email
                   $extra_cols
            FROM   disease_records dr
            JOIN   users u ON u.id = dr.user_id
            WHERE  dr.id = ?
            LIMIT  1
        ";
        $rStmt = $pdo->prepare($sql);
        $rStmt->execute([$record_id]);
    } else {
        $extra_cols_plain = '';
        if ($has_agri) $extra_cols_plain .= ', agri_contacted';
        if ($has_dd)   $extra_cols_plain .= ', disease_detected';
        $sql = "
            SELECT id, user_id, plant_name, disease_name, status,
                   treatment, estimated_days, scanned_at
                   $extra_cols_plain
            FROM   disease_records
            WHERE  id = ? AND user_id = ?
            LIMIT  1
        ";
        $rStmt = $pdo->prepare($sql);
        $rStmt->execute([$record_id, $session_user_id]);
    }

    $record = $rStmt->fetch(PDO::FETCH_ASSOC);

    if (!$record) {
        http_response_code(404);
        echo json_encode(['success' => false, 'error' => 'Record not found or access denied.']);
        exit;
    }

    // Defaults for optional columns
    if (!$has_agri) $record['agri_contacted']  = 0;
    if (!$has_dd)   $record['disease_detected'] = (stripos($record['disease_name'] ?? '', 'healthy') === false) ? 1 : 0;
    if (!isset($record['owner_name']))  $record['owner_name']  = null;
    if (!isset($record['owner_email'])) $record['owner_email'] = null;

    // Cast types
    $record['id']               = (int) $record['id'];
    $record['user_id']          = (int) $record['user_id'];
    $record['agri_contacted']   = (int) $record['agri_contacted'];
    $record['disease_detected'] = (int) $record['disease_detected'];
    $record['estimated_days']   = isset($record['estimated_days']) ? (int) $record['estimated_days'] : null;
    $record['is_admin_view']    = $is_admin;

    // Fetch weekly tracking rows
    $tblCheck = $pdo->query("SHOW TABLES LIKE 'treatment_logs'")->fetchAll();
    $weeks    = [];

    if (!empty($tblCheck)) {
        $wStmt = $pdo->prepare("
            SELECT id, week_number, infected_leaf, improvement,
                   severity_level, recovery_pct, notes, logged_at
            FROM   treatment_logs
            WHERE  record_id = ?
            ORDER  BY week_number ASC
        ");
        $wStmt->execute([$record_id]);
        $rows = $wStmt->fetchAll(PDO::FETCH_ASSOC);

        foreach ($rows as $row) {
            $row['id']            = (int) $row['id'];
            $row['week_number']   = (int) $row['week_number'];
            $row['infected_leaf'] = (int) $row['infected_leaf'];
            $row['improvement']   = isset($row['improvement'])  ? (int) $row['improvement']  : null;
            $row['recovery_pct']  = isset($row['recovery_pct']) ? (int) $row['recovery_pct'] : null;
            $weeks[]              = $row;
        }
    }

    echo json_encode([
        'success' => true,
        'record'  => $record,
        'weeks'   => $weeks,
    ]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'DB error: ' . $e->getMessage()]);
}