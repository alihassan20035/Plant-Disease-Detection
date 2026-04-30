<?php
/**
 * BATANOX — get_medicine_suggestions.php
 * Returns all admin medicine suggestions for a given disease_record.
 * Called by: GET /api/medicine_suggestions?record_id=X
 *
 * Access: any authenticated user (user sees suggestions for their own record;
 *         admin sees suggestions for any record).
 */

session_start();
require_once 'db_config.php';

header('Content-Type: application/json; charset=UTF-8');

// ── Auth check ─────────────────────────────────────────────────────────────
if (!isset($_SESSION['user_id'])) {
    echo json_encode(['success' => false, 'error' => 'Not authenticated.']);
    exit;
}

$user_id   = (int)$_SESSION['user_id'];
$user_role = $_SESSION['role'] ?? $_SESSION['user_role'] ?? 'user';
$record_id = (int)($_GET['record_id'] ?? 0);

if ($record_id <= 0) {
    echo json_encode(['success' => false, 'error' => 'Invalid record_id.']);
    exit;
}

try {
    // ── Verify the record exists and user has access ────────────────────────
    if ($user_role === 'admin') {
        $stmt = $pdo->prepare("SELECT id FROM disease_records WHERE id = ? LIMIT 1");
        $stmt->execute([$record_id]);
    } else {
        // Regular user: can only see suggestions for their own records
        $stmt = $pdo->prepare("SELECT id FROM disease_records WHERE id = ? AND user_id = ? LIMIT 1");
        $stmt->execute([$record_id, $user_id]);
    }

    if (!$stmt->fetch()) {
        echo json_encode(['success' => false, 'error' => 'Record not found or access denied.']);
        exit;
    }

    // ── Create table if it doesn't exist ───────────────────────────────────
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

    // ── Fetch suggestions ──────────────────────────────────────────────────
    $q = $pdo->prepare("
        SELECT ms.id, ms.admin_name, ms.medicine_name, ms.notes, ms.created_at
        FROM medicine_suggestions ms
        WHERE ms.record_id = ?
        ORDER BY ms.created_at DESC
        LIMIT 50
    ");
    $q->execute([$record_id]);
    $rows = $q->fetchAll(PDO::FETCH_ASSOC);

    // Ensure types are correct
    foreach ($rows as &$r) {
        $r['id']    = (int)$r['id'];
        $r['notes'] = $r['notes'] ?? '';
    }
    unset($r);

    echo json_encode([
        'success'     => true,
        'record_id'   => $record_id,
        'suggestions' => $rows,
    ]);

} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => 'Database error: ' . $e->getMessage()]);
}