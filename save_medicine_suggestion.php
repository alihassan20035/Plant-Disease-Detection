<?php
/**
 * BATANOX — save_medicine_suggestion.php
 * Admin posts a medicine suggestion for a patient's disease record.
 * The suggestion is saved to `medicine_suggestions` table and becomes
 * visible to the patient in their treatment log as a notification.
 *
 * Called by: POST /api/medicine_suggestions
 * Body JSON: { record_id, medicine_name, notes? }
 * Access: admin only (enforced in app.py and here)
 */

session_start();
require_once 'db_config.php';

header('Content-Type: application/json; charset=UTF-8');

// ── Admin-only guard ───────────────────────────────────────────────────────
$role = $_SESSION['role'] ?? $_SESSION['user_role'] ?? '';
if (!isset($_SESSION['user_id']) || $role !== 'admin') {
    echo json_encode(['success' => false, 'error' => 'Admin access required.']);
    exit;
}

$admin_id   = (int)$_SESSION['user_id'];
$admin_name = $_SESSION['user_name'] ?? $_SESSION['name'] ?? 'Admin';

// ── Parse body ─────────────────────────────────────────────────────────────
$raw  = file_get_contents('php://input');
$body = json_decode($raw, true);

if (!$body) {
    echo json_encode(['success' => false, 'error' => 'Invalid JSON body.']);
    exit;
}

$record_id    = (int)($body['record_id']    ?? 0);
$medicine_name = trim((string)($body['medicine_name'] ?? ''));
$notes         = isset($body['notes']) ? trim((string)$body['notes']) : '';

if ($record_id <= 0) {
    echo json_encode(['success' => false, 'error' => 'Invalid record_id.']);
    exit;
}
if ($medicine_name === '') {
    echo json_encode(['success' => false, 'error' => 'medicine_name is required.']);
    exit;
}

try {
    // ── Ensure table exists ────────────────────────────────────────────────
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS medicine_suggestions (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            record_id    INT NOT NULL,
            admin_id     INT NOT NULL,
            admin_name   VARCHAR(255) NOT NULL DEFAULT '',
            medicine_name VARCHAR(500) NOT NULL,
            notes        TEXT,
            created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_record (record_id),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ");

    // ── Verify the record exists ───────────────────────────────────────────
    $chk = $pdo->prepare("SELECT id FROM disease_records WHERE id = ? LIMIT 1");
    $chk->execute([$record_id]);
    if (!$chk->fetch()) {
        echo json_encode(['success' => false, 'error' => 'Record not found.']);
        exit;
    }

    // ── Insert suggestion ──────────────────────────────────────────────────
    $ins = $pdo->prepare("
        INSERT INTO medicine_suggestions (record_id, admin_id, admin_name, medicine_name, notes, created_at)
        VALUES (?, ?, ?, ?, ?, NOW())
    ");
    $ins->execute([
        $record_id,
        $admin_id,
        $admin_name,
        $medicine_name,
        $notes !== '' ? $notes : null,
    ]);

    $new_id = (int)$pdo->lastInsertId();

    echo json_encode([
        'success'       => true,
        'suggestion_id' => $new_id,
        'message'       => 'Medicine suggestion saved and notification sent to patient.',
    ]);

} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => 'Database error: ' . $e->getMessage()]);
}