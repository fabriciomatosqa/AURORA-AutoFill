"""Persistência local e motor de modelos sem dependência de interface."""
from __future__ import annotations

from dataclasses import dataclass
from collections import OrderedDict

from .data_paths import application_db_path
from .welcome import initial_snippets
from .productivity_data import (initialize_productivity, search_ids, record_success,
                                usage_report, usage_days, usage_day_top, reset_usage)
from .smart_templates import advanced_variables
from datetime import date, datetime
from pathlib import Path
import json
import os
import re
import sqlite3
import sys
import tempfile

SHORTCUT_PATTERN = re.compile(r"^/[^\s/]{1,30}$")
VARIABLE_PATTERN = re.compile(r"\{\{([a-zA-Z_]+)\}\}")


def shortcut_key(shortcut: str) -> str:
    """Uma única regra Unicode para cadastro, reconhecimento e recuperação."""
    return shortcut.casefold()


@dataclass(frozen=True)
class Snippet:
    id: int
    folder_id: int
    title: str
    shortcut: str
    content: str
    rich_content: str = ""


@dataclass(frozen=True)
class ShortcutConflict:
    """Comando que torna uma nova abreviação ambígua, mesmo em outra pasta."""
    id: int
    shortcut: str
    title: str
    folder: str


def shortcut_conflict_message(shortcut: str, conflict: ShortcutConflict) -> str:
    return (
        f"O atalho {shortcut} conflita com {conflict.shortcut}, já utilizado "
        f"pelo comando «{conflict.title}» na pasta «{conflict.folder}». "
        "Escolha um atalho diferente, que não seja igual nem comece "
        "com outro atalho (e vice-versa)."
    )


@dataclass(frozen=True)
class RenderResult:
    text: str
    left_moves: int = 0


def validate_shortcut(shortcut: str) -> None:
    if not isinstance(shortcut, str) or not SHORTCUT_PATTERN.fullmatch(shortcut):
        raise ValueError("O atalho deve começar com / e ter de 1 a 30 caracteres, sem espaços nem outras barras.")


def render_snippet(template: str, clipboard_text: str = "", now: datetime | None = None) -> RenderResult:
    """Resolve variáveis. {{cursor}} marca onde o cursor termina após a inserção."""
    now = now or datetime.now()
    template = advanced_variables(template, now)
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


class SnippetStore:
    def __init__(self, db_path: str | Path):
        path = Path(db_path)
        # Um banco já existente, inclusive vazio, não deve receber exemplos de
        # novo após uma atualização, exclusão ou restauração de backup.
        self._fresh_database = not path.exists()
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
        # A migração mantém a ordem antiga (id DESC) para posições iguais.
        if "sort_order" not in columns:
            self.connection.execute("ALTER TABLE snippets ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        self.connection.commit()
        self._fts_available = initialize_productivity(self.connection)
        self._shortcut_version = None
        self._shortcut_ids = {}
        self._snippet_cache = OrderedDict()
        self._snippet_cache_size = 0

    def folders(self) -> list[tuple[int, str]]:
        return [(int(r["id"]), str(r["name"])) for r in self.connection.execute(
            "SELECT id, name FROM folders ORDER BY name COLLATE NOCASE")]

    def create_folder(self, name: str) -> int:
        if not isinstance(name, str):
            raise ValueError("Informe o nome da pasta.")
        name = name.strip()
        if not name:
            raise ValueError("Informe o nome da pasta.")
        with self.connection:
            cursor = self.connection.execute("INSERT INTO folders(name) VALUES (?)", (name,))
        return int(cursor.lastrowid)

    def delete_folder(self, folder_id: int) -> tuple[int, str]:
        """Apaga somente a pasta; preserva seus comandos em outra pasta."""
        with self.connection:
            existing = self.connection.execute(
                "SELECT name FROM folders WHERE id=?", (folder_id,)).fetchone()
            if existing is None:
                raise ValueError("Esta pasta não existe mais.")
            alternatives = self.connection.execute(
                "SELECT id, name FROM folders WHERE id<>? ORDER BY name COLLATE NOCASE",
                (folder_id,)).fetchall()
            if alternatives:
                target = next((row for row in alternatives if row["name"].casefold() == "meus atalhos"),
                              alternatives[0])
                target_id, target_name = int(target["id"]), str(target["name"])
            else:
                target_name = "Sem pasta" if existing["name"].casefold() == "meus atalhos" else "Meus atalhos"
                target_id = int(self.connection.execute(
                    "INSERT INTO folders(name) VALUES (?)", (target_name,)).lastrowid)
            count = int(self.connection.execute(
                "SELECT COUNT(*) FROM snippets WHERE folder_id=?", (folder_id,)).fetchone()[0])
            self.connection.execute("UPDATE snippets SET folder_id=? WHERE folder_id=?",
                                    (target_id, folder_id))
            self.connection.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        return count, target_name

    def reorder_snippets(self, folder_id: int | None, ordered_ids: list[int]) -> None:
        """Persiste drag-and-drop sem mover comandos entre pastas."""
        with self.connection:
            rows = self.connection.execute(
                "SELECT id, folder_id FROM snippets ORDER BY sort_order ASC, id DESC").fetchall()
            all_ids = [int(row["id"]) for row in rows]
            positions = [index for index, row in enumerate(rows)
                         if folder_id is None or row["folder_id"] == folder_id]
            allowed = {all_ids[index] for index in positions}
            if (len(ordered_ids) != len(positions) or len(set(ordered_ids)) != len(ordered_ids)
                    or set(ordered_ids) != allowed):
                raise ValueError("A lista de comandos mudou. Atualize antes de reorganizar.")
            for index, snippet_id in zip(positions, ordered_ids):
                all_ids[index] = snippet_id
            self.connection.executemany(
                "UPDATE snippets SET sort_order=? WHERE id=?",
                ((index, snippet_id) for index, snippet_id in enumerate(all_ids)))

    def snippets(self, folder_id: int | None = None, query: str = "") -> list[Snippet]:
        sql = "SELECT id, folder_id, title, shortcut, content, rich_content FROM snippets WHERE 1=1"
        params: list[object] = []
        if folder_id is not None:
            sql += " AND folder_id = ?"
            params.append(folder_id)
        if query:
            hit_ids = search_ids(self.connection, query) if self._fts_available else None
            if hit_ids:
                # Sem reordenação: a pasta e a organização manual prevalecem.
                sql += " AND id IN (" + ",".join("?" for _ in hit_ids) + ")"
                params.extend(hit_ids)
            else:
                # Compatibilidade com buscas por trechos no meio da palavra.
                sql += " AND (title LIKE ? OR shortcut LIKE ? OR content LIKE ?)"
                params.extend([f"%{query}%"] * 3)
        sql += " ORDER BY sort_order ASC, id DESC"
        return [Snippet(**dict(row)) for row in self.connection.execute(sql, params)]

    def register_expansion(self, snippet_id: int, when: date | None = None) -> bool:
        return record_success(self.connection, snippet_id, when)

    def usage_report(self, today: date | None = None) -> dict:
        return usage_report(self.connection, today)

    def usage_days(self, year: int, month: int) -> dict[int, int]:
        return usage_days(self.connection, year, month)

    def usage_day_top(self, day: date, limit: int = 5) -> list[tuple[str, int]]:
        return usage_day_top(self.connection, day, limit)

    def reset_usage(self) -> None:
        reset_usage(self.connection)

    def snippet_by_shortcut(self, shortcut: str) -> Snippet | None:
        """Índice Unicode leve + cache limitado, sem reler imagens a cada uso.

        NOCASE do SQLite só cobre ASCII. O índice em memória usa a mesma chave
        do matcher e recusa colisões legadas em vez de escolher o texto errado.
        total_changes/data_version invalidam edições locais e de outra conexão.
        """
        if not shortcut:
            return None
        self._refresh_shortcut_index()
        identifier = self._shortcut_ids.get(shortcut_key(shortcut.strip()))
        if identifier is None:
            return None
        cached = self._snippet_cache.get(identifier)
        if cached is not None:
            self._snippet_cache.move_to_end(identifier)
            return cached
        row = self.connection.execute(
            "SELECT id, folder_id, title, shortcut, content, rich_content "
            "FROM snippets WHERE id = ?", (identifier,),
        ).fetchone()
        if row is None:
            return None
        snippet = Snippet(**dict(row))
        weight = len(snippet.content) + len(snippet.rich_content)
        # Até 16 modelos / 4 milhões de caracteres (~16 MB no pior caso).
        # Um modelo enorme ainda funciona, mas não ocupa o cache inteiro.
        if weight <= 4_000_000:
            self._snippet_cache[identifier] = snippet
            self._snippet_cache_size += weight
            while len(self._snippet_cache) > 16 or self._snippet_cache_size > 4_000_000:
                _, old = self._snippet_cache.popitem(last=False)
                self._snippet_cache_size -= len(old.content) + len(old.rich_content)
        return snippet

    def _refresh_shortcut_index(self) -> None:
        version = (self.connection.total_changes,
                   self.connection.execute("PRAGMA data_version").fetchone()[0],
                   self.connection.in_transaction)
        if version == self._shortcut_version:
            return
        ids = {}
        for row in self.connection.execute("SELECT id, shortcut FROM snippets ORDER BY id"):
            key = shortcut_key(str(row["shortcut"]))
            ids[key] = int(row["id"]) if key not in ids else None
        self._shortcut_ids = ids
        self._shortcut_version = version
        self._snippet_cache.clear()
        self._snippet_cache_size = 0

    def shortcuts(self) -> list[str]:
        """Metadados para o hook: nunca carrega corpos ou imagens."""
        self._refresh_shortcut_index()
        return [key for key, identifier in self._shortcut_ids.items() if identifier is not None]

    def shortcut_conflict(self, shortcut: str, excluding_id: int | None = None) -> ShortcutConflict | None:
        """Compara só metadados, sem carregar HTML/base64 ou conteúdo de snippets.

        Conflito se um atalho é prefixo do outro, inclusive igual (sem distinção
        de maiúsculas/minúsculas) e mesmo que pertençam a pastas diferentes.
        Ignora o registro atual ao editar o próprio atalho.
        """
        needle = shortcut_key(shortcut)
        rows = self.connection.execute(
            "SELECT s.id, s.shortcut, s.title, f.name AS folder "
            "FROM snippets AS s JOIN folders AS f ON f.id = s.folder_id"
        )
        for row in rows:
            if excluding_id is not None and int(row["id"]) == excluding_id:
                continue
            existing = shortcut_key(str(row["shortcut"]))
            if needle.startswith(existing) or existing.startswith(needle):
                return ShortcutConflict(
                    int(row["id"]), str(row["shortcut"]), str(row["title"]), str(row["folder"]))
        return None

    def save(self, folder_id: int, title: str, shortcut: str, content: str,
             snippet_id: int | None = None, rich_content: str = "") -> int:
        if not all(isinstance(value, str) for value in (title, shortcut, content, rich_content)):
            raise ValueError("Título, atalho e conteúdo devem ser textos.")
        title = title.strip()
        shortcut = shortcut.strip()
        if not title:
            raise ValueError("Informe um título.")
        validate_shortcut(shortcut)
        if not content.strip():
            raise ValueError("Informe o texto do comando.")
        try:
            with self.connection:
                # Segunda validação obrigatória no banco, mesmo que a interface
                # já tenha desativado Salvar. Vale também para edições e scripts.
                conflict = self.shortcut_conflict(shortcut, excluding_id=snippet_id)
                if conflict is not None:
                    raise ValueError(shortcut_conflict_message(shortcut, conflict))
                if snippet_id is None:
                    position = self.connection.execute(
                        "SELECT COALESCE(MIN(sort_order), 0) - 1 FROM snippets").fetchone()[0]
                    cur = self.connection.execute(
                        "INSERT INTO snippets(folder_id, title, shortcut, content, rich_content, sort_order) VALUES (?,?,?,?,?,?)",
                        (folder_id, title, shortcut, content, rich_content, position))
                    return int(cur.lastrowid)
                updated = self.connection.execute(
                    "UPDATE snippets SET folder_id=?, title=?, shortcut=?, content=?, rich_content=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (folder_id, title, shortcut, content, rich_content, snippet_id))
                if updated.rowcount != 1:
                    raise ValueError("Este comando não existe mais. Atualize a lista antes de salvar.")
                return snippet_id
        except sqlite3.IntegrityError as error:
            raise ValueError("Esse atalho já existe ou a pasta é inválida.") from error

    def update_snippet_fields(self, snippet_id: int, **fields) -> None:
        """Salva imediatamente somente os campos alterados, sem reler imagens HTML.

        A atualização do atalho permanece atômica e sujeita à verificação global
        de prefixos. Não cria rascunhos inválidos nem descarta dados anteriores.
        """
        allowed = {"title", "shortcut", "folder_id", "content", "rich_content"}
        if not fields or not set(fields).issubset(allowed):
            raise ValueError("Campos de edição inválidos.")
        for key in ("title", "shortcut", "content", "rich_content"):
            if key in fields and not isinstance(fields[key], str):
                raise ValueError("O campo precisa ser texto.")
        if "title" in fields:
            fields["title"] = fields["title"].strip()
            if not fields["title"]:
                raise ValueError("Informe um título para salvar automaticamente.")
        if "content" in fields and not fields["content"].strip():
            raise ValueError("Informe o conteúdo para salvar automaticamente.")
        if "shortcut" in fields:
            fields["shortcut"] = fields["shortcut"].strip()
            validate_shortcut(fields["shortcut"])
        try:
            with self.connection:
                if "shortcut" in fields:
                    conflict = self.shortcut_conflict(fields["shortcut"], excluding_id=snippet_id)
                    if conflict is not None:
                        raise ValueError(shortcut_conflict_message(fields["shortcut"], conflict))
                assignments = ", ".join(f"{key}=?" for key in fields)
                changed = self.connection.execute(
                    f"UPDATE snippets SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (*fields.values(), snippet_id))
                if changed.rowcount != 1:
                    raise ValueError("O comando não existe mais; atualize a lista.")
        except sqlite3.IntegrityError as error:
            raise ValueError("O atalho já existe ou a pasta não é válida.") from error

    def delete(self, snippet_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM snippets WHERE id=?", (snippet_id,))

    def delete_with_undo(self, snippet_id: int) -> dict:
        """Remove a snippet while preserving all columns for a 10-second undo."""
        with self.connection:
            row = self.connection.execute(
                "SELECT * FROM snippets WHERE id=?", (snippet_id,)).fetchone()
            if row is None:
                raise ValueError("Comando não encontrado.")
            snapshot = dict(row)
            folder = self.connection.execute("SELECT name FROM folders WHERE id=?",
                                             (row["folder_id"],)).fetchone()
            snapshot["_folder_name"] = folder[0] if folder else "Comandos recuperados"
            self.connection.execute("DELETE FROM snippets WHERE id=?", (snippet_id,))
        return snapshot

    def restore_deleted_snippet(self, snapshot: dict) -> None:
        columns = ("id", "folder_id", "title", "shortcut", "content", "rich_content",
                   "sort_order", "created_at", "updated_at")
        with self.connection:
            values = dict(snapshot)
            if not self.connection.execute("SELECT 1 FROM folders WHERE id=?",
                                           (values["folder_id"],)).fetchone():
                name = snapshot.get("_folder_name", "Comandos recuperados")
                existing = self.connection.execute(
                    "SELECT id FROM folders WHERE name=? COLLATE NOCASE", (name,)).fetchone()
                if existing:
                    values["folder_id"] = existing[0]
                else:
                    self.connection.execute("INSERT INTO folders(id, name) VALUES (?, ?)",
                                            (values["folder_id"], name))
            self.connection.execute(
                f"INSERT INTO snippets({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(values[key] for key in columns))

    def delete_folder_with_undo(self, folder_id: int) -> tuple[int, str, dict]:
        """Keep the original ID and moved-snippet IDs for a safe short-term undo."""
        folder = self.connection.execute(
            "SELECT name FROM folders WHERE id=?", (folder_id,)).fetchone()
        if folder is None:
            raise ValueError("Pasta não encontrada.")
        old_folders = {folder_id for folder_id, _ in self.folders()}
        snippet_ids = [item.id for item in self.snippets(folder_id)]
        name = str(folder["name"])
        count, destination = self.delete_folder(folder_id)
        destination_id = next(fid for fid, label in self.folders() if label == destination)
        return count, destination, {
            "id": folder_id, "name": name, "snippet_ids": snippet_ids,
            "destination_id": destination_id,
            "created_destination": destination_id not in old_folders,
        }

    def restore_deleted_folder(self, snapshot: dict) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO folders(id, name) VALUES (?, ?)",
                (snapshot["id"], snapshot["name"]))
            for snippet_id in snapshot["snippet_ids"]:
                self.connection.execute(
                    "UPDATE snippets SET folder_id=? WHERE id=? AND folder_id=?",
                    (snapshot["id"], snippet_id, snapshot["destination_id"]))
            if snapshot["created_destination"]:
                self.connection.execute(
                    "DELETE FROM folders WHERE id=? AND NOT EXISTS "
                    "(SELECT 1 FROM snippets WHERE folder_id=?)",
                    (snapshot["destination_id"], snapshot["destination_id"]))

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
        destination = Path(destination)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                             prefix=".aurora-export-", suffix=".tmp",
                                             delete=False) as output:
                temporary = Path(output.name)
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def import_json(self, source: str | Path) -> tuple[int, int]:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != "AutoFillStudioBackup" or payload.get("version") != 1:
            raise ValueError("Arquivo de backup não reconhecido.")
        items = payload.get("snippets")
        if not isinstance(items, list) or len(items) > 20000:
            raise ValueError("Lista de comandos inválida ou grande demais.")
        folders = payload.get("folders", [])
        if (not isinstance(folders, list) or len(folders) > 20000
                or any(not isinstance(name, str) or not name.strip() for name in folders)):
            raise ValueError("Lista de pastas inválida ou grande demais.")
        # Match SQLite NOCASE (ASCII), preserving distinct accented names that
        # may coexist in a profile, e.g. 'Área' and 'área'.
        translation = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
        folder_map = {name.translate(translation): folder_id for folder_id, name in self.folders()}
        imported = skipped = 0
        # Backup JSON pode conter milhares de comandos e imagens incorporadas.
        # A validação de importação usa somente as chaves dos atalhos: O(n * L)
        # em vez de reler todos os registros para cada novo item.
        shortcuts = {
            shortcut_key(str(row[0])) for row in
            self.connection.execute("SELECT shortcut FROM snippets")
        }
        prefixes = {
            key[:length]
            for key in shortcuts for length in range(2, len(key))
        }

        def is_conflicting(key: str) -> bool:
            return (key in shortcuts or key in prefixes
                    or any(key[:length] in shortcuts for length in range(2, len(key))))

        with self.connection:
            def ensure_folder(name):
                normalized = name.strip()
                key = normalized.translate(translation)
                if key not in folder_map:
                    folder_map[key] = int(self.connection.execute(
                        "INSERT INTO folders(name) VALUES (?)", (normalized,)).lastrowid)
                return folder_map[key]

            # Include empty folders too; they are part of the exported profile.
            for name in folders:
                ensure_folder(name)
            position = int(self.connection.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM snippets").fetchone()[0])
            for item in items:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                folder_name = item.get("folder")
                values = [item.get(key) for key in ("title", "shortcut", "content")]
                rich_content = item.get("rich_content") or ""
                if (not isinstance(folder_name, str) or not folder_name.strip()
                        or not all(isinstance(value, str) for value in [*values, rich_content])):
                    skipped += 1
                    continue
                title, shortcut, content = values
                try:
                    if not title.strip() or not content.strip():
                        raise ValueError("Comando vazio.")
                    validate_shortcut(shortcut.strip())
                    # Atalhos idênticos e prefixos sobrepostos são ignorados sem
                    # criar pastas vazias nem alterar dados já cadastrados.
                    key = shortcut_key(shortcut.strip())
                    if is_conflicting(key):
                        skipped += 1
                        continue
                    folder_id = ensure_folder(folder_name)
                    self.connection.execute(
                        "INSERT INTO snippets(folder_id, title, shortcut, content, rich_content, sort_order) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (folder_id, title.strip(), shortcut.strip(), content, rich_content, position))
                    imported += 1
                    position += 1
                    shortcuts.add(key)
                    prefixes.update(key[:length] for length in range(2, len(key)))
                except (ValueError, sqlite3.IntegrityError):
                    skipped += 1
        return imported, skipped

    def seed_if_empty(self) -> None:
        """Introduz o AURORA apenas quando o banco realmente acaba de nascer."""
        if not self._fresh_database or self.folders() or self.snippets():
            return
        # A operação é atômica: nunca disponibiliza quatro modelos incompletos.
        with self.connection:
            folder = self.connection.execute(
                "INSERT INTO folders(name) VALUES (?)", ("Conheça o AURORA",)
            ).lastrowid
            for position, (title, shortcut, content, rich_content) in enumerate(initial_snippets()):
                validate_shortcut(shortcut)
                self.connection.execute(
                    "INSERT INTO snippets(folder_id, title, shortcut, content, rich_content, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (folder, title, shortcut, content, rich_content, position),
                )
        self._fresh_database = False

    def close(self) -> None:
        self.connection.close()
