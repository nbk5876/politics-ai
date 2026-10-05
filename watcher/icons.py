"""Small source icons for the links page, served from our own files (no third-party requests).

config/source_icons.json maps a source name to a web domain; the icon for a domain is the PNG
assets/source-icons/<domain>.png or .jpg (saved once by scripts/fetch_source_icons.py and committed). The page
embeds each icon it uses as a data: URI, so there is nothing extra to upload and the page's byte-for-byte
upload check still covers it. A source with no icon gets a letter badge.
"""
import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "config" / "source_icons.json"
ICON_DIR = ROOT / "assets" / "source-icons"

MAX_ICON_BYTES = 20_000
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF])
_DOMAIN = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}")
_AGGREGATOR = re.compile(r"\s+on\s+msn$", re.IGNORECASE)


def outlet(source):
    """The outlet behind a source name: 'Al Jazeera on MSN' is Al Jazeera, so its own icon is used
    rather than the aggregator's."""
    return _AGGREGATOR.sub("", (source or "").strip())


def load_map(path=MAP_PATH):
    """{lower-case source name: domain}. A missing or unreadable file means no icons, never an error;
    entries whose domain looks wrong are ignored."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k.strip().lower(): v for k, v in raw.items()
            if isinstance(k, str) and isinstance(v, str) and _DOMAIN.fullmatch(v)}


def icon_kind(data):
    """'png' or 'jpeg' from the file's first bytes (never from its name), else None."""
    if data.startswith(_PNG_MAGIC):
        return "png"
    if data.startswith(_JPEG_MAGIC):
        return "jpeg"
    return None


def icon_uri(domain, directory=ICON_DIR):
    """data: URI for a domain's icon file (<domain>.png or <domain>.jpg), or None if it is missing, too
    big or not really a PNG/JPEG."""
    for ext in ("png", "jpg"):
        try:
            data = (Path(directory) / f"{domain}.{ext}").read_bytes()
        except OSError:
            continue
        kind = icon_kind(data)
        if kind and len(data) <= MAX_ICON_BYTES:
            return f"data:image/{kind};base64," + base64.b64encode(data).decode("ascii")
    return None


def default_icons(path=MAP_PATH, directory=ICON_DIR):
    """{lower-case outlet name: data: URI} for every mapped source that has a usable icon file."""
    out = {}
    for name, domain in load_map(path).items():
        uri = icon_uri(domain, directory)
        if uri:
            out[name] = uri
    return out


def icon_for(source, icons):
    """The data: URI for a source name (outlet name, case-insensitive), or None."""
    return (icons or {}).get(outlet(source).lower())
