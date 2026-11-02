SET client_min_messages = warning;

BEGIN;

CREATE TABLE IF NOT EXISTS product_detections (
    image_id    TEXT              NOT NULL,
    class_name  TEXT              NOT NULL,
    x_center    DOUBLE PRECISION  NOT NULL,
    y_center    DOUBLE PRECISION  NOT NULL,
    bbox_width  DOUBLE PRECISION  NOT NULL,
    bbox_height DOUBLE PRECISION  NOT NULL,
    synced_at   TIMESTAMP,
    model_id    VARCHAR(150),
    id          VARCHAR(64)
);

ALTER TABLE product_detections ADD COLUMN IF NOT EXISTS id        VARCHAR(64);
ALTER TABLE product_detections ADD COLUMN IF NOT EXISTS model_id  VARCHAR(150);
ALTER TABLE product_detections ADD COLUMN IF NOT EXISTS synced_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS data_dump_jobs (
    job_id          TEXT PRIMARY KEY,
    source_filename TEXT        NOT NULL,
    status          TEXT        NOT NULL,
    total_images    INTEGER     NOT NULL,
    error           TEXT,
    config_key      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);

ALTER TABLE data_dump_jobs ADD COLUMN IF NOT EXISTS config_key TEXT;

CREATE TABLE IF NOT EXISTS data_dump_items (
    job_id       TEXT        NOT NULL REFERENCES data_dump_jobs(job_id) ON DELETE CASCADE,
    image_id     TEXT        NOT NULL,
    image_url    TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'pending',
    reason       TEXT,
    rows_written INTEGER     NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, image_id)
);

CREATE INDEX IF NOT EXISTS data_dump_items_job_status_idx
    ON data_dump_items (job_id, status);

CREATE INDEX IF NOT EXISTS data_dump_items_activity_idx
    ON data_dump_items (updated_at DESC) WHERE status <> 'pending';

CREATE TABLE IF NOT EXISTS image_inference_runs (
    image_id     TEXT        NOT NULL,
    config_key   TEXT        NOT NULL,
    detections   INTEGER     NOT NULL DEFAULT 0,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (image_id, config_key)
);

CREATE TABLE IF NOT EXISTS model_registry (
    model_id             VARCHAR(150) PRIMARY KEY,
    config_key           VARCHAR(64)  NOT NULL UNIQUE,
    detection_model      TEXT,
    classification_model TEXT,
    use_sahi             BOOLEAN,
    detection_conf       DOUBLE PRECISION,
    classifier_threshold DOUBLE PRECISION,
    known_label_count    INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Model Versions dashboard. Metrics are fractions 0-1; NULL = not applicable.
CREATE TABLE IF NOT EXISTS model_versions (
    id                 BIGSERIAL PRIMARY KEY,
    model_name         VARCHAR(100) NOT NULL,
    model_type         VARCHAR(20)  NOT NULL
                       CHECK (model_type IN ('detection', 'classification')),
    version            VARCHAR(50)  NOT NULL,
    training_date      DATE,
    dataset_name       VARCHAR(200),
    map50              NUMERIC CHECK (map50     BETWEEN 0 AND 1),
    map50_95           NUMERIC CHECK (map50_95  BETWEEN 0 AND 1),
    accuracy           NUMERIC CHECK (accuracy  BETWEEN 0 AND 1),
    precision          NUMERIC CHECK (precision BETWEEN 0 AND 1),
    recall             NUMERIC CHECK (recall    BETWEEN 0 AND 1),
    f1_score           NUMERIC CHECK (f1_score  BETWEEN 0 AND 1),
    number_of_classes  INTEGER CHECK (number_of_classes >= 0),
    change_summary     TEXT,
    model_artifact_uri TEXT,
    notes              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (model_name, version)
);

COMMIT;

CREATE INDEX IF NOT EXISTS product_detections_image_id_idx
    ON product_detections (image_id);

CREATE UNIQUE INDEX IF NOT EXISTS product_detections_id_idx
    ON product_detections (id);

CREATE INDEX IF NOT EXISTS product_detections_unsynced_idx
    ON product_detections (id) WHERE synced_at IS NULL;
