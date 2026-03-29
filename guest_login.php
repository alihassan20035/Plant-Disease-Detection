<?php
/**
 * BATANOX — Guest Login Entry Point
 * File: batanox/guest_login.php
 *
 * Sets a guest session flag and redirects to the Flask guest detection page.
 * Place this file at: C:\wamp64\www\batanox\guest_login.php
 */

session_start();

// Mark session as guest so Flask auth_check.php returns {"guest": true}
$_SESSION['user_id']  = 0;
$_SESSION['role']     = 'guest';
$_SESSION['name']     = 'Guest';
$_SESSION['is_guest'] = true;

// Redirect to Flask guest page
header('Location: http://localhost:5000/guest');
exit;