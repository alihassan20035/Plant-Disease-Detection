<?php
/**
 * BATANOX — auth_check.php  (v5 — final fixed)
 * Called by Flask to verify the current browser session.
 */

session_start();
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: http://localhost:5000');
header('Access-Control-Allow-Credentials: true');

// ── Guest / unauthenticated ──────────────────────────────────────────────────
if (!isset($_SESSION['user_id'])) {
    echo json_encode([
        'authenticated' => false,
        'guest'         => !empty($_SESSION['guest']),
        'name'          => 'Guest',
        'id'            => null,
        'role'          => 'guest',
    ]);
    exit;
}

// ── Logged-in user ───────────────────────────────────────────────────────────
require_once __DIR__ . '/db_config.php';

$uid  = (int) $_SESSION['user_id'];
$stmt = $pdo->prepare("SELECT id, name, role FROM users WHERE id = ? LIMIT 1");
$stmt->execute([$uid]);
$user = $stmt->fetch();

if (!$user) {
    session_destroy();
    echo json_encode(['authenticated' => false, 'guest' => false, 'name' => '', 'id' => null, 'role' => '']);
    exit;
}

// Keep both session keys in sync
$_SESSION['role']      = $user['role'];
$_SESSION['user_role'] = $user['role'];
$_SESSION['user_name'] = $user['name'];

echo json_encode([
    'authenticated' => true,
    'guest'         => false,
    'name'          => $user['name'],
    'id'            => $user['id'],
    'role'          => $user['role'],
]);