<?php
/**
 * BATANOX — Database Configuration
 * WAMP Server / XAMPP MySQL Connection
 */

define('DB_HOST',    'localhost');
define('DB_NAME',    'BATANOX');
define('DB_USER',    'root');
define('DB_PASS',    '');         // WAMP default: empty password
define('DB_CHARSET', 'utf8mb4');

$dsn = "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";charset=" . DB_CHARSET;

$pdo_options = [
    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO($dsn, DB_USER, DB_PASS, $pdo_options);
} catch (PDOException $e) {
    die('
    <div style="font-family:system-ui,sans-serif;padding:40px;background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;border-radius:12px;max-width:600px;margin:60px auto;">
        <h2 style="margin:0 0 12px;">⚠️ Database Connection Failed</h2>
        <p style="margin:0 0 8px;">' . htmlspecialchars($e->getMessage()) . '</p>
        <p style="color:#15803d;font-size:14px;">Make sure WAMP Server is running and the BATANOX database is imported.</p>
    </div>');
}