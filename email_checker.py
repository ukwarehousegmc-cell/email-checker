#!/usr/bin/env python3
"""
Daily Unreplied Email Checker — Railway Cloud Version
NEW FEATURE: Quote emails detect karke AI draft reply banata hai
"""

import os
import base64
import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ── Config ───────────────────────────────────────────────────
NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "expressmattingsales@gmail.com")
WHATSAPP_NUMBER    = os.environ.get("WHATSAPP_NUMBER", "447548740783")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
HOURS_THRESHOLD    = 24
SCOPES             = ["https://www.googleapis.com/auth/gmail.modify"]

SKIP_SENDERS = [
    "noreply", "no-reply", "donotreply", "mailer-daemon",
    "mailer@shopify", "pkginfo@ups", "fedex", "ebay@ebay",
    "quickbooks", "intuit", "notifications@"
]

QUOTE_KEYWORDS = [
    "quote", "quotation", "price", "pricing", "how much", "cost",
    "rate", "rates", "per metre", "per meter", "per sqm", "per m2",
    "how much does", "what is the price", "can you quote",
    "please quote", "need a quote", "require a quote", "get a quote"
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def get_gmail_service():
    token_json = os.environ.get("GMAIL_TOKEN_JSON")
    if not token_json:
        raise ValueError("GMAIL_TOKEN_JSON environment variable not set!")
    token_data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    if creds.expired and creds.refresh_token:
        log.info("Refreshing Gmail token...")
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def get_my_email(service):
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"].lower()


def get_email_body(service, message_id):
    try:
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        payload = msg.get("payload", {})
        def extract_text(part):
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            if "parts" in part:
                for p in part["parts"]:
                    result = extract_text(p)
                    if result:
                        return result
            return ""
        body = extract_text(payload)
        return body[:2000] if body else ""
    except Exception as e:
        log.error(f"Error getting email body: {e}")
        return ""


def is_quote_email(subject, body, snippet):
    text = f"{subject} {body} {snippet}".lower()
    return any(keyword in text for keyword in QUOTE_KEYWORDS)


def generate_ai_draft(customer_name, customer_email, subject, body):
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — skipping AI draft")
        return None
    try:
        prompt = f"""You are a professional sales assistant for an online rubber matting and flooring company in the UK called Express Matting.

A customer has sent a quote/price enquiry. Write a professional, friendly reply that:
1. Thanks them for their enquiry
2. Acknowledges what product they are asking about
3. Asks any clarifying questions needed (quantity, size, color, delivery postcode)
4. Mentions you will get back with accurate pricing shortly
5. Keeps it brief — 3 to 4 short paragraphs max
6. Signs off as: Kind regards, Express Matting Sales Team

Customer Name: {customer_name}
Subject: {subject}
Customer Email:
{body[:1000]}

Write ONLY the email body text — no subject line, no markdown formatting."""

        data = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["content"][0]["text"]
    except Exception as e:
        log.error(f"AI draft error: {e}")
        return None


def create_gmail_draft(service, to_email, to_name, subject, body, thread_id):
    try:
        reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
        msg = MIMEMultipart("alternative")
        msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email
        msg["Subject"] = reply_subject
        msg.attach(MIMEText(body, "plain"))
        raw   = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw, "threadId": thread_id}}
        ).execute()
        log.info(f"Draft created — ID: {draft['id']}")
        return draft["id"]
    except Exception as e:
        log.error(f"Error creating draft: {e}")
        return None


def check_unreplied(service, my_email):
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=HOURS_THRESHOLD)
    two_days_ago = now - timedelta(days=2)
    after_epoch  = int(two_days_ago.timestamp())

    log.info("Searching Gmail inbox...")
    threads    = []
    page_token = None
    while True:
        params = {"userId": "me", "q": f"in:inbox older_than:1d after:{after_epoch}", "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        results = service.users().threads().list(**params).execute()
        threads.extend(results.get("threads", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    log.info(f"Found {len(threads)} threads to check")
    unreplied    = []
    quote_drafts = []

    for t in threads:
        thread   = service.users().threads().get(userId="me", id=t["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
        messages = thread.get("messages", [])
        if not messages:
            continue

        last_msg  = messages[-1]
        headers   = {h["name"]: h["value"] for h in last_msg.get("payload", {}).get("headers", [])}
        from_addr = headers.get("From", "").lower()
        subject   = headers.get("Subject", "(no subject)")

        if my_email in from_addr:
            continue
        if any(skip in from_addr for skip in SKIP_SENDERS):
            continue

        try:
            internal_date = int(last_msg.get("internalDate", 0)) / 1000
            msg_time = datetime.fromtimestamp(internal_date, tz=timezone.utc)
        except:
            continue

        if msg_time > cutoff:
            continue

        hours_old = int((now - msg_time).total_seconds() / 3600)
        days_old  = hours_old // 24
        age_label = f"{days_old} day(s) ago" if days_old >= 1 else f"{hours_old} hours ago"
        is_old    = days_old >= 5
        snippet   = thread.get("snippet", "")[:150]
        thread_id = thread["id"]

        gmail_link    = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"
        wa_text       = f"Reminder: Reply to '{subject}' from {headers.get('From', '')}"
        whatsapp_link = f"https://wa.me/{WHATSAPP_NUMBER}?text={wa_text.replace(' ', '%20')}"

        from_full  = headers.get("From", "")
        from_name  = from_full.split("<")[0].strip().strip('"') if "<" in from_full else ""
        from_email = from_full.split("<")[-1].strip(">") if "<" in from_full else from_full

        email_body = get_email_body(service, last_msg["id"])
        is_quote   = is_quote_email(subject, email_body, snippet)
        draft_id   = None
        draft_link = None

        # Check if I already replied anywhere in the thread
        i_already_replied = any(
            my_email in h.get("value", "").lower()
            for msg in messages
            for h in msg.get("payload", {}).get("headers", [])
            if h.get("name") == "From"
        )

        if is_quote and not i_already_replied:
            log.info(f"Quote email (unreplied): {subject} from {from_email}")
            ai_reply = generate_ai_draft(from_name, from_email, subject, email_body)
            if ai_reply:
                draft_id = create_gmail_draft(service, from_email, from_name, subject, ai_reply, thread_id)
                if draft_id:
                    draft_link = f"https://mail.google.com/mail/u/0/#drafts?compose={draft_id}"
                    quote_drafts.append({
                        "from": from_full, "subject": subject,
                        "received": msg_time.strftime("%a %d %b %Y"),
                        "age": age_label, "snippet": snippet,
                        "gmail_link": gmail_link, "draft_link": draft_link
                    })

        unreplied.append({
            "from": from_full, "subject": subject,
            "received": msg_time.strftime("%a %d %b %Y"),
            "age": age_label, "snippet": snippet,
            "gmail_link": gmail_link, "whatsapp_link": whatsapp_link,
            "is_old": is_old, "is_quote": is_quote, "draft_link": draft_link
        })

    return unreplied, quote_drafts


def build_html(emails, quote_drafts, now):
    date_str = now.strftime("%d %B %Y")
    html  = f"<h2>📬 {len(emails)} unreplied email(s) older than 24 hours — {date_str}</h2>"

    if quote_drafts:
        html += f"""<div style="background:#e8f5e9;border:2px solid #4CAF50;border-radius:8px;padding:16px;margin:16px 0;">
        <h3>🤖 AI Quote Drafts Ready — {len(quote_drafts)} draft(s)</h3>
        <p>AI ne in quote emails ka draft reply tayar kar diya hai. Review karke send karein!</p>"""
        for q in quote_drafts:
            html += f"""<div style="background:white;border-radius:6px;padding:12px;margin:8px 0;">
            <p><strong>{q['from']}</strong> — {q['subject']}</p>
            <a href="{q['draft_link']}" style="background:#4CAF50;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;">✏️ Review & Send Draft</a>
            </div>"""
        html += "</div><hr>"

    for i, e in enumerate(emails, 1):
        if e["is_quote"]:
            border = "border:2px solid #4CAF50;background:#f1f8f1;"
        elif e["is_old"]:
            border = "border:2px solid #f0ad4e;background:#fffbf0;"
        else:
            border = "border:1px solid #ddd;"

        html += f'<div style="margin-bottom:20px;padding:16px;border-radius:8px;{border}">'
        if e["is_quote"] and e["draft_link"]:
            html += "<p>🤖 <strong>QUOTE — AI Draft Ready!</strong></p>"
        elif e["is_quote"]:
            html += "<p>💰 <strong>QUOTE EMAIL</strong></p>"
        if e["is_old"]:
            html += "<p>⚠️ <strong>OLD — urgent reply needed!</strong></p>"
        html += f'<p><strong>{i}. From:</strong> {e["from"]}</p>'
        html += f'<p><strong>Subject:</strong> {e["subject"]}</p>'
        html += f'<p><strong>Received:</strong> {e["received"]} ({e["age"]})</p>'
        html += f'<p><strong>Preview:</strong> {e["snippet"]}...</p><p>'
        html += f'<a href="{e["gmail_link"]}" style="background:#4285F4;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;margin-right:8px;">✉️ Reply in Gmail</a>'
        html += f'<a href="{e["whatsapp_link"]}" style="background:#25D366;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;margin-right:8px;">💬 WhatsApp</a>'
        if e["draft_link"]:
            html += f'<a href="{e["draft_link"]}" style="background:#4CAF50;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;">✏️ Review Draft</a>'
        html += '</p></div><hr>'

    html += '<p style="color:#888;font-size:12px;">Sent automatically via Railway · Daily Email Checker</p>'
    return html


def build_quote_html(quote_drafts, now):
    date_str = now.strftime("%d %B %Y")
    html  = f"<h2>🤖 AI Quote Drafts Ready — {date_str}</h2>"
    html += f"<p>{len(quote_drafts)} quote email(s) ka draft ready hai. Review karke send karein!</p><hr>"
    for i, q in enumerate(quote_drafts, 1):
        html += f"""<div style="margin-bottom:20px;padding:16px;border-radius:8px;border:2px solid #4CAF50;background:#f1f8f1;">
        <p><strong>{i}. From:</strong> {q['from']}</p>
        <p><strong>Subject:</strong> {q['subject']}</p>
        <p><strong>Received:</strong> {q['received']} ({q['age']})</p>
        <p><strong>Preview:</strong> {q['snippet']}...</p>
        <p>
            <a href="{q['draft_link']}" style="background:#4CAF50;color:white;padding:10px 20px;border-radius:4px;text-decoration:none;margin-right:8px;">✏️ Review & Send Draft</a>
            <a href="{q['gmail_link']}" style="background:#4285F4;color:white;padding:10px 20px;border-radius:4px;text-decoration:none;">📧 View Original</a>
        </p></div><hr>"""
    html += '<p style="color:#888;font-size:12px;">AI Draft Generator · Express Matting · Railway</p>'
    return html


def send_email(service, to, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    log.info(f"Email sent to {to}")


def main():
    log.info("=" * 50)
    log.info("Daily Email Checker starting...")

    service  = get_gmail_service()
    my_email = get_my_email(service)
    log.info(f"Logged in as: {my_email}")

    now = datetime.now(timezone.utc)
    unreplied, quote_drafts = check_unreplied(service, my_email)

    log.info(f"Found {len(unreplied)} unreplied, {len(quote_drafts)} quote drafts created")

    if unreplied:
        subject = f"📬 Unreplied Email Digest — {now.strftime('%d %B %Y')} ({len(unreplied)} emails)"
        html    = build_html(unreplied, quote_drafts, now)
        send_email(service, NOTIFICATION_EMAIL, subject, html)
        log.info("Main digest sent!")
    else:
        send_email(service, NOTIFICATION_EMAIL,
            f"✅ All Clear — {now.strftime('%d %B %Y')}",
            "<h2>✅ All clear!</h2><p>No unreplied emails older than 24 hours.</p>")
        log.info("All clear sent!")

    if quote_drafts:
        send_email(service, NOTIFICATION_EMAIL,
            f"🤖 AI Quote Drafts Ready — {now.strftime('%d %B %Y')} ({len(quote_drafts)} drafts)",
            build_quote_html(quote_drafts, now))
        log.info(f"Quote drafts email sent — {len(quote_drafts)} drafts")


if __name__ == "__main__":
    main()
