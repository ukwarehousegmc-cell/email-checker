#!/usr/bin/env python3
"""
Daily Unreplied Email Checker — Railway Cloud Version
=====================================================
Runs automatically every 24 hours on Railway.
No Windows PC needed!
"""

import os
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ── Config (set these in Railway environment variables) ──────
NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "expressmattingsales@gmail.com")
WHATSAPP_NUMBER    = os.environ.get("WHATSAPP_NUMBER", "447548740783")
HOURS_THRESHOLD    = 24
SCOPES             = ["https://www.googleapis.com/auth/gmail.modify"]

SKIP_SENDERS = [
    "noreply", "no-reply", "donotreply", "mailer-daemon",
    "mailer@shopify", "pkginfo@ups", "fedex", "ebay@ebay",
    "quickbooks", "intuit", "notifications@"
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# ── Gmail Auth (uses environment variables, no files needed) ─
def get_gmail_service():
    # Read token from environment variable (set in Railway)
    token_json = os.environ.get("GMAIL_TOKEN_JSON")
    if not token_json:
        raise ValueError("GMAIL_TOKEN_JSON environment variable not set!")

    token_data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if creds.expired and creds.refresh_token:
        log.info("Refreshing Gmail token...")
        creds.refresh(Request())
        # Log new token so you can update Railway env var if needed
        log.info(f"Token refreshed. New expiry: {creds.expiry}")

    return build("gmail", "v1", credentials=creds)


# ── Get my email address ─────────────────────────────────────
def get_my_email(service):
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"].lower()


# ── Check unreplied emails ───────────────────────────────────
def check_unreplied(service, my_email):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=HOURS_THRESHOLD)

    log.info("Searching Gmail inbox for unreplied emails...")

    # Only last 48 hours window for speed
    two_days_ago = now - timedelta(days=2)
    after_epoch = int(two_days_ago.timestamp())

    threads = []
    page_token = None
    while True:
        params = {
            "userId": "me",
            "q": f"in:inbox older_than:1d after:{after_epoch}",
            "maxResults": 100
        }
        if page_token:
            params["pageToken"] = page_token
        results = service.users().threads().list(**params).execute()
        threads.extend(results.get("threads", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    log.info(f"Found {len(threads)} threads to check")
    unreplied = []

    for t in threads:
        thread = service.users().threads().get(
            userId="me", id=t["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()

        messages = thread.get("messages", [])
        if not messages:
            continue

        last_msg = messages[-1]
        headers = {h["name"]: h["value"] for h in last_msg.get("payload", {}).get("headers", [])}

        from_addr = headers.get("From", "").lower()
        subject   = headers.get("Subject", "(no subject)")

        # Skip if I sent the last message
        if my_email in from_addr:
            continue

        # Skip automated senders
        if any(skip in from_addr for skip in SKIP_SENDERS):
            continue

        # Parse date and check age
        try:
            internal_date = int(last_msg.get("internalDate", 0)) / 1000
            msg_time = datetime.fromtimestamp(internal_date, tz=timezone.utc)
        except:
            continue

        if msg_time > cutoff:
            continue  # Less than 24 hours old

        # Calculate age
        hours_old = int((now - msg_time).total_seconds() / 3600)
        days_old  = hours_old // 24
        age_label = f"{days_old} day(s) ago" if days_old >= 1 else f"{hours_old} hours ago"
        is_old    = days_old >= 5

        snippet = thread.get("snippet", "")[:150]

        thread_id     = thread["id"]
        gmail_link    = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"
        wa_text       = f"Reminder: Reply to '{subject}' from {headers.get('From', '')}"
        whatsapp_link = f"https://wa.me/{WHATSAPP_NUMBER}?text={wa_text.replace(' ', '%20')}"

        unreplied.append({
            "from":          headers.get("From", "Unknown"),
            "subject":       subject,
            "received":      msg_time.strftime("%a %d %b %Y"),
            "age":           age_label,
            "snippet":       snippet,
            "gmail_link":    gmail_link,
            "whatsapp_link": whatsapp_link,
            "is_old":        is_old
        })

    return unreplied


# ── Build HTML digest ────────────────────────────────────────
def build_html(emails, now):
    date_str = now.strftime("%d %B %Y")
    html = f"<h2>📬 You have {len(emails)} unreplied email(s) older than 24 hours</h2>"
    html += f"<p>Daily digest for <strong>{date_str}</strong>.</p><hr>"

    for i, e in enumerate(emails, 1):
        border = "border:2px solid #f0ad4e; background:#fffbf0;" if e["is_old"] else "border:1px solid #ddd;"
        html += f'<div style="margin-bottom:20px;padding:16px;border-radius:8px;{border}">'
        if e["is_old"]:
            html += "<p>⚠️ <strong>OLD — needs urgent reply!</strong></p>"
        html += f'<p><strong>{i}. From:</strong> {e["from"]}</p>'
        html += f'<p><strong>Subject:</strong> {e["subject"]}</p>'
        html += f'<p><strong>Received:</strong> {e["received"]} ({e["age"]})</p>'
        html += f'<p><strong>Preview:</strong> {e["snippet"]}...</p>'
        html += f'''<p>
            <a href="{e["gmail_link"]}" style="background:#4285F4;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;margin-right:8px;">✉️ Reply in Gmail</a>
            <a href="{e["whatsapp_link"]}" style="background:#25D366;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;">💬 WhatsApp Reminder</a>
        </p></div><hr>'''

    html += '<p style="color:#888;font-size:12px;">Sent automatically via Railway · Daily Email Checker</p>'
    return html


# ── Send email via Gmail API ─────────────────────────────────
def send_email(service, to, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    log.info(f"Email sent to {to}")


# ── Main ─────────────────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info("Daily Email Checker starting...")

    service  = get_gmail_service()
    my_email = get_my_email(service)
    log.info(f"Logged in as: {my_email}")

    now       = datetime.now(timezone.utc)
    unreplied = check_unreplied(service, my_email)

    log.info(f"Found {len(unreplied)} unreplied emails")

    if unreplied:
        date_str = now.strftime("%d %B %Y")
        subject  = f"📬 Unreplied Email Digest — {date_str} ({len(unreplied)} emails)"
        html     = build_html(unreplied, now)
        send_email(service, NOTIFICATION_EMAIL, subject, html)
        log.info("Digest sent!")
    else:
        subject = f"✅ All Clear — No Unreplied Emails · {now.strftime('%d %B %Y')}"
        html    = f"<h2>✅ All clear!</h2><p>No unreplied emails older than 24 hours on {now.strftime('%d %B %Y')}.</p>"
        send_email(service, NOTIFICATION_EMAIL, subject, html)
        log.info("All clear email sent!")


if __name__ == "__main__":
    main()
