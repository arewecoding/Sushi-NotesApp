import os
import sqlite3
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Union
from sushi.logger_service import sys_log, LogSource, LogLevel


@dataclass
class NoteMetadata:
    note_id: str
    note_title: str
    note_version: str
    note_dir: Path

    # This is necessary to ensure Path is always a Path object
    def __post_init__(self):
        if not isinstance(self.note_dir, Path):
            self.note_dir = Path(self.note_dir)


@dataclass
class DirectoryMetadata:
    dir_path: Path
    dir_name: str
    parent_path: Optional[Path] = None

    def __post_init__(self):
        if not isinstance(self.dir_path, Path):
            self.dir_path = Path(self.dir_path)
        if self.parent_path and not isinstance(self.parent_path, Path):
            self.parent_path = Path(self.parent_path)


class FileIndex:
    def __init__(self, db_path: str = ":memory:"):
        # Log the connection attempt
        sys_log.log(
            LogSource.DB, LogLevel.INFO, f"Initializing DB connection at {db_path}"
        )

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._setup_db()

    def _setup_db(self):
        cursor = self.conn.cursor()

        # Table for notes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY,
                note_title TEXT NOT NULL,
                note_version TEXT NOT NULL,
                note_dir TEXT NOT NULL
            )
        """)

        # Table for directories
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS directories (
                dir_path TEXT PRIMARY KEY,
                dir_name TEXT NOT NULL,
                parent_path TEXT
            )
        """)

        self.conn.commit()
        sys_log.log(LogSource.DB, LogLevel.DEBUG, "Database tables ready")

    # Wipes all data. Used by VaultWatcher before a fresh scan.
    def clear_all(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM notes")
        cursor.execute("DELETE FROM directories")
        self.conn.commit()
        sys_log.log(LogSource.DB, LogLevel.INFO, "Database cleared for fresh scan")

    # =====================
    # READ (From Cache)
    # =====================
    def get_directory_contents(self, target_path: Union[str, Path]) -> Dict:
        cursor = self.conn.cursor()
        # Normalize path
        target_path = str(Path(target_path).resolve())

        subdirs = cursor.execute(
            "SELECT * FROM directories WHERE parent_path = ?", (target_path,)
        ).fetchall()
        notes = cursor.execute(
            "SELECT * FROM notes WHERE note_dir = ?", (target_path,)
        ).fetchall()

        return {
            "subdirs": [dict(d) for d in subdirs],
            "notes": [dict(n) for n in notes],
        }

    def get_metadata(self, note_id: str) -> Optional[NoteMetadata]:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT * FROM notes WHERE note_id = ?", (note_id,)
        ).fetchone()
        if row:
            return NoteMetadata(**dict(row))
        return None

    def get_all_notes(self) -> List[NoteMetadata]:
        cursor = self.conn.cursor()
        rows = cursor.execute("SELECT * FROM notes").fetchall()
        return [
            NoteMetadata(
                note_id=row["note_id"],
                note_title=row["note_title"],
                note_version=row["note_version"],
                note_dir=Path(row["note_dir"]),
            )
            for row in rows
        ]

    # =====================
    # WRITE (From Watcher)
    # =====================

    def add_directory(self, directory: DirectoryMetadata):
        cursor = self.conn.cursor()
        # Convert Paths to strings for SQLite
        dir_path_str = str(directory.dir_path.resolve())
        parent_path_str = (
            str(directory.parent_path.resolve()) if directory.parent_path else None
        )

        cursor.execute(
            """
            INSERT OR REPLACE INTO directories (dir_path, dir_name, parent_path)
            VALUES (?, ?, ?)
        """,
            (dir_path_str, directory.dir_name, parent_path_str),
        )

        self.conn.commit()
        sys_log.log(
            LogSource.DB, LogLevel.DEBUG, f"Added/Updated Dir: {directory.dir_name}"
        )

    def add_metadata(self, note: NoteMetadata):
        cursor = self.conn.cursor()
        # Normalize note_dir path for consistent storage
        note_dir_str = str(note.note_dir.resolve())

        cursor.execute(
            """
            INSERT OR REPLACE INTO notes (note_id, note_title, note_version, note_dir)
            VALUES (?, ?, ?, ?)
        """,
            (note.note_id, note.note_title, note.note_version, note_dir_str),
        )

        self.conn.commit()
        sys_log.log(
            LogSource.DB, LogLevel.DEBUG, f"Added/Updated Note: {note.note_title}"
        )

    # =====================
    # DELETE
    # =====================

    # Deletes a single note by ID.
    def delete_note(self, note_id: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM notes WHERE note_id = ?", (note_id,))
        self.conn.commit()
        sys_log.log(LogSource.DB, LogLevel.INFO, f"Deleted note: {note_id}")

    #
    #     Deletes the directory, ALL sub-directories, and ALL notes inside them.
    #     Uses LIKE 'path/ %' to find children (fixing the prefix bug).
    #
    def delete_directory_recursive(self, dir_path: str):
        cursor = self.conn.cursor()
        # Normalize path
        dir_path = str(Path(dir_path).resolve())
        # The wildcard path needs a trailing separator to avoid matching 'dir_path_extra'
        wildcard_path = dir_path + os.sep + "%"

        # 1. Find all notes inside this directory and its subdirectories
        notes_to_delete = cursor.execute(
            "SELECT note_id FROM notes WHERE note_dir = ? OR note_dir LIKE ?",
            (dir_path, wildcard_path),
        ).fetchall()
        for note in notes_to_delete:
            sys_log.log(
                LogSource.DB, LogLevel.DEBUG, f"Cascade delete note: {note['note_id']}"
            )

        # 2. Find all subdirectories
        dirs_to_delete = cursor.execute(
            "SELECT dir_path FROM directories WHERE dir_path = ? OR dir_path LIKE ?",
            (dir_path, wildcard_path),
        ).fetchall()
        for d in dirs_to_delete:
            sys_log.log(
                LogSource.DB, LogLevel.DEBUG, f"Cascade delete dir: {d['dir_path']}"
            )

        # 3. Execute Deletions
        cursor.execute(
            "DELETE FROM notes WHERE note_dir = ? OR note_dir LIKE ?",
            (dir_path, wildcard_path),
        )
        cursor.execute(
            "DELETE FROM directories WHERE dir_path = ? OR dir_path LIKE ?",
            (dir_path, wildcard_path),
        )
        self.conn.commit()

        sys_log.log(
            LogSource.DB, LogLevel.INFO, f"Recursively deleted directory: {dir_path}"
        )

    #
    #     Renames a directory and updates all children (files and subfolders)
    #     to point to the new path.
    #
    def update_directory(self, old_path: str, new_path: str, new_name: str):
        cursor = self.conn.cursor()
        old_path = str(Path(old_path).resolve())
        new_path = str(Path(new_path).resolve())
        wildcard_old = old_path + os.sep + "%"

        # 1. Update the directory's own record
        cursor.execute(
            """
            UPDATE directories SET dir_path = ?, dir_name = ?
            WHERE dir_path = ?
        """,
            (new_path, new_name, old_path),
        )

        # 2. Update all child directories
        child_dirs = cursor.execute(
            "SELECT dir_path FROM directories WHERE dir_path LIKE ?", (wildcard_old,)
        ).fetchall()
        for child in child_dirs:
            child_old_path = child["dir_path"]
            child_new_path = child_old_path.replace(old_path, new_path, 1)
            cursor.execute(
                "UPDATE directories SET dir_path = ?, parent_path = REPLACE(parent_path, ?, ?) WHERE dir_path = ?",
                (child_new_path, old_path, new_path, child_old_path),
            )

        # 3. Update all notes inside
        cursor.execute(
            "UPDATE notes SET note_dir = REPLACE(note_dir, ?, ?) WHERE note_dir = ? OR note_dir LIKE ?",
            (old_path, new_path, old_path, wildcard_old),
        )

        self.conn.commit()
        sys_log.log(
            LogSource.DB,
            LogLevel.INFO,
            f"Renamed directory from {old_path} to {new_path}",
        )
