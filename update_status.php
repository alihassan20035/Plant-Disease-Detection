<?php
/**
 * BATANOX — update_status.php  (v5 — final fixed)
 * Accepts JSON POST: { record_id: int, status: "detected"|"in_progress"|"recovered" }
 * Only updates records that belong to the logged-in user.
 * FIX: Checks if 'status' column exists before attempting update.
 */

session_start();
header('Content-Type: application/json');

if (!isset($_SESSION['user_id'])) {
    http_response_code(401);
    echo json_encode(['success' => false, 'error' => 'Not authenticated']);
    exit;
}

require_once __DIR__ . '/db_config.php';

// Check if status column exists
$cols = $pdo->query("SHOW COLUMNS FROM disease_records")->fetchAll(PDO::FETCH_COLUMN);
if (!in_array('status', $cols)) {
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error'   => 'Database needs updating. Please run batanox_fix.sql in phpMyAdmin.'
    ]);
    exit;
}

$body      = json_decode(file_get_contents('php://input'), true);
$record_id = (int) ($body['record_id'] ?? 0);
$status    = trim((string) ($body['status'] ?? ''));
$allowed   = ['detected', 'in_progress', 'recovered'];

if (!$record_id || !in_array($status, $allowed, true)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Invalid parameters']);
    exit;
}

$user_id = (int) $_SESSION['user_id'];

try {
    $stmt = $pdo->prepare(
        "UPDATE disease_records SET status = ? WHERE id = ? AND user_id = ?"
    );
    $stmt->execute([$status, $record_id, $user_id]);

    if ($stmt->rowCount() === 0) {
        http_response_code(404);
        echo json_encode(['success' => false, 'error' => 'Record not found or access denied']);
        exit;
    }

    echo json_encode(['success' => true, 'status' => $status]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}