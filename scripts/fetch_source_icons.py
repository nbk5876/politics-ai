"""Save the source icons used on the links page into assets/source-icons/ (run by hand, then commit).

For each domain in config/source_icons.json that has no icon file yet, download a small PNG or JPEG from Google's
favicon service. The page itself never calls that service: it embeds the saved files. Look at the files
before committing them; a source whose icon looks wrong or is missing just shows a letter badge.

    python scripts/fetch_source_icons.py
"""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from watcher.icons import ICON_DIR, MAP_PATH, MAX_ICON_BYTES, icon_kind, load_map  # noqa: E402

SERVICE = "https://www.google.com/s2/favicons?domain={domain}&sz=64"


def main():
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    for domain in sorted(set(load_map(MAP_PATH).values())):
        if any((ICON_DIR / f"{domain}.{ext}").exists() for ext in ("png", "jpg")):
            print(f"have   {domain}")
            continue
        try:
            req = urllib.request.Request(SERVICE.format(domain=domain), headers={"User-Agent": "politics-ai-watcher/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read(MAX_ICON_BYTES + 1)
        except Exception as e:  # noqa: BLE001 - report and carry on with the other domains
            print(f"FAILED {domain}: {type(e).__name__}")
            continue
        kind = icon_kind(data)
        if not kind or len(data) > MAX_ICON_BYTES:
            print(f"SKIPPED {domain}: not a small PNG or JPEG")
            continue
        target = ICON_DIR / f"{domain}.{'png' if kind == 'png' else 'jpg'}"
        target.write_bytes(data)
        print(f"saved  {domain} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
