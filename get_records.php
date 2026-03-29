<?php
/**
 * BATANOX — get_records.php  (v5 — final fixed)
 *
 * FIX: Detects which columns exist before querying.
 *      This prevents "Unknown column" crashes on outdated DBs.
 */

session_start();
header('Content-Type: application/json');

if (!isset($_SESSION['user_id'])) {
    http_response_code(401);
    echo json_encode(['success' => false, 'error' => 'Not authenticated', 'records' => []]);
    exit;
}

require_once __DIR__ . '/db_config.php';

$user_id = (int) $_SESSION['user_id'];

try {
    // Detect available columns
    $existing = $pdo->query("SHOW COLUMNS FROM disease_records")->fetchAll(PDO::FETCH_COLUMN);
    $has = array_flip($existing);

    // Core columns that should always exist
    $select = ['id', 'user_id', 'disease_name'];

    // Optional columns — add only if they exist
    $optional = ['plant_name', 'confidence', 'image_path', 'result_path',
                 'treatment', 'status', 'estimated_days', 'next_reminder',
                 'reminder_note', 'scanned_at'];

    foreach ($optional as $col) {
        if (isset($has[$col])) $select[] = $col;
    }

    $select_sql = implode(', ', $select);

    $stmt = $pdo->prepare("
        SELECT $select_sql
        FROM   disease_records
        WHERE  user_id = ?
        ORDER  BY scanned_at DESC
    ");
    $stmt->execute([$user_id]);
    $records = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Cast types
    foreach ($records as &$r) {
        $r['id']     = (int) $r['id'];
        $r['user_id'] = (int) $r['user_id'];
        if (isset($r['confidence']))     $r['confidence']     = (float) $r['confidence'];
        if (isset($r['estimated_days'])) $r['estimated_days'] = $r['estimated_days'] !== null ? (int) $r['estimated_days'] : null;
        // Defaults for missing columns
        if (!isset($r['status']))        $r['status']         = 'detected';
        if (!isset($r['treatment']))     $r['treatment']      = '';
        if (!isset($r['plant_name']))    $r['plant_name']     = '';
        if (!isset($r['scanned_at']))    $r['scanned_at']     = '';
    }
    unset($r);

    echo json_encode(['success' => true, 'records' => $records]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => $e->getMessage(), 'records' => []]);
}