<?php
/**
 * BATANOX — get_admin_stats.php
 * Returns real-time admin dashboard stats across all users.
 * Called by admin.php directly (included/fetched server-side).
 * Also accessible via AJAX for dynamic refresh.
 */

session_start();
header('Content-Type: application/json');

$role = $_SESSION['role'] ?? $_SESSION['user_role'] ?? '';
if (!isset($_SESSION['user_id']) || $role !== 'admin') {
    http_response_code(403);
    echo json_encode(['success' => false, 'error' => 'Admin access required']);
    exit;
}

require_once __DIR__ . '/db_config.php';

try {
    $cols = $pdo->query("SHOW COLUMNS FROM disease_records")->fetchAll(PDO::FETCH_COLUMN);
    $has  = array_flip($cols);

    // Total users (non-admin)
    $total_users = (int) $pdo->query("SELECT COUNT(*) FROM users WHERE role = 'user'")->fetchColumn();

    // Total scans
    $total_scans = (int) $pdo->query("SELECT COUNT(*) FROM disease_records")->fetchColumn();

    // Recovered
    $recovered = 0;
    if (isset($has['status'])) {
        $recovered = (int) $pdo->query("SELECT COUNT(*) FROM disease_records WHERE status = 'recovered'")->fetchColumn();
    }

    // Active
    $active = 0;
    if (isset($has['status'])) {
        $active = (int) $pdo->query("SELECT COUNT(*) FROM disease_records WHERE status = 'in_progress'")->fetchColumn();
    }

    // Most detected disease
    $top_disease = ['name' => 'N/A', 'count' => 0];
    $row = $pdo->query("SELECT disease_name, COUNT(*) AS cnt FROM disease_records
        GROUP BY disease_name ORDER BY cnt DESC LIMIT 1")->fetch(PDO::FETCH_ASSOC);
    if ($row) $top_disease = ['name' => $row['disease_name'], 'count' => (int) $row['cnt']];

    // Most affected plant
    $top_plant = ['name' => 'N/A', 'count' => 0];
    if (isset($has['plant_name'])) {
        $row = $pdo->query("SELECT plant_name, COUNT(*) AS cnt FROM disease_records
            WHERE plant_name != '' GROUP BY plant_name ORDER BY cnt DESC LIMIT 1")->fetch(PDO::FETCH_ASSOC);
        if ($row) $top_plant = ['name' => $row['plant_name'], 'count' => (int) $row['cnt']];
    }

    // Recent scans (last 5 across all users)
    $recent_cols = ['dr.id', 'dr.disease_name', 'dr.scanned_at', 'u.name AS user_name'];
    if (isset($has['plant_name'])) $recent_cols[] = 'dr.plant_name';
    if (isset($has['status']))     $recent_cols[] = 'dr.status';
    if (isset($has['confidence'])) $recent_cols[] = 'dr.confidence';

    $recent = $pdo->query("
        SELECT " . implode(', ', $recent_cols) . "
        FROM disease_records dr
        JOIN users u ON dr.user_id = u.id
        ORDER BY dr.scanned_at DESC LIMIT 5
    ")->fetchAll(PDO::FETCH_ASSOC);

    foreach ($recent as &$r) {
        if (!isset($r['status']))     $r['status']     = 'detected';
        if (!isset($r['plant_name'])) $r['plant_name'] = '';
        if (!isset($r['confidence'])) $r['confidence'] = 0;
        $r['confidence'] = (float) $r['confidence'];
    }
    unset($r);

    // Disease breakdown (top 5)
    $disease_breakdown = $pdo->query("
        SELECT disease_name, COUNT(*) AS cnt
        FROM disease_records
        GROUP BY disease_name ORDER BY cnt DESC LIMIT 5
    ")->fetchAll(PDO::FETCH_ASSOC);

    foreach ($disease_breakdown as &$d) { $d['cnt'] = (int) $d['cnt']; }
    unset($d);

    echo json_encode([
        'success'           => true,
        'total_users'       => $total_users,
        'total_scans'       => $total_scans,
        'recovered'         => $recovered,
        'active'            => $active,
        'top_disease'       => $top_disease,
        'top_plant'         => $top_plant,
        'recent_scans'      => $recent,
        'disease_breakdown' => $disease_breakdown,
    ]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}