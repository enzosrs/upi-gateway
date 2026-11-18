__author__ = "enzosrs"
__github__ = "https://github.com/enzosrs"
__community__ = "https://t.me/devcommunityx"

import os
import re
import base64
from typing import Tuple, Optional, Dict, Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels"
]

TOKEN_PATH = "token.json"
CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    }
}

def get_oauth_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

def store_flow_state(state: str, code_verifier: str):
    from db import save_flow_state
    save_flow_state(state, code_verifier)

def get_flow_state(state: str) -> str | None:
    from db import pop_flow_state
    return pop_flow_state(state)

def get_credentials() -> Optional[Credentials]:
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(TOKEN_PATH, "w") as token_file:
                        token_file.write(creds.to_json())
                except Exception:
                    return None
            return creds
        except Exception:
            return None
    return None

def save_credentials_from_auth_code(code: str, redirect_uri: str, state: str) -> Credentials:
    code_verifier = get_flow_state(state)
    flow = get_oauth_flow(redirect_uri)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_PATH, "w") as token_file:
        token_file.write(creds.to_json())
    return creds

def get_gmail_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("User not authenticated. Please visit /auth first.")
    return build("gmail", "v1", credentials=creds)

_label_cache = {}

def get_or_create_label(service, label_name: str = "PAYMENT_PROCESSED") -> str:
    global _label_cache
    if label_name in _label_cache:
        return _label_cache[label_name]

    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        for label in labels:
            if label["name"].upper() == label_name.upper():
                _label_cache[label_name] = label["id"]
                return label["id"]

        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show"
        }
        created_label = service.users().labels().create(userId="me", body=label_body).execute()
        _label_cache[label_name] = created_label["id"]
        return created_label["id"]
    except HttpError as error:
        raise error

def decode_body(payload: Dict[str, Any], prefer_html: bool = False) -> str:
    if "parts" in payload:
        target_mime = "text/html" if prefer_html else "text/plain"
        for part in payload["parts"]:
            if part.get("mimeType") == target_mime:
                return decode_body(part, prefer_html)

        body = ""
        for part in payload["parts"]:
            body += decode_body(part, prefer_html)
        return body
    else:
        data = payload.get("body", {}).get("data")
        if data:
            try:
                return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8")
            except Exception:
                pass
    return ""

def clean_email_text(body: str) -> str:
    if not body:
        return ""
    clean = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<script[^>]*>.*?</script>', '', clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def is_received_payment(subject: str, body: str, sender: str = "") -> bool:
    full_text = f"{subject} {body}".lower()
    subject_lower = subject.lower()

    non_payment_subjects = [
        "new beneficiary added", "beneficiary added", "security alert",
        "card blocked", "welcome", "otp", "verification code", "login alert",
        "statement", "password reset", "account created"
    ]
    for nps in non_payment_subjects:
        if nps in subject_lower:
            return False

    if "fmpu" in full_text:
        return False
    if "fmpi" in full_text and ("received" in full_text or "credited" in full_text):
        return True

    debit_keywords = [
        "sent to", "paid to", "debited", "you paid", "sent ₹", "sent rs",
        "spent", "debit card", "payment to", "transferred to", "you sent",
        "withdrawn", "withdrawal", "sent money to", "paid securely via famapp",
        "paid securely", "paid via famapp"
    ]
    for kw in debit_keywords:
        if kw in full_text:
            return False

    credit_keywords = [
        "received", "credited", "added to your account", "credited with",
        "money received", "received ₹", "received rs", "received from",
        "has sent you", "transferred to your", "successful deposit",
        "payment received"
    ]
    for kw in credit_keywords:
        if kw in full_text:
            return True

    if "fam" in sender.lower() or "fam" in subject_lower:
        if "received" in full_text or "credited" in full_text:
            return True

    return False

def parse_payment_details(body: str) -> Tuple[Optional[str], Optional[float]]:
    clean_text = clean_email_text(body)

    utr_match = re.search(r'\b(?:UTR|Ref\s*(?:no|num|number)?|UPI\s*Ref\s*(?:no|num|number)?)\s*[:\-\s\/\.]*\s*([a-zA-Z0-9]{8,22})\b', clean_text, re.IGNORECASE)
    utr = utr_match.group(1).strip() if utr_match else None

    if not utr:
        fmpi_match = re.search(r'\b(FMPI[a-zA-Z0-9]+)\b', clean_text, re.IGNORECASE)
        if fmpi_match:
            utr = fmpi_match.group(1).strip()

    if not utr:
        tx_match = re.search(r'\b(?:Transaction\s*(?:ID|Ref|Reference)?|Txn\s*ID)\s*[:\-\s\/\.]*\s*([a-zA-Z0-9\-]{8,40})\b', clean_text, re.IGNORECASE)
        utr = tx_match.group(1).strip() if tx_match else None

    if not utr:
        upi_match = re.search(r'\b(\d{12})\b', clean_text)
        if upi_match:
            utr = upi_match.group(1).strip()

    amount = None
    rcvd_amt_match = re.search(r'(?:received|credited|added)\s*(?:Rs\.?|INR|Amt|Amount|₹)?\s*[:\s\-]*([\d,]+\.?\d*)', clean_text, re.IGNORECASE)
    if rcvd_amt_match:
        try:
            val = rcvd_amt_match.group(1).replace(",", "").strip()
            if val:
                amount = float(val)
        except ValueError:
            pass

    if amount is None:
        amount_match = re.search(r'(?:Rs\.?|INR|Amt|Amount|₹)[:\s\-]*([\d,]+\.?\d*)', clean_text, re.IGNORECASE)
        if amount_match:
            try:
                val = amount_match.group(1).replace(",", "").strip()
                if val:
                    amount = float(val)
            except ValueError:
                pass

    return utr, amount

def parse_email_metadata(body: str) -> dict:
    clean_text = clean_email_text(body)

    recipient_match = re.search(r'Hey\s+([^,]+),', clean_text, re.IGNORECASE)
    recipient_name = recipient_match.group(1).strip() if recipient_match else None

    sender_match = re.search(r'received\s+[^a-zA-Z0-9]*[\d\.]+\s+from\s+([A-Za-z0-9\s]+?)(?:\s+at|\s+on|\s+with|\s*\.|\s*Transaction|\s*UTR|\s*Ref|\s*Updated|$)', clean_text, re.IGNORECASE)
    sender_name = sender_match.group(1).strip() if sender_match else None
    if not sender_name:
        sender_match2 = re.search(r'from\s+([A-Za-z0-9\s]+?)(?:\s+at|\s+on|\s+with|\s*\.|\s*Transaction|\s*UTR|\s*Ref|\s*Updated|$)', clean_text, re.IGNORECASE)
        sender_name = sender_match2.group(1).strip() if sender_match2 else None

    if sender_name:
        sender_name = re.sub(r'\s+(at|with|on|via)$', '', sender_name, flags=re.IGNORECASE).strip()

    tx_match = re.search(r'\b(?:Transaction\s*(?:ID|Ref|Reference)?|Txn\s*ID)\s*[:\-\s\/\.]*\s*([a-zA-Z0-9\-]+)\b', clean_text, re.IGNORECASE)
    tx_id = tx_match.group(1).strip() if tx_match else None
    if not tx_id:
        fmpi_match = re.search(r'\b(FMPI[a-zA-Z0-9]+)\b', clean_text, re.IGNORECASE)
        tx_id = fmpi_match.group(1).strip() if fmpi_match else None

    utr_match = re.search(r'\b(?:UTR|Ref\s*(?:no|num|number)?|UPI\s*Ref)\s*[:\-\s\/\.]*\s*([a-zA-Z0-9]+)\b', clean_text, re.IGNORECASE)
    utr = utr_match.group(1).strip() if utr_match else None
    if not utr and tx_id and tx_id.upper().startswith("FMPI"):
        utr = tx_id

    purpose_match = re.search(r'\b(?:Purpose)\s*[:\-\s\/\.]*\s*([a-zA-Z0-9\s]+?)(?:\.|\s*\n|$)', clean_text, re.IGNORECASE)
    purpose = purpose_match.group(1).strip() if purpose_match else None
    if not purpose and tx_id:
        purpose = tx_id

    return {
        "recipient_name": recipient_name,
        "sender_name": sender_name,
        "transaction_id": tx_id,
        "utr": utr,
        "purpose": purpose
    }

def list_messages(service, query: str = "", max_results: int = 100, page_token: str = None) -> dict:
    try:
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results,
            pageToken=page_token
        ).execute()
        return results
    except HttpError as error:
        raise error

def get_message_details(service, msg_id: str) -> dict:
    try:
        message = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        return message
    except HttpError as error:
        raise error

def send_webhook_notification(payment: dict):
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        return

    webhook_secret = os.environ.get("WEBHOOK_SECRET", "")

    import httpx
    import hmac
    import hashlib
    import json

    payload_bytes = json.dumps(payment, sort_keys=True).encode("utf-8")

    headers = {
        "Content-Type": "application/json"
    }

    if webhook_secret:
        headers["X-Webhook-Secret"] = webhook_secret
        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        headers["X-Gateway-Signature"] = signature

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(webhook_url, content=payload_bytes, headers=headers)
            print(f"Webhook notification sent to {webhook_url}. Status: {resp.status_code}")
    except Exception as e:
        print(f"Failed to send webhook notification: {e}")

def scan_unread_payments(db_session) -> list:
    from db import save_payment
    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"Skipping scan: {e}")
        return []

    processed_payments = []
    try:
        label_id = get_or_create_label(service, "PAYMENT_PROCESSED")
        results = service.users().messages().list(userId="me", q="is:unread").execute()
        messages = results.get("messages", [])

        for msg in messages:
            msg_id = msg["id"]
            message = service.users().messages().get(userId="me", id=msg_id, format="full").execute()

            headers = message.get("payload", {}).get("headers", [])
            subject = ""
            sender = ""
            date = ""

            for header in headers:
                if header["name"].lower() == "subject":
                    subject = header["value"]
                elif header["name"].lower() == "from":
                    sender = header["value"]
                elif header["name"].lower() == "date":
                    date = header["value"]

            body = decode_body(message.get("payload", {}))
            clean_b = clean_email_text(body)

            if not is_received_payment(subject, clean_b, sender):
                try:
                    service.users().messages().modify(
                        userId="me",
                        id=msg_id,
                        body={"removeLabelIds": ["UNREAD"]}
                    ).execute()
                except Exception:
                    pass
                continue

            utr, amount = parse_payment_details(body)
            meta = parse_email_metadata(body)
            final_utr = meta["utr"] if meta["utr"] else utr

            if not final_utr or len(str(final_utr).strip()) < 5:
                final_utr = f"MSG-{msg_id}"

            success = save_payment(
                db=db_session,
                utr=final_utr,
                message_id=msg_id,
                amount=amount,
                date=date,
                sender=sender,
                subject=subject,
                recipient_name=meta["recipient_name"],
                sender_name=meta["sender_name"],
                purpose=meta["purpose"]
            )

            if success:
                service.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={
                        "removeLabelIds": ["UNREAD"],
                        "addLabelIds": [label_id]
                    }
                ).execute()

                payment_data = {
                    "message_id": msg_id,
                    "utr": final_utr,
                    "amount": amount,
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "recipient_name": meta["recipient_name"],
                    "sender_name": meta["sender_name"],
                    "purpose": meta["purpose"]
                }
                processed_payments.append(payment_data)
                send_webhook_notification(payment_data)
    except HttpError as error:
        print(f"An error occurred during scanning: {error}")
        raise

    return processed_payments

def scan_all_fampay_payments(db_session, query: str = "from:no-reply@famapp.in OR FamApp OR FamPay OR payment", max_results: int = 500) -> list:
    from db import save_payment
    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"Skipping FamPay full scan: {e}")
        return []

    processed_payments = []
    try:
        messages = []
        page_token = None

        while True:
            kwargs = {"userId": "me", "q": query, "maxResults": 100}
            if page_token:
                kwargs["pageToken"] = page_token
            results = service.users().messages().list(**kwargs).execute()
            msgs = results.get("messages", [])
            messages.extend(msgs)
            page_token = results.get("nextPageToken")

            if not page_token or len(messages) >= max_results:
                break

        for msg in messages[:max_results]:
            msg_id = msg["id"]
            message = get_message_details(service, msg_id)

            headers = message.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
            sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
            date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)

            body = decode_body(message.get("payload", {}))
            clean_b = clean_email_text(body)

            if not is_received_payment(subject, clean_b, sender):
                continue

            meta = parse_email_metadata(body)
            parsed_utr, parsed_amount = parse_payment_details(body)

            utr = meta.get("utr") or parsed_utr
            amount = meta.get("amount") or parsed_amount

            if not utr or len(str(utr).strip()) < 5:
                utr = f"MSG-{msg_id}"

            success = save_payment(
                db=db_session,
                utr=utr,
                message_id=msg_id,
                amount=amount,
                date=date,
                sender=sender,
                subject=subject,
                recipient_name=meta.get("recipient_name"),
                sender_name=meta.get("sender_name"),
                purpose=meta.get("purpose")
            )

            if success:
                payment_data = {
                    "message_id": msg_id,
                    "utr": utr,
                    "amount": amount,
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "recipient_name": meta.get("recipient_name"),
                    "sender_name": meta.get("sender_name"),
                    "purpose": meta.get("purpose")
                }
                processed_payments.append(payment_data)
    except HttpError as error:
        print(f"An error occurred during FamPay full scan: {error}")

    return processed_payments
