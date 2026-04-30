<?php
session_start();
require_once 'db_config.php';

if (isset($_SESSION['user_id'])) {
    $role = $_SESSION['role'] ?? $_SESSION['user_role'] ?? 'user';
    header('Location: ' . ($role === 'admin' ? 'admin.php' : 'http://localhost:5000/'));
    exit;
}

$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name     = trim($_POST['name'] ?? '');
    $email    = trim($_POST['email'] ?? '');
    $password = $_POST['password'] ?? '';
    $confirm  = $_POST['confirm_password'] ?? '';

    if (empty($name) || empty($email) || empty($password) || empty($confirm)) {
        $error = 'Please fill in all fields.';
    } elseif (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
        $error = 'Please enter a valid email address.';
    } elseif (strlen($password) < 6) {
        $error = 'Password must be at least 6 characters.';
    } elseif ($password !== $confirm) {
        $error = 'Passwords do not match.';
    } else {
        $stmt = $pdo->prepare("SELECT id FROM users WHERE email = ?");
        $stmt->execute([$email]);
        if ($stmt->fetch()) {
            $error = 'An account with this email already exists.';
        } else {
            $hashed = password_hash($password, PASSWORD_DEFAULT);
            $stmt = $pdo->prepare("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, 'user')");
            $stmt->execute([$name, $email, $hashed]);
            header('Location: login.php?registered=1');
            exit;
        }
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create Account — BATANOX</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --green-50:  #f0fdf4;
            --green-100: #dcfce7;
            --green-200: #bbf7d0;
            --green-500: #22c55e;
            --green-600: #16a34a;
            --green-700: #15803d;
            --white: #ffffff;
            --gray-50:  #f9fafb;
            --gray-100: #f3f4f6;
            --gray-300: #d1d5db;
            --gray-500: #6b7280;
            --gray-700: #374151;
            --gray-900: #111827;
            --shadow-lg: 0 8px 40px rgba(0,0,0,0.10);
        }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--gray-50);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }

        .page-bg {
            position: fixed; inset: 0;
            background:
                radial-gradient(ellipse 80% 50% at 20% 0%, rgba(34,197,94,0.08) 0%, transparent 60%),
                radial-gradient(ellipse 60% 60% at 80% 100%, rgba(22,163,74,0.06) 0%, transparent 60%);
            z-index: 0;
        }

        .card {
            position: relative; z-index: 1;
            background: var(--white);
            border: 1px solid var(--gray-100);
            border-radius: 20px;
            padding: 48px 44px;
            width: 100%; max-width: 460px;
            box-shadow: var(--shadow-lg);
        }

        .logo { display: flex; align-items: center; gap: 10px; margin-bottom: 36px; }
        .logo-mark {
            width: 38px; height: 38px;
            background: linear-gradient(135deg, var(--green-600), var(--green-500));
            border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 4px 12px rgba(34,197,94,0.3);
        }
        .logo-mark svg { width: 20px; height: 20px; fill: white; }
        .logo-name { font-size: 20px; font-weight: 800; color: var(--gray-900); letter-spacing: -0.3px; }
        .logo-name span { color: var(--green-600); }

        h1 { font-size: 28px; font-weight: 800; color: var(--gray-900); letter-spacing: -0.5px; margin-bottom: 6px; }
        .subtitle { font-size: 14px; color: var(--gray-500); margin-bottom: 32px; }

        .alert { padding: 12px 16px; border-radius: 10px; font-size: 13px; font-weight: 500; margin-bottom: 20px; }
        .alert-error { background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c; }

        .form-group { margin-bottom: 18px; }
        label { display: block; font-size: 13px; font-weight: 600; color: var(--gray-700); margin-bottom: 8px; }

        input[type="email"], input[type="password"], input[type="text"] {
            width: 100%; padding: 12px 16px;
            border: 1.5px solid var(--gray-300); border-radius: 10px;
            font-family: 'Plus Jakarta Sans', sans-serif; font-size: 14px;
            color: var(--gray-900); background: var(--white);
            transition: border-color 0.2s, box-shadow 0.2s; outline: none;
        }
        input:focus { border-color: var(--green-500); box-shadow: 0 0 0 3px rgba(34,197,94,0.12); }
        input::placeholder { color: var(--gray-300); }

        .hint { font-size: 12px; color: var(--gray-500); margin-top: 5px; }

        .btn {
            width: 100%; padding: 14px; margin-top: 8px;
            background: linear-gradient(135deg, var(--green-600), var(--green-500));
            color: white; border: none; border-radius: 10px;
            font-family: 'Plus Jakarta Sans', sans-serif; font-size: 15px; font-weight: 700;
            cursor: pointer; transition: all 0.2s;
            box-shadow: 0 4px 14px rgba(34,197,94,0.35); letter-spacing: 0.2px;
        }
        .btn:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(34,197,94,0.45); }

        .switch { text-align: center; margin-top: 24px; font-size: 14px; color: var(--gray-500); }
        .switch a { color: var(--green-600); font-weight: 700; text-decoration: none; }
        .switch a:hover { text-decoration: underline; }

        .terms { font-size: 12px; color: var(--gray-500); text-align: center; margin-top: 14px; }
        .terms a { color: var(--green-600); text-decoration: none; }
    </style>
</head>
<body>
<div class="page-bg"></div>
<div class="card">
    <div class="logo">
        <img src="templates/fyp-logo-01.png" alt="BATANOX Logo" style="height:42px;width:auto;object-fit:contain;border-radius:8px;">
        <div class="logo-name">BATA<span>NOX</span></div>
    </div>

    <h1>Create account</h1>
    <p class="subtitle">Start detecting plant diseases with AI</p>

    <?php if ($error): ?>
    <div class="alert alert-error">⚠ <?= htmlspecialchars($error) ?></div>
    <?php endif; ?>

    <form method="POST" action="">
        <div class="form-group">
            <label for="name">Full Name</label>
            <input type="text" id="name" name="name" placeholder="John Doe" required
                   value="<?= isset($_POST['name']) ? htmlspecialchars($_POST['name']) : '' ?>">
        </div>
        <div class="form-group">
            <label for="email">Email Address</label>
            <input type="email" id="email" name="email" placeholder="you@example.com" required
                   value="<?= isset($_POST['email']) ? htmlspecialchars($_POST['email']) : '' ?>">
        </div>
        <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="Minimum 6 characters" required>
            <p class="hint">Use at least 6 characters with letters and numbers</p>
        </div>
        <div class="form-group">
            <label for="confirm_password">Confirm Password</label>
            <input type="password" id="confirm_password" name="confirm_password" placeholder="Repeat your password" required>
        </div>
        <button type="submit" class="btn">Create Account →</button>
    </form>

    <p class="terms">By signing up you agree to our <a href="#">Terms of Service</a> and <a href="#">Privacy Policy</a></p>
    <p class="switch">Already have an account? <a href="login.php">Sign In</a></p>
</div>
</body>
</html>