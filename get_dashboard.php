<?php
/**
 * BATANOX — get_dashboard.php
 * Returns real-time dashboard stats for the logged-in user.
 * Called by Flask proxy: GET /api/dashboard
 */

session_start();
header('Content-Type: application/json');

if (!isset($_SESSION['user_id'])) {
    http_response_code(401);
    echo json_encode(['success' => false, 'error' => 'Not authenticated']);
    exit;
}

require_once __DIR__ . '/db_config.php';

$user_id = (int) $_SESSION['user_id'];

try {
    // Detect columns
    $cols = $pdo->query("SHOW COLUMNS FROM disease_records")->fetchAll(PDO::FETCH_COLUMN);
    $has  = array_flip($cols);

    // --- Total detections for this user ---
    $total = (int) $pdo->prepare("SELECT COUNT(*) FROM disease_records WHERE user_id = ?")
                       ->execute([$user_id]) ? 0 : 0;
    $stmt = $pdo->prepare("SELECT COUNT(*) FROM disease_records WHERE user_id = ?");
    $stmt->execute([$user_id]);
    $total = (int) $stmt->fetchColumn();

    // --- Active (in_progress) ---
    $active = 0;
    if (isset($has['status'])) {
        $stmt = $pdo->prepare("SELECT COUNT(*) FROM disease_records WHERE user_id = ? AND status = 'in_progress'");
        $stmt->execute([$user_id]);
        $active = (int) $stmt->fetchColumn();
    }

    // --- Recovered ---
    $recovered = 0;
    if (isset($has['status'])) {
        $stmt = $pdo->prepare("SELECT COUNT(*) FROM disease_records WHERE user_id = ? AND status = 'recovered'");
        $stmt->execute([$user_id]);
        $recovered = (int) $stmt->fetchColumn();
    }

    // --- Detected (default/unhandled) ---
    $detected = 0;
    if (isset($has['status'])) {
        $stmt = $pdo->prepare("SELECT COUNT(*) FROM disease_records WHERE user_id = ? AND status = 'detected'");
        $stmt->execute([$user_id]);
        $detected = (int) $stmt->fetchColumn();
    } else {
        $detected = $total;
    }

    // --- Recent 5 records ---
    $select_cols = ['id', 'disease_name', 'scanned_at'];
    if (isset($has['plant_name']))   $select_cols[] = 'plant_name';
    if (isset($has['confidence']))   $select_cols[] = 'confidence';
    if (isset($has['status']))       $select_cols[] = 'status';
    if (isset($has['estimated_days'])) $select_cols[] = 'estimated_days';

    $stmt = $pdo->prepare("SELECT " . implode(', ', $select_cols) . "
        FROM disease_records WHERE user_id = ?
        ORDER BY scanned_at DESC LIMIT 5");
    $stmt->execute([$user_id]);
    $recent = $stmt->fetchAll(PDO::FETCH_ASSOC);

    foreach ($recent as &$r) {
        $r['id'] = (int) $r['id'];
        if (isset($r['confidence']))     $r['confidence']     = (float) $r['confidence'];
        if (isset($r['estimated_days'])) $r['estimated_days'] = (int) $r['estimated_days'];
        if (!isset($r['status']))        $r['status']         = 'detected';
        if (!isset($r['plant_name']))    $r['plant_name']     = '';
    }
    unset($r);

    // --- Most common disease for this user ---
    $top_disease = null;
    $stmt = $pdo->prepare("SELECT disease_name, COUNT(*) AS cnt FROM disease_records
        WHERE user_id = ? GROUP BY disease_name ORDER BY cnt DESC LIMIT 1");
    $stmt->execute([$user_id]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($row) $top_disease = $row['disease_name'];

    echo json_encode([
        'success'    => true,
        'total'      => $total,
        'active'     => $active,
        'recovered'  => $recovered,
        'detected'   => $detected,
        'recent'     => $recent,
        'top_disease'=> $top_disease,
    ]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}