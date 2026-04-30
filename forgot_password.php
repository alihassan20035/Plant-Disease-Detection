<?php
use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

session_start();
require_once __DIR__ . '/db_config.php';
require_once __DIR__ . '/vendor/autoload.php';

define('MAIL_HOST',      'smtp.gmail.com');
define('MAIL_PORT',      587);
define('MAIL_USERNAME',  'sm.alihassan.shah@gmail.com');
define('MAIL_PASSWORD',  'zqhm qyis vnls bqou');
define('MAIL_FROM',      'sm.alihassan.shah@gmail.com');
define('MAIL_FROM_NAME', 'BATANOX');
define('APP_URL',        'http://localhost/batanox');

$message = '';
$msgType = '';

try {
    $pdo->exec("CREATE TABLE IF NOT EXISTS password_resets (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        email      VARCHAR(255) NOT NULL,
        token      VARCHAR(64)  NOT NULL,
        expires_at DATETIME     NOT NULL,
        used       TINYINT(1)   DEFAULT 0,
        created_at DATETIME     DEFAULT CURRENT_TIMESTAMP
    )");
} catch (PDOException $e) {}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $email = trim($_POST['email'] ?? '');

    if ($email === '') {
        $message = 'Please enter your email address.';
        $msgType = 'error';
    } else {
        $stmt = $pdo->prepare("SELECT id, name FROM users WHERE email = ? LIMIT 1");
        $stmt->execute([$email]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        $message = 'If this email is registered, you will receive a password reset link shortly.';
        $msgType = 'success';

        if ($user) {
            $token     = bin2hex(random_bytes(32));
          $stmt2 = $pdo->query("SELECT DATE_ADD(NOW(), INTERVAL 1 HOUR) as exp");
          $expiresAt = $stmt2->fetch()['exp'];

            $pdo->prepare("DELETE FROM password_resets WHERE email = ?")->execute([$email]);
            $pdo->prepare("INSERT INTO password_resets (email, token, expires_at) VALUES (?, ?, ?)")
                ->execute([$email, $token, $expiresAt]);

            $resetLink = APP_URL . '/reset_password.php?token=' . $token;

            try {
                $mail = new PHPMailer(true);
                $mail->isSMTP();
                $mail->Host       = MAIL_HOST;
                $mail->SMTPAuth   = true;
                $mail->Username   = MAIL_USERNAME;
                $mail->Password   = MAIL_PASSWORD;
                $mail->SMTPSecure = PHPMailer::ENCRYPTION_STARTTLS;
                $mail->Port       = MAIL_PORT;

                $mail->setFrom(MAIL_FROM, MAIL_FROM_NAME);
                $mail->addAddress($email, $user['name']);
                $mail->isHTML(true);
                $mail->Subject = 'BATANOX - Reset Your Password';
                $mail->Body    = "
                <div style='font-family:sans-serif;max-width:480px;margin:auto;padding:32px;'>
                    <h2 style='color:#15803d;'>BATANOX Password Reset</h2>
                    <p>Hello <strong>" . htmlspecialchars($user['name']) . "</strong>,</p>
                    <p>We received a request to reset your password. Click the button below:</p>
                    <p style='margin:28px 0;'>
                        <a href='" . $resetLink . "'
                           style='background:#16a34a;color:white;padding:12px 28px;
                                  border-radius:8px;text-decoration:none;font-weight:bold;'>
                            Reset My Password
                        </a>
                    </p>
                    <p style='color:#6b7280;font-size:13px;'>
                        This link expires in <strong>1 hour</strong>.<br>
                        If you did not request this, ignore this email.
                    </p>
                    <hr style='border:none;border-top:1px solid #e5e7eb;margin:24px 0;'>
                    <p style='color:#9ca3af;font-size:12px;'>BATANOX Plant Management System</p>
                </div>";
                $mail->AltBody = "Reset your password: " . $resetLink . " (expires in 1 hour)";
                $mail->send();
            } catch (Exception $ex) {
                error_log('Mailer Error: ' . $ex->getMessage());
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
    <title>Forgot Password - BATANOX</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --g500:#22c55e; --g600:#16a34a; --g700:#15803d;
            --white:#ffffff;
            --gr50:#f9fafb; --gr200:#e5e7eb; --gr300:#d1d5db;
            --gr400:#9ca3af; --gr500:#6b7280; --gr700:#374151; --gr900:#111827;
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
        .brand {
            display: flex; align-items: center; gap: 10px;
            justify-content: center; margin-bottom: 32px;
        }
        .brand-name { font-size: 24px; font-weight: 800; letter-spacing: -0.5px; color: var(--gr900); }
        .brand-name em { font-style: normal; color: var(--g600); }
        .icon-wrap {
            width: 56px; height: 56px; border-radius: 16px;
            background: #f0fdf4; border: 1px solid #bbf7d0;
            display: flex; align-items: center; justify-content: center;
            font-size: 26px; margin: 0 auto 20px;
        }
        .heading { font-size: 22px; font-weight: 800; color: var(--gr900); text-align: center; margin-bottom: 8px; }
        .sub { font-size: 14px; color: var(--gr500); text-align: center; margin-bottom: 28px; line-height: 1.6; }
        .field { margin-bottom: 18px; }
        .field label { display: block; font-size: 13px; font-weight: 600; color: var(--gr700); margin-bottom: 7px; }
        .field input {
            width: 100%; padding: 12px 16px;
            border: 1.5px solid var(--gr300); border-radius: 10px;
            font-family: inherit; font-size: 14px; color: var(--gr900); outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .field input:focus { border-color: var(--g500); box-shadow: 0 0 0 3px rgba(34,197,94,0.12); }
        .field input::placeholder { color: var(--gr400); }
        .msg-box {
            border-radius: 10px; padding: 12px 16px; font-size: 13px; font-weight: 500;
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
        .btn-submit:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(34,197,94,0.42); }
        .foot { margin-top: 22px; text-align: center; font-size: 13px; color: var(--gr500); }
        .foot a { color: var(--g600); font-weight: 700; text-decoration: none; }
        .foot a:hover { text-decoration: underline; }
    </style>
</head>
<body>
<div class="card">

    <div class="brand">
        <img src="templates/app logo 01.png" alt="" width="40" height="50">
        <span class="brand-name">BATA<em>NOX</em></span>
    </div>

    <div class="icon-wrap">&#128273;</div>
    <div class="heading">Forgot Password?</div>
    <div class="sub">Enter your email and we'll send you a link to reset your password.</div>

    <?php if ($message !== ''): ?>
    <div class="msg-box <?php echo $msgType; ?>">
        <span><?php echo ($msgType === 'success') ? '&#9989;' : '&#9888;'; ?></span>
        <span><?php echo htmlspecialchars($message); ?></span>
    </div>
    <?php endif; ?>

    <?php if ($msgType !== 'success'): ?>
    <form method="POST" action="">
        <div class="field">
            <label for="email">Email address</label>
            <input type="email" id="email" name="email"
                   placeholder="you@example.com"
                   value="<?php echo htmlspecialchars($_POST['email'] ?? ''); ?>"
                   required autocomplete="email">
        </div>
        <button type="submit" class="btn-submit">Send Reset Link &rarr;</button>
    </form>
    <?php endif; ?>

    <div class="foot">
        Remember your password? <a href="login.php">Back to Login</a>
    </div>

</div>
</body>
</html>