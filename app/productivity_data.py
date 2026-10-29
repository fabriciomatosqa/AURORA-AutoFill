"""Pesquisa SQLite FTS5 e estatísticas locais dos comandos.

Nenhum texto digitado em outros aplicativos é guardado. Apenas agregados
diários de expansões que terminaram com sucesso.
"""
from __future__ import annotations

from datetime import date, datetime
import re
import sqlite3


def initialize_productivity(connection: sqlite3.Connection) -> bool:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS usage_daily (
            day TEXT NOT NULL,
            snippet_id INTEGER NOT NULL,
            shortcut TEXT NOT NULL,
            uses INTEGER NOT NULL DEFAULT 0 CHECK (uses >= 0),
            PRIMARY KEY(day, snippet_id)
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_usage_month ON usage_daily(day)")
    previous = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name='snippet_fts' AND type='table'"
    ).fetchone()
    try:
        connection.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS snippet_fts USING fts5(
                title, shortcut, content,
                content='snippets', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TRIGGER IF NOT EXISTS snippet_fts_insert AFTER INSERT ON snippets BEGIN
                INSERT INTO snippet_fts(rowid, title, shortcut, content)
                VALUES(new.id, new.title, new.shortcut, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS snippet_fts_delete AFTER DELETE ON snippets BEGIN
                INSERT INTO snippet_fts(snippet_fts, rowid, title, shortcut, content)
                VALUES('delete', old.id, old.title, old.shortcut, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS snippet_fts_update AFTER UPDATE ON snippets BEGIN
                INSERT INTO snippet_fts(snippet_fts, rowid, title, shortcut, content)
                VALUES('delete', old.id, old.title, old.shortcut, old.content);
                INSERT INTO snippet_fts(rowid, title, shortcut, content)
                VALUES(new.id, new.title, new.shortcut, new.content);
            END;
        """)
        if not previous:
            connection.execute("INSERT INTO snippet_fts(snippet_fts) VALUES('rebuild')")
        connection.commit()
        return True
    except sqlite3.OperationalError:
        # SQLite customizada sem FTS5: pesquisa LIKE continua funcionando.
        connection.rollback()
        return False


def search_ids(connection: sqlite3.Connection, search: str) -> list[int] | None:
    terms = re.findall(r"\w+", search, flags=re.UNICODE)
    if not terms or not 2 <= len(search.strip()) <= 160:
        return None
    # Nunca interpretar entrada do usuário como sintaxe FTS. Cada token
    # é escapado e tratado como busca por prefixo de palavra.
    pattern = " AND ".join('"' + term.replace('"', '""') + '"*' for term in terms[:8])
    try:
        rows = connection.execute(
            "SELECT rowid FROM snippet_fts WHERE snippet_fts MATCH ? LIMIT 1500", (pattern,)
        ).fetchall()
        return [int(row[0]) for row in rows] or None
    except sqlite3.OperationalError:
        return None


def record_success(connection: sqlite3.Connection, snippet_id: int,
                   when: date | None = None) -> bool:
    row = connection.execute(
        "SELECT shortcut FROM snippets WHERE id=?", (snippet_id,)
    ).fetchone()
    if row is None:
        return False
    day = (when or date.today()).isoformat()
    with connection:
        connection.execute("""
            INSERT INTO usage_daily(day, snippet_id, shortcut, uses)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(day, snippet_id) DO UPDATE SET
                uses = usage_daily.uses + 1, shortcut=excluded.shortcut
        """, (day, snippet_id, str(row[0])))
    return True


def usage_report(connection: sqlite3.Connection,
                 today: date | None = None) -> dict:
    now = today or date.today()
    today_text = now.isoformat()
    month = today_text[:7]
    year = today_text[:4]
    total = connection.execute(
        "SELECT COALESCE(SUM(uses), 0) FROM usage_daily"
    ).fetchone()[0]
    def count(prefix):
        return int(connection.execute(
            "SELECT COALESCE(SUM(uses), 0) FROM usage_daily WHERE day LIKE ?",
            (prefix + "%",)
        ).fetchone()[0])
    daily = connection.execute(
        "SELECT COALESCE(SUM(uses), 0) FROM usage_daily WHERE day=?",
        (today_text,)
    ).fetchone()[0]
    monthly = connection.execute("""
        SELECT substr(day, 1, 7) AS period, SUM(uses) AS n
        FROM usage_daily WHERE day >= ?
        GROUP BY period ORDER BY period
    """, (f"{now.year - 1:04d}-01-01",)).fetchall()
    top = connection.execute("""
        SELECT u.snippet_id, COALESCE(s.title, u.shortcut) AS label,
               COALESCE(s.shortcut, u.shortcut) AS shortcut,
               SUM(u.uses) AS n
        FROM usage_daily u LEFT JOIN snippets s ON s.id=u.snippet_id
        GROUP BY u.snippet_id ORDER BY n DESC, label LIMIT 10
    """).fetchall()
    return {"today": int(daily), "month": count(month), "year": count(year),
            "total": int(total),
            "months": [(str(r[0]), int(r[1])) for r in monthly],
            "top": [(int(r[0]), str(r[1]), str(r[2]), int(r[3])) for r in top]}


def reset_usage(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute("DELETE FROM usage_daily")

def usage_days(connection: sqlite3.Connection, year: int, month: int) -> dict[int, int]:
    """Aggregated daily totals for one month, without reading typed content."""
    if not 1 <= month <= 12 or not 1 <= year <= 9999:
        raise ValueError("Mês inválido.")
    prefix = f"{year:04d}-{month:02d}-"
    rows = connection.execute(
        "SELECT day, SUM(uses) FROM usage_daily WHERE day LIKE ? "
        "GROUP BY day ORDER BY day", (prefix + "%",)
    ).fetchall()
    return {int(str(day)[-2:]): int(count) for day, count in rows}


def usage_day_top(connection: sqlite3.Connection, day: date,
                  limit: int = 5) -> list[tuple[str, int]]:
    """Optional day breakdown; never stores or retrieves text typed elsewhere."""
    rows = connection.execute("""
        SELECT COALESCE(s.title, u.shortcut) AS label, SUM(u.uses) AS n
        FROM usage_daily u
        LEFT JOIN snippets s ON s.id = u.snippet_id
        WHERE u.day = ?
        GROUP BY u.snippet_id ORDER BY n DESC, label LIMIT ?
    """, (day.isoformat(), max(1, min(int(limit), 10)))).fetchall()
    return [(str(label), int(count)) for label, count in rows]
