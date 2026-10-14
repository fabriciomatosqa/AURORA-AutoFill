"""Persistência local e motor de modelos sem dependência de interface."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import os
import re
import sqlite3
import sys

SHORTCUT_PATTERN = re.compile(r"^/[^\s/]{1,30}$")
VARIABLE_PATTERN = re.compile(r"\{\{([a-zA-Z_]+)\}\}")


@dataclass(frozen=True)
class Snippet:
    id: int
    folder_id: int
    title: str
    shortcut: str
    content: str
    rich_content: str = ""


@dataclass(frozen=True)
class RenderResult:
    text: str
    left_moves: int = 0


def validate_shortcut(shortcut: str) -> None:
    if not SHORTCUT_PATTERN.fullmatch(shortcut):
        raise ValueError("O atalho deve começar com / e ter de 1 a 30 caracteres, sem espaços nem outras barras.")


def render_snippet(template: str, clipboard_text: str = "", now: datetime | None = None) -> RenderResult:
    """Resolve variáveis. {{cursor}} marca onde o cursor termina após a inserção."""
    now = now or datetime.now()
    values = {
        "data": now.strftime("%d/%m/%Y"),
        "hora": now.strftime("%H:%M"),
        "data_hora": now.strftime("%d/%m/%Y %H:%M"),
        "clipboard": clipboard_text,
        "area_transferencia": clipboard_text,
    }
    result: list[str] = []
    total_length = 0
    cursor_pos: int | None = None
    index = 0
    for match in VARIABLE_PATTERN.finditer(template):
        literal = template[index:match.start()]
        result.append(literal)
        total_length += len(literal)
        token = match.group(1)
        if token == "cursor":
            if cursor_pos is None:
                cursor_pos = total_length
            replacement = ""
        else:
            replacement = values.get(token, match.group(0))
        result.append(replacement)
        total_length += len(replacement)
        index = match.end()
    tail = template[index:]
    result.append(tail)
    total_length += len(tail)
    return RenderResult("".join(result), 0 if cursor_pos is None else total_length - cursor_pos)


def application_db_path() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return root / "AutoFillStudio" / "snippets.sqlite3"


class SnippetStore:
    def __init__(self, db_path: str | Path):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE
            );
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL REFERENCES folders(id),
                title TEXT NOT NULL,
                shortcut TEXT NOT NULL UNIQUE COLLATE NOCASE,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_snippets_folder ON snippets(folder_id);
        """)
        # Migração conservadora: mantém os atalhos já cadastrados na versão 0.1.
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(snippets)")}
        if "rich_content" not in columns:
            self.connection.execute("ALTER TABLE snippets ADD COLUMN rich_content TEXT NOT NULL DEFAULT ''")
        self.connection.commit()

    def folders(self) -> list[tuple[int, str]]:
        return [(int(r["id"]), str(r["name"])) for r in self.connection.execute(
            "SELECT id, name FROM folders ORDER BY name COLLATE NOCASE")]

    def create_folder(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Informe o nome da pasta.")
        with self.connection:
            cursor = self.connection.execute("INSERT INTO folders(name) VALUES (?)", (name,))
        return int(cursor.lastrowid)

    def snippets(self, folder_id: int | None = None, query: str = "") -> list[Snippet]:
        sql = "SELECT id, folder_id, title, shortcut, content, rich_content FROM snippets WHERE 1=1"
        params: list[object] = []
        if folder_id is not None:
            sql += " AND folder_id = ?"
            params.append(folder_id)
        if query:
            sql += " AND (title LIKE ? OR shortcut LIKE ? OR content LIKE ?)"
            params.extend([f"%{query}%"] * 3)
        sql += " ORDER BY id DESC"
        return [Snippet(**dict(row)) for row in self.connection.execute(sql, params)]

    def save(self, folder_id: int, title: str, shortcut: str, content: str,
             snippet_id: int | None = None, rich_content: str = "") -> int:
        title = title.strip()
        shortcut = shortcut.strip()
        if not title:
            raise ValueError("Informe um título.")
        validate_shortcut(shortcut)
        if not content.strip():
            raise ValueError("Informe o texto do comando.")
        try:
            with self.connection:
                if snippet_id is None:
                    cur = self.connection.execute(
                        "INSERT INTO snippets(folder_id, title, shortcut, content, rich_content) VALUES (?,?,?,?,?)",
                        (folder_id, title, shortcut, content, rich_content))
                    return int(cur.lastrowid)
                self.connection.execute(
                    "UPDATE snippets SET folder_id=?, title=?, shortcut=?, content=?, rich_content=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (folder_id, title, shortcut, content, rich_content, snippet_id))
                return snippet_id
        except sqlite3.IntegrityError as error:
            raise ValueError("Esse atalho já existe ou a pasta é inválida.") from error

    def delete(self, snippet_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM snippets WHERE id=?", (snippet_id,))

    def export_json(self, destination: str | Path) -> None:
        folders = self.folders()
        contents = self.snippets()
        mapping = dict(folders)
        payload = {
            "format": "AutoFillStudioBackup", "version": 1,
            "folders": [name for _, name in folders],
            "snippets": [{"folder": mapping[s.folder_id], "title": s.title,
                          "shortcut": s.shortcut, "content": s.content, "rich_content": s.rich_content} for s in contents],
        }
        Path(destination).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_json(self, source: str | Path) -> tuple[int, int]:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != "AutoFillStudioBackup" or payload.get("version") != 1:
            raise ValueError("Arquivo de backup não reconhecido.")
        items = payload.get("snippets")
        if not isinstance(items, list) or len(items) > 20000:
            raise ValueError("Lista de comandos inválida ou grande demais.")
        folder_map = {name.casefold(): folder_id for folder_id, name in self.folders()}
        imported = skipped = 0
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            folder_name = item.get("folder")
            if not isinstance(folder_name, str) or not folder_name.strip():
                skipped += 1
                continue
            try:
                if folder_name.casefold() not in folder_map:
                    folder_map[folder_name.casefold()] = self.create_folder(folder_name)
                self.save(folder_map[folder_name.casefold()], item["title"], item["shortcut"], item["content"],
                          rich_content=str(item.get("rich_content") or ""))
                imported += 1
            except (ValueError, KeyError, TypeError, sqlite3.IntegrityError):
                skipped += 1
        return imported, skipped

    def seed_if_empty(self) -> None:
        if self.folders():
            return
        folder = self.create_folder("Meus atalhos")
        self.save(folder, "Boas-vindas", "/ola", "Olá! Tudo bem? Posso ajudar em alguma coisa?")
        self.save(folder, "Data e hora", "/agora", "Hoje é {{data}}, às {{hora}}.")
        self.save(folder, "Chamado de TI", "/chamado", "Olá,\n\nSua solicitação foi registrada em {{data}}.\n\nAtenciosamente,\nEquipe de TI")
        self.save(folder, "Modelo com cursor", "/resposta", "Olá, {{cursor}}!\n\nObrigado pelo contato.")
        self.save(folder, "Conteúdo copiado", "/colar", "Informação recebida: {{clipboard}}")

    def close(self) -> None:
        self.connection.close()