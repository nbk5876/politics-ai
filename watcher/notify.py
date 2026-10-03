"""Notifications: LabChan message and email. Used only in --live mode.

Feed titles and links go into the message text as-is. They are untrusted input: fine while the
recipient is a person, but never pass them to an agent that acts on instructions."""
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
        lines.append(f"Saved: {saved_name}" + ("" if extraction_ok else " (text extraction incomplete)"))
    text = "\n".join(lines)
    return text[:LABCHAN_LIMIT]


def format_digest(matches, cap, limit=LABCHAN_LIMIT):
    """Return (text, listed): as many titles as fit within the limit, then 'N more not listed'."""
    head = f"Politics AI: {len(matches)} more matches beyond today's cap of {cap}\n"
    lines, used = [], len(head)
    for m in matches:
        line = f"- {m['item']['title'][:120]} ({m['source']['label']}) {m['item']['link']}"
        footer_room = 60  # room for the 'N more not listed' line
        if used + len(line) + 1 + footer_room > limit:
            break
        lines.append(line)
        used += len(line) + 1
    text = head + "\n".join(lines)
    if len(lines) < len(matches):
        text += f"\n(+{len(matches) - len(lines)} more not listed; they will be reported next run)"
    return text, len(lines)


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
