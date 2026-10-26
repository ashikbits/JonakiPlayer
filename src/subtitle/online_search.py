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
        if file_size < 65536 * 2:
            return None

        hash_val = file_size
        fmt = "<8s"  # 64-bit little endian

        with open(file_path, "rb") as f:
            # First 64KB (8192 64-bit integers)
            for _ in range(8192):
                chunk = f.read(8)
                (val,) = struct.unpack("<Q", chunk)
                hash_val = (hash_val + val) & 0xFFFFFFFFFFFFFFFF

            # Last 64KB
            f.seek(max(0, file_size - 65536), os.SEEK_SET)
            for _ in range(8192):
                chunk = f.read(8)
                (val,) = struct.unpack("<Q", chunk)
                hash_val = (hash_val + val) & 0xFFFFFFFFFFFFFFFF

        return f"{hash_val:016x}"
    except Exception as e:
        print(f"[SubtitleSearch] Error computing hash for {file_path}: {e}")
        return None


class SubtitleSearchClient:
    def __init__(self, user_agent: str = "JonakiLinux v1.0"):
        self.user_agent = user_agent

    def search_by_hash(self, file_path: str, lang: str = "eng") -> List[Dict[str, Any]]:
        file_hash = compute_opensubtitles_hash(file_path)
        if not file_hash:
            return []

        file_size = os.path.getsize(file_path)
        # Query OpenSubtitles API
        api_url = f"https://rest.opensubtitles.org/search/moviebytesize-{file_size}/moviehash-{file_hash}/sublanguageid-{lang}"
        req = urllib.request.Request(api_url, headers={"User-Agent": self.user_agent})
        
        results = []
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    results.append({
                        "title": item.get("MovieReleaseName", item.get("SubFileName", "")),
                        "language": item.get("LanguageName", lang),
                        "format": item.get("SubFormat", "srt"),
                        "download_url": item.get("SubDownloadLink", ""),
                        "rating": item.get("SubRating", "0.0")
                    })
        except Exception as e:
            print(f"[SubtitleSearch] Hash search failed: {e}")

        return results

    def search_by_query(self, query: str, lang: str = "eng") -> List[Dict[str, Any]]:
        api_url = f"https://rest.opensubtitles.org/search/query-{urllib.parse.quote(query)}/sublanguageid-{lang}"
        req = urllib.request.Request(api_url, headers={"User-Agent": self.user_agent})
        results = []
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    results.append({
                        "title": item.get("MovieReleaseName", item.get("SubFileName", "")),
                        "language": item.get("LanguageName", lang),
                        "format": item.get("SubFormat", "srt"),
                        "download_url": item.get("SubDownloadLink", ""),
                        "rating": item.get("SubRating", "0.0")
                    })
        except Exception as e:
            print(f"[SubtitleSearch] Query search failed: {e}")

        return results

    def download_subtitle(self, download_url: str, output_path: str) -> bool:
        """
        Downloads a subtitle file from the given URL and decompresses gzip if necessary.
        """
        if not download_url:
            return False
        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = resp.read()
                # Check for gzip header magic bytes (\x1f\x8b)
                if len(data) >= 2 and data[:2] == b"\x1f\x8b":
                    try:
                        data = gzip.decompress(data)
                    except Exception as gz_err:
                        print(f"[SubtitleSearch] Gzip decompression notice: {gz_err}")
                with open(output_path, "wb") as f:
                    f.write(data)
            return True
        except Exception as e:
            print(f"[SubtitleSearch] Download failed: {e}")
            return False

