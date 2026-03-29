<?php
/**
 * BATANOX — login.php  (final)
 *
 * Role-based redirect after login:
 *   admin  →  admin.php
 *   user   →  http://localhost:5000/
 *
 * Session keys written:
 *   $_SESSION['user_id']   int
 *   $_SESSION['user_name'] string
 *   $_SESSION['name']      string  (alias)
 *   $_SESSION['role']      'user'|'admin'
 *   $_SESSION['user_role'] 'user'|'admin'  (legacy compat)
 */

session_start();
require_once __DIR__ . '/db_config.php';

// ── Already logged in → send to right place ──────────────────────────────────
if (isset($_SESSION['user_id'])) {
    $role = $_SESSION['role'] ?? $_SESSION['user_role'] ?? 'user';
    // Admins skip welcome screen; regular users see it
    header('Location: ' . ($role === 'admin' ? 'admin.php' : 'welcome.php'));
    exit;
}

$error = '';

// ── Handle POST ───────────────────────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    $email    = trim($_POST['email']    ?? '');
    $password = trim($_POST['password'] ?? '');

    if ($email === '' || $password === '') {
        $error = 'Please enter both email and password.';
    } else {
        try {
            $stmt = $pdo->prepare(
                "SELECT id, name, email, password, role
                 FROM   users
                 WHERE  email = ?
                 LIMIT  1"
            );
            $stmt->execute([$email]);
            $user = $stmt->fetch(PDO::FETCH_ASSOC);
        } catch (PDOException $e) {
            $error = 'Database error: ' . $e->getMessage();
            $user  = null;
        }

        if (!$error) {
            if ($user && password_verify($password, $user['password'])) {

                // ── Valid credentials ─────────────────────────────────────
                session_regenerate_id(true);

                $_SESSION['user_id']   = (int)    $user['id'];
                $_SESSION['user_name'] = (string) $user['name'];
                $_SESSION['name']      = (string) $user['name'];
                $_SESSION['role']      = (string) $user['role'];
                $_SESSION['user_role'] = (string) $user['role'];

                // ── Role-based redirect ───────────────────────────────────
                if ($user['role'] === 'admin') {
                    header('Location: admin.php');
                } else {
                    // Regular users see the Plant Tips Welcome Screen first
                    header('Location: welcome.php');
                }
                exit;

            } else {
                // Separate messages help distinguish "wrong password" vs "no account"
                $error = $user
                    ? 'Incorrect password. Please try again.'
                    : 'No account found with that email address.';
            }
        }
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login — BATANOX</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --g50:#f0fdf4; --g100:#dcfce7; --g200:#bbf7d0;
            --g500:#22c55e; --g600:#16a34a; --g700:#15803d;
            --white:#ffffff;
            --gr50:#f9fafb; --gr100:#f3f4f6; --gr200:#e5e7eb;
            --gr300:#d1d5db; --gr400:#9ca3af; --gr500:#6b7280;
            --gr700:#374151; --gr900:#111827;
            --r50:#fef2f2; --r200:#fecaca; --r600:#dc2626; --r700:#b91c1c;
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
        .brand-mark {
            width: 42px; height: 42px; border-radius: 12px;
            background: linear-gradient(135deg, var(--g700), var(--g500));
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 4px 14px rgba(22,163,74,0.3);
        }
        .brand-mark svg { width: 22px; height: 22px; fill: white; }
        .brand-name { font-size: 24px; font-weight: 800; letter-spacing: -0.5px; color: var(--gr900); }
        .brand-name em { font-style: normal; color: var(--g600); }
        .heading { font-size: 22px; font-weight: 800; color: var(--gr900); text-align: center; margin-bottom: 6px; }
        .sub     { font-size: 14px; color: var(--gr500); text-align: center; margin-bottom: 28px; }
        .field       { margin-bottom: 18px; }
        .field label { display: block; font-size: 13px; font-weight: 600; color: var(--gr700); margin-bottom: 7px; }
        .field input {
            width: 100%; padding: 12px 16px;
            border: 1.5px solid var(--gr300); border-radius: 10px;
            font-family: inherit; font-size: 14px; color: var(--gr900); outline: none;
            transition: border-color 0.2s, box-shadow 0.2s; background: var(--white);
        }
        .field input:focus { border-color: var(--g500); box-shadow: 0 0 0 3px rgba(34,197,94,0.12); }
        .field input::placeholder { color: var(--gr400); }
        .error-box {
            background: var(--r50); border: 1px solid var(--r200); border-radius: 10px;
            padding: 12px 16px; font-size: 13px; font-weight: 500; color: var(--r700);
            display: flex; align-items: flex-start; gap: 8px; margin-bottom: 20px;
        }
        .btn-submit {
            width: 100%; padding: 13px;
            background: linear-gradient(135deg, var(--g700), var(--g500));
            border: none; border-radius: 10px; cursor: pointer;
            font-family: inherit; font-size: 15px; font-weight: 700; color: white;
            box-shadow: 0 4px 14px rgba(34,197,94,0.32); transition: all 0.2s; margin-top: 4px;
        }
        .btn-submit:hover  { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(34,197,94,0.42); }
        .btn-submit:active { transform: none; }
        .foot { margin-top: 22px; text-align: center; font-size: 13px; color: var(--gr500); }
        .foot a { color: var(--g600); font-weight: 700; text-decoration: none; }
        .foot a:hover { text-decoration: underline; }
        .divider {
            display: flex; align-items: center; gap: 12px;
            margin: 22px 0; color: var(--gr400); font-size: 12px; font-weight: 600;
        }
        .divider::before, .divider::after { content:''; flex:1; height:1px; background:var(--gr200); }
        .btn-guest {
            width: 100%; padding: 12px; background: var(--white);
            border: 1.5px solid var(--gr300); border-radius: 10px; cursor: pointer;
            font-family: inherit; font-size: 14px; font-weight: 600; color: var(--gr700);
            transition: all 0.15s;
        }
        .btn-guest:hover { background: var(--gr50); border-color: var(--gr400); }
    </style>
</head>
<body>
<div class="card">

    <div class="brand">
        <div class="brand-mark">
            <svg viewBox="0 0 24 24">
                <path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1-2.3A4.49 4.49 0 008 20C19 20 22 3 22 3c-1 2-8 2-13 6 1-2.17 2.64-4.41 8-5z"/>
            </svg>
        </div>
        <span class="brand-name">BATA<em>NOX</em></span>
    </div>

    <div class="heading">Welcome back</div>
    <div class="sub">Sign in to your BATANOX account</div>

    <?php if ($error !== ''): ?>
    <div class="error-box">
        <span>⚠</span>
        <span><?= htmlspecialchars($error) ?></span>
    </div>
    <?php endif; ?>

    <form method="POST" action="">
        <div class="field">
            <label for="email">Email address</label>
            <input type="email" id="email" name="email"
                   placeholder="you@example.com"
                   value="<?= htmlspecialchars($_POST['email'] ?? '') ?>"
                   required autocomplete="email">
        </div>
        <div class="field">
            <label for="password">Password</label>
            <input type="password" id="password" name="password"
                   placeholder="Enter your password"
                   required autocomplete="current-password">
        </div>
        <button type="submit" class="btn-submit">Sign In →</button>
    </form>

    <div class="divider">or</div>

    <form method="POST" action="guest_login.php">
        <button type="submit" class="btn-guest">🌿 Continue as Guest</button>
    </form>

    <div class="foot">
        Don't have an account? <a href="register.php">Create one</a>
    </div>

</div>
</body>
</html>