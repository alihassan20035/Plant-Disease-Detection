-- ================================================================
-- BATANOX  ·  Complete Database Setup  (v3 — safe re-import)
-- How to use:
--   phpMyAdmin → Import → choose this file → Go
-- This script is safe to run multiple times (uses IF NOT EXISTS).
-- ================================================================

CREATE DATABASE IF NOT EXISTS `BATANOX`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `BATANOX`;

-- ================================================================
-- TABLE: users
-- ================================================================
CREATE TABLE IF NOT EXISTS `users` (
    `id`         INT(11)      NOT NULL AUTO_INCREMENT,
    `name`       VARCHAR(100) NOT NULL,
    `email`      VARCHAR(150) NOT NULL,
    `password`   VARCHAR(255) NOT NULL,
    `role`       ENUM('user','admin') NOT NULL DEFAULT 'user',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================================
-- TABLE: disease_records
-- (Replaces the old scan_history table)
-- ================================================================
CREATE TABLE IF NOT EXISTS `disease_records` (
    `id`             INT(11)      NOT NULL AUTO_INCREMENT,
    `user_id`        INT(11)      NOT NULL,
    `plant_name`     VARCHAR(150) NOT NULL DEFAULT '',
    `disease_name`   VARCHAR(255) NOT NULL DEFAULT '',
    `confidence`     DECIMAL(5,1) NOT NULL DEFAULT 0.0,
    `image_path`     VARCHAR(500) NOT NULL DEFAULT '',
    `result_path`    VARCHAR(500) NOT NULL DEFAULT '',
    `treatment`      TEXT                  DEFAULT NULL,
    `status`         ENUM('detected','in_progress','recovered')
                                  NOT NULL DEFAULT 'detected',
    `estimated_days` INT(4)                DEFAULT NULL,
    `next_reminder`  DATETIME              DEFAULT NULL,
    `reminder_note`  VARCHAR(255)          DEFAULT NULL,
    `scanned_at`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `fk_dr_user`
        FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_scanned` (`user_id`, `scanned_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================================
-- Migrate old scan_history rows into disease_records if that
-- table still exists from a previous version.
-- ================================================================
DROP PROCEDURE IF EXISTS `batanox_migrate`;
DELIMITER $$
CREATE PROCEDURE `batanox_migrate`()
BEGIN
    DECLARE tbl_exists INT DEFAULT 0;
    SELECT COUNT(*) INTO tbl_exists
    FROM   information_schema.tables
    WHERE  table_schema = DATABASE()
      AND  table_name   = 'scan_history';

    IF tbl_exists > 0 THEN
        INSERT IGNORE INTO disease_records
            (user_id, disease_name, image_path, result_path, scanned_at)
        SELECT user_id, disease_name, image_path, result_path, scanned_at
        FROM   scan_history;
    END IF;
END$$
DELIMITER ;
CALL `batanox_migrate`();
DROP PROCEDURE IF EXISTS `batanox_migrate`;

-- ================================================================
-- Demo admin account
-- Email:    admin@batanox.local
-- Password: admin123
-- ================================================================
INSERT IGNORE INTO `users` (`name`, `email`, `password`, `role`)
VALUES (
    'Admin',
    'admin@batanox.local',
    '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi',
    'admin'
);