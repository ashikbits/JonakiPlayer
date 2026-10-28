# SPDX-License-Identifier: GPL-3.0-or-later
"""
Torrent Stream Dialog for Jonaki Player.
Provides a PotPlayer-inspired GTK3 interface for opening magnet URIs or .torrent files,
retrieving metadata asynchronously, selecting files, and streaming video.
"""

import os
import sys
import threading
from typing import Optional, Callable, List, Any

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from torrent.models import TorrentFileInfo, TorrentStatusInfo
from torrent.manager import TorrentStreamManager
from torrent.engine import validate_magnet_uri


class TorrentStreamDialog(Gtk.Dialog):
    """
    Dialog for adding and managing torrent video streams.
    """

    def __init__(
        self,
        parent: Optional[Gtk.Window],
        manager: TorrentStreamManager,
        on_start_playback: Callable[[str, str], None],
        initial_source: Optional[str] = None,
    ):
        super().__init__(
            title="Open Torrent / Magnet Stream - Jonaki",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )
        self.set_default_size(760, 520)
        self.manager = manager
        self.on_start_playback = on_start_playback
        self.initial_source = initial_source

        self._cancel_event = threading.Event()
        self._is_loading = False
        self._status_timer_id: Optional[int] = None
        self._selected_file_idx: Optional[int] = None
        self._is_destroyed = False

        self.connect("destroy", self._on_destroy)
        self.connect("response", self._on_response)

        self._setup_ui()
        self._apply_styling()

        # Start periodic status refresh
        self._status_timer_id = GLib.timeout_add(500, self._on_status_tick)

        # If an initial source was provided (e.g. from clipboard or CLI), start loading
        if self.initial_source:
            self.source_entry.set_text(self.initial_source)
            GLib.idle_add(self._on_load_clicked, None)

    def _setup_ui(self) -> None:
        content_area = self.get_content_area()
        content_area.set_spacing(10)
        content_area.set_margin_top(12)
        content_area.set_margin_bottom(12)
        content_area.set_margin_start(16)
        content_area.set_margin_end(16)

        # 1. Top Source Input Area
        input_label = Gtk.Label(
            label="Magnet URI or Local .torrent File:",
            xalign=0.0,
        )
        content_area.pack_start(input_label, False, False, 0)

        source_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.source_entry = Gtk.Entry()
        self.source_entry.set_placeholder_text("magnet:?xt=urn:btih:... or /path/to/media.torrent")
        self.source_entry.set_hexpand(True)
        self.source_entry.connect("activate", self._on_load_clicked)
        source_box.pack_start(self.source_entry, True, True, 0)

        self.browse_btn = Gtk.Button(label="Browse File...")
        self.browse_btn.connect("clicked", self._on_browse_clicked)
        source_box.pack_start(self.browse_btn, False, False, 0)

        self.load_btn = Gtk.Button(label="Load Torrent")
        self.load_btn.get_style_context().add_class("suggested-action")
        self.load_btn.connect("clicked", self._on_load_clicked)
        source_box.pack_start(self.load_btn, False, False, 0)

        content_area.pack_start(source_box, False, False, 0)

        # 2. Status & Progress Feedback Bar
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.spinner = Gtk.Spinner()
        status_box.pack_start(self.spinner, False, False, 0)

        self.status_label = Gtk.Label(label="Paste a magnet link or choose a .torrent file to begin.", xalign=0.0)
        self.status_label.set_hexpand(True)
        self.status_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        status_box.pack_start(self.status_label, True, True, 0)

        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.set_sensitive(False)
        self.cancel_btn.connect("clicked", self._on_cancel_clicked)
        status_box.pack_start(self.cancel_btn, False, False, 0)

        content_area.pack_start(status_box, False, False, 0)

        # 3. File List View
        files_label = Gtk.Label(label="Files in Torrent (Select a video to stream):", xalign=0.0)
        content_area.pack_start(files_label, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        # ListStore: [index (int), name (str), size (str), type (str), is_video (bool)]
        self.liststore = Gtk.ListStore(int, str, str, str, bool)
        self.treeview = Gtk.TreeView(model=self.liststore)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.treeview.get_selection().connect("changed", self._on_selection_changed)
        self.treeview.connect("row-activated", self._on_row_activated)

        # Column 0: Index
        col_idx = Gtk.TreeViewColumn("#", Gtk.CellRendererText(), text=0)
        col_idx.set_fixed_width(45)
        col_idx.set_resizable(False)
        self.treeview.append_column(col_idx)

        # Column 1: Filename
        renderer_text = Gtk.CellRendererText()
        renderer_text.set_property("ellipsize", 3)
        col_name = Gtk.TreeViewColumn("File Name", renderer_text, text=1)
        col_name.set_expand(True)
        col_name.set_resizable(True)
        self.treeview.append_column(col_name)

        # Column 2: Size
        col_size = Gtk.TreeViewColumn("Size", Gtk.CellRendererText(), text=2)
        col_size.set_fixed_width(110)
        col_size.set_resizable(True)
        self.treeview.append_column(col_size)

        # Column 3: Type
        col_type = Gtk.TreeViewColumn("Kind", Gtk.CellRendererText(), text=3)
        col_type.set_fixed_width(80)
        col_type.set_resizable(False)
        self.treeview.append_column(col_type)

        scrolled.add(self.treeview)
        content_area.pack_start(scrolled, True, True, 0)

        # 4. Live Statistics Bar
        metrics_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        metrics_box.set_margin_top(4)

        self.rate_label = Gtk.Label(label="Down: 0 B/s", xalign=0.0)
        self.peers_label = Gtk.Label(label="Peers: 0", xalign=0.0)
        self.progress_label = Gtk.Label(label="Progress: 0.0%", xalign=0.0)

        metrics_box.pack_start(self.rate_label, False, False, 0)
        metrics_box.pack_start(self.peers_label, False, False, 0)
        metrics_box.pack_start(self.progress_label, False, False, 0)

        content_area.pack_start(metrics_box, False, False, 0)

        # 5. Dialog Action Buttons
        self.add_button("Close", Gtk.ResponseType.CLOSE)
        self.stream_btn = self.add_button("Stream Video", Gtk.ResponseType.OK)
        self.stream_btn.get_style_context().add_class("suggested-action")
        self.stream_btn.set_sensitive(False)

    def _apply_styling(self) -> None:
        css = b"""
        dialog, window {
            background-color: #1e1e1e;
            color: #dcdcdc;
        }
        entry {
            background-color: #2b2b2b;
            color: #ffffff;
            border: 1px solid #3d3d3d;
            border-radius: 3px;
            padding: 6px;
        }
        entry:focus {
            border-color: #4a90e2;
        }
        treeview {
            background-color: #252525;
            color: #dcdcdc;
        }
        treeview:selected {
            background-color: #4a90e2;
            color: #ffffff;
        }
        button {
            background-color: #2e2e2e;
            color: #ffffff;
            border: 1px solid #444444;
            border-radius: 3px;
            padding: 5px 14px;
        }
        button:hover {
            background-color: #3e3e3e;
        }
        button.suggested-action {
            background-color: #1a5fb4;
            color: #ffffff;
            border-color: #3584e4;
        }
        button.suggested-action:hover {
            background-color: #3584e4;
        }
        label {
            color: #cccccc;
        }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        self.get_style_context().add_provider(
            style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _on_browse_clicked(self, widget: Any) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Select Torrent File",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        chooser.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        torrent_filter = Gtk.FileFilter()
        torrent_filter.set_name("BitTorrent Files (*.torrent)")
        torrent_filter.add_pattern("*.torrent")
        chooser.add_filter(torrent_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("All Files (*.*)")
        all_filter.add_pattern("*")
        chooser.add_filter(all_filter)

        res = chooser.run()
        if res == Gtk.ResponseType.OK:
            filename = chooser.get_filename()
            if filename:
                self.source_entry.set_text(filename)
                self._on_load_clicked(None)
        chooser.destroy()

    def _on_load_clicked(self, widget: Any) -> None:
        source = self.source_entry.get_text().strip()
        if not source:
            self.status_label.set_text("Please enter a magnet URI or select a .torrent file.")
            return

        if not source.startswith("magnet:") and not os.path.isfile(source):
            self.status_label.set_text("Error: Specified torrent file does not exist.")
            return

        if source.startswith("magnet:") and not validate_magnet_uri(source):
            self.status_label.set_text("Error: Invalid magnet URI (missing BTIH info hash).")
            return

        self._is_loading = True
        self._cancel_event.clear()
        self.spinner.start()
        self.load_btn.set_sensitive(False)
        self.browse_btn.set_sensitive(False)
        self.cancel_btn.set_sensitive(True)
        self.stream_btn.set_sensitive(False)
        self.liststore.clear()
        self.status_label.set_text("Connecting to swarm & resolving metadata...")

        threading.Thread(
            target=self._worker_fetch_metadata, args=(source,), daemon=True
        ).start()

    def _worker_fetch_metadata(self, source: str) -> None:
        try:
            status = self.manager.prepare_torrent(
                source=source,
                timeout=60.0,
                cancel_event=self._cancel_event,
            )
            GLib.idle_add(self._on_metadata_loaded, status)
        except Exception as e:
            GLib.idle_add(self._on_metadata_error, str(e))

    def _on_metadata_loaded(self, status: TorrentStatusInfo) -> None:
        if self._is_destroyed:
            return

        self._is_loading = False
        self.spinner.stop()
        self.load_btn.set_sensitive(True)
        self.browse_btn.set_sensitive(True)
        self.cancel_btn.set_sensitive(False)

        files = status.files
        if not files:
            self.status_label.set_text("Metadata loaded, but no files found in torrent.")
            return

        self.liststore.clear()
        best_video_idx = None
        best_video_size = -1

        for f in files:
            kind_str = "Video" if f.is_video else "Other"
            tree_iter = self.liststore.append([f.index, f.name, f.formatted_size, kind_str, f.is_video])
            if f.is_video and f.size > best_video_size:
                best_video_size = f.size
                best_video_idx = f.index

        if best_video_idx is None and files:
            best_video_idx = files[0].index

        # Select the best video in TreeView
        self._select_file_index_in_tree(best_video_idx)
        self.status_label.set_text(
            f"Ready: '{status.name}' ({len(files)} files). Select a video to stream."
        )

    def _select_file_index_in_tree(self, target_idx: int) -> None:
        for row in self.liststore:
            if row[0] == target_idx:
                self.treeview.get_selection().select_iter(row.iter)
                self._selected_file_idx = target_idx
                self.stream_btn.set_sensitive(True)
                break

    def _on_metadata_error(self, err_msg: str) -> None:
        if self._is_destroyed:
            return
        self._is_loading = False
        self.spinner.stop()
        self.load_btn.set_sensitive(True)
        self.browse_btn.set_sensitive(True)
        self.cancel_btn.set_sensitive(False)
        self.stream_btn.set_sensitive(False)
        self.status_label.set_text(f"Failed: {err_msg}")

    def _on_cancel_clicked(self, widget: Any) -> None:
        self._cancel_event.set()
        self.manager.stop_session()
        self._is_loading = False
        self.spinner.stop()
        self.load_btn.set_sensitive(True)
        self.browse_btn.set_sensitive(True)
        self.cancel_btn.set_sensitive(False)
        self.status_label.set_text("Operation cancelled by user.")

    def _on_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        model, tree_iter = selection.get_selected()
        if tree_iter is not None:
            self._selected_file_idx = model.get_value(tree_iter, 0)
            self.stream_btn.set_sensitive(True)
        else:
            self._selected_file_idx = None
            self.stream_btn.set_sensitive(False)

    def _on_row_activated(self, treeview: Gtk.TreeView, path: Gtk.TreePath, column: Gtk.TreeViewColumn) -> None:
        self._on_stream_clicked()

    def _on_status_tick(self) -> bool:
        if self._is_destroyed:
            return False

        status = self.manager.get_status()
        self.rate_label.set_text(f"Down: {status.formatted_download_rate}")
        self.peers_label.set_text(f"Peers: {status.num_peers} ({status.num_seeds} seeds)")
        self.progress_label.set_text(f"Progress: {status.formatted_progress}")
        return True

    def _on_stream_clicked(self) -> None:
        if self._selected_file_idx is None:
            return

        try:
            # Find file name from liststore
            file_name = "Torrent Video"
            for row in self.liststore:
                if row[0] == self._selected_file_idx:
                    file_name = row[1]
                    break

            stream_url = self.manager.start_streaming(file_index=self._selected_file_idx)
            self.status_label.set_text(f"Streaming started for '{file_name}'!")

            # Pass stream URL to main player callback
            if self.on_start_playback:
                self.on_start_playback(stream_url, file_name)

            self.response(Gtk.ResponseType.OK)
        except Exception as e:
            self.status_label.set_text(f"Error starting stream: {e}")

    def _on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.OK:
            self._on_stream_clicked()
        elif response_id in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            if self._is_loading:
                self._cancel_event.set()
                self.manager.stop_session()
            self.destroy()

    def _on_destroy(self, widget: Any) -> None:
        self._is_destroyed = True
        self._cancel_event.set()
        if self._status_timer_id is not None:
            GLib.source_remove(self._status_timer_id)
            self._status_timer_id = None
