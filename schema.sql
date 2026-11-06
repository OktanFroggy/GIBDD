CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS inspectors (
    id SERIAL PRIMARY KEY,
    login VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    lockout_until TIMESTAMPTZ,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS drivers (
    guid UUID PRIMARY KEY,
    last_name VARCHAR(100) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    middle_name VARCHAR(100) NOT NULL,
    birth_date DATE NOT NULL,
    license_number VARCHAR(50) NOT NULL UNIQUE,
    passport VARCHAR(20) NOT NULL UNIQUE,
    reg_city VARCHAR(100) NOT NULL,
    reg_address TEXT NOT NULL,
    living_city VARCHAR(100) NOT NULL,
    living_address TEXT NOT NULL,
    workplace VARCHAR(200),
    position VARCHAR(100),
    phone VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    photo_path TEXT NOT NULL,
    notes TEXT,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS fines (
    id SERIAL PRIMARY KEY,
    source_fine_id VARCHAR(100) UNIQUE,
    driver_guid UUID REFERENCES drivers(guid) ON DELETE SET NULL,
    vehicle_number VARCHAR(20),
    amount NUMERIC(10, 2) NOT NULL,
    issue_date DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'не оплачен'
        CHECK (status IN ('не оплачен', 'передан в ФССП')),
    photo_url TEXT,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_drivers_name_birth_date
    ON drivers (last_name, first_name, middle_name, birth_date)
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_fines_driver_guid
    ON fines (driver_guid)
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_fines_unmatched
    ON fines (issue_date)
    WHERE driver_guid IS NULL AND is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_fines_fssp_candidates
    ON fines (issue_date)
    WHERE status = 'не оплачен' AND is_deleted = FALSE;

INSERT INTO inspectors (login, password_hash, must_change_password)
VALUES ('inspector', crypt('Temp12345', gen_salt('bf', 12)), TRUE)
ON CONFLICT (login) DO NOTHING;
