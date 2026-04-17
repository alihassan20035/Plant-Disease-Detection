<?php
/**
 * BATANOX — reset_password.php
 *
 * User yahan aata hai email ke link se.
 * Token verify hota hai, naya password set hota hai.
 */

session_start();
require_once __DIR__ . '/db_config.php';

$token   = trim($_GET['token'] ?? '');
$error   = '';
$success = false;

// Validate token
if ($token === '') {
    $error = 'Invalid or missing reset token.';
} else {
    $stmt = $pdo->prepare("
        SELECT * FROM password_resets
        WHERE token = ? AND used = 0 AND expires_at > NOW()
        LIMIT 1
    ");
    $stmt->execute([$token]);
    $resetRow = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$resetRow) {
        $error = 'This reset link is invalid or has expired. Please request a new one.';
    }
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && !$error) {

    $newPass     = $_POST['password']         ?? '';
    $confirmPass = $_POST['password_confirm'] ?? '';

    if (strlen($newPass) < 8) {
        $error = 'Password must be at least 8 characters.';
    } elseif ($newPass !== $confirmPass) {
        $error = 'Passwords do not match.';
    } else {
        // Update password
        $hash = password_hash($newPass, PASSWORD_DEFAULT);
        $upd  = $pdo->prepare("UPDATE users SET password = ? WHERE email = ?");
        $upd->execute([$hash, $resetRow['email']]);

        // Mark token as used
        $used = $pdo->prepare("UPDATE password_resets SET used = 1 WHERE token = ?");
        $used->execute([$token]);

        $success = true;
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Password — BATANOX</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --g500:#22c55e; --g600:#16a34a; --g700:#15803d;
            --white:#ffffff; --gr50:#f9fafb; --gr200:#e5e7eb;
            --gr300:#d1d5db; --gr400:#9ca3af; --gr500:#6b7280;
            --gr700:#374151; --gr900:#111827;
            --r50:#fef2f2; --r200:#fecaca; --r700:#b91c1c;
        }
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--gr50); min-height: 100vh;
            display: flex; align-items: center; justify-content: center; padding: 24px;
        }
        .card {
            background: var(--white); border: 1px solid var(--gr200);
            border-radius: 20px; padding: 48px 44px;
            width: 100%; max-width: 420px;
            box-shadow: 0 8px 40px rgba(0,0,0,0.07);
        }
        .brand { display: flex; align-items: center; gap: 10px; justify-content: center; margin-bottom: 32px; }
        .brand-name { font-size: 24px; font-weight: 800; letter-spacing: -0.5px; color: var(--gr900); }
        .brand-name em { font-style: normal; color: var(--g600); }
        .icon-wrap {
            width: 56px; height: 56px; border-radius: 16px;
            background: #f0fdf4; border: 1px solid #bbf7d0;
            display: flex; align-items: center; justify-content: center;
            font-size: 26px; margin: 0 auto 20px;
        }
        .heading { font-size: 22px; font-weight: 800; color: var(--gr900); text-align: center; margin-bottom: 8px; }
        .sub     { font-size: 14px; color: var(--gr500); text-align: center; margin-bottom: 28px; }
        .field       { margin-bottom: 18px; }
        .field label { display: block; font-size: 13px; font-weight: 600; color: var(--gr700); margin-bottom: 7px; }
        .field input {
            width: 100%; padding: 12px 16px;
            border: 1.5px solid var(--gr300); border-radius: 10px;
            font-family: inherit; font-size: 14px; color: var(--gr900); outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .field input:focus { border-color: var(--g500); box-shadow: 0 0 0 3px rgba(34,197,94,0.12); }
        .msg-box {
            border-radius: 10px; padding: 12px 16px;
            font-size: 13px; font-weight: 500;
            display: flex; align-items: flex-start; gap: 8px; margin-bottom: 20px;
        }
        .msg-box.success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #15803d; }
        .msg-box.error   { background: var(--r50); border: 1px solid var(--r200); color: var(--r700); }
        .btn-submit {
            width: 100%; padding: 13px;
            background: linear-gradient(135deg, var(--g700), var(--g500));
            border: none; border-radius: 10px; cursor: pointer;
            font-family: inherit; font-size: 15px; font-weight: 700; color: white;
            box-shadow: 0 4px 14px rgba(34,197,94,0.32); transition: all 0.2s;
        }
        .btn-submit:hover { transform: translateY(-1px); }
        .foot { margin-top: 22px; text-align: center; font-size: 13px; color: var(--gr500); }
        .foot a { color: var(--g600); font-weight: 700; text-decoration: none; }
    </style>
</head>
<body>
<div class="card">

    <div class="brand">
        <img src="templates/app logo 01.png" alt="" width="40" height="50">
        <span class="brand-name">BATA<em>NOX</em></span>
    </div>

    <?php if ($success): ?>
        <div class="icon-wrap">✅</div>
        <div class="heading">Password Updated!</div>
        <div class="sub">Your password has been reset successfully.</div>
        <div class="foot" style="margin-top:0;">
            <a href="login.php">← Back to Login</a>
        </div>

    <?php elseif ($error !== '' && !isset($resetRow)): ?>
        <div class="icon-wrap">❌</div>
        <div class="heading">Link Expired</div>
        <div class="msg-box error"><span>⚠</span><span><?= htmlspecialchars($error) ?></span></div>
        <div class="foot" style="margin-top:0;">
            <a href="forgot_password.php">Request a new link</a>
        </div>

    <?php else: ?>
        <div class="icon-wrap">🔒</div>
        <div class="heading">Set New Password</div>
        <div class="sub">Choose a strong password (min. 8 characters).</div>

        <?php if ($error): ?>
        <div class="msg-box error"><span>⚠</span><span><?= htmlspecialchars($error) ?></span></div>
        <?php endif; ?>

        <form method="POST" action="">
            <input type="hidden" name="token" value="<?= htmlspecialchars($token) ?>">
            <div class="field">
                <label for="password">New Password</label>
                <input type="password" id="password" name="password"
                       placeholder="Min. 8 characters" required>
            </div>
            <div class="field">
                <label for="password_confirm">Confirm Password</label>
                <input type="password" id="password_confirm" name="password_confirm"
                       placeholder="Repeat password" required>
            </div>
            <button type="submit" class="btn-submit">Update Password →</button>
        </form>

        <div class="foot">
            <a href="login.php">← Back to Login</a>
        </div>
    <?php endif; ?>

</div>
</body>
</html>