# модуль для работы с базой данных postgresql
# здесь хранятся все функции для сохранения и загрузки проектов

import configparser
import json
from pathlib import Path

# пытаемся импортировать библиотеку для работы с postgresql
try:
    import psycopg2
    import psycopg2.extras
    _PG_OK = True
except ImportError:
    # если psycopg2 не установлен, работа с бд будет недоступна
    _PG_OK = False

# путь к файлу настроек подключения
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.ini"


# читает параметры подключения из config.ini
def _cfg() -> dict:
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATH, encoding="utf-8")
    s = cfg["postgresql"]
    return {
        "host":     s.get("host",     "localhost"),
        "port":     s.getint("port",  5432),
        "dbname":   s.get("database", "postgres"),
        "user":     s.get("user",     "postgres"),
        "password": s.get("password", ""),
    }


# создаёт и возвращает соединение с базой данных
def get_connection():
    if not _PG_OK:
        raise ImportError("Установите psycopg2:  pip install psycopg2-binary")
    return psycopg2.connect(**_cfg())


# sql-скрипт для создания таблиц если их ещё нет
_DDL = """
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
"""


# создаёт таблицы в базе данных при первом запуске
def init_schema():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
            # добавляем колонку model_path если её нет (для старых баз данных)
            cur.execute("""
                ALTER TABLE projects
                ADD COLUMN IF NOT EXISTS model_path TEXT DEFAULT ''
            """)
        conn.commit()


# возвращает список всех проектов из базы данных
def list_projects() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # сортируем по дате обновления, новые идут первыми
            cur.execute("""
                SELECT id, name, description, created_at, updated_at
                FROM projects ORDER BY updated_at DESC
            """)
            return [dict(r) for r in cur.fetchall()]


# создаёт новый пустой проект и возвращает его id
def create_project(name: str, description: str = "") -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO projects (name, description)
                VALUES (%s, %s) RETURNING id
            """, (name, description))
            pid = cur.fetchone()[0]
        conn.commit()
    return pid


# обновляет название и описание существующего проекта
def update_project_meta(project_id: int, name: str, description: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE projects SET name=%s, description=%s, updated_at=NOW()
                WHERE id=%s
            """, (name, description, project_id))
        conn.commit()


# удаляет проект и все его данные из базы (связанные таблицы удаляются каскадно)
def delete_project(project_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM projects WHERE id=%s", (project_id,))
        conn.commit()


# сохраняет новый проект со всеми данными: граф, пары соединений, параметры
def save_project(name: str, description: str,
                 graph_dict: dict, pairs: list[dict],
                 aco_params: dict | None = None,
                 model_path: str = "") -> int:
    aco_params = aco_params or {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            # создаём запись проекта и получаем его id
            cur.execute("""
                INSERT INTO projects (name, description, aco_params, next_node_id, model_path)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (name, description,
                  json.dumps(aco_params, ensure_ascii=False),
                  graph_dict.get("next_id", 0),
                  model_path))
            project_id = cur.fetchone()[0]
            # вставляем узлы, рёбра и пары соединений
            _insert_graph(cur, project_id, graph_dict, pairs)
        conn.commit()
    return project_id


# обновляет существующий проект: перезаписывает граф и пары соединений
def update_project(project_id: int, name: str, description: str,
                   graph_dict: dict, pairs: list[dict],
                   aco_params: dict | None = None,
                   model_path: str = ""):
    aco_params = aco_params or {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            # обновляем метаданные проекта
            cur.execute("""
                UPDATE projects
                SET name=%s, description=%s, aco_params=%s,
                    next_node_id=%s, model_path=%s, updated_at=NOW()
                WHERE id=%s
            """, (name, description,
                  json.dumps(aco_params, ensure_ascii=False),
                  graph_dict.get("next_id", 0), model_path, project_id))
            # удаляем старые данные графа и пар перед вставкой новых
            cur.execute("DELETE FROM graph_nodes WHERE project_id=%s",       (project_id,))
            cur.execute("DELETE FROM graph_edges WHERE project_id=%s",       (project_id,))
            cur.execute("DELETE FROM connection_pairs WHERE project_id=%s",  (project_id,))
            _insert_graph(cur, project_id, graph_dict, pairs)
        conn.commit()


# вспомогательная функция: вставляет узлы, рёбра и пары в таблицы
def _insert_graph(cur, project_id: int, graph_dict: dict, pairs: list[dict]):
    # вставляем все узлы графа с их координатами
    for n in graph_dict.get("nodes", []):
        pos = n["pos"]
        cur.execute("""
            INSERT INTO graph_nodes (project_id, node_id, pos_x, pos_y, pos_z)
            VALUES (%s, %s, %s, %s, %s)
        """, (project_id, n["id"], pos[0], pos[1], pos[2]))

    # вставляем все рёбра графа
    for e in graph_dict.get("edges", []):
        cur.execute("""
            INSERT INTO graph_edges (project_id, node_u, node_v, weight)
            VALUES (%s, %s, %s, %s)
        """, (project_id, e["u"], e["v"], e.get("weight", 1.0)))

    # вставляем все пары соединений
    for p in pairs:
        cur.execute("""
            INSERT INTO connection_pairs
                (project_id, source, target, label, cable_type, emc_group)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (project_id, p["source"], p["target"],
              p.get("label", ""),
              p.get("wire_type", "Цифровой"),
              # emc_group=1 означает экранированный провод
              1 if p.get("shielded", False) else 0))


# загружает проект из базы данных по id и возвращает словарь со всеми данными
def load_project(project_id: int) -> dict:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # загружаем основные данные проекта
            cur.execute("SELECT * FROM projects WHERE id=%s", (project_id,))
            proj = dict(cur.fetchone())

            # загружаем узлы графа
            cur.execute(
                "SELECT node_id, pos_x, pos_y, pos_z FROM graph_nodes WHERE project_id=%s",
                (project_id,))
            nodes = [{"id": r["node_id"], "pos": [r["pos_x"], r["pos_y"], r["pos_z"]]}
                     for r in cur.fetchall()]

            # загружаем рёбра графа
            cur.execute("""
                SELECT node_u, node_v, weight
                FROM graph_edges WHERE project_id=%s
            """, (project_id,))
            edges = [{"u": r["node_u"], "v": r["node_v"], "weight": r["weight"]}
                     for r in cur.fetchall()]

            # загружаем пары соединений
            cur.execute("""
                SELECT source, target, label, cable_type, emc_group
                FROM connection_pairs WHERE project_id=%s
            """, (project_id,))
            pairs = [
                {"source": r["source"], "target": r["target"], "label": r["label"],
                 "wire_type": r["cable_type"], "shielded": bool(r["emc_group"])}
                for r in cur.fetchall()
            ]

    # собираем всё в один словарь для возврата
    return {
        "name":        proj["name"],
        "description": proj["description"],
        "aco_params":  proj["aco_params"] or {},
        "model_path":  proj.get("model_path", "") or "",
        "graph":       {"next_id": proj["next_node_id"], "nodes": nodes, "edges": edges},
        "pairs":       pairs,
    }
