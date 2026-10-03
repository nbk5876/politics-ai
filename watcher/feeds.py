"""Parse RSS 2.0 and Atom feeds into plain item dicts."""
import re
import xml.etree.ElementTree as ET
from html import unescape


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _strip_tags(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_feed(xml_text):
    """Return a list of {id, title, link, published, summary, author}."""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    items = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        d = {"id": "", "title": "", "link": "", "published": "", "summary": "", "author": ""}
        for child in el:
            n = _local(child.tag)
            if n == "title":
                d["title"] = _strip_tags("".join(child.itertext()))
            elif n == "link":
                href = child.get("href")
                if href:
                    if child.get("rel", "alternate") == "alternate" or not d["link"]:
                        d["link"] = href
                else:
                    d["link"] = d["link"] or _text(child)
            elif n in ("guid", "id"):
                d["id"] = _text(child)
            elif n in ("pubDate", "published", "updated", "date"):
                d["published"] = d["published"] or _text(child)
            elif n in ("description", "summary", "content", "encoded"):
                d["summary"] = d["summary"] or _strip_tags("".join(child.itertext()))
            elif n in ("creator", "author"):
                d["author"] = d["author"] or _strip_tags("".join(child.itertext()))
        d["id"] = d["id"] or d["link"]
        if d["title"] or d["link"]:
            items.append(d)
    return items
