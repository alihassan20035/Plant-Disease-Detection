<?php
/**
 * BATANOX — get_reminders.php
 * Returns disease records whose next_reminder is due (≤ NOW()).
 */

session_start();
header('Content-Type: application/json');

if (!isset($_SESSION['user_id'])) {
    http_response_code(401);
    echo json_encode(['success' => false, 'reminders' => []]);
    exit;
}

require_once __DIR__ . '/db_config.php';

$user_id = (int) $_SESSION['user_id'];

try {
    $stmt = $pdo->prepare("
        SELECT id, plant_name, disease_name, reminder_note, next_reminder, status
        FROM   disease_records
        WHERE  user_id        = ?
          AND  next_reminder IS NOT NULL
          AND  next_reminder <= NOW()
          AND  status        != 'recovered'
        ORDER BY next_reminder ASC
        LIMIT 10
    ");
    $stmt->execute([$user_id]);
    $reminders = $stmt->fetchAll(PDO::FETCH_ASSOC);

    foreach ($reminders as &$r) {
        $r['id'] = (int) $r['id'];
    }
    unset($r);

    echo json_encode(['success' => true, 'reminders' => $reminders]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'reminders' => [], 'error' => $e->getMessage()]);
}