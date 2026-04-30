<?php
/**
 * BATANOX — get_all_medicine_suggestions.php
 *
 * Returns ALL admin medicine suggestions for the currently logged-in user,
 * across ALL their disease records. Also includes disease name and plant name
 * so the user knows which plant/disease the suggestion is for.
 *
 * Called by: GET /api/all_medicine_suggestions
 * Access: any authenticated user (returns only their own data)
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

try {
    // ── Ensure the medicine_suggestions table exists ───────────────────────
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS medicine_suggestions (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            record_id     INT NOT NULL,
            admin_id      INT NOT NULL,
            admin_name    VARCHAR(255) NOT NULL DEFAULT '',
            medicine_name VARCHAR(500) NOT NULL,
            notes         TEXT,
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_record  (record_id),
            INDEX idx_admin   (admin_id),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ");

    // ── Build query ────────────────────────────────────────────────────────
    // Check which columns exist in disease_records
    $cols = $pdo->query("SHOW COLUMNS FROM disease_records")->fetchAll(PDO::FETCH_COLUMN);
    $has  = array_flip($cols);

    $plant_col = isset($has['plant_name']) ? 'dr.plant_name' : "'' AS plant_name";

    if ($user_role === 'admin') {
        // Admin can see all suggestions
        $stmt = $pdo->prepare("
            SELECT
                ms.id,
                ms.record_id,
                ms.admin_id,
                ms.admin_name,
                ms.medicine_name,
                ms.notes,
                ms.created_at,
                dr.disease_name,
                $plant_col,
                u.name  AS user_name,
                u.email AS user_email
            FROM medicine_suggestions ms
            JOIN disease_records dr ON ms.record_id = dr.id
            JOIN users u ON dr.user_id = u.id
            ORDER BY ms.created_at DESC
            LIMIT 200
        ");
        $stmt->execute();
    } else {
        // Regular user: only suggestions for their own records
        $stmt = $pdo->prepare("
            SELECT
                ms.id,
                ms.record_id,
                ms.admin_id,
                ms.admin_name,
                ms.medicine_name,
                ms.notes,
                ms.created_at,
                dr.disease_name,
                $plant_col
            FROM medicine_suggestions ms
            JOIN disease_records dr ON ms.record_id = dr.id
            WHERE dr.user_id = ?
            ORDER BY ms.created_at DESC
            LIMIT 100
        ");
        $stmt->execute([$user_id]);
    }

    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Clean up types
    foreach ($rows as &$r) {
        $r['id']        = (int)$r['id'];
        $r['record_id'] = (int)$r['record_id'];
        $r['admin_id']  = (int)$r['admin_id'];
        $r['notes']     = $r['notes'] ?? '';
        $r['plant_name']= $r['plant_name'] ?? '';
    }
    unset($r);

    echo json_encode([
        'success'     => true,
        'count'       => count($rows),
        'suggestions' => $rows,
    ]);

} catch (PDOException $e) {
    echo json_encode([
        'success' => false,
        'error'   => 'Database error: ' . $e->getMessage(),
    ]);
}