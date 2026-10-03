"""HTTP fetching with a polite user agent and a timeout."""
import urllib.request

UA = "politics-ai-watcher/0.1 (+https://github.com/nbk5876/politics-ai)"


def fetch(url, timeout=20):
    """Return (text, final_url). Raises on network or HTTP errors."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), resp.geturl()
