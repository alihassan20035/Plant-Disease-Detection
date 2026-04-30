<?php
/**
 * BATANOX — get_my_orders.php
 *
 * Called by Flask route GET /api/shop/my_orders
 * Returns all orders for the currently logged-in user,
 * including each order's line items.
 *
 * Place in: C:/wamp64/www/batanox/get_my_orders.php
 */

session_start();
require_once 'db_config.php';

header('Content-Type: application/json; charset=UTF-8');

/* ── Auth check ─────────────────────────────────────────────────────────── */
if (!isset($_SESSION['user_id'])) {
    echo json_encode(['success' => false, 'error' => 'Not authenticated', 'orders' => []]);
    exit;
}

$user_id   = (int)$_SESSION['user_id'];
$user_name = $_SESSION['name'] ?? '';

/* ── Fetch orders ───────────────────────────────────────────────────────── */
try {
    /* Fetch all orders for this user, newest first */
    $stmt = $pdo->prepare("
        SELECT id, user_id, user_name, user_email,
               total_price, item_count, status, ordered_at
        FROM   medicine_orders
        WHERE  user_id = ?
           OR  user_name = ?
        ORDER  BY ordered_at DESC
        LIMIT  100
    ");
    $stmt->execute([$user_id, $user_name]);
    $orders = $stmt->fetchAll(PDO::FETCH_ASSOC);

    if (empty($orders)) {
        echo json_encode(['success' => true, 'orders' => []]);
        exit;
    }

    /* Collect order IDs */
    $order_ids     = array_column($orders, 'id');
    $placeholders  = implode(',', array_fill(0, count($order_ids), '?'));

    /* Fetch all line items for these orders in one query */
    $istmt = $pdo->prepare("
        SELECT order_id, medicine_id, medicine_name, medicine_type,
               plant_target, unit_price, quantity, line_total
        FROM   medicine_order_items
        WHERE  order_id IN ($placeholders)
        ORDER  BY order_id, id
    ");
    $istmt->execute($order_ids);
    $all_items = $istmt->fetchAll(PDO::FETCH_ASSOC);

    /* Group items by order_id */
    $items_by_order = [];
    foreach ($all_items as $item) {
        $items_by_order[(int)$item['order_id']][] = $item;
    }

    /* Attach items to each order */
    foreach ($orders as &$order) {
        $order['items'] = $items_by_order[(int)$order['id']] ?? [];
    }
    unset($order);

    echo json_encode(['success' => true, 'orders' => $orders]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Database error: ' . $e->getMessage(), 'orders' => []]);
}
exit;