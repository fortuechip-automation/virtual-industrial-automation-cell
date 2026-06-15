-- Virtual Industrial Automation Cell
-- Historian database schema
-- Database: industrial_cell

CREATE TABLE machine_telemetry (
    id               BIGSERIAL PRIMARY KEY,
    ts               TIMESTAMPTZ NOT NULL DEFAULT now(),
    machine_id       TEXT        NOT NULL DEFAULT 'cell_01',
    machine_state    TEXT        NOT NULL,
    conveyor_running BOOLEAN     NOT NULL DEFAULT false,
    conveyor_speed   REAL        NOT NULL DEFAULT 0,
    entry_sensor     BOOLEAN     NOT NULL DEFAULT false,
    exit_sensor      BOOLEAN     NOT NULL DEFAULT false,
    part_count       INTEGER     NOT NULL DEFAULT 0,
    fault_active     BOOLEAN     NOT NULL DEFAULT false
);

CREATE TABLE machine_events (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    machine_id    TEXT        NOT NULL DEFAULT 'cell_01',
    event_type    TEXT        NOT NULL,
    event_message TEXT        NOT NULL
);

CREATE TABLE machine_alarms (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    machine_id    TEXT        NOT NULL DEFAULT 'cell_01',
    alarm_code    TEXT        NOT NULL,
    alarm_message TEXT        NOT NULL,
    active        BOOLEAN     NOT NULL DEFAULT true,
    acknowledged  BOOLEAN     NOT NULL DEFAULT false
);

CREATE TABLE production_counts (
    id             BIGSERIAL PRIMARY KEY,
    ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
    machine_id     TEXT        NOT NULL DEFAULT 'cell_01',
    good_parts     INTEGER     NOT NULL DEFAULT 0,
    rejected_parts INTEGER     NOT NULL DEFAULT 0,
    total_parts    INTEGER     NOT NULL DEFAULT 0
);
