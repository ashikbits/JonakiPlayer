"""
Jonaki for Linux - Real-Time AI Subtitle Translator
Integrates Google Translate, DeepL, LibreTranslate, and Local LLMs (Ollama / LM Studio).
"""

import json
import threading
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Dict, Optional, Tuple


class SubtitleTranslator:
    def __init__(self, provider: str = "google", target_lang: str = "en", api_key: str = "",
                 local_endpoint: str = "http://localhost:11434/api/generate", local_model: str = "qwen2.5",
                 max_cache_size: int = 1000):
        self._provider = provider
        self.target_lang = target_lang
        self.api_key = api_key
        self.local_endpoint = local_endpoint
        self.local_model = local_model
        self.max_cache_size = max_cache_size
        # In-memory bounded LRU cache: (text, src, dst) -> translated_text
        self._cache: OrderedDict[Tuple[str, str, str], str] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def provider(self) -> str:
        return self._provider

    @provider.setter
    def provider(self, val: str) -> None:
        if self._provider != val:
            self._provider = val
            if hasattr(self, "_cache"):
                self.clear_cache()

    def clear_cache(self) -> None:
        with getattr(self, "_lock", None) or threading.Lock():
            self._cache.clear()

    def translate(self, text: str, src_lang: str = "auto", dst_lang: Optional[str] = None) -> str:
        if not text or not text.strip():
            return text

        dst = dst_lang or self.target_lang
        cache_key = (text.strip(), src_lang, dst)
        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
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

            with self._lock:
                if len(self._cache) >= self.max_cache_size:
                    self._cache.popitem(last=False)
                self._cache[cache_key] = translated
        except Exception as e:
            # Fall back to original text on network timeout
            print(f"[SubtitleTranslator] Translation error: {e}")
            translated = text

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
        target_lang = dst.upper()
        if target_lang == "EN":
            target_lang = "EN-US"
        elif target_lang == "PT":
            target_lang = "PT-BR"
        payload = urllib.parse.urlencode({
            "auth_key": self.api_key,
            "text": text,
            "target_lang": target_lang
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "translations" in data and data["translations"]:
                return data["translations"][0]["text"]
        return text

    def _translate_libre(self, text: str, src: str, dst: str) -> str:
        url = "https://libretranslate.com/translate"
        payload_dict = {
            "q": text,
            "source": "auto" if src == "auto" else src,
            "target": dst,
            "format": "text"
        }
        if self.api_key:
            payload_dict["api_key"] = self.api_key
        payload = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("translatedText", text)

    def _translate_local_llm(self, text: str, src: str, dst: str) -> str:
        parsed = urllib.parse.urlsplit(self.local_endpoint)
        if parsed.scheme.lower() not in ("http", "https"):
            raise ValueError(f"Invalid local endpoint URL scheme: {parsed.scheme}")
        prompt = f"Translate this subtitle accurately into {dst}. Output ONLY the translated text:\n{text}"
        is_openai_compat = "/v1/" in self.local_endpoint or "chat/completions" in self.local_endpoint

        if is_openai_compat:
            payload_dict = {
                "model": self.local_model,
                "messages": [
                    {
                        "role": "system",
                        "content": f"You are a subtitle translator. Translate the text accurately into {dst}. Output ONLY the translated text."
                    },
                    {"role": "user", "content": text}
                ],
                "temperature": 0.3
            }
        else:
            payload_dict = {
                "model": self.local_model,
                "prompt": prompt,
                "stream": False
            }

        payload = json.dumps(payload_dict).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(self.local_endpoint, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"].strip()
                elif "text" in choice:
                    return choice["text"].strip()
            resp_val = data.get("response", text)
            return str(resp_val).strip() if resp_val is not None else text
