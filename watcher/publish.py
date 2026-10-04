"""Upload the links page to the web server over SFTP, then check that the live copy matches.

Safety rules:
- The password is never put on a command line or in a log. It is read from the DH_PASS
  environment variable (or the Windows user environment) and handed to curl on stdin.
- The server's host key must be pinned (`hostkey_sha256` in config/local.json). With no pin, nothing
  is uploaded. curl refuses the connection if the key does not match.
- Settings live in config/local.json, which is not committed.
"""
import hashlib
import os
import subprocess
import time
import urllib.request


class PublishError(RuntimeError):
    pass


def get_secret(name="DH_PASS"):
    """Environment first, then the Windows user environment (covers scheduled tasks)."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except (ImportError, OSError):
        return ""


def _quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def upload(local_path, cfg, secret=None, runner=subprocess.run):
    """Upload one file. Raises PublishError, with the password removed from any message."""
    pin = cfg.get("hostkey_sha256")
    if not pin:
        raise PublishError("no hostkey_sha256 in the publish settings: refusing to upload without a pinned host key")
    pw = secret if secret is not None else get_secret()
    if not pw:
        raise PublishError("DH_PASS is not set")
    url = f"sftp://{cfg['host']}{cfg['remote_path']}"
    cmd = [cfg.get("curl", "curl"), "-sS", "--hostpubsha256", pin, "--ftp-create-dirs",
           "-K", "-", "-T", str(local_path), url]
    cfg_stdin = f"user = {_quote(cfg['user'] + ':' + pw)}\n"  # stdin, so it never appears in a process list
    try:
        p = runner(cmd, input=cfg_stdin, capture_output=True, text=True, timeout=90)
    except Exception as e:
        raise PublishError(f"upload could not run: {type(e).__name__}") from None
    if p.returncode != 0:
        msg = (p.stderr or p.stdout or "").replace(pw, "***").strip()[-200:]
        raise PublishError(f"upload failed (curl exit {p.returncode}): {msg}")


def verify(local_path, public_url, fetcher=None):
    """The live page must be byte-for-byte the file we uploaded."""
    want = hashlib.sha256(open(local_path, "rb").read()).hexdigest()
    if fetcher is None:
        def fetcher(u):
            req = urllib.request.Request(u, headers={"User-Agent": "politics-ai-watcher/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
    status, data = fetcher(f"{public_url}?nc={int(time.time())}")
    if status != 200:
        raise PublishError(f"live page returned HTTP {status}")
    if hashlib.sha256(data).hexdigest() != want:
        raise PublishError("live page does not match the uploaded file")


def publish_page(local_path, cfg, secret=None, runner=subprocess.run, fetcher=None):
    upload(local_path, cfg, secret=secret, runner=runner)
    verify(local_path, cfg["public_url"], fetcher=fetcher)
