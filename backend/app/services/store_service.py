import re
import unicodedata


def normalize_store_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name.lower())
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
