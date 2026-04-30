<?php
/**
 * BATANOX — auth_check.php  (v2)
 *
 * Flask app.py calls this to check if session is valid.
 * IMPORTANT: Must return user_id and role so Flask can
 * inject them as proxy headers into PHP requests.
 *
 * Response JSON:
 * {
 *   "authenticated": true/false,
 *   "user_id": 5,
 *   "name": "Ali",
 *   "role": "user" | "admin",
 *   "guest": false
 * }
 */

session_start();
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: http://localhost:5000');
header('Access-Control-Allow-Credentials: true');

if (!isset($_SESSION['user_id'])) {
    // Check for guest session
    if (isset($_SESSION['guest']) && $_SESSION['guest'] === true) {
        echo json_encode([
            'authenticated' => false,
            'guest'         => true,
            'user_id'       => 0,
            'role'          => 'guest',
        ]);
        exit;
    }
    echo json_encode([
        'authenticated' => false,
        'guest'         => false,
        'user_id'       => 0,
        'role'          => 'user',
    ]);
    exit;
}

echo json_encode([
    'authenticated' => true,
    'guest'         => false,
    'user_id'       => (int) $_SESSION['user_id'],                        // ← REQUIRED for proxy headers
    'name'          => $_SESSION['user_name'] ?? $_SESSION['name'] ?? 'User',
    'role'          => $_SESSION['role'] ?? $_SESSION['user_role'] ?? 'user',  // ← REQUIRED for proxy headers
]);