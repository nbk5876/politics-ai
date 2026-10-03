"""Pull readable text out of an HTML page (standard library only)."""
import re
from html.parser import HTMLParser

SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"}
KEEP = {"p", "h1", "h2", "h3", "h4", "li", "blockquote"}


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.keep = 0
        self.title = ""
        self._in_title = False
        self.blocks = []
        self._buf = []
        self.in_main = 0
        self.main_blocks = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in SKIP:
            self.skip += 1
        if tag in ("article", "main"):
            self.in_main += 1
        if tag in KEEP and not self.skip:
            self.keep += 1
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in SKIP and self.skip:
            self.skip -= 1
        if tag in ("article", "main") and self.in_main:
            self.in_main -= 1
        if tag in KEEP and self.keep:
            self.keep -= 1
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text:
                self.blocks.append(text)
                if self.in_main:
                    self.main_blocks.append(text)
            self._buf = []

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self.keep and not self.skip:
            self._buf.append(data)


def extract(html_text):
    """Return (title, text). Uses <article>/<main> paragraphs when present."""
    p = _Parser()
    p.feed(html_text)
    blocks = p.main_blocks if len(" ".join(p.main_blocks)) > 200 else p.blocks
    return p.title.strip(), "\n\n".join(blocks)
