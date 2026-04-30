<?php
/**
 * BATANOX — save_order.php
 *
 * Called by Flask route /api/shop/order (POST).
 * Receives JSON order data, saves to medicine_orders + medicine_order_items.
 * Returns JSON: { "success": true, "order_id": 42 }
 *
 * Place this file in: C:/wamp64/www/batanox/save_order.php
 */

session_start();
require_once 'db_config.php';

header('Content-Type: application/json; charset=UTF-8');

// ── Only accept POST ───────────────────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['success' => false, 'error' => 'Method not allowed']);
    exit;
}

// ── Parse JSON body ────────────────────────────────────────────────────────────
$raw  = file_get_contents('php://input');
$body = json_decode($raw, true);

if (!$body || !isset($body['items']) || !is_array($body['items']) || count($body['items']) === 0) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Invalid or empty order data']);
    exit;
}

// ── Extract fields ─────────────────────────────────────────────────────────────
$user_id    = isset($body['user_id'])    ? (int)$body['user_id']   : null;
$user_name  = isset($body['user_name'])  ? trim(substr($body['user_name'],  0, 120)) : 'Guest';
$user_email = isset($body['user_email']) ? trim(substr($body['user_email'], 0, 180)) : '';
$items      = $body['items'];  // array of { id, name, type, plant, price, quantity }

if ($user_name === '') $user_name = 'Guest';

// ── Calculate totals ───────────────────────────────────────────────────────────
$total_price = 0.0;
$item_count  = 0;

foreach ($items as $it) {
    $qty        = max(1, (int)($it['quantity'] ?? 1));
    $unit_price = (float)($it['price'] ?? 0);
    $total_price += $unit_price * $qty;
    $item_count  += $qty;
}

// ── Save to DB in a transaction ────────────────────────────────────────────────
try {
    $pdo->beginTransaction();

    // Insert order header
    $stmt = $pdo->prepare("
        INSERT INTO medicine_orders
            (user_id, user_name, user_email, total_price, item_count, status, ordered_at)
        VALUES
            (?, ?, ?, ?, ?, 'pending', NOW())
    ");
    $stmt->execute([$user_id ?: null, $user_name, $user_email, $total_price, $item_count]);
    $order_id = (int)$pdo->lastInsertId();

    // Insert line items
    $ist = $pdo->prepare("
        INSERT INTO medicine_order_items
            (order_id, medicine_id, medicine_name, medicine_type, plant_target, unit_price, quantity, line_total)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?)
    ");

    foreach ($items as $it) {
        $mid        = (int)($it['id']       ?? 0);
        $mname      = substr(trim($it['name']  ?? 'Unknown'), 0, 200);
        $mtype      = substr(trim($it['type']  ?? ''),        0, 60);
        $mplant     = substr(trim($it['plant'] ?? ''),        0, 80);
        $unit_price = (float)($it['price']    ?? 0);
        $qty        = max(1, (int)($it['quantity'] ?? 1));
        $line_total = $unit_price * $qty;

        $ist->execute([$order_id, $mid, $mname, $mtype, $mplant, $unit_price, $qty, $line_total]);
    }

    $pdo->commit();

    echo json_encode([
        'success'     => true,
        'order_id'    => $order_id,
        'total_price' => round($total_price, 2),
        'item_count'  => $item_count,
        'message'     => 'Order saved successfully',
    ]);

} catch (PDOException $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Database error: ' . $e->getMessage()]);
}
exit;