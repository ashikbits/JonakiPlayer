"""
Jonaki for Linux - Playlist Window (F8 / F12)
Album tabs, search filter, shuffle, sorting, and drag-and-drop.
"""

import os
import random
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from typing import Any, List, Dict


class PlaylistWindow(Gtk.Window):
    def __init__(self, player_controller: Any):
        super().__init__(title="Jonaki Playlist (F8 / F12)")
        self.player = player_controller
        if isinstance(player_controller, Gtk.Window):
            self.set_transient_for(player_controller)
        self.set_default_size(360, 520)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_margin_start(8)
        vbox.set_margin_end(8)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)
        self.add(vbox)

        # Search Bar
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.connect("search-changed", self._on_search_changed)
        vbox.pack_start(self.search_entry, False, False, 0)

        # TreeView List: (Index, Title, Duration, FilePath)
        self.list_store = Gtk.ListStore(int, str, str, str)
        self.tree_view = Gtk.TreeView(model=self.list_store)
        self.tree_view.set_headers_visible(True)
        self.tree_view.set_reorderable(True)
        self.tree_view.connect("row-activated", self._on_row_activated)
        self.tree_view.connect("drag-end", self._on_drag_end)

        # Drag and Drop support for URI lists
        self.tree_view.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.tree_view.drag_dest_add_uri_targets()
        self.tree_view.connect("drag-data-received", self._on_drag_data_received)
        self.tree_view.connect("button-press-event", self._on_tree_button_press)

        # Columns
        col_idx = Gtk.TreeViewColumn("#", Gtk.CellRendererText(), text=0)
        col_idx.set_fixed_width(40)
        self.tree_view.append_column(col_idx)

        col_title = Gtk.TreeViewColumn("Title", Gtk.CellRendererText(), text=1)
        col_title.set_expand(True)
        self.tree_view.append_column(col_title)

        col_dur = Gtk.TreeViewColumn("Time", Gtk.CellRendererText(), text=2)
        col_dur.set_fixed_width(60)
        self.tree_view.append_column(col_dur)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.add(self.tree_view)
        vbox.pack_start(scrolled, True, True, 0)

        # Bottom Bar: Summary & Buttons
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.lbl_summary = Gtk.Label(label="0 items | 00:00:00")
        self.lbl_summary.set_xalign(0.0)
        bottom_box.pack_start(self.lbl_summary, True, True, 0)

        btn_add = Gtk.Button(label="+ Add")
        btn_add.connect("clicked", self._on_add_clicked)
        bottom_box.pack_end(btn_add, False, False, 0)

        btn_remove = Gtk.Button(label="- Remove")
        btn_remove.connect("clicked", self._on_remove_clicked)
        bottom_box.pack_end(btn_remove, False, False, 0)

        btn_clear = Gtk.Button(label="Clear")
        btn_clear.connect("clicked", self._on_clear_clicked)
        bottom_box.pack_end(btn_clear, False, False, 0)

        btn_sort = Gtk.Button(label="Sort")
        btn_sort.connect("clicked", self._on_sort_clicked)
        bottom_box.pack_end(btn_sort, False, False, 0)

        btn_shuffle = Gtk.Button(label="Shuffle")
        btn_shuffle.connect("clicked", self._on_shuffle_clicked)
        bottom_box.pack_end(btn_shuffle, False, False, 0)

        vbox.pack_start(bottom_box, False, False, 4)

        self.connect("delete-event", lambda w, e: self.hide_on_delete())
        self.connect("key-press-event", self._on_key_press)

    def _on_key_press(self, widget, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_F8, Gdk.KEY_F12):
            self.hide()
            return True
        elif event.keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace, Gdk.KEY_KP_Delete):
            self._on_remove_clicked(None)
            return True
        return False

    def _on_drag_end(self, widget, context):
        if self.search_entry.get_text().strip():
            return
        new_playlist = []
        current_path = None
        cur_idx = getattr(self.player, "current_index", -1)
        if 0 <= cur_idx < len(self.player.playlist):
            current_path = self.player.playlist[cur_idx]["path"]

        path_map = {item["path"]: item for item in self.player.playlist}
        for row in self.list_store:
            fp = row[3]
            if fp in path_map:
                new_playlist.append(path_map[fp])

        if len(new_playlist) == len(self.player.playlist):
            self.player.playlist = new_playlist
            if current_path:
                for i, it in enumerate(self.player.playlist):
                    if it["path"] == current_path:
                        self.player.current_index = i
                        break
            try:
                self.player.db.save_playlist(self.player.playlist)
            except Exception:
                pass
            for i, row in enumerate(self.list_store):
                row[0] = i + 1

    def _on_drag_data_received(self, widget, drag_context, x, y, data, info, time):
        uris = data.get_uris()
        if uris:
            files = []
            for u in uris:
                p = GLib.filename_from_uri(u)[0] if u.startswith("file://") else u
                if p:
                    files.append(p)
            if files:
                self.player.add_files_to_playlist(files, auto_play=False, clear_existing=False)
                drag_context.finish(True, False, time)
                return
        drag_context.finish(False, False, time)

    def _on_tree_button_press(self, tree_view, event):
        if event.button == 3:
            path_info = tree_view.get_path_at_pos(int(event.x), int(event.y))
            if path_info:
                path, col, _, _ = path_info
                tree_view.get_selection().select_path(path)
            menu = Gtk.Menu()
            item_play = Gtk.MenuItem(label="Play")
            def _play_selected(w):
                model, rows = tree_view.get_selection().get_selected_rows()
                if rows:
                    self._on_row_activated(tree_view, rows[0], None)
            item_play.connect("activate", _play_selected)
            menu.append(item_play)

            item_remove = Gtk.MenuItem(label="Remove")
            item_remove.connect("activate", self._on_remove_clicked)
            menu.append(item_remove)

            menu.append(Gtk.SeparatorMenuItem())

            item_clear = Gtk.MenuItem(label="Clear Playlist")
            item_clear.connect("activate", self._on_clear_clicked)
            menu.append(item_clear)

            menu.show_all()
            menu.popup(None, None, None, None, event.button, event.time)
            return True
        return False

    def _on_clear_clicked(self, widget):
        if hasattr(self.player, "handle_command"):
            self.player.handle_command("CMD_CLEAR_PLAYLIST")
        else:
            if hasattr(self.player, "playlist") and isinstance(self.player.playlist, list):
                self.player.playlist.clear()
            if hasattr(self.player, "current_index"):
                self.player.current_index = -1
            if hasattr(self.player, "core") and hasattr(self.player.core, "stop"):
                self.player.core.stop()
            self.update_playlist([])

    def update_playlist(self, items: List[Dict[str, Any]]) -> None:
        query = self.search_entry.get_text().strip()
        if query:
            self._on_search_changed(self.search_entry)
            return

        self.list_store.clear()
        total_sec = 0.0
        cur_idx = getattr(self.player, "current_index", -1)
        active_iter = None
        for i, item in enumerate(items):
            item_path = item.get("path") or ""
            raw_title = item.get("title") or (os.path.basename(item_path) if item_path else "Unknown")
            is_active = (isinstance(cur_idx, int) and i == cur_idx)
            title = f"▶ {raw_title}" if is_active else raw_title
            dur = item.get("duration", 0.0)
            total_sec += dur
            dur_str = self._format_duration(dur)
            row_iter = self.list_store.append([i + 1, title, dur_str, item_path])
            if is_active:
                active_iter = row_iter

        self.lbl_summary.set_text(f"{len(items)} items | {self._format_duration(total_sec)}")
        if active_iter is not None:
            path = self.list_store.get_path(active_iter)
            self.tree_view.get_selection().select_iter(active_iter)
            try:
                self.tree_view.scroll_to_cell(path, None, True, 0.5, 0.0)
            except Exception:
                pass

    def _format_duration(self, sec: float) -> str:
        s = int(max(0.0, sec))
        h = s // 3600
        m = (s % 3600) // 60
        s = s % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _on_row_activated(self, tree_view, path, column):
        itr = self.list_store.get_iter(path)
        if itr:
            idx = self.list_store.get_value(itr, 0) - 1
            if 0 <= idx < len(self.player.playlist):
                self.player.play_index(idx)
            else:
                file_path = self.list_store.get_value(itr, 3)
                self.player.play_file(file_path)

    def _on_add_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(title="Add File(s) to Playlist", parent=self,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        dialog.set_select_multiple(True)
        if dialog.run() == Gtk.ResponseType.OK:
            filenames = dialog.get_filenames()
            self.player.add_files_to_playlist(filenames)
        dialog.destroy()

    def _on_remove_clicked(self, widget):
        selection = self.tree_view.get_selection()
        model, itr = selection.get_selected()
        if itr:
            idx = model.get_value(itr, 0) - 1
            self.player.remove_from_playlist(idx)
            if self.search_entry.get_text().strip():
                self._on_search_changed(self.search_entry)

    def _on_sort_clicked(self, widget):
        self.player.sort_playlist()

    def _on_shuffle_clicked(self, widget):
        self.player.shuffle_playlist()

    def _on_search_changed(self, entry):
        # Quick filter implementation preserving original playlist indices
        query = entry.get_text().lower().strip()
        filtered = []
        cur_idx = getattr(self.player, "current_index", -1)
        for orig_idx, item in enumerate(self.player.playlist):
            title = (item.get("title") or "").lower()
            path = (item.get("path") or "").lower()
            if not query or ((query in title) or (query in path)):
                filtered.append((orig_idx, item))

        self.list_store.clear()
        total_sec = 0.0
        active_iter = None
        for orig_idx, item in filtered:
            item_path = item.get("path") or ""
            raw_title = item.get("title") or (os.path.basename(item_path) if item_path else "Unknown")
            is_active = (isinstance(cur_idx, int) and orig_idx == cur_idx)
            title = f"▶ {raw_title}" if is_active else raw_title
            dur = item.get("duration", 0.0)
            total_sec += dur
            dur_str = self._format_duration(dur)
            row_iter = self.list_store.append([orig_idx + 1, title, dur_str, item_path])
            if is_active:
                active_iter = row_iter
        self.lbl_summary.set_text(f"{len(filtered)} items | {self._format_duration(total_sec)}")
        if active_iter is not None:
            path = self.list_store.get_path(active_iter)
            self.tree_view.get_selection().select_iter(active_iter)
            try:
                self.tree_view.scroll_to_cell(path, None, True, 0.5, 0.0)
            except Exception:
                pass
