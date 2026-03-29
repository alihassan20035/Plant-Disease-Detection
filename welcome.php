<?php
/**
 * BATANOX — welcome.php
 *
 * Shown ONLY to logged-in regular users after login.
 * - Admins are sent directly to admin.php (login.php handles this)
 * - Guests never reach this page
 * - Displays plant care tips for 2.5 seconds, then redirects to Flask dashboard
 *
 * HOW IT FITS:
 *   login.php  →  (role = user)  →  welcome.php  →  http://localhost:5000/
 *   login.php  →  (role = admin) →  admin.php              (unchanged)
 */

session_start();

// Guard: only logged-in regular users may see this
if (!isset($_SESSION['user_id'])) {
    header('Location: login.php');
    exit;
}
$role = $_SESSION['role'] ?? $_SESSION['user_role'] ?? 'user';
if ($role === 'admin') {
    header('Location: admin.php');
    exit;
}

$user_name = htmlspecialchars($_SESSION['user_name'] ?? $_SESSION['name'] ?? 'there');
$redirect  = 'http://localhost:5000/';
$delay_ms  = 2800;   // total screen time in milliseconds
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome — BATANOX</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --g50:  #f0fdf4;  --g100: #dcfce7;  --g200: #bbf7d0;
            --g500: #22c55e;  --g600: #16a34a;  --g700: #15803d;
            --white: #ffffff;
            --gr50: #f9fafb;  --gr200: #e5e7eb;
            --gr400: #9ca3af; --gr500: #6b7280;  --gr700: #374151; --gr900: #111827;
        }

        /* ── Full-screen wrapper ─────────────────────────────── */
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--gr50);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
            overflow: hidden;
        }

        /* ── Animated background blobs ───────────────────────── */
        .bg-blob {
            position: fixed;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.18;
            pointer-events: none;
            z-index: 0;
        }
        .bg-blob-1 {
            width: 500px; height: 500px;
            background: var(--g500);
            top: -160px; right: -140px;
            animation: blobFloat 6s ease-in-out infinite alternate;
        }
        .bg-blob-2 {
            width: 380px; height: 380px;
            background: var(--g700);
            bottom: -120px; left: -100px;
            animation: blobFloat 8s ease-in-out infinite alternate-reverse;
        }
        @keyframes blobFloat {
            from { transform: translate(0, 0) scale(1); }
            to   { transform: translate(30px, 20px) scale(1.06); }
        }

        /* ── Card ────────────────────────────────────────────── */
        .card {
            position: relative; z-index: 1;
            background: var(--white);
            border: 1px solid var(--gr200);
            border-radius: 24px;
            padding: 52px 48px 40px;
            width: 100%;
            max-width: 560px;
            box-shadow: 0 12px 48px rgba(0, 0, 0, 0.09);
            animation: cardIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
        }
        @keyframes cardIn {
            from { opacity: 0; transform: translateY(28px) scale(0.97); }
            to   { opacity: 1; transform: translateY(0)    scale(1); }
        }

        /* ── Brand ───────────────────────────────────────────── */
        .brand {
            display: flex; align-items: center; gap: 12px;
            justify-content: center; margin-bottom: 32px;
        }
        .brand-mark {
            width: 48px; height: 48px; border-radius: 14px;
            background: linear-gradient(135deg, var(--g700), var(--g500));
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 6px 18px rgba(22, 163, 74, 0.35);
        }
        .brand-mark svg { width: 24px; height: 24px; fill: white; }
        .brand-name {
            font-size: 26px; font-weight: 800;
            letter-spacing: -0.5px; color: var(--gr900);
        }
        .brand-name em { font-style: normal; color: var(--g600); }

        /* ── Welcome heading ─────────────────────────────────── */
        .welcome-badge {
            display: inline-flex; align-items: center; gap: 6px;
            background: var(--g50); border: 1px solid var(--g200);
            border-radius: 20px; padding: 5px 14px;
            font-size: 12px; font-weight: 700; color: var(--g700);
            margin-bottom: 14px;
        }
        .welcome-badge .dot {
            width: 7px; height: 7px; border-radius: 50%;
            background: var(--g500);
            animation: pulse 1.4s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); opacity: 1; }
            50%       { transform: scale(1.35); opacity: 0.65; }
        }

        .welcome-heading {
            font-size: 26px; font-weight: 800;
            color: var(--gr900); letter-spacing: -0.5px;
            margin-bottom: 6px; text-align: center;
        }
        .welcome-heading span { color: var(--g600); }

        .welcome-sub {
            font-size: 14px; color: var(--gr500);
            text-align: center; margin-bottom: 32px; line-height: 1.6;
        }

        /* ── Tips ────────────────────────────────────────────── */
        .tips-list {
            display: flex; flex-direction: column; gap: 12px;
            margin-bottom: 36px;
        }
        .tip-item {
            display: flex; align-items: flex-start; gap: 14px;
            background: var(--g50); border: 1px solid var(--g200);
            border-radius: 14px; padding: 14px 18px;
            animation: tipIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) both;
        }
        .tip-item:nth-child(1) { animation-delay: 0.15s; }
        .tip-item:nth-child(2) { animation-delay: 0.30s; }
        .tip-item:nth-child(3) { animation-delay: 0.45s; }
        @keyframes tipIn {
            from { opacity: 0; transform: translateX(-14px); }
            to   { opacity: 1; transform: translateX(0); }
        }

        .tip-icon {
            font-size: 22px; flex-shrink: 0;
            width: 40px; height: 40px;
            background: var(--white); border: 1px solid var(--g200);
            border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 2px 6px rgba(22, 163, 74, 0.1);
        }
        .tip-text { flex: 1; }
        .tip-label {
            font-size: 11px; font-weight: 700;
            color: var(--g600); text-transform: uppercase;
            letter-spacing: 0.8px; margin-bottom: 3px;
        }
        .tip-body {
            font-size: 14px; font-weight: 500;
            color: var(--gr700); line-height: 1.5;
        }

        /* ── Progress bar ────────────────────────────────────── */
        .progress-wrap {
            display: flex; flex-direction: column; gap: 8px;
        }
        .progress-row {
            display: flex; align-items: center; justify-content: space-between;
            font-size: 12px; font-weight: 600; color: var(--gr400);
        }
        .progress-track {
            height: 6px; background: var(--gr200);
            border-radius: 10px; overflow: hidden;
        }
        .progress-fill {
            height: 100%; width: 0%;
            background: linear-gradient(90deg, var(--g500), var(--g700));
            border-radius: 10px;
            /* duration set by JS to match $delay_ms */
            transition: width <?= $delay_ms ?>ms linear;
        }

        /* ── Skip link ───────────────────────────────────────── */
        .skip-row {
            text-align: center; margin-top: 20px;
        }
        .skip-link {
            font-size: 13px; font-weight: 600;
            color: var(--gr400); text-decoration: none; cursor: pointer;
            background: none; border: none; font-family: inherit;
            transition: color 0.15s;
        }
        .skip-link:hover { color: var(--g600); }
    </style>
</head>
<body>

<!-- Background decorative blobs -->
<div class="bg-blob bg-blob-1"></div>
<div class="bg-blob bg-blob-2"></div>

<div class="card">

    <!-- Brand -->
    <div class="brand">
        <div class="brand-mark">
            <svg viewBox="0 0 24 24">
                <path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1-2.3A4.49 4.49 0 008 20C19 20 22 3 22 3c-1 2-8 2-13 6 1-2.17 2.64-4.41 8-5z"/>
            </svg>
        </div>
        <span class="brand-name">BATA<em>NOX</em></span>
    </div>

    <!-- Welcome heading -->
    <div style="text-align:center;">
        <div class="welcome-badge">
            <span class="dot"></span>
            Logged in successfully
        </div>
    </div>

    <div class="welcome-heading">
        Welcome back, <span><?= $user_name ?>!</span>
    </div>
    <div class="welcome-sub">
        Here are today's quick plant care tips before you start.
    </div>

    <!-- Tips -->
    <div class="tips-list">
        <div class="tip-item">
            <div class="tip-icon">🌱</div>
            <div class="tip-text">
                <div class="tip-label">Tip 1 · Watering</div>
                <div class="tip-body">Water plants early in the morning for better absorption and to reduce evaporation loss.</div>
            </div>
        </div>
        <div class="tip-item">
            <div class="tip-icon">🌿</div>
            <div class="tip-text">
                <div class="tip-label">Tip 2 · Disease Control</div>
                <div class="tip-body">Remove infected leaves immediately to prevent the disease from spreading to healthy parts.</div>
            </div>
        </div>
        <div class="tip-item">
            <div class="tip-icon">☀️</div>
            <div class="tip-text">
                <div class="tip-label">Tip 3 · Sunlight</div>
                <div class="tip-body">Ensure plants receive adequate sunlight every day — most crops need at least 6 hours of direct sun.</div>
            </div>
        </div>
    </div>

    <!-- Progress bar -->
    <div class="progress-wrap">
        <div class="progress-row">
            <span>Taking you to your dashboard…</span>
            <span id="countdown">2.8s</span>
        </div>
        <div class="progress-track">
            <div class="progress-fill" id="progressFill"></div>
        </div>
    </div>

    <!-- Skip -->
    <div class="skip-row">
        <button class="skip-link" onclick="goNow()">Skip → Go to Dashboard</button>
    </div>

</div>

<script>
(function () {
    var DELAY   = <?= $delay_ms ?>;
    var TARGET  = <?= json_encode($redirect) ?>;
    var timer;

    function goNow() {
        clearInterval(cdInterval);
        clearTimeout(timer);
        window.location.href = TARGET;
    }
    window.goNow = goNow;

    // Trigger progress bar fill (small delay so CSS transition runs)
    setTimeout(function () {
        document.getElementById("progressFill").style.width = "100%";
    }, 60);

    // Live countdown text
    var remaining = DELAY / 1000;
    var cdInterval = setInterval(function () {
        remaining -= 0.1;
        if (remaining <= 0) {
            clearInterval(cdInterval);
            document.getElementById("countdown").textContent = "0.0s";
        } else {
            document.getElementById("countdown").textContent = remaining.toFixed(1) + "s";
        }
    }, 100);

    // Auto-redirect
    timer = setTimeout(goNow, DELAY);
}());
</script>
</body>
</html>