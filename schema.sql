-- DDL-скрипт для создания схемы базы данных
-- система трассировки межмодульных соединений
-- postgresql 12+

CREATE TABLE IF NOT EXISTS projects (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    description  TEXT         DEFAULT '',
    aco_params   JSONB        DEFAULT '{}',
    next_node_id INTEGER      DEFAULT 0,
    model_path   TEXT         DEFAULT '',
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    id         SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    node_id    INTEGER NOT NULL,
    pos_x      DOUBLE PRECISION NOT NULL,
    pos_y      DOUBLE PRECISION NOT NULL,
    pos_z      DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id         SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    node_u     INTEGER NOT NULL,
    node_v     INTEGER NOT NULL,
    weight     DOUBLE PRECISION DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS connection_pairs (
    id          SERIAL PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source      INTEGER NOT NULL,
    target      INTEGER NOT NULL,
    label       VARCHAR(255) DEFAULT '',
    cable_type  VARCHAR(100) DEFAULT 'Цифровой',
    emc_group   INTEGER      DEFAULT 0
);
