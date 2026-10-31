"""
Jonaki for Linux - Online Subtitle Search Dialog
Provides a GUI dialog for searching and downloading subtitles via OpenSubtitles hash and text search.
"""

import os
import tempfile
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
from typing import Optional, Callable, Any

from subtitle.online_search import SubtitleSearchClient, compute_opensubtitles_hash


LANGUAGES = [
    ("English", "eng"),
    ("All Languages", "all"),
    ("Spanish", "spa"),
    ("French", "fre"),
    ("German", "ger"),
    ("Japanese", "jpn"),
    ("Korean", "kor"),
    ("Chinese", "chi"),
    ("Russian", "rus"),
    ("Arabic", "ara"),
    ("Hindi", "hin"),
    ("Bengali", "ben"),
    ("Portuguese", "por"),
    ("Italian", "ita"),
]


class SubtitleSearchDialog(Gtk.Dialog):
    """
    Dialog for searching online subtitles via hash checksum and keyword queries.
    """
    def __init__(self, parent: Optional[Gtk.Window], current_file: Optional[str],
                 on_subtitle_downloaded: Callable[[str], None]):
        super().__init__(title="Search Subtitles Online - Jonaki",
                         transient_for=parent,
                         modal=True,
                         destroy_with_parent=True)
        self.set_default_size(720, 480)
        self.current_file = current_file
        self.on_subtitle_downloaded = on_subtitle_downloaded
        self.client = SubtitleSearchClient()
        self._is_searching = False
        self._is_destroyed = False

        self.connect("destroy", self._on_destroy)
        self.connect("response", self._on_response)

        self._setup_ui()
        self._apply_styling()

        # If a file is currently playing, trigger an initial hash search automatically
        if self.current_file and os.path.exists(self.current_file):
            GLib.idle_add(self._on_search_by_hash_clicked, None)

    def _setup_ui(self) -> None:
        content_area = self.get_content_area()
        content_area.set_spacing(10)
        content_area.set_margin_top(12)
        content_area.set_margin_bottom(12)
        content_area.set_margin_start(16)
        content_area.set_margin_end(16)

        # Top search controls
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        # Default query from filename
        default_query = ""
        if self.current_file:
            base = os.path.basename(self.current_file)
            name, _ = os.path.splitext(base)
            default_query = name

        self.query_entry = Gtk.Entry()
        self.query_entry.set_placeholder_text("Enter movie or episode title...")
        self.query_entry.set_text(default_query)
        self.query_entry.set_hexpand(True)
        self.query_entry.connect("activate", self._on_search_clicked)
        search_box.pack_start(self.query_entry, True, True, 0)

        # Language dropdown
        self.lang_combo = Gtk.ComboBoxText()
        for label, code in LANGUAGES:
            self.lang_combo.append(code, label)
        self.lang_combo.set_active(0)  # Default: English
        search_box.pack_start(self.lang_combo, False, False, 0)

        # Search by Query button
        self.search_btn = Gtk.Button(label="Search")
        self.search_btn.connect("clicked", self._on_search_clicked)
        search_box.pack_start(self.search_btn, False, False, 0)

        # Hash search button
        self.hash_btn = Gtk.Button(label="Match Hash")
        self.hash_btn.set_tooltip_text("Search exact matching subtitles using OpenSubtitles file checksum")
        self.hash_btn.connect("clicked", self._on_search_by_hash_clicked)
        if not self.current_file or not os.path.exists(self.current_file):
            self.hash_btn.set_sensitive(False)
        search_box.pack_start(self.hash_btn, False, False, 0)

        content_area.pack_start(search_box, False, False, 0)

        # Results TreeView inside ScrolledWindow
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        # Columns: [Title, Language, Format, Rating, DownloadURL]
        self.liststore = Gtk.ListStore(str, str, str, str, str)
        self.treeview = Gtk.TreeView(model=self.liststore)
        self.treeview.connect("row-activated", self._on_row_activated)

        # Column 0: Release Title
        renderer_text = Gtk.CellRendererText()
        renderer_text.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_title = Gtk.TreeViewColumn("Subtitle / Release Name", renderer_text, text=0)
        col_title.set_expand(True)
        col_title.set_resizable(True)
        self.treeview.append_column(col_title)

        # Column 1: Language
        renderer_lang = Gtk.CellRendererText()
        col_lang = Gtk.TreeViewColumn("Language", renderer_lang, text=1)
        col_lang.set_min_width(90)
        self.treeview.append_column(col_lang)

        # Column 2: Format
        renderer_fmt = Gtk.CellRendererText()
        col_fmt = Gtk.TreeViewColumn("Format", renderer_fmt, text=2)
        col_fmt.set_min_width(70)
        self.treeview.append_column(col_fmt)

        # Column 3: Rating
        renderer_rating = Gtk.CellRendererText()
        col_rating = Gtk.TreeViewColumn("Rating", renderer_rating, text=3)
        col_rating.set_min_width(60)
        self.treeview.append_column(col_rating)

        scroll.add(self.treeview)
        content_area.pack_start(scroll, True, True, 0)

        # Status and Spinner row
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.spinner = Gtk.Spinner()
        status_box.pack_start(self.spinner, False, False, 0)

        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_halign(Gtk.Align.START)
        status_box.pack_start(self.status_label, True, True, 0)

        content_area.pack_start(status_box, False, False, 0)

        # Action Buttons
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.download_btn = self.add_button("Download & Apply", Gtk.ResponseType.OK)
        self.download_btn.connect("clicked", self._on_download_clicked)
        self.download_btn.set_sensitive(False)

        # Selection changed triggers download button sensitivity
        selection = self.treeview.get_selection()
        selection.connect("changed", self._on_selection_changed)

    def _apply_styling(self) -> None:
        css = b"""
        dialog {
            background-color: #1e1e1e;
            color: #dcdcdc;
        }
        entry {
            background-color: #2b2b2b;
            color: #ffffff;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            padding: 4px 8px;
        }
        combobox button {
            background-color: #2b2b2b;
            color: #ffffff;
            border: 1px solid #3c3c3c;
        }
        treeview {
            background-color: #181818;
            color: #e0e0e0;
        }
        treeview:selected {
            background-color: #0d47a1;
            color: #ffffff;
        }
        button {
            background-color: #2d2d2d;
            color: #ffffff;
            border: 1px solid #444444;
            border-radius: 4px;
            padding: 4px 12px;
        }
        button:hover {
            background-color: #3d3d3d;
        }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        self.get_style_context().add_provider(
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _on_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        model, tree_iter = selection.get_selected()
        self.download_btn.set_sensitive(tree_iter is not None)

    def _on_search_clicked(self, widget: Any) -> None:
        query = self.query_entry.get_text().strip()
        if not query:
            return
        lang = self.lang_combo.get_active_id() or "eng"
        self._start_search(lambda: self.client.search_by_query(query, lang=lang), f"Searching for '{query}'...")

    def _on_search_by_hash_clicked(self, widget: Any) -> None:
        if not self.current_file or not os.path.exists(self.current_file):
            self.status_label.set_text("No active local video file to compute hash.")
            return
        lang = self.lang_combo.get_active_id() or "eng"
        self._start_search(lambda: self.client.search_by_hash(self.current_file, lang=lang), "Matching video hash with OpenSubtitles...")

    def _start_search(self, search_func: Callable[[], list], status_msg: str) -> None:
        if self._is_searching:
            return
        self._is_searching = True
        self.spinner.start()
        self.status_label.set_text(status_msg)
        self.search_btn.set_sensitive(False)
        self.hash_btn.set_sensitive(False)
        self.liststore.clear()

        def _worker():
            try:
                results = search_func()
            except Exception as e:
                results = []
                err_msg = str(e)
            else:
                err_msg = ""
            GLib.idle_add(self._on_search_finished, results, err_msg)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_destroy(self, widget: Any) -> None:
        self._is_destroyed = True

    def _on_response(self, dialog: Any, response_id: int) -> None:
        if response_id in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()

    def _on_search_finished(self, results: list, err_msg: str) -> None:
        if getattr(self, "_is_destroyed", False):
            return False
        self._is_searching = False
        self.spinner.stop()
        self.search_btn.set_sensitive(True)
        if self.current_file and os.path.exists(self.current_file):
            self.hash_btn.set_sensitive(True)

        if err_msg:
            self.status_label.set_text(f"Search error: {err_msg}")
            return

        if not results:
            self.status_label.set_text("No subtitles found. Try refining your search query.")
            return

        for r in results:
            title = r.get("title") or "Unknown"
            lang = r.get("language") or ""
            fmt = (r.get("format") or "srt").upper()
            rating = f"★ {r.get('rating', '0.0')}"
            url = r.get("download_url") or ""
            self.liststore.append([title, lang, fmt, rating, url])

        self.status_label.set_text(f"Found {len(results)} subtitle(s).")

    def _on_row_activated(self, treeview: Gtk.TreeView, path: Gtk.TreePath, column: Gtk.TreeViewColumn) -> None:
        self._on_download_clicked(None)

    def _on_download_clicked(self, widget: Any) -> None:
        selection = self.treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if not tree_iter:
            return

        title = model[tree_iter][0]
        lang = str(model[tree_iter][1]).strip().lower()
        fmt = model[tree_iter][2].lower()
        url = model[tree_iter][4]

        if not url:
            self.status_label.set_text("Selected subtitle has no download URL.")
            return

        self.spinner.start()
        self.status_label.set_text(f"Downloading '{title}'...")
        self.download_btn.set_sensitive(False)

        # Target destination path: save alongside video file if accessible
        ext = fmt if fmt in ("srt", "ass", "vtt", "sub") else "srt"
        dest_path = None
        if self.current_file and os.path.exists(self.current_file):
            video_dir = os.path.dirname(os.path.abspath(self.current_file))
            base_name = os.path.splitext(os.path.basename(self.current_file))[0]
            prefix = f"{base_name}.{lang}" if lang else base_name
            candidate = os.path.join(video_dir, f"{prefix}.{ext}")
            if os.path.exists(candidate):
                counter = 1
                while os.path.exists(os.path.join(video_dir, f"{prefix}.{counter}.{ext}")):
                    counter += 1
                candidate = os.path.join(video_dir, f"{prefix}.{counter}.{ext}")
            if os.access(video_dir, os.W_OK):
                dest_path = candidate
        if not dest_path:
            cache_dir = os.path.expanduser("~/.cache/jonaki/subtitles")
            os.makedirs(cache_dir, exist_ok=True)
            dest_path = os.path.join(cache_dir, f"sub_{hash(url) & 0xFFFFFFFF}.{ext}")

        def _download_worker():
            success = self.client.download_subtitle(url, dest_path)
            GLib.idle_add(self._on_download_finished, success, dest_path, title)

        threading.Thread(target=_download_worker, daemon=True).start()

    def _on_download_finished(self, success: bool, dest_path: str, title: str) -> None:
        if getattr(self, "_is_destroyed", False):
            return False
        self.spinner.stop()
        self.download_btn.set_sensitive(True)
        if success and os.path.exists(dest_path):
            self.status_label.set_text(f"Downloaded: {os.path.basename(dest_path)}")
            if self.on_subtitle_downloaded:
                self.on_subtitle_downloaded(dest_path)
            self.response(Gtk.ResponseType.OK)
            self.destroy()
        else:
            self.status_label.set_text(f"Failed to download '{title}'.")
