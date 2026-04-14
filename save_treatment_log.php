<?php
/**
 * BATANOX — save_treatment_log.php  (v2)
 *
 * - Regular users: can only save to their own records
 * - Admin users:   can save to ANY record
 *                  uses the record's ACTUAL owner user_id for treatment_logs rows
 *
 * POST JSON body:
 * {
 *   "record_id":        int,
 *   "agri_contacted":   0|1,
 *   "disease_detected": 0|1,
 *   "week": { week_number, infected_leaf, improvement,
 *             severity_level, recovery_pct, notes }  // optional
 * }
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

// Auth guard
if (!isset($_SESSION['user_id'])) {
    http_response_code(401);
    echo json_encode(['success' => false, 'error' => 'Not authenticated.']);
    exit;
}

$session_user_id = (int) $_SESSION['user_id'];
$session_role    = $_SESSION['role'] ?? $_SESSION['user_role'] ?? 'user';
$is_admin        = ($session_role === 'admin');

$body = json_decode(file_get_contents('php://input'), true);
if (!is_array($body)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Invalid JSON body.']);
    exit;
}

$record_id        = (int) ($body['record_id']        ?? 0);
$agri_contacted   = isset($body['agri_contacted'])   ? (int)(bool)$body['agri_contacted']   : null;
$disease_detected = isset($body['disease_detected'])  ? (int)(bool)$body['disease_detected'] : null;

if ($record_id <= 0) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'record_id is required.']);
    exit;
}

require_once __DIR__ . '/db_config.php';

$week_id      = null;
$meta_updated = false;

try {
    // Verify record exists and get its real owner
    if ($is_admin) {
        // Admin: fetch record without user_id restriction, get real owner
        $own = $pdo->prepare("SELECT id, user_id FROM disease_records WHERE id = ? LIMIT 1");
        $own->execute([$record_id]);
    } else {
        // Regular user: must own the record
        $own = $pdo->prepare("SELECT id, user_id FROM disease_records WHERE id = ? AND user_id = ? LIMIT 1");
        $own->execute([$record_id, $session_user_id]);
    }

    $ownerRow = $own->fetch(PDO::FETCH_ASSOC);
    if (!$ownerRow) {
        http_response_code(403);
        echo json_encode(['success' => false, 'error' => 'Record not found or access denied.']);
        exit;
    }

    // Use the RECORD'S actual owner for treatment_logs (important for admin edits)
    $record_owner_id = (int) $ownerRow['user_id'];

    // Update parent record meta (agri_contacted, disease_detected)
    $ecols = $pdo->query("SHOW COLUMNS FROM disease_records")->fetchAll(PDO::FETCH_COLUMN);
    $has   = array_flip($ecols);

    $set_parts = [];
    $set_vals  = [];

    if ($agri_contacted !== null && isset($has['agri_contacted'])) {
        $set_parts[] = 'agri_contacted = ?';
        $set_vals[]  = $agri_contacted;
    }
    if ($disease_detected !== null && isset($has['disease_detected'])) {
        $set_parts[] = 'disease_detected = ?';
        $set_vals[]  = $disease_detected;
    }

    if (!empty($set_parts)) {
        $set_vals[] = $record_id;
        $pdo->prepare("UPDATE disease_records SET " . implode(', ', $set_parts) . " WHERE id = ?")
            ->execute($set_vals);
        $meta_updated = true;
    }

    // Upsert weekly tracking row
    if (isset($body['week']) && is_array($body['week'])) {
        $w = $body['week'];

        $week_num    = max(1, (int) ($w['week_number']  ?? 1));
        $inf_leaf    = isset($w['infected_leaf']) ? (int)(bool)$w['infected_leaf'] : 1;

        // Handle improvement: null/missing = N/A, 0 = No, 1 = Yes
        if (!isset($w['improvement']) || $w['improvement'] === null || $w['improvement'] === 'na') {
            $improvement = null;
        } else {
            $improvement = (int)(bool)$w['improvement'];
        }

        $severity = in_array($w['severity_level'] ?? '', ['None','Low','Moderate','High','Critical'])
                    ? $w['severity_level'] : 'Moderate';
        $rec_pct  = isset($w['recovery_pct']) ? max(0, min(100, (int)$w['recovery_pct'])) : null;
        $notes    = isset($w['notes']) ? trim((string)$w['notes']) : null;
        if ($notes === '') $notes = null;

        // Check table exists
        $tblCheck = $pdo->query("SHOW TABLES LIKE 'treatment_logs'")->fetchAll();
        if (empty($tblCheck)) {
            http_response_code(500);
            echo json_encode(['success' => false, 'error' => 'treatment_logs table missing. Please run batanox_treatment_update.sql first.']);
            exit;
        }

        // UPSERT — store with record's actual owner_id (not admin's id)
        $upsert = $pdo->prepare("
            INSERT INTO treatment_logs
                (record_id, user_id, week_number, infected_leaf, improvement,
                 severity_level, recovery_pct, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                infected_leaf  = VALUES(infected_leaf),
                improvement    = VALUES(improvement),
                severity_level = VALUES(severity_level),
                recovery_pct   = VALUES(recovery_pct),
                notes          = VALUES(notes),
                updated_at     = NOW()
        ");
        $upsert->execute([
            $record_id, $record_owner_id, $week_num,
            $inf_leaf, $improvement, $severity, $rec_pct, $notes,
        ]);

        $week_id = (int) $pdo->lastInsertId();
        if ($week_id === 0) {
            // Was an UPDATE — fetch the actual ID
            $idRow = $pdo->prepare("SELECT id FROM treatment_logs WHERE record_id = ? AND week_number = ?");
            $idRow->execute([$record_id, $week_num]);
            $week_id = (int) ($idRow->fetchColumn() ?: 0);
        }
    }

    echo json_encode([
        'success'      => true,
        'week_id'      => $week_id ?: null,
        'meta_updated' => $meta_updated,
    ]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'DB error: ' . $e->getMessage()]);
}