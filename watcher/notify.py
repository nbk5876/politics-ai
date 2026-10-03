"""Notifications: LabChan message and email. Used only in --live mode."""
import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage

LABCHAN_LIMIT = 1900  # LabChan TX cuts messages at 2000 characters


def format_match(m, saved_name=None, extraction_ok=True):
    """One short, line-broken message for a matched article."""
    it, src = m["item"], m["source"]
    lines = [
        f"Politics AI: new match ({m['status']})",
        "",
        f"Title: {it['title'][:200]}",
        f"Source: {src['label']}",
        f"Link: {it['link']}",
        f"Published: {it.get('published', '') or 'unknown'}",
        "",
        "Why it matched: " + "; ".join(m["reasons"]),
    ]
    if saved_name:
        lines.append(f"Saved: {saved_name}" + ("" if extraction_ok else " (text extraction failed)"))
    text = "\n".join(lines)
    return text[:LABCHAN_LIMIT]


def format_digest(matches, cap):
    lines = [f"Politics AI: {len(matches)} more matches beyond today's cap of {cap}", ""]
    for m in matches[:20]:
        lines.append(f"- {m['item']['title']} ({m['source']['label']}) {m['item']['link']}")
    return "\n".join(lines)[:LABCHAN_LIMIT]


def send_labchan(message, local):
    """Send through the AI-Lab-Ops tx.cli. Raises on failure."""
    cmd = [sys.executable, "-m", "tx.cli", "config.json",
           "--from", local.get("labchan_from", "jeff"),
           "--to", local.get("labchan_to", "tb"),
           "--yes", "--message", message]
    p = subprocess.run(cmd, cwd=local["labchan_dir"], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError((p.stdout + p.stderr).strip()[-300:])
    return p.stdout.strip()


def send_email(subject, body):
    """SMTP settings come from environment variables; nothing is stored in the repo.

    POLITICS_SMTP_HOST, POLITICS_SMTP_PORT (default 465), POLITICS_SMTP_USER,
    POLITICS_SMTP_PASS, POLITICS_MAIL_TO. Returns False when not configured.
    """
    host, user = os.environ.get("POLITICS_SMTP_HOST"), os.environ.get("POLITICS_SMTP_USER")
    pw, to = os.environ.get("POLITICS_SMTP_PASS"), os.environ.get("POLITICS_MAIL_TO")
    if not all([host, user, pw, to]):
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, to, subject
    msg.set_content(body)
    with smtplib.SMTP_SSL(host, int(os.environ.get("POLITICS_SMTP_PORT", "465")), timeout=30) as s:
        s.login(user, pw)
        s.send_message(msg)
    return True
