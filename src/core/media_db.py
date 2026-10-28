"""
Jonaki for Linux - Media Database & Persistence Layer
Stores playback history, resume points, visual bookmarks, album favorites, and presets.
"""

import os
import sqlite3
import time
import shutil
import contextlib
from typing import List, Dict, Optional, Any


class MediaDatabase:
    """
    SQLite-backed persistence layer for Jonaki.
    Default path: ~/.config/jonaki/mediadb.sqlite
    """
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            config_dir = os.path.expanduser("~/.config/jonaki")
            os.makedirs(config_dir, exist_ok=True)
            db_path = os.path.join(config_dir, "mediadb.sqlite")
            # Migrate legacy potplayer db if present and new db doesn't exist
            legacy_db = os.path.expanduser("~/.config/potplayer/mediadb.sqlite")
            if not os.path.exists(db_path) and os.path.exists(legacy_db):
                try:
                    shutil.copy2(legacy_db, db_path)
                except Exception:
                    pass
        self.db_path = db_path
        try:
            self._init_database()
        except sqlite3.DatabaseError as e:
            # Corrupted database: quarantine and recreate clean database
            try:
                corrupt_backup = f"{self.db_path}.corrupt.{int(time.time())}"
                if os.path.exists(self.db_path):
                    shutil.move(self.db_path, corrupt_backup)
                for ext in ("-wal", "-shm"):
                    p = self.db_path + ext
                    if os.path.exists(p):
                        try:
                            os.unlink(p)
                        except OSError:
                            pass
            except Exception:
                pass
            self._init_database()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_database(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode = WAL;")
            
            # History & Resume points
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS playback_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                title TEXT,
                duration REAL,
                last_position REAL NOT NULL,
                last_played_at REAL NOT NULL,
                completed INTEGER DEFAULT 0,
                audio_track INTEGER DEFAULT 1,
                subtitle_track INTEGER DEFAULT 1,
                volume REAL DEFAULT 100.0
            );
            """)

            # Check and migrate legacy columns if table was created by older schema
            cursor.execute("PRAGMA table_info(playback_history)")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            if existing_cols:
                if "audio_track" not in existing_cols:
                    cursor.execute("ALTER TABLE playback_history ADD COLUMN audio_track INTEGER DEFAULT 1")
                if "subtitle_track" not in existing_cols:
                    cursor.execute("ALTER TABLE playback_history ADD COLUMN subtitle_track INTEGER DEFAULT 1")
                if "volume" not in existing_cols:
                    cursor.execute("ALTER TABLE playback_history ADD COLUMN volume REAL DEFAULT 100.0")

            # Bookmarks
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                timestamp REAL NOT NULL,
                title TEXT,
                thumbnail_path TEXT,
                created_at REAL NOT NULL
            );
            """)

            # Playlist Albums / Favorites
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlist_albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_name TEXT UNIQUE NOT NULL,
                created_at REAL NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                title TEXT,
                duration REAL,
                order_index INTEGER NOT NULL,
                FOREIGN KEY(album_id) REFERENCES playlist_albums(id) ON DELETE CASCADE
            );
            """)

            # Settings & Presets
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """)

            # Create Default Album if not exists
            cursor.execute("INSERT OR IGNORE INTO playlist_albums (id, album_name, created_at) VALUES (1, 'Default', ?)", (time.time(),))
            conn.commit()

    # --- Resume & History ---

    def save_playback_position(self, file_path: str, position: float, duration: float = 0.0,
                               title: Optional[str] = None, audio_track: int = 1,
                               subtitle_track: int = 1, volume: float = 100.0) -> None:
        completed = 1 if duration > 0 and position >= duration * 0.95 else 0
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO playback_history (file_path, title, duration, last_position, last_played_at, completed, audio_track, subtitle_track, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                title = coalesce(?, title),
                duration = max(coalesce(duration, 0.0), coalesce(?, 0.0)),
                last_position = case when ? > 0.0 then ? else last_position end,
                last_played_at = ?,
                completed = ?,
                audio_track = ?,
                subtitle_track = ?,
                volume = ?
            """, (file_path, title, duration, position, now, completed, audio_track, subtitle_track, volume,
                  title, duration, position, position, now, completed, audio_track, subtitle_track, volume))
            conn.commit()

    def get_playback_position(self, file_path: str) -> Optional[float]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_position, completed FROM playback_history WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                if row["completed"]:
                    return 0.0  # Finished video restarts from beginning
                return float(row["last_position"])
            return None

    def get_recent_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT file_path, title, duration, last_position, last_played_at, completed
            FROM playback_history ORDER BY last_played_at DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def add_to_history(self, file_path: str, title: Optional[str] = None, duration: float = 0.0,
                       position: float = 0.0) -> None:
        """
        Adds or updates a media file in the playback history ledger.
        Preserves existing last_position if position is 0.0 or not specified.
        """
        if position <= 0.0:
            existing_pos = self.get_playback_position(file_path)
            if existing_pos is not None and existing_pos > 0.0:
                position = existing_pos
        self.save_playback_position(file_path=file_path, position=position, duration=duration, title=title)

    def clear_history(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM playback_history")
            conn.commit()

    # --- Bookmarks ---

    def add_bookmark(self, file_path: str, timestamp: float, title: Optional[str] = None, thumbnail_path: Optional[str] = None) -> int:
        if title is None:
            # Format timestamp as hh:mm:ss
            hrs = int(timestamp // 3600)
            mins = int((timestamp % 3600) // 60)
            secs = int(timestamp % 60)
            title = f"Bookmark at {hrs:02d}:{mins:02d}:{secs:02d}"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO bookmarks (file_path, timestamp, title, thumbnail_path, created_at)
            VALUES (?, ?, ?, ?, ?)
            """, (file_path, timestamp, title, thumbnail_path, time.time()))
            conn.commit()
            return cursor.lastrowid

    def get_bookmarks(self, file_path: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, file_path, timestamp, title, thumbnail_path, created_at
            FROM bookmarks WHERE file_path = ? ORDER BY timestamp ASC
            """, (file_path,))
            return [dict(row) for row in cursor.fetchall()]

    def delete_bookmark(self, bookmark_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
            conn.commit()

    def clear_bookmarks(self, file_path: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bookmarks WHERE file_path = ?", (file_path,))
            conn.commit()

    # --- Playlists & Albums ---

    def get_albums(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, album_name FROM playlist_albums ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def add_album(self, album_name: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO playlist_albums (album_name, created_at) VALUES (?, ?)", (album_name, time.time()))
            conn.commit()
            cursor.execute("SELECT id FROM playlist_albums WHERE album_name = ?", (album_name,))
            row = cursor.fetchone()
            return row["id"] if row else 1

    def get_playlist_items(self, album_id: int = 1) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, file_path, title, duration, order_index
            FROM playlist_items WHERE album_id = ? ORDER BY order_index ASC
            """, (album_id,))
            return [dict(row) for row in cursor.fetchall()]

    def save_playlist(self, items: List[Dict[str, Any]], album_id: int = 1) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM playlist_items WHERE album_id = ?", (album_id,))
            for idx, item in enumerate(items):
                path = item.get("path") or item.get("file_path", "")
                title = item.get("title") or (os.path.basename(path) if path else "")
                cursor.execute("""
                INSERT INTO playlist_items (album_id, file_path, title, duration, order_index)
                VALUES (?, ?, ?, ?, ?)
                """, (album_id, path, title, item.get("duration", 0.0), idx))
            conn.commit()

    # --- Settings Key-Value ---

    def set_setting(self, key: str, value: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row["value"]
            return default
