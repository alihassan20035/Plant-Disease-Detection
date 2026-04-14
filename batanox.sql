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
-- TABLE: disease_profiles
-- Stores detailed disease information for the "About This Disease"
-- feature.  Keyed by a normalised slug (lowercase, spaces → underscores).
-- ================================================================
CREATE TABLE IF NOT EXISTS `disease_profiles` (
    `id`               INT(11)      NOT NULL AUTO_INCREMENT,
    `slug`             VARCHAR(120) NOT NULL COMMENT 'Normalised key used for lookups, e.g. early_blight',
    `common_name`      VARCHAR(255) NOT NULL COMMENT 'Human-readable disease name',
    `pathogen`         VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Scientific name of causal agent',
    `severity`         ENUM('Low','Moderate','Moderate–High','High','Critical')
                                    NOT NULL DEFAULT 'Moderate',
    `spread_method`    VARCHAR(255) NOT NULL DEFAULT '',
    `peak_season`      VARCHAR(255) NOT NULL DEFAULT '',
    `recovery_days`    INT(4)       NOT NULL DEFAULT 0,
    `description`      TEXT         NOT NULL,
    `treatments`       TEXT         NOT NULL COMMENT 'Pipe-separated treatment steps',
    `medicines`        TEXT         NOT NULL COMMENT 'JSON array of {name,type,price_usd,description}',
    `prevention_tips`  TEXT         NOT NULL COMMENT 'JSON array of {icon,title,tip}',
    `total_cost_usd`   VARCHAR(30)  NOT NULL DEFAULT '',
    `cost_note`        VARCHAR(500) NOT NULL DEFAULT '',
    `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_slug` (`slug`),
    FULLTEXT KEY `ft_name_desc` (`common_name`, `description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Disease knowledge base for the About This Disease feature';

-- ================================================================
-- TABLE: disease_medicines
-- Normalised medicine records linked to disease_profiles
-- ================================================================
CREATE TABLE IF NOT EXISTS `disease_medicines` (
    `id`             INT(11)      NOT NULL AUTO_INCREMENT,
    `disease_id`     INT(11)      NOT NULL,
    `medicine_name`  VARCHAR(255) NOT NULL,
    `medicine_type`  VARCHAR(120) NOT NULL DEFAULT '',
    `price_usd`      VARCHAR(60)  NOT NULL DEFAULT '',
    `description`    TEXT         NOT NULL,
    `sort_order`     TINYINT(3)   NOT NULL DEFAULT 0,
    PRIMARY KEY (`id`),
    CONSTRAINT `fk_dm_disease`
        FOREIGN KEY (`disease_id`) REFERENCES `disease_profiles`(`id`) ON DELETE CASCADE,
    INDEX `idx_dm_disease` (`disease_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================================
-- TABLE: disease_prevention_tips
-- Normalised prevention tips linked to disease_profiles
-- ================================================================
CREATE TABLE IF NOT EXISTS `disease_prevention_tips` (
    `id`          INT(11)      NOT NULL AUTO_INCREMENT,
    `disease_id`  INT(11)      NOT NULL,
    `icon`        VARCHAR(10)  NOT NULL DEFAULT '🌿',
    `title`       VARCHAR(120) NOT NULL,
    `tip`         TEXT         NOT NULL,
    `sort_order`  TINYINT(3)   NOT NULL DEFAULT 0,
    PRIMARY KEY (`id`),
    CONSTRAINT `fk_dpt_disease`
        FOREIGN KEY (`disease_id`) REFERENCES `disease_profiles`(`id`) ON DELETE CASCADE,
    INDEX `idx_dpt_disease` (`disease_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ================================================================
-- SEED DATA  — 12 disease profiles
-- Safe to re-run: INSERT IGNORE skips duplicates on the slug key.
-- ================================================================

-- ── 1. Tomato Leaf Mosaic Virus ───────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'tomato_leaf_mosaic_virus',
    'Tomato Leaf Mosaic Virus',
    'Tobamovirus (ToLMV)',
    'High',
    'Contact / Aphids / Infected tools',
    'Year-round (worse in warm humid conditions)',
    35,
    'Tomato Leaf Mosaic Virus (ToLMV) is a highly contagious viral pathogen belonging to the Tobamovirus genus. It causes characteristic mosaic or mottled patterns on leaves, stunted growth, and reduced fruit quality. The virus spreads primarily through infected plant debris, contaminated tools, and aphid vectors. Once a plant is infected, there is no chemical cure — management focuses on prevention, containment, and vector control.',
    'Remove and destroy all visibly infected plants immediately — do not compost|Control aphid populations using insecticidal soap or neem oil spray|Disinfect all pruning tools with 10% bleach solution between cuts|Apply mineral oil spray to reduce aphid transmission rates|Use reflective mulches to deter aphid landing on plants',
    '[{"name":"Imidacloprid (Admire Pro)","type":"Systemic Insecticide","price_usd":"$18–$35 / 8 oz","description":"Controls aphid vectors; apply as soil drench or foliar spray"},{"name":"Spinosad (Entrust SC)","type":"Bio-Insecticide","price_usd":"$28–$55 / pint","description":"Organic-certified aphid control; low mammalian toxicity"},{"name":"Neem Oil (70% Cold Pressed)","type":"Organic Repellent","price_usd":"$8–$15 / quart","description":"Disrupts aphid feeding; also has antifungal properties"},{"name":"Pyrethrin (PyGanic)","type":"Contact Insecticide","price_usd":"$22–$40 / quart","description":"Fast knockdown of aphid colonies; OMRI listed for organic use"}]',
    '[{"icon":"🌱","title":"Use Certified Seeds","tip":"Always source seeds from certified virus-free nurseries and seed suppliers"},{"icon":"🧤","title":"Sanitize Tools","tip":"Disinfect pruning shears with 70% alcohol or 10% bleach solution after each use"},{"icon":"🦗","title":"Monitor Aphids","tip":"Set up yellow sticky traps to monitor aphid populations weekly"},{"icon":"🪴","title":"Resistant Varieties","tip":"Select ToMV-resistant tomato varieties (look for Tm-2² resistance genes)"}]',
    '$45–$120',
    'Estimated total treatment cost including insecticides, removal labor, and preventive measures per 100 sq ft plot'
);

-- ── 2. Early Blight ───────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'early_blight',
    'Early Blight',
    'Alternaria solani',
    'Moderate–High',
    'Wind / Rain splash / Infected debris',
    'Mid-summer to fall; worse in humid conditions',
    21,
    'Early Blight, caused by Alternaria solani, is one of the most common foliar diseases of tomato and potato. It appears as dark concentric-ringed lesions (bullseye pattern) on older leaves first, gradually progressing up the plant. High humidity and temperatures between 24–29°C create ideal infection conditions. Spores survive in soil and infected plant debris for multiple seasons.',
    'Apply copper-based fungicide (copper hydroxide) every 7–10 days|Remove and dispose of infected lower leaves immediately|Avoid overhead watering; water at soil level in early morning|Improve plant spacing to enhance air circulation|Apply organic mulch to prevent soil splash onto lower leaves',
    '[{"name":"Copper Hydroxide (Kocide 3000)","type":"Copper Fungicide","price_usd":"$12–$25 / lb","description":"Broad-spectrum; apply preventively every 7–10 days in wet weather"},{"name":"Chlorothalonil (Daconil)","type":"Protectant Fungicide","price_usd":"$10–$22 / quart","description":"Prevents spore germination; apply before disease onset"},{"name":"Mancozeb (Dithane)","type":"Contact Fungicide","price_usd":"$8–$18 / lb","description":"Effective multi-site fungicide; use in rotation to prevent resistance"},{"name":"Azoxystrobin (Quadris)","type":"Systemic Fungicide","price_usd":"$30–$60 / quart","description":"Systemic protection; excellent curative and preventive activity"}]',
    '[{"icon":"💧","title":"Drip Irrigation","tip":"Use drip irrigation instead of overhead watering to keep foliage dry"},{"icon":"🌿","title":"Crop Rotation","tip":"Rotate tomatoes and potatoes with non-solanaceous crops every 2–3 years"},{"icon":"🍂","title":"Remove Debris","tip":"Clean up and destroy all plant debris at end of season to remove overwintering spores"},{"icon":"📏","title":"Proper Spacing","tip":"Space plants 18–24 inches apart to improve airflow and reduce humidity"}]',
    '$30–$80',
    'Estimated total treatment cost including fungicides and application supplies per season per 100 sq ft'
);

-- ── 3. Late Blight ────────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'late_blight',
    'Late Blight',
    'Phytophthora infestans',
    'Critical',
    'Wind-dispersed sporangia / Rain splash / Infected tubers',
    'Cool, wet weather (15–22°C, >90% humidity)',
    28,
    'Late Blight, caused by Phytophthora infestans, is one of the most devastating plant diseases worldwide — responsible for the Irish Potato Famine. It spreads with terrifying speed in cool, wet conditions, destroying entire crops within days. Water-soaked lesions on leaves rapidly turn brown and necrotic; white fuzzy sporulation is visible on the underside of infected leaves in humid conditions.',
    'Apply metalaxyl-based fungicide immediately upon first sign of infection|Remove and seal infected plant material in plastic bags before disposal|Never compost infected material — burn or bag for landfill|Apply preventive fungicide spray before forecasted cool, wet periods|Avoid overhead irrigation; keep foliage as dry as possible',
    '[{"name":"Metalaxyl-M (Ridomil Gold)","type":"Systemic Fungicide","price_usd":"$35–$70 / lb","description":"Gold standard for late blight; systemic action through plant tissue"},{"name":"Cymoxanil + Famoxadone (Tanos)","type":"Combination Fungicide","price_usd":"$28–$55 / lb","description":"Dual mode of action; excellent curative and preventive"},{"name":"Fluopicolide (Presidio)","type":"Systemic Fungicide","price_usd":"$45–$90 / pint","description":"Novel mode of action; use in rotation to manage resistance"},{"name":"Copper Octanoate (Cueva)","type":"Organic Copper","price_usd":"$14–$28 / quart","description":"Organically approved option; protective (not curative) activity"}]',
    '[{"icon":"🌦️","title":"Monitor Weather","tip":"Use blight forecasting tools (BlightPro) to anticipate high-risk periods"},{"icon":"🧬","title":"Resistant Varieties","tip":"Plant late blight-resistant varieties such as Defiant PhR or Mountain Magic"},{"icon":"🥔","title":"Certified Seed Tubers","tip":"Use only certified disease-free potato seed; inspect tubers before planting"},{"icon":"🚿","title":"Avoid Wet Foliage","tip":"Never leave foliage wet overnight; improve drainage around plants"}]',
    '$60–$150',
    'Estimated total cost including emergency fungicide application and potential replanting per 100 sq ft'
);

-- ── 4. Powdery Mildew ─────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'powdery_mildew',
    'Powdery Mildew',
    'Erysiphales spp.',
    'Moderate',
    'Airborne conidia / Wind',
    'Late spring through fall; dry warm days, cool nights',
    14,
    'Powdery Mildew is a widespread fungal disease caused by various Erysiphales species, recognizable by its distinctive white to grayish powdery coating on leaf surfaces. Unlike most fungi, it thrives in warm, dry conditions with low humidity and does not require free water on leaves for infection. It can affect hundreds of plant species and spreads rapidly through airborne conidia.',
    'Apply sulfur-based fungicide or potassium bicarbonate spray at first sign|Use baking soda solution (1 tbsp per gallon water + dish soap) for organic control|Prune and remove heavily infected leaves and stems|Improve air circulation by opening up the plant canopy|Apply neem oil as both a preventive and mild curative treatment',
    '[{"name":"Sulfur Dust (Bonide)","type":"Protectant Fungicide","price_usd":"$6–$14 / 4 lb","description":"Highly effective preventive; do not apply when temp >90°F"},{"name":"Potassium Bicarbonate (Milstop)","type":"Organic Fungicide","price_usd":"$15–$30 / lb","description":"OMRI-listed; curative activity by disrupting pH on leaf surface"},{"name":"Myclobutanil (Eagle 20EW)","type":"Systemic DMI Fungicide","price_usd":"$18–$35 / 8 oz","description":"Excellent systemic curative; rotate with other modes of action"},{"name":"Tebuconazole (Spectracide Immunox)","type":"Triazole Fungicide","price_usd":"$12–$22 / pint","description":"Broad-spectrum; curative and preventive against powdery mildew"}]',
    '[{"icon":"✂️","title":"Prune for Airflow","tip":"Prune plants to open the canopy and reduce humidity in the leaf zone"},{"icon":"☀️","title":"Sunlight Exposure","tip":"Plant in full sun locations; powdery mildew is suppressed by UV light"},{"icon":"🌿","title":"Resistant Cultivars","tip":"Choose mildew-resistant cultivars — most modern varieties have improved resistance"},{"icon":"🚫","title":"Avoid Excess Nitrogen","tip":"Do not over-fertilize with nitrogen — it produces lush growth susceptible to infection"}]',
    '$20–$60',
    'Estimated total treatment cost for a typical home garden or small plot over one season'
);

-- ── 5. Leaf Spot ──────────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'leaf_spot',
    'Leaf Spot',
    'Septoria lycopersici / Cercospora spp. / Alternaria spp.',
    'Moderate',
    'Rain splash / Wind / Contaminated tools',
    'Warm, humid conditions throughout growing season',
    21,
    'Leaf Spot diseases encompass a broad group of fungal and bacterial infections that produce distinct circular to irregular spots on leaves, typically with defined margins. Common causal agents include Septoria lycopersici, Cercospora spp., and Alternaria spp. Infected spots often show a tan or brown center with a darker border, and in advanced stages affected leaves yellow and drop prematurely, weakening the plant.',
    'Apply mancozeb or chlorothalonil fungicide at first symptom appearance|Remove and destroy all infected leaves to reduce spore reservoir|Avoid wetting foliage during irrigation; use drip systems|Improve airflow by proper plant spacing and pruning|Apply preventive copper-based spray during high-humidity periods',
    '[{"name":"Chlorothalonil (Bravo 720)","type":"Protectant Fungicide","price_usd":"$10–$22 / quart","description":"Multi-site fungicide; apply preventively; excellent spectrum of activity"},{"name":"Mancozeb (Dithane M-45)","type":"Contact Fungicide","price_usd":"$8–$18 / lb","description":"Broad-spectrum protectant; effective against many Cercospora species"},{"name":"Propiconazole (Banner Maxx)","type":"Systemic Fungicide","price_usd":"$22–$45 / quart","description":"Systemic DMI fungicide; curative and preventive action"},{"name":"Copper Hydroxide (Kocide)","type":"Copper Bactericide/Fungicide","price_usd":"$12–$25 / lb","description":"Effective against bacterial leaf spot; apply during wet weather"}]',
    '[{"icon":"🌧️","title":"Avoid Leaf Wetness","tip":"Water at the base of plants; avoid wetting foliage, especially in evenings"},{"icon":"🔄","title":"Rotate Crops","tip":"Practice 2–3 year crop rotation to reduce pathogen buildup in soil"},{"icon":"🧹","title":"Garden Sanitation","tip":"Remove and destroy infected plant debris at end of each growing season"},{"icon":"📊","title":"Monitor Regularly","tip":"Scout plants weekly; early detection dramatically improves treatment success"}]',
    '$25–$70',
    'Estimated total treatment cost for fungicide applications over one growing season per 100 sq ft'
);

-- ── 6. Common Rust ────────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'common_rust',
    'Common Rust',
    'Puccinia sorghi / Phragmidium spp.',
    'Moderate–High',
    'Wind-dispersed urediniospores',
    'Cool, humid conditions (16–23°C with high humidity)',
    18,
    'Common Rust, caused by Puccinia sorghi on corn and Phragmidium spp. on roses, presents as brick-red to orange-brown pustules on leaf surfaces that release powdery spores when ruptured. The disease can cause significant yield losses in susceptible crops and spreads rapidly under cool, moist conditions. Severe infections cause premature leaf death and weaken the overall plant structure.',
    'Apply triazole fungicide (propiconazole, tebuconazole) at first pustule appearance|Remove heavily infected leaves to reduce local spore load|Apply fungicide preventively when conditions favor rust development|Use strobilurin fungicides for excellent protective and curative activity|Ensure good plant nutrition — potassium deficiency increases rust severity',
    '[{"name":"Propiconazole (Tilt)","type":"Triazole Fungicide","price_usd":"$20–$40 / pint","description":"Excellent systemic activity against rusts; curative and preventive"},{"name":"Pyraclostrobin (Headline)","type":"Strobilurin Fungicide","price_usd":"$35–$65 / quart","description":"Broad-spectrum systemic; also improves plant health"},{"name":"Tebuconazole (Folicur)","type":"DMI Fungicide","price_usd":"$25–$50 / pint","description":"Highly effective against rust pathogens; systemic uptake"},{"name":"Sulfur (Bonide Sulfur)","type":"Protective Fungicide","price_usd":"$6–$14 / 4 lb","description":"Organic option; preventive only; reapply after rain"}]',
    '[{"icon":"🌽","title":"Resistant Hybrids","tip":"Select rust-resistant corn hybrids or rose cultivars for your region"},{"icon":"📅","title":"Early Planting","tip":"Plant early in the season to allow crops to develop before peak rust pressure"},{"icon":"🌬️","title":"Improve Airflow","tip":"Adequate plant spacing promotes air circulation and reduces leaf moisture"},{"icon":"🔭","title":"Scout Weekly","tip":"Begin scouting for rust pustules from mid-season; early detection is key"}]',
    '$35–$90',
    'Estimated total treatment cost per season including fungicide applications and labor'
);

-- ── 7. Bacterial Spot ─────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'bacterial_spot',
    'Bacterial Spot',
    'Xanthomonas vesicatoria / X. euvesicatoria',
    'Moderate–High',
    'Rain splash / Wind / Infected seed / Contaminated tools',
    'Warm, wet weather (>24°C); rainy periods',
    20,
    'Bacterial Spot, caused by Xanthomonas spp., affects tomato, pepper, and other crops producing small, water-soaked lesions that turn brown with yellow halos. Warm, wet weather accelerates spread dramatically. Severe infections defoliate plants and reduce fruit quality, making the disease one of the most economically important bacterial diseases of vegetable crops worldwide.',
    'Apply copper-based bactericide at first symptom appearance|Avoid overhead irrigation; use drip systems to keep foliage dry|Remove and destroy heavily infected plant material|Apply copper + mancozeb mixture for enhanced effectiveness|Reduce plant density to improve air circulation',
    '[{"name":"Copper Hydroxide (Kocide 3000)","type":"Copper Bactericide","price_usd":"$12–$25 / lb","description":"Primary bactericide for bacterial spot; apply preventively"},{"name":"Copper Sulfate + Lime (Bordeaux)","type":"Classic Copper Mix","price_usd":"$8–$16 / lb","description":"Traditional broad-spectrum copper formulation"},{"name":"Kasugamycin (Kasumin)","type":"Antibiotic Bactericide","price_usd":"$40–$80 / quart","description":"Antibiotic bactericide; restricted use in some regions"},{"name":"Acibenzolar-S-methyl (Actigard)","type":"SAR Inducer","price_usd":"$30–$60 / 10 oz","description":"Induces systemic acquired resistance in the plant"}]',
    '[{"icon":"🌱","title":"Certified Seed","tip":"Use pathogen-free certified seed; hot-water seed treatment reduces risk"},{"icon":"💧","title":"Avoid Wetting Leaves","tip":"Use drip irrigation; do not work in plants when foliage is wet"},{"icon":"🛡️","title":"Copper Sprays","tip":"Apply preventive copper sprays before rainy forecasts"},{"icon":"🧬","title":"Resistant Varieties","tip":"Select bacterial spot-resistant tomato or pepper varieties"}]',
    '$30–$85',
    'Estimated total treatment cost per season per 100 sq ft'
);

-- ── 8. Septoria Leaf Spot ─────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'septoria',
    'Septoria Leaf Spot',
    'Septoria lycopersici',
    'Moderate–High',
    'Rain splash / Wind / Contaminated tools / Soil',
    'Warm, humid conditions; especially after fruit set',
    18,
    'Septoria Leaf Spot is a common and destructive fungal disease of tomatoes. It appears as numerous small, circular spots with dark borders and lighter tan centers containing tiny black pycnidia. The disease progresses upward from older leaves and can cause complete defoliation if left untreated, severely reducing fruit production and quality.',
    'Apply chlorothalonil or propiconazole at first sign of symptoms|Remove infected lower leaves and dispose of immediately|Mulch around plants to prevent soil splash onto lower leaves|Stake plants to improve air circulation|Rotate fungicides to prevent resistance development',
    '[{"name":"Chlorothalonil (Daconil)","type":"Protectant Fungicide","price_usd":"$10–$22 / quart","description":"Highly effective against Septoria; apply every 7–10 days"},{"name":"Propiconazole (Tilt)","type":"Systemic Fungicide","price_usd":"$20–$40 / pint","description":"Systemic curative and preventive; excellent Septoria control"},{"name":"Mancozeb (Dithane)","type":"Contact Fungicide","price_usd":"$8–$18 / lb","description":"Broad-spectrum protectant; use in rotation programs"},{"name":"Copper Hydroxide (Kocide)","type":"Copper Fungicide","price_usd":"$12–$25 / lb","description":"Effective copper option; apply during wet weather"}]',
    '[{"icon":"🔄","title":"Crop Rotation","tip":"Do not grow tomatoes in the same location for 2+ consecutive years"},{"icon":"🌿","title":"Stake and Prune","tip":"Stake plants upright and remove suckers to maximize airflow"},{"icon":"🍂","title":"Bury Debris","tip":"Till or bury crop residue deeply after harvest to destroy spores"},{"icon":"🧬","title":"Resistant Varieties","tip":"Some modern hybrids have improved tolerance to Septoria"}]',
    '$25–$65',
    'Estimated total treatment cost per growing season per 100 sq ft'
);

-- ── 9. Apple Scab ─────────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'scab',
    'Apple Scab',
    'Venturia inaequalis',
    'High',
    'Wind / Rain-dispersed ascospores from infected leaf litter',
    'Spring and early summer during wet, cool weather',
    30,
    'Apple Scab, caused by Venturia inaequalis, is a destructive fungal disease of apples and pears causing olive-green to dark brown scab-like lesions on leaves and fruit. Spores overwinter in fallen leaves and are released during wet spring weather. Infected fruit is unmarketable and heavily infected trees may defoliate, significantly reducing the following year\'s crop.',
    'Apply captan or myclobutanil fungicide starting at green tip bud stage|Maintain spray schedule every 7–14 days during wet spring weather|Prune trees to open canopy and improve air circulation|Rake and destroy fallen leaves to remove overwintering spores|Apply urea to fallen leaves in autumn to accelerate decomposition',
    '[{"name":"Captan 50WP","type":"Protectant Fungicide","price_usd":"$15–$30 / lb","description":"Excellent broad-spectrum protectant; apply before rain events"},{"name":"Myclobutanil (Rally 40WSP)","type":"Systemic DMI Fungicide","price_usd":"$25–$50 / lb","description":"Systemic curative; effective up to 96hr post-infection"},{"name":"Lime Sulfur","type":"Dormant/Early Season","price_usd":"$10–$20 / quart","description":"Apply at silver tip to delayed dormant; kills overwintering spores"},{"name":"Sulfur (Wettable Sulfur)","type":"Protectant Fungicide","price_usd":"$6–$14 / 4 lb","description":"Organic option; protective activity; safe for bees post-dry"}]',
    '[{"icon":"🍎","title":"Resistant Varieties","tip":"Plant scab-resistant apple varieties such as Liberty, Freedom, or Enterprise"},{"icon":"🍂","title":"Rake Leaves","tip":"Collect and destroy fallen leaves each autumn — this is the single most important control measure"},{"icon":"✂️","title":"Prune Annually","tip":"Annual dormant pruning improves light and airflow through the canopy"},{"icon":"📅","title":"Time Sprays","tip":"Use a disease prediction model (RIMpro) to time fungicide applications correctly"}]',
    '$40–$110',
    'Estimated annual treatment cost per tree including fungicides, pruning, and debris management'
);

-- ── 10. Black Rot ─────────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'black_rot',
    'Black Rot',
    'Guignardia bidwellii',
    'High',
    'Rain-dispersed conidia / Wind / Infected mummified berries',
    'Spring through summer; peak infection during bloom to 3 weeks post-bloom',
    25,
    'Black Rot, caused by Guignardia bidwellii on grapes, produces wedge-shaped brown lesions on leaves with tiny black pycnidia visible under magnification, and causes infected berries to shrivel into hard black mummies. It is one of the most economically damaging grape diseases in humid growing regions and can destroy an entire crop in a single season if not managed proactively.',
    'Apply myclobutanil or mancozeb starting at bud break|Remove and destroy all mummified berries and infected canes|Maintain rigorous spray schedule (every 7–10 days) during wet periods|Improve canopy management to enhance air circulation|Apply captan as a broad-spectrum supplemental fungicide',
    '[{"name":"Myclobutanil (Rally)","type":"DMI Fungicide","price_usd":"$25–$50 / lb","description":"Excellent systemic curative and preventive against black rot"},{"name":"Mancozeb (Dithane)","type":"Contact Fungicide","price_usd":"$8–$18 / lb","description":"Broad-spectrum protectant; use in rotation programs"},{"name":"Captan 50WP","type":"Protectant Fungicide","price_usd":"$15–$30 / lb","description":"Excellent protectant; apply before rain events"},{"name":"Tebuconazole (Elite)","type":"Triazole Fungicide","price_usd":"$25–$50 / pint","description":"Strong curative activity; apply within 96hr of infection"}]',
    '[{"icon":"🍇","title":"Remove Mummies","tip":"Pick and destroy all mummified berries before the new growing season"},{"icon":"✂️","title":"Prune Canes","tip":"Remove and burn infected canes during dormant pruning"},{"icon":"🌬️","title":"Canopy Management","tip":"Shoot positioning and leaf removal improve airflow and spray penetration"},{"icon":"📅","title":"Early Season Timing","tip":"Critical spray window is from bud break through 3 weeks after bloom"}]',
    '$45–$120',
    'Estimated total annual treatment cost per 100 sq ft vineyard block'
);

-- ── 11. Rice Blast ────────────────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'blast',
    'Rice Blast',
    'Magnaporthe oryzae',
    'Critical',
    'Wind-dispersed conidia / Infected seed / Water splash',
    'Humid conditions; especially with cool nights (20–22°C) and warm days',
    21,
    'Rice Blast, caused by Magnaporthe oryzae, is the most destructive rice disease worldwide, capable of destroying entire crops in weeks. It causes diamond-shaped gray lesions on leaves, and in severe cases infects the neck node, causing neck rot that prevents grain filling. The disease is favored by cool nights, high humidity, and excess nitrogen fertilization.',
    'Apply tricyclazole or isoprothiolane fungicide at first symptom|Use azoxystrobin at heading stage to prevent neck blast|Reduce nitrogen fertilizer rates — excess nitrogen dramatically increases susceptibility|Ensure proper water management (avoid deep flooding during susceptible stages)|Use silicon fertilizer amendments to strengthen plant cell walls',
    '[{"name":"Tricyclazole (Beam)","type":"Melanin Biosynthesis Inhibitor","price_usd":"$25–$50 / lb","description":"Highly specific to Magnaporthe; excellent curative activity"},{"name":"Isoprothiolane (Fuji-one)","type":"Systemic Fungicide","price_usd":"$20–$40 / liter","description":"Systemic activity; also controls brown planthopper"},{"name":"Azoxystrobin (Amistar)","type":"Strobilurin Fungicide","price_usd":"$30–$60 / quart","description":"Excellent for neck blast prevention at heading; broad-spectrum"},{"name":"Propiconazole (Tilt)","type":"Triazole Fungicide","price_usd":"$20–$40 / pint","description":"Effective curative; use in combination products for best results"}]',
    '[{"icon":"🌾","title":"Resistant Varieties","tip":"Plant blast-resistant rice varieties — this is the most cost-effective control measure"},{"icon":"🧪","title":"Balanced Nitrogen","tip":"Split nitrogen applications; avoid heavy doses during susceptible growth stages"},{"icon":"💧","title":"Field Drainage","tip":"Periodic drainage reduces leaf wetness duration and infection risk"},{"icon":"🌱","title":"Seed Treatment","tip":"Treat seeds with thiram or carbendazim before planting to prevent seedling blast"}]',
    '$30–$80',
    'Estimated total treatment cost per season per 100 sq meter paddy'
);

-- ── 12. Mosaic Virus (generic) ────────────────────────────────────────────────
INSERT IGNORE INTO `disease_profiles`
    (slug, common_name, pathogen, severity, spread_method, peak_season,
     recovery_days, description, treatments, medicines, prevention_tips,
     total_cost_usd, cost_note)
VALUES (
    'mosaic',
    'Mosaic Virus',
    'TMV / CMV / WMV (various Potyviruses)',
    'High',
    'Aphid vectors / Mechanical contact / Contaminated tools',
    'Year-round; peak in spring and summer when aphid populations are high',
    35,
    'Mosaic viruses (including TMV, CMV, and WMV) cause light and dark green mottling on leaves, leaf curling, stunted growth, and distorted fruit. There is no chemical cure — management centers on vector control, rigorous sanitation, and the use of resistant varieties. Early removal of infected plants is the single most important management step.',
    'Remove and destroy infected plants to prevent spread to healthy plants|Control aphid vectors with insecticidal soap, neem oil, or systemic insecticides|Disinfect all tools with 10% bleach solution or 70% isopropyl alcohol|Apply reflective silver mulch to confuse and deter aphids|Weed control is critical — many weeds serve as virus reservoirs',
    '[{"name":"Imidacloprid (Admire Pro)","type":"Systemic Insecticide","price_usd":"$18–$35 / 8 oz","description":"Systemic aphid control; soil or foliar application"},{"name":"Insecticidal Soap (Safer Brand)","type":"Contact Insecticide","price_usd":"$8–$14 / quart","description":"Organic; kills soft-bodied insects on contact"},{"name":"Pyrethrin (PyGanic)","type":"Contact Insecticide","price_usd":"$22–$40 / quart","description":"Fast-acting organic knockdown of aphid colonies"},{"name":"Mineral Oil Spray","type":"Vector Suppression","price_usd":"$6–$12 / quart","description":"Disrupts aphid probing and virus transmission"}]',
    '[{"icon":"🌱","title":"Certified Seeds","tip":"Always use certified virus-free seeds from reputable sources"},{"icon":"🪞","title":"Reflective Mulch","tip":"Silver reflective mulch disorients aphids and dramatically reduces landings"},{"icon":"🌿","title":"Weed Management","tip":"Remove weeds that serve as virus reservoirs around the growing area"},{"icon":"🧬","title":"Resistant Varieties","tip":"Select varieties with TMV/CMV resistance ratings for your crop"}]',
    '$40–$100',
    'Estimated total cost including vector control and preventive measures per 100 sq ft'
);

-- ================================================================
-- SEED: Normalised disease_medicines rows
-- Inserted in a second pass after disease_profiles are created.
-- ================================================================
DROP PROCEDURE IF EXISTS `batanox_seed_medicines`;
DELIMITER $$
CREATE PROCEDURE `batanox_seed_medicines`()
BEGIN
    DECLARE done   INT DEFAULT FALSE;
    DECLARE dis_id INT;
    DECLARE slug_v VARCHAR(120);

    -- Cursor over all slugs we just inserted
    DECLARE cur CURSOR FOR
        SELECT id, slug FROM disease_profiles;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO dis_id, slug_v;
        IF done THEN LEAVE read_loop; END IF;

        -- Skip if medicines already seeded for this disease
        IF (SELECT COUNT(*) FROM disease_medicines WHERE disease_id = dis_id) = 0 THEN
            -- Parse and insert medicines from the JSON column
            -- (requires MySQL 5.7+ JSON functions)
            IF (SELECT JSON_VALID(medicines) FROM disease_profiles WHERE id = dis_id) = 1 THEN
                SET @j = (SELECT medicines FROM disease_profiles WHERE id = dis_id);
                SET @cnt = JSON_LENGTH(@j);
                SET @i = 0;
                WHILE @i < @cnt DO
                    INSERT INTO disease_medicines
                        (disease_id, medicine_name, medicine_type, price_usd, description, sort_order)
                    VALUES (
                        dis_id,
                        JSON_UNQUOTE(JSON_EXTRACT(@j, CONCAT('$[', @i, '].name'))),
                        JSON_UNQUOTE(JSON_EXTRACT(@j, CONCAT('$[', @i, '].type'))),
                        JSON_UNQUOTE(JSON_EXTRACT(@j, CONCAT('$[', @i, '].price_usd'))),
                        JSON_UNQUOTE(JSON_EXTRACT(@j, CONCAT('$[', @i, '].description'))),
                        @i
                    );
                    SET @i = @i + 1;
                END WHILE;
            END IF;
        END IF;

        -- Skip if prevention tips already seeded
        IF (SELECT COUNT(*) FROM disease_prevention_tips WHERE disease_id = dis_id) = 0 THEN
            IF (SELECT JSON_VALID(prevention_tips) FROM disease_profiles WHERE id = dis_id) = 1 THEN
                SET @j2 = (SELECT prevention_tips FROM disease_profiles WHERE id = dis_id);
                SET @cnt2 = JSON_LENGTH(@j2);
                SET @i2 = 0;
                WHILE @i2 < @cnt2 DO
                    INSERT INTO disease_prevention_tips
                        (disease_id, icon, title, tip, sort_order)
                    VALUES (
                        dis_id,
                        JSON_UNQUOTE(JSON_EXTRACT(@j2, CONCAT('$[', @i2, '].icon'))),
                        JSON_UNQUOTE(JSON_EXTRACT(@j2, CONCAT('$[', @i2, '].title'))),
                        JSON_UNQUOTE(JSON_EXTRACT(@j2, CONCAT('$[', @i2, '].tip'))),
                        @i2
                    );
                    SET @i2 = @i2 + 1;
                END WHILE;
            END IF;
        END IF;

    END LOOP;
    CLOSE cur;
END$$
DELIMITER ;
CALL `batanox_seed_medicines`();
DROP PROCEDURE IF EXISTS `batanox_seed_medicines`;

-- ================================================================
-- HELPER VIEW: disease_full_view
-- Joins disease_profiles with its normalised child rows so the admin
-- panel (or a future API endpoint) can query everything in one go.
-- ================================================================
CREATE OR REPLACE VIEW `disease_full_view` AS
SELECT
    p.id,
    p.slug,
    p.common_name,
    p.pathogen,
    p.severity,
    p.spread_method,
    p.peak_season,
    p.recovery_days,
    p.description,
    p.total_cost_usd,
    p.cost_note,
    GROUP_CONCAT(DISTINCT CONCAT(m.sort_order, '||', m.medicine_name, '||', m.medicine_type, '||', m.price_usd)
                 ORDER BY m.sort_order SEPARATOR ';;') AS medicines_flat,
    GROUP_CONCAT(DISTINCT CONCAT(t.sort_order, '||', t.icon, '||', t.title, '||', t.tip)
                 ORDER BY t.sort_order SEPARATOR ';;') AS tips_flat
FROM   disease_profiles p
LEFT JOIN disease_medicines       m ON m.disease_id = p.id
LEFT JOIN disease_prevention_tips t ON t.disease_id = p.id
GROUP BY p.id;

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