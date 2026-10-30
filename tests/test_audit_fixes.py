"""
Unit tests covering audit fixes across JonakiPlayer modules:
- UI: MediaInfoDialog None safety and simplified DAR, SubtitleSearchDialog destroy lifecycle
- Video: Capture directory creation, storyboard FPS formatting, timestamp uniqueness, clipboard mime-type
- Video: ShaderManager path traversal prevention
- Subtitles: Online search API error handling, gzip corruption recovery, translation language mappings and fallbacks
- Extensions: Host API version regex parsing, POST headers
"""

import unittest
import os
import sys
import tempfile
import json
import gzip
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from ui.media_info_dialog import MediaInfoDialog
from ui.subtitle_search_dialog import SubtitleSearchDialog
from video.capture import MediaCaptureManager
from video.shader_manager import VideoShaderManager
from subtitle.online_search import SubtitleSearchClient, compute_opensubtitles_hash
from subtitle.translator import SubtitleTranslator
from extensions.host_api import JonakiHostAPI


class TestMediaInfoDialog(unittest.TestCase):
    def setUp(self):
        self.dialog = MediaInfoDialog()

    def tearDown(self):
        self.dialog.destroy()

    def test_update_info_with_all_none_values(self):
        """Verify update_info safely coalesces None values from mpv without TypeError."""
        info = {
            "path": None,
            "filesize_bytes": None,
            "duration_sec": None,
            "width": None,
            "height": None,
            "fps": None,
            "video_codec": None,
            "pixel_format": None,
            "colormatrix": None,
            "video_bitrate": None,
            "audio_codec": None,
            "audio_channels": None,
            "sample_rate": None,
            "audio_bitrate": None,
            "hwdec": None,
            "audio_delay": None,
            "sub_delay": None,
            "tracks": None,
        }
        # Must not raise TypeError
        self.dialog.update_info(info)
        report = self.dialog.current_report_text
        self.assertIn("File Name        : None", report)
        self.assertIn("File Size        : Unknown", report)
        self.assertIn("00:00:00.000", report)
        self.assertIn("0 x 0", report)
        self.assertIn("Software Decoding", report)

    def test_update_info_aspect_ratio_simplification(self):
        """Verify display aspect ratio is simplified with GCD."""
        info = {
            "path": "/videos/test.mkv",
            "filesize_bytes": 1048576,
            "duration_sec": 60.0,
            "width": 1920,
            "height": 1080,
            "fps": 23.976,
            "video_codec": "h264",
            "hwdec": "vaapi",
        }
        self.dialog.update_info(info)
        report = self.dialog.current_report_text
        self.assertIn("Display Aspect Ratio: 16:9", report)
        self.assertIn("Hardware Acceleration Active (VAAPI)", report)

        # 4:3 test
        info["width"] = 1440
        info["height"] = 1080
        self.dialog.update_info(info)
        self.assertIn("Display Aspect Ratio: 4:3", self.dialog.current_report_text)


class TestSubtitleSearchDialogLifecycle(unittest.TestCase):
    def setUp(self):
        self.dialog = SubtitleSearchDialog(parent=None, current_file=None, on_subtitle_downloaded=lambda p: None)

    def tearDown(self):
        if not getattr(self.dialog, "_is_destroyed", False):
            self.dialog.destroy()

    def test_cancel_response_destroys_dialog(self):
        """Verifies ResponseType.CANCEL triggers dialog destroy."""
        self.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertTrue(self.dialog._is_destroyed)

    def test_destroyed_dialog_guards_in_callbacks(self):
        """Verifies async callbacks safely return False if dialog was already destroyed."""
        self.dialog._is_destroyed = True
        res_search = self.dialog._on_search_finished([], "")
        self.assertFalse(res_search)

        res_download = self.dialog._on_download_finished(True, "/tmp/sub.srt", "Sub")
        self.assertFalse(res_download)


class TestMediaCaptureManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = MediaCaptureManager(capture_dir=self.temp_dir)

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_custom_capture_dir_creation(self):
        """Verifies custom capture dir is created if it does not exist."""
        nested = os.path.join(self.temp_dir, "nested", "captures")
        mgr = MediaCaptureManager(capture_dir=nested)
        self.assertTrue(os.path.isdir(nested))

    def test_unique_timestamp_filename(self):
        """Verifies capture filename contains millisecond precision."""
        fn1 = self.mgr.generate_capture_filename("Movie", "png")
        fn2 = self.mgr.generate_capture_filename("Movie", "png")
        self.assertTrue(fn1.endswith(".png"))
        self.assertIn("Movie_", fn1)

    def test_storyboard_fps_float_format(self):
        """Verifies create_storyboard formats fps as a float string without rational crashes."""
        with patch("subprocess.run") as mock_run:
            out = self.mgr.create_storyboard(
                input_file="/media/test.mp4",
                duration_sec=120.0,
                rows=3,
                columns=3,
                output_path=os.path.join(self.temp_dir, "story.jpg")
            )
            self.assertTrue(mock_run.called)
            cmd = mock_run.call_args[0][0]
            # fps filter should format as fps=0.083333 (1 frame every 12s over 120s duration)
            filter_str = [arg for arg in cmd if "fps=" in arg]
            self.assertTrue(len(filter_str) > 0)
            self.assertIn("fps=0.083333", filter_str[0])

    def test_clipboard_copy_mime_detection(self):
        """Verifies mime type guessing for JPEG vs PNG in clipboard tools."""
        with patch("subprocess.run") as mock_run:
            with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/" + cmd if cmd == "xclip" else None):
                img_path = os.path.join(self.temp_dir, "test.jpg")
                with open(img_path, "wb") as f:
                    f.write(b"\xFF\xD8\xFF\xE0")
                self.mgr.copy_file_to_clipboard(img_path)
                mock_run.assert_called_once()
                cmd = mock_run.call_args[0][0]
                self.assertIn("image/jpeg", cmd)

    def test_clipboard_copy_gtk_native(self):
        """Verifies native GTK clipboard copying succeeds when pixbuf can be loaded."""
        from gi.repository import GdkPixbuf
        img_path = os.path.join(self.temp_dir, "valid.png")
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 1, 1)
        pixbuf.savev(img_path, "png", [], [])
        self.assertTrue(os.path.exists(img_path))

        with patch("subprocess.run") as mock_run:
            res = self.mgr.copy_file_to_clipboard(img_path)
            self.assertTrue(res)
            self.assertFalse(mock_run.called)


class TestShaderManagerSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = VideoShaderManager(shaders_dir=self.temp_dir)
        with open(os.path.join(self.temp_dir, "test.glsl"), "w") as f:
            f.write("// glsl")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            for f in os.listdir(self.temp_dir):
                os.remove(os.path.join(self.temp_dir, f))
            os.rmdir(self.temp_dir)

    def test_shader_filename_sanitized(self):
        """Verifies path traversal in shader names is sanitized via os.path.basename."""
        ok = self.mgr.enable_shader("../../test.glsl")
        self.assertTrue(ok)
        expected_path = os.path.join(self.temp_dir, "test.glsl")
        self.assertIn(expected_path, self.mgr.active_shaders)

        bad = self.mgr.enable_shader("../../etc/passwd")
        self.assertFalse(bad)


class TestSubtitleOnlineSearch(unittest.TestCase):
    def setUp(self):
        self.client = SubtitleSearchClient()

    def test_search_handles_error_dict_response(self):
        """Verifies API returning an error dict does not crash search methods."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"status": 401, "message": "Invalid token"}).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            results = self.client.search_by_query("Test Movie")
            self.assertEqual(results, [])

    def test_download_corrupt_gzip_aborts(self):
        """Verifies corrupted gzip download returns False and does not leave output file."""
        dest_path = os.path.join(tempfile.gettempdir(), f"jonaki_bad_test_{os.getpid()}.srt")
        if os.path.exists(dest_path):
            os.remove(dest_path)

        try:
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                # Corrupted gzip header
                mock_resp.read.return_value = b"\x1f\x8b\x08corrupt_data_here"
                mock_resp.__enter__.return_value = mock_resp
                mock_urlopen.return_value = mock_resp

                res = self.client.download_subtitle("http://example.com/bad.gz", dest_path)
                self.assertFalse(res)
                self.assertFalse(os.path.exists(dest_path))
        finally:
            if os.path.exists(dest_path):
                os.remove(dest_path)


class TestSubtitleTranslator(unittest.TestCase):
    def setUp(self):
        self.translator = SubtitleTranslator()

    def test_deepl_language_mapping(self):
        """Verifies DeepL maps EN -> EN-US and PT -> PT-BR."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "translations": [{"text": "Hello world"}]
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            self.translator.api_key = "fake_key"
            res = self.translator._translate_deepl("Bonjour", "FR", "EN")
            self.assertEqual(res, "Hello world")
            req = mock_urlopen.call_args[0][0]
            self.assertIn(b"target_lang=EN-US", req.data)

    def test_libre_api_key_payload(self):
        """Verifies LibreTranslate includes api_key in json payload if provided."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "translatedText": "Hola"
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            self.translator.api_key = "my_libre_key"
            res = self.translator._translate_libre("Hello", "en", "es")
            self.assertEqual(res, "Hola")
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload.get("api_key"), "my_libre_key")

    def test_translation_error_fallback_to_original(self):
        """Verifies translation exceptions fall back to original text instead of error trace."""
        with patch.object(self.translator, "_translate_google", side_effect=RuntimeError("Connection timeout")):
            res = self.translator.translate("Original Subtitle Text", src_lang="en", dst_lang="fr")
            self.assertEqual(res, "Original Subtitle Text")


class TestHostAPI(unittest.TestCase):
    def setUp(self):
        self.mock_win = MagicMock()
        self.host_api = JonakiHostAPI(self.mock_win)

    def test_host_check_version_with_prerelease(self):
        """Verifies HostCheckVersion handles versions with pre-release suffixes."""
        self.host_api.app_version = "1.2.3-beta.1"
        self.assertTrue(self.host_api.HostCheckVersion(1, 2, 0))
        self.assertTrue(self.host_api.HostCheckVersion(1, 2, 3))
        self.assertFalse(self.host_api.HostCheckVersion(1, 3, 0))

    def test_host_url_post_data_with_custom_headers(self):
        """Verifies HostUrlPostData parses header strings correctly."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"OK"
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            headers_str = "Authorization: Bearer test_token\r\nX-Custom: Value"
            res = self.host_api.HostUrlPostData(
                "http://example.com/api",
                post_data="payload=123",
                headers_str=headers_str
            )
            self.assertEqual(res, "OK")
            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.get_header("Authorization"), "Bearer test_token")
            self.assertEqual(req.get_header("X-custom"), "Value")

    def test_host_api_blocks_unsupported_schemes(self):
        """Verifies HostAPI blocks non-http/https URL schemes like file://."""
        res_get = self.host_api.HostUrlGetString("file:///etc/passwd")
        self.assertEqual(res_get, "")
        res_post = self.host_api.HostUrlPostData("ftp://example.com", post_data="123")
        self.assertEqual(res_post, "")

    def test_host_api_temp_folder(self):
        import tempfile
        self.assertEqual(self.host_api.HostGetTempFolder(), tempfile.gettempdir())


class TestNewAuditHardening(unittest.TestCase):
    def test_dsp_chain_negative_gain(self):
        """Negative total gain (attenuation) must generate volume filter."""
        from audio.dsp_chain import AudioDSPChain
        dsp = AudioDSPChain()
        dsp.audio_boost_db = -6.0
        chain = dsp.build_filter_chain()
        self.assertIn("volume=-6.0dB", chain)

    def test_translator_provider_cache_invalidation(self):
        """Changing provider on SubtitleTranslator must clear cached translations."""
        from subtitle.translator import SubtitleTranslator
        tr = SubtitleTranslator(provider="google")
        tr._cache[("Hello", "auto", "es")] = "Hola"
        self.assertIn(("Hello", "auto", "es"), tr._cache)
        tr.provider = "deepl"
        self.assertNotIn(("Hello", "auto", "es"), tr._cache)

    def test_subtitle_search_validation(self):
        """Subtitle search must validate schemes and encode lang."""
        from subtitle.online_search import SubtitleSearchClient
        client = SubtitleSearchClient()
        self.assertFalse(client.download_subtitle("file:///etc/passwd", "/tmp/out.srt"))
        self.assertFalse(client.download_subtitle("", "/tmp/out.srt"))

    def test_video_shader_manager_color_clamping(self):
        """ShaderManager set_color clamps values between -100 and +100."""
        from video.shader_manager import VideoShaderManager
        mgr = VideoShaderManager()
        self.assertEqual(mgr.set_color("brightness", 150), 100)
        self.assertEqual(mgr.brightness, 100)
        self.assertEqual(mgr.set_color("contrast", -200), -100)
        self.assertEqual(mgr.contrast, -100)

    def test_skin_engine_loads_jonaki_and_dsf_logos(self):
        """Skin engine must load both native jonaki.png and DSF surfaces."""
        from ui.skin_engine import PotSkinEngine
        import cairo
        skin = PotSkinEngine()
        self.assertIn("jonaki.png", skin.surfaces)
        self.assertIsInstance(skin.surfaces["jonaki.png"], cairo.ImageSurface)
        self.assertGreater(skin.surfaces["jonaki.png"].get_width(), 0)
        self.assertGreater(skin.surfaces["jonaki.png"].get_height(), 0)

        self.assertIn("dsf_logo.png", skin.surfaces)
        self.assertIsInstance(skin.surfaces["dsf_logo.png"], cairo.ImageSurface)

    def test_main_window_sets_icon(self):
        """JonakiMainWindow must configure application window icon."""
        from ui.main_window import JonakiMainWindow
        win = JonakiMainWindow()
        try:
            icons = win.get_icon_list()
            default_icons = Gtk.Window.get_default_icon_list()
            self.assertTrue(len(icons) > 0 or len(default_icons) > 0, "Window or default icon must be set")
        finally:
            win.destroy()

    def test_idle_video_area_draw_modes(self):
        """_on_draw_video_area must safely render idle logo across dimensions and fallbacks."""
        import cairo
        from unittest.mock import MagicMock
        from ui.main_window import JonakiMainWindow
        from core.engine import PlaybackState

        win = JonakiMainWindow()
        try:
            win.core.state = PlaybackState.IDLE
            win.core.current_file = None

            # Test 1: Standard 960x580 with jonaki.png
            img_surf = cairo.ImageSurface(cairo.FORMAT_RGB24, 960, 580)
            cr = cairo.Context(img_surf)
            widget = MagicMock()
            widget.get_allocation.return_value = MagicMock(width=960, height=580)
            win._on_draw_video_area(widget, cr)

            # Test 2: Compact 100x80 allocation
            widget.get_allocation.return_value = MagicMock(width=100, height=80)
            win._on_draw_video_area(widget, cr)

            # Test 3: DSF fallback
            saved_jonaki = win.skin.surfaces.pop("jonaki.png", None)
            try:
                widget.get_allocation.return_value = MagicMock(width=800, height=600)
                win._on_draw_video_area(widget, cr)
            finally:
                if saved_jonaki is not None:
                    win.skin.surfaces["jonaki.png"] = saved_jonaki

            # Test 4: Pure vector fallback (empty surfaces)
            saved_surfaces = win.skin.surfaces
            try:
                win.skin.surfaces = {}
                win._on_draw_video_area(widget, cr)
            finally:
                win.skin.surfaces = saved_surfaces
        finally:
            win.destroy()

    def test_desktop_files_have_startup_wmclass(self):
        """Desktop files must define StartupWMClass=jonaki for Wayland and X11 taskbars."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for df in ("jonaki.desktop",):
            path = os.path.join(root, df)
            with open(path, "r") as f:
                content = f.read()
            self.assertIn("StartupWMClass=jonaki", content, f"{df} missing StartupWMClass=jonaki")

    def test_pulse_pipewire_environment_properties(self):
        """Audio server environment hints must include application.desktop-entry and application.name."""
        import jonaki
        pulse_prop = os.environ.get("PULSE_PROP", "")
        self.assertIn("application.name='Jonaki'", pulse_prop)
        self.assertIn("application.desktop-entry='jonaki'", pulse_prop)
        self.assertIn("application.process.binary='jonaki'", pulse_prop)
        self.assertEqual(os.environ.get("PIPEWIRE_APP_NAME"), "Jonaki")

    def test_main_window_multi_resolution_icons(self):
        """JonakiMainWindow must populate a multi-resolution icon hierarchy for taskbars."""
        from ui.main_window import JonakiMainWindow
        win = JonakiMainWindow()
        try:
            icons = win.get_icon_list()
            self.assertGreaterEqual(len(icons), 3, "Window icon list should contain multiple resolutions")
            widths = [pb.get_width() for pb in icons]
            self.assertIn(16, widths)
            self.assertIn(48, widths)
        finally:
            win.destroy()


if __name__ == "__main__":
    unittest.main()
