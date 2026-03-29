<?php
/**
 * BATANOX — create_admin.php
 *
 * PURPOSE: Creates or resets the admin account with a correctly
 *          generated bcrypt password hash.
 *
 * HOW TO USE:
 *   1. Place this file in C:\wamp64\www\batanox\
 *   2. Visit: http://localhost/batanox/create_admin.php
 *   3. The page will create/reset the admin account instantly.
 *   4. DELETE this file after use (security).
 *
 * Default credentials created:
 *   Email:    admin@batanox.local
 *   Password: admin123
 *
 * You can change them below before running.
 */

// ── Config — change these if you want different credentials ──────────────────
define('ADMIN_NAME',     'Admin');
define('ADMIN_EMAIL',    'admin@batanox.local');
define('ADMIN_PASSWORD', 'admin123');

// ────────────────────────────────────────────────────────────────────────────
require_once __DIR__ . '/db_config.php';

$result  = '';
$success = false;
$error   = '';

try {
    // Generate a fresh, correct bcrypt hash right now on this server
    $hash = password_hash(ADMIN_PASSWORD, PASSWORD_BCRYPT);

    // Delete any existing admin with this email (avoids duplicate key error)
    $del = $pdo->prepare("DELETE FROM `users` WHERE `email` = ?");
    $del->execute([ADMIN_EMAIL]);

    // Insert fresh admin account
    $ins = $pdo->prepare("
        INSERT INTO `users` (`name`, `email`, `password`, `role`, `created_at`)
        VALUES (?, ?, ?, 'admin', NOW())
    ");
    $ins->execute([ADMIN_NAME, ADMIN_EMAIL, $hash]);

    $new_id  = (int) $pdo->lastInsertId();
    $success = true;
    $result  = "Admin account created successfully! (User ID: $new_id)";

    // Verify it works immediately
    $check = $pdo->prepare("SELECT id, name, password, role FROM users WHERE email = ? LIMIT 1");
    $check->execute([ADMIN_EMAIL]);
    $row = $check->fetch();

    $verify_ok = $row && password_verify(ADMIN_PASSWORD, $row['password']);

} catch (PDOException $e) {
    $error = "Database error: " . $e->getMessage();
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create Admin — BATANOX</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: #f0fdf4; min-height: 100vh;
            display: flex; align-items: center; justify-content: center; padding: 24px;
        }
        .card {
            background: white; border: 1px solid #bbf7d0; border-radius: 20px;
            padding: 48px 44px; width: 100%; max-width: 500px;
            box-shadow: 0 8px 40px rgba(0,0,0,0.07);
        }
        .brand { display: flex; align-items: center; gap: 10px; justify-content: center; margin-bottom: 32px; }
        .brand-mark {
            width: 42px; height: 42px; border-radius: 12px;
            background: linear-gradient(135deg, #15803d, #22c55e);
            display: flex; align-items: center; justify-content: center;
        }
        .brand-mark svg { width: 22px; height: 22px; fill: white; }
        .brand-name { font-size: 24px; font-weight: 800; color: #111827; }
        .brand-name em { font-style: normal; color: #16a34a; }
        h1 { font-size: 20px; font-weight: 800; color: #111827; text-align: center; margin-bottom: 8px; }
        .sub { font-size: 14px; color: #6b7280; text-align: center; margin-bottom: 28px; }
        .box-ok  { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; }
        .box-err { background: #fef2f2; border: 1.5px solid #fecaca; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; }
        .box-ok h2  { font-size: 15px; font-weight: 700; color: #15803d; margin-bottom: 14px; }
        .box-err h2 { font-size: 15px; font-weight: 700; color: #b91c1c; margin-bottom: 14px; }
        .cred-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; font-size: 14px; }
        .cred-lbl { font-weight: 700; color: #374151; width: 80px; flex-shrink: 0; }
        .cred-val { background: #111827; color: #4ade80; font-family: monospace; font-size: 14px; padding: 6px 14px; border-radius: 7px; letter-spacing: 0.5px; }
        .verify { margin-top: 14px; font-size: 13px; font-weight: 600; }
        .verify.ok  { color: #15803d; }
        .verify.bad { color: #b91c1c; }
        .warn { background: #fefce8; border: 1.5px solid #fef08a; border-radius: 12px; padding: 14px 18px; font-size: 13px; color: #92400e; font-weight: 600; margin-bottom: 24px; }
        .btn-login { display: block; width: 100%; padding: 13px; text-align: center; text-decoration: none;
            background: linear-gradient(135deg, #15803d, #22c55e); color: white; border-radius: 10px;
            font-family: inherit; font-size: 15px; font-weight: 700;
            box-shadow: 0 4px 14px rgba(34,197,94,0.32); transition: all 0.2s; }
        .btn-login:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(34,197,94,0.42); }
        .hash-box { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 14px; font-family: monospace; font-size: 11px; color: #6b7280; word-break: break-all; margin-top: 14px; }
    </style>
</head>
<body>
<div class="card">

    <div class="brand">
        <div class="brand-mark">
            <svg viewBox="0 0 24 24"><path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1-2.3A4.49 4.49 0 008 20C19 20 22 3 22 3c-1 2-8 2-13 6 1-2.17 2.64-4.41 8-5z"/></svg>
        </div>
        <span class="brand-name">BATA<em>NOX</em></span>
    </div>

    <h1>Admin Account Setup</h1>
    <p class="sub">Creates or resets the admin account in the database</p>

    <?php if ($success): ?>
    <div class="box-ok">
        <h2>✅ <?= htmlspecialchars($result) ?></h2>
        <div class="cred-row">
            <span class="cred-lbl">Email</span>
            <span class="cred-val"><?= htmlspecialchars(ADMIN_EMAIL) ?></span>
        </div>
        <div class="cred-row">
            <span class="cred-lbl">Password</span>
            <span class="cred-val"><?= htmlspecialchars(ADMIN_PASSWORD) ?></span>
        </div>
        <div class="cred-row">
            <span class="cred-lbl">Role</span>
            <span class="cred-val">admin</span>
        </div>
        <div class="verify <?= $verify_ok ? 'ok' : 'bad' ?>">
            <?= $verify_ok
                ? '✔ Password verification confirmed — login will work'
                : '✘ Verification failed — contact developer' ?>
        </div>
        <?php if (isset($hash)): ?>
        <div class="hash-box">Hash stored: <?= htmlspecialchars($hash) ?></div>
        <?php endif; ?>
    </div>

    <div class="warn">
        ⚠️ <strong>Security:</strong> Delete <code>create_admin.php</code> from your server after logging in successfully.
    </div>

    <a href="login.php" class="btn-login">→ Go to Login Page</a>

    <?php else: ?>
    <div class="box-err">
        <h2>❌ Failed to create admin account</h2>
        <p style="font-size:14px;color:#374151;"><?= htmlspecialchars($error) ?></p>
        <p style="font-size:13px;color:#6b7280;margin-top:10px;">Make sure WAMP is running and the BATANOX database exists. Import <code>batanox.sql</code> first if you haven't.</p>
    </div>
    <?php endif; ?>

</div>
</body>
</html>