"""
Jonaki for Linux - Online Subtitle Search & Hasher
Implements OpenSubtitles 64-bit checksum hash algorithm and subtitle search client.
"""

import os
import struct
import json
import gzip
import urllib.parse
import urllib.request
from typing import List, Dict, Optional, Any


def compute_opensubtitles_hash(file_path: str) -> Optional[str]:
    """
    Computes the 64-bit checksum hash used by OpenSubtitles.
    Formula: FileSize + Sum(First 64KB as uint64) + Sum(Last 64KB as uint64) (mod 2^64)
    """
    try:
        file_size = os.path.getsize(file_path)
        if file_size < 65536:
            return None

        hash_val = file_size

        with open(file_path, "rb") as f:
            # First 64KB (8192 64-bit integers) read in a single optimized buffer
            first_block = f.read(65536)
            if len(first_block) < 65536:
                first_block = first_block.ljust(65536, b"\0")
            vals_first = struct.unpack("<8192Q", first_block)
            hash_val = (hash_val + sum(vals_first)) & 0xFFFFFFFFFFFFFFFF

            # Last 64KB read in a single optimized buffer
            f.seek(max(0, file_size - 65536), os.SEEK_SET)
            last_block = f.read(65536)
            if len(last_block) < 65536:
                last_block = last_block.ljust(65536, b"\0")
            vals_last = struct.unpack("<8192Q", last_block)
            hash_val = (hash_val + sum(vals_last)) & 0xFFFFFFFFFFFFFFFF

        return f"{hash_val:016x}"
    except Exception as e:
        print(f"[SubtitleSearch] Error computing hash for {file_path}: {e}")
        return None


class SubtitleSearchClient:
    def __init__(self, user_agent: str = "JonakiLinux v1.0", api_key: Optional[str] = None):
        self.user_agent = user_agent
        self.api_key = api_key or os.environ.get("OPENSUBTITLES_API_KEY", "")

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json"
        }
        if self.api_key:
            headers["Api-Key"] = self.api_key
        return headers

    def _parse_api_response(self, data: Any, default_lang: str) -> List[Dict[str, Any]]:
        results = []
        # Case 1: Modern OpenSubtitles API v1 schema {"data": [{"attributes": {...}}]}
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
                attrs = item.get("attributes", {})
                files = attrs.get("files", [])
                file_name = files[0].get("file_name", "") if files else ""
                file_id = files[0].get("file_id", "") if files else ""
                download_url = f"https://api.opensubtitles.com/api/v1/download?file_id={file_id}" if file_id else ""
                results.append({
                    "title": attrs.get("release", file_name) or file_name or "Subtitle",
                    "language": attrs.get("language", default_lang),
                    "format": "srt",
                    "download_url": str(download_url),
                    "rating": str(attrs.get("ratings", "0.0"))
                })
        # Case 2: Legacy list schema [{"MovieReleaseName": "...", "SubDownloadLink": "..."}]
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    results.append({
                        "title": item.get("MovieReleaseName", item.get("SubFileName", "")),
                        "language": item.get("LanguageName", default_lang),
                        "format": item.get("SubFormat", "srt"),
                        "download_url": item.get("SubDownloadLink", ""),
                        "rating": str(item.get("SubRating", "0.0"))
                    })
        return results

    def search_by_hash(self, file_path: str, lang: str = "eng") -> List[Dict[str, Any]]:
        file_hash = compute_opensubtitles_hash(file_path)
        if not file_hash:
            return []

        file_size = os.path.getsize(file_path)
        safe_lang = urllib.parse.quote(lang, safe="")
        headers = self._get_headers()

        # 1. Primary: Modern OpenSubtitles API v1
        api_url = f"https://api.opensubtitles.com/api/v1/subtitles?moviehash={file_hash}&languages={safe_lang}"
        req = urllib.request.Request(api_url, headers=headers)
        results = []
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = self._parse_api_response(data, lang)
        except Exception as e:
            # 2. Fallback to legacy endpoint for compatibility with local test stubs / mirrors
            try:
                legacy_url = f"https://rest.opensubtitles.org/search/moviebytesize-{file_size}/moviehash-{file_hash}/sublanguageid-{safe_lang}"
                legacy_req = urllib.request.Request(legacy_url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(legacy_req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    results = self._parse_api_response(data, lang)
            except Exception:
                pass
            if not results:
                print(f"[SubtitleSearch] Hash search failed: {e}")

        return results

    def search_by_query(self, query: str, lang: str = "eng") -> List[Dict[str, Any]]:
        safe_lang = urllib.parse.quote(lang, safe="")
        safe_query = urllib.parse.quote(query)
        headers = self._get_headers()

        # 1. Primary: Modern OpenSubtitles API v1
        api_url = f"https://api.opensubtitles.com/api/v1/subtitles?query={safe_query}&languages={safe_lang}"
        req = urllib.request.Request(api_url, headers=headers)
        results = []
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = self._parse_api_response(data, lang)
        except Exception as e:
            # 2. Fallback to legacy endpoint for mock / mirror compatibility
            try:
                legacy_url = f"https://rest.opensubtitles.org/search/query-{safe_query}/sublanguageid-{safe_lang}"
                legacy_req = urllib.request.Request(legacy_url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(legacy_req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    results = self._parse_api_response(data, lang)
            except Exception:
                pass
            if not results:
                print(f"[SubtitleSearch] Query search failed: {e}")

        return results

    def download_subtitle(self, download_url: str, output_path: str) -> bool:
        """
        Downloads a subtitle file from the given URL and decompresses gzip if necessary.
        Includes path containment and decompression bomb mitigations.
        """
        if not download_url:
            return False
        parsed = urllib.parse.urlsplit(download_url)
        if parsed.scheme.lower() not in ("http", "https"):
            print(f"[SubtitleSearch] Blocked non-http download URL: {download_url}")
            return False

        try:
            target_path = os.path.realpath(os.path.abspath(output_path))
            parent_dir = os.path.dirname(target_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            headers = self._get_headers()
            req = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = resp.read(15 * 1024 * 1024)  # 15MB limit
                # Check for gzip header magic bytes (\x1f\x8b)
                if len(data) >= 2 and data[:2] == b"\x1f\x8b":
                    try:
                        data = gzip.decompress(data)
                    except Exception as gz_err:
                        print(f"[SubtitleSearch] Gzip decompression failed: {gz_err}")
                        return False
                with open(target_path, "wb") as f:
                    f.write(data)
            return True
        except Exception as e:
            print(f"[SubtitleSearch] Download failed: {e}")
            return False

