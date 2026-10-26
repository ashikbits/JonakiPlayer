"""
Jonaki for Linux - Real-Time AI Subtitle Translator
Integrates Google Translate, DeepL, LibreTranslate, and Local LLMs (Ollama / LM Studio).
"""

import json
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple


class SubtitleTranslator:
    def __init__(self, provider: str = "google", target_lang: str = "en", api_key: str = "",
                 local_endpoint: str = "http://localhost:11434/api/generate", local_model: str = "qwen2.5"):
        self.provider = provider
        self.target_lang = target_lang
        self.api_key = api_key
        self.local_endpoint = local_endpoint
        self.local_model = local_model
        # In-memory LRU cache: (text, src, dst) -> translated_text
        self._cache: Dict[Tuple[str, str, str], str] = {}

    def translate(self, text: str, src_lang: str = "auto", dst_lang: Optional[str] = None) -> str:
        if not text or not text.strip():
            return text

        dst = dst_lang or self.target_lang
        cache_key = (text.strip(), src_lang, dst)
        if cache_key in self._cache:
            return self._cache[cache_key]

        translated = text
        try:
            if self.provider == "google":
                translated = self._translate_google(text, src_lang, dst)
            elif self.provider == "deepl":
                translated = self._translate_deepl(text, src_lang, dst)
            elif self.provider == "libre":
                translated = self._translate_libre(text, src_lang, dst)
            elif self.provider == "local_llm":
                translated = self._translate_local_llm(text, src_lang, dst)
            else:
                translated = self._translate_google(text, src_lang, dst)

            self._cache[cache_key] = translated
        except Exception as e:
            # Fall back to original text on network timeout
            translated = f"{text} [{e}]"

        return translated

    def _translate_google(self, text: str, src: str, dst: str) -> str:
        # Free public web translate endpoint
        base_url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": src,
            "tl": dst,
            "dt": "t",
            "q": text
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list) and data[0]:
                translated_parts = [segment[0] for segment in data[0] if segment and segment[0]]
                return "".join(translated_parts)
        return text

    def _translate_deepl(self, text: str, src: str, dst: str) -> str:
        if not self.api_key:
            return text
        url = "https://api-free.deepl.com/v2/translate" if self.api_key.endswith(":fx") else "https://api.deepl.com/v2/translate"
        payload = urllib.parse.urlencode({
            "auth_key": self.api_key,
            "text": text,
            "target_lang": dst.upper()
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "translations" in data and data["translations"]:
                return data["translations"][0]["text"]
        return text

    def _translate_libre(self, text: str, src: str, dst: str) -> str:
        url = "https://libretranslate.com/translate"
        payload = json.dumps({
            "q": text,
            "source": "auto" if src == "auto" else src,
            "target": dst,
            "format": "text"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("translatedText", text)

    def _translate_local_llm(self, text: str, src: str, dst: str) -> str:
        prompt = f"Translate this subtitle accurately into {dst}. Output ONLY the translated text:\n{text}"
        payload = json.dumps({
            "model": self.local_model,
            "prompt": prompt,
            "stream": False
        }).encode("utf-8")
        req = urllib.request.Request(self.local_endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", text).strip()
