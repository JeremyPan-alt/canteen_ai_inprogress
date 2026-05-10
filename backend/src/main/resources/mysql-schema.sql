CREATE TABLE IF NOT EXISTS intake_records (
  id VARCHAR(64) PRIMARY KEY,
  job_id VARCHAR(64),
  batch_id VARCHAR(64) NOT NULL,
  trigger_type VARCHAR(32),
  recorded_by VARCHAR(128),
  supplier VARCHAR(255),
  vegetables JSON,
  weight DECIMAL(10, 3),
  captured_at TIMESTAMP,
  raw_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
