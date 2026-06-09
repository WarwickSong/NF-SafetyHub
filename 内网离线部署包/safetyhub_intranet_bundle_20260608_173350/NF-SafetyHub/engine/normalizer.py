from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import unquote

ZERO_WIDTH_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\ufeff",
    "\u2060",
}
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE_PATTERN = re.compile(r"\s+")


class TextNormalizer:
    def normalize(self, text: str) -> str:
        if not text:
            return ""
        normalized = self._decode_repeatedly(text)
        normalized = html.unescape(normalized)
        normalized = unicodedata.normalize("NFKC", normalized)
        normalized = self._remove_zero_width_chars(normalized)
        normalized = CONTROL_CHAR_PATTERN.sub("", normalized)
        normalized = WHITESPACE_PATTERN.sub(" ", normalized)
        return normalized.strip()

    def _decode_repeatedly(self, text: str) -> str:
        decoded = text
        for _ in range(2):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        return decoded

    def _remove_zero_width_chars(self, text: str) -> str:
        return "".join(char for char in text if char not in ZERO_WIDTH_CHARS)


def normalize_text(text: str) -> str:
    return TextNormalizer().normalize(text)
