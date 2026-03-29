<?php
/**
 * BATANOX — clear_records.php
 * Deletes every disease_record belonging to the logged-in user.
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
    $stmt = $pdo->prepare("DELETE FROM disease_records WHERE user_id = ?");
    $stmt->execute([$user_id]);
    echo json_encode(['success' => true, 'deleted' => $stmt->rowCount()]);
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}