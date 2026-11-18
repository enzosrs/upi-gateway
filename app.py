__author__ = "enzosrs"
__github__ = "https://github.com/enzosrs"
__community__ = "https://t.me/devcommunityx"

import os
import urllib.parse
import datetime
import email.utils
import socket
import asyncio
import time
import math
import random
import threading
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
socket.setdefaulttimeout(15.0)

from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, text, or_, desc
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

from db import init_db, get_db, Payment, save_payment, Order, AdminUser, IPBan, AuditLog
from gmail import (
    get_oauth_flow, save_credentials_from_auth_code, scan_unread_payments,
    store_flow_state, get_gmail_service, list_messages, get_message_details,
    parse_email_metadata, decode_body, parse_payment_details, send_webhook_notification,
    clean_email_text, is_received_payment
)
from telegram import (
    send_telegram_order_created, send_telegram_order_status_reply,
    send_admin_log, start_telegram_bot_loop
)

init_db()

scheduler = BackgroundScheduler()

def scheduled_scan():
    db = next(get_db())
    try:
        scan_unread_payments(db)
    except Exception as scan_ex:
        err_str = str(scan_ex)
        is_rate_limit = (
            "rateLimitExceeded" in err_str
            or "429" in err_str
            or "User-rate limit exceeded" in err_str
        )
        if is_rate_limit:
            send_admin_log(
                "⚠️ Gmail Rate Limit Exceeded",
                f"Background Gmail scanner hit API rate limit (429). Auto-retry on next interval (10s).\n<code>{err_str[:350]}</code>",
                level="WARNING"
            )
        print(f"[Scanner] Notice: {err_str[:200]}")
    finally:
        db.close()

def expire_pending_orders():
    db = next(get_db())
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
        stale_orders = db.query(Order).filter(
            Order.status == "PENDING",
            Order.created_at <= cutoff
        ).all()
        for order in stale_orders:
            order.status = "EXPIRED"
            try:
                send_telegram_order_status_reply(
                    telegram_message_id=order.telegram_message_id,
                    order_id=order.order_id,
                    status="EXPIRED",
                    amount=order.amount,
                    target_chat_id=order.telegram_chat_id
                )
            except Exception as tg_err:
                print(f"[Expiry] Telegram error: {tg_err}")

        db.commit()
    except Exception as err:
        db.rollback()
        print(f"[Expiry] Error: {err}")
    finally:
        db.close()

_unread_messages_cache = {
    "timestamp": 0.0,
    "data": []
}
_parsed_messages_cache = {}

def get_cached_unread_messages(service):
    global _unread_messages_cache
    now = time.time()
    if now - _unread_messages_cache["timestamp"] < 4.0:
        return _unread_messages_cache["data"]

    try:
        q = "from:no-reply@famapp.in OR FamApp OR FamPay OR payment OR received is:unread"
        results = service.users().messages().list(userId="me", q=q, maxResults=15).execute()
        messages = results.get("messages", [])
        _unread_messages_cache["timestamp"] = now
        _unread_messages_cache["data"] = messages
        return messages
    except Exception as e:
        if _unread_messages_cache["data"]:
            return _unread_messages_cache["data"]
        raise e

def get_cached_parsed_payment(msg_id):
    global _parsed_messages_cache
    return _parsed_messages_cache.get(msg_id)

def set_cached_parsed_payment(msg_id, data):
    global _parsed_messages_cache
    _parsed_messages_cache[msg_id] = data

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        expire_pending_orders()
    except Exception as e:
        print(f"[Lifespan] Order cleanup error: {e}")

    scheduler.add_job(scheduled_scan, "interval", seconds=60, id="gmail_scanner")
    scheduler.add_job(expire_pending_orders, "interval", seconds=60, id="order_expiry")
    scheduler.start()

    db = next(get_db())
    try:
        pending_orders = db.query(Order).filter(Order.status == "PENDING").all()
        for order in pending_orders:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
            if order.created_at >= cutoff:
                threading.Thread(target=monitor_order_payment, args=(order.order_id,), daemon=True).start()
    except Exception as e:
        print(f"[Lifespan] Error resuming pending orders: {e}")
    finally:
        db.close()

    threading.Thread(target=start_telegram_bot_loop, daemon=True).start()
    print("=" * 60)
    print("FamPay UPI Payment Gateway")
    print("Developed by: enzosrs (https://github.com/enzosrs)")
    print("Telegram Community: https://t.me/devcommunityx")
    print("=" * 60)
    yield

app = FastAPI(
    title="FamPay UPI Payment Gateway",
    description="Zero-fee automated UPI payment gateway. Developed by enzosrs (https://t.me/devcommunityx)",
    version="2.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def add_gateway_watermark(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Powered-By"] = "enzosrs-upi-gateway"
    response.headers["X-Author"] = "enzosrs"
    response.headers["X-Community"] = "https://t.me/devcommunityx"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def gateway_root():
    return {
        "name": "FamPay UPI Payment Gateway",
        "version": "2.0.0",
        "author": "enzosrs",
        "github": "https://github.com/enzosrs",
        "community": "https://t.me/devcommunityx",
        "docs": "/docs",
        "status": "online"
    }

def get_redirect_uri(request: Request) -> str:
    env_uri = os.environ.get("GOOGLE_REDIRECT_URI")
    if env_uri:
        return env_uri

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc

    if "localhost" not in host and "127.0.0.1" not in host:
        scheme = "https"

    return f"{scheme}://{host}/auth/google/callback"

@app.get("/auth")
def auth(request: Request):
    redirect_uri = get_redirect_uri(request)
    flow = get_oauth_flow(redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true"
    )
    store_flow_state(state, flow.code_verifier)
    return RedirectResponse(url=authorization_url)

@app.get("/oauth2callback")
@app.get("/auth/google/callback")
def oauth2callback(request: Request, code: str = None, error: str = None, state: str = None):
    if error:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code missing")

    redirect_uri = get_redirect_uri(request)
    try:
        save_credentials_from_auth_code(code, redirect_uri, state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve tokens: {e}")

    return {"status": "success", "message": "Authentication successful. You can start scanning."}

class GatewayPayload(BaseModel):
    key: str
    name: str

class VerifyPaymentRequest(GatewayPayload):
    utr: str
    order_id: Optional[str] = None
    amount: Optional[float] = None

class AutopaySubmitUtrRequest(BaseModel):
    order_id: str
    utr: str

class EmailsRequest(GatewayPayload):
    query: str = "from:no-reply@famapp.in"
    max_results: int = 50
    page_token: str = None

class AutopayCreateRequest(BaseModel):
    amount: float
    note: Optional[str] = None
    customer_name: Optional[str] = None
    customer_mobile: Optional[str] = None
    client_ip: Optional[str] = None

class AutopayVerifyRequest(BaseModel):
    order_id: str

GATEWAY_API_KEY = os.environ.get("GATEWAY_API_KEY", "")
GATEWAY_CLIENT_NAME = os.environ.get("GATEWAY_CLIENT_NAME", "")

def verify_gateway_auth(payload: GatewayPayload):
    if GATEWAY_API_KEY and GATEWAY_CLIENT_NAME:
        if payload.key != GATEWAY_API_KEY or payload.name != GATEWAY_CLIENT_NAME:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid key or name")

@app.post("/scan")
def scan(payload: GatewayPayload, db: Session = Depends(get_db)):
    verify_gateway_auth(payload)
    try:
        payments = scan_unread_payments(db)
        return {"status": "success", "scanned_payments": payments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/emails")
def list_emails(payload: EmailsRequest):
    verify_gateway_auth(payload)
    try:
        service = get_gmail_service()
        result = list_messages(service, query=payload.query, max_results=payload.max_results, page_token=payload.page_token)
        messages = result.get("messages", [])

        detailed_messages = []
        for msg in messages:
            msg_id = msg["id"]
            try:
                detail = get_message_details(service, msg_id)
                headers = detail.get("payload", {}).get("headers", [])

                subject = ""
                sender = ""
                date = ""
                for header in headers:
                    name_lower = header["name"].lower()
                    if name_lower == "subject":
                        subject = header["value"]
                    elif name_lower == "from":
                        sender = header["value"]
                    elif name_lower == "date":
                        date = header["value"]

                body = decode_body(detail.get("payload", {}))
                utr, amount = parse_payment_details(body)
                meta = parse_email_metadata(body)

                detailed_messages.append({
                    "id": msg_id,
                    "threadId": msg.get("threadId"),
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "recipient_name": meta["recipient_name"],
                    "sender_name": meta["sender_name"],
                    "amount": amount,
                    "utr": meta["utr"] if meta["utr"] else utr,
                    "transaction_id": meta["transaction_id"],
                    "purpose": meta["purpose"],
                    "snippet": detail.get("snippet", ""),
                    "body": body
                })
            except Exception as msg_err:
                print(f"Failed to fetch details for message {msg_id}: {msg_err}")

        return {
            "messages": detailed_messages,
            "nextPageToken": result.get("nextPageToken"),
            "resultSizeEstimate": result.get("resultSizeEstimate")
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/emails/{msg_id}")
def get_email(msg_id: str, payload: GatewayPayload):
    verify_gateway_auth(payload)
    try:
        service = get_gmail_service()
        message = get_message_details(service, msg_id)
        return message
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/payments")
def list_payments(payload: GatewayPayload, db: Session = Depends(get_db)):
    verify_gateway_auth(payload)
    payments = db.query(Payment).order_by(Payment.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "utr": p.utr,
            "message_id": p.message_id,
            "amount": p.amount,
            "date": p.date,
            "sender": p.sender,
            "subject": p.subject,
            "recipient_name": p.recipient_name,
            "sender_name": p.sender_name,
            "purpose": p.purpose,
            "created_at": p.created_at
        }
        for p in payments
    ]

@app.post("/verify/payment")
def verify_payment(payload: VerifyPaymentRequest, db: Session = Depends(get_db)):
    verify_gateway_auth(payload)
    raw_utr = (payload.utr or "").strip()
    utr_to_check = raw_utr.replace(" ", "").replace("-", "")
    if not utr_to_check or len(utr_to_check) < 6 or utr_to_check.upper().startswith("MSG-"):
        raise HTTPException(status_code=400, detail="Invalid UTR format. Minimum 6 characters required.")

    already_claimed = db.query(Order).filter(
        func.lower(Order.utr) == utr_to_check.lower(),
        Order.status == "SUCCESS"
    ).first()
    if already_claimed:
        if payload.order_id and already_claimed.order_id != payload.order_id:
            raise HTTPException(
                status_code=409,
                detail=f"This UTR ({utr_to_check}) has already been claimed for order {already_claimed.order_id}."
            )

    payment = db.query(Payment).filter(
        or_(
            func.lower(Payment.utr) == utr_to_check.lower(),
            func.lower(Payment.purpose) == utr_to_check.lower()
        )
    ).first()

    if not payment:
        try:
            service = get_gmail_service()
            if service:
                q = f'"{utr_to_check}"'
                results = service.users().messages().list(userId="me", q=q, maxResults=5).execute()
                messages = results.get("messages", [])

                for msg in messages:
                    msg_id = msg["id"]
                    existing = db.query(Payment).filter(Payment.message_id == msg_id).first()
                    if existing:
                        clean_ex_utr = (existing.utr or "").replace(" ", "").replace("-", "").lower()
                        clean_ex_purp = (existing.purpose or "").replace(" ", "").replace("-", "").lower()
                        if utr_to_check.lower() in (clean_ex_utr, clean_ex_purp):
                            payment = existing
                            break
                        continue
                    else:
                        msg_detail = get_message_details(service, msg_id)
                        headers = msg_detail.get("payload", {}).get("headers", [])
                        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
                        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
                        date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)

                        body = decode_body(msg_detail.get("payload", {}))
                        clean_b = clean_email_text(body)
                        if not is_received_payment(subject, clean_b, sender):
                            continue

                        meta = parse_email_metadata(body)
                        parsed_utr, parsed_amount = parse_payment_details(body)
                        found_utr = meta.get("utr") or parsed_utr
                        tx_id = meta.get("transaction_id")
                        clean_found = (found_utr or "").replace(" ", "").replace("-", "")
                        clean_tx = (tx_id or "").replace(" ", "").replace("-", "")

                        if (clean_found.lower() == utr_to_check.lower()
                            or clean_tx.lower() == utr_to_check.lower()
                            or utr_to_check.lower() in clean_b.lower()):
                            amount_val = meta.get("amount") if meta.get("amount") is not None else parsed_amount
                            save_payment(
                                db=db,
                                message_id=msg_id,
                                utr=found_utr or utr_to_check,
                                amount=amount_val,
                                sender=sender,
                                subject=subject,
                                date=date,
                                recipient_name=meta.get("recipient_name"),
                                sender_name=meta.get("sender_name"),
                                purpose=tx_id or meta.get("purpose")
                            )
                            payment = db.query(Payment).filter(
                                or_(
                                    func.lower(Payment.utr) == (found_utr or utr_to_check).lower(),
                                    func.lower(Payment.purpose) == utr_to_check.lower()
                                )
                            ).first()

                            payload_to_send = {
                                "message_id": msg_id,
                                "utr": found_utr or utr_to_check,
                                "amount": float(amount_val) if amount_val else None,
                                "sender": sender,
                                "subject": subject,
                                "date": date,
                                "recipient_name": meta.get("recipient_name"),
                                "sender_name": meta.get("sender_name"),
                                "purpose": meta.get("purpose")
                            }
                            send_webhook_notification(payload_to_send)
                            break
        except Exception as scan_err:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"Direct GMail lookup failed: {scan_err}")

    if payment:
        if payload.amount and payment.amount:
            if abs(payment.amount - payload.amount) > 0.05:
                raise HTTPException(
                    status_code=400,
                    detail=f"Amount mismatch: Payment amount ₹{payment.amount:.2f} does not match expected ₹{payload.amount:.2f}"
                )

        linked_order = None
        if payload.order_id:
            ord_obj = db.query(Order).filter(Order.order_id == payload.order_id).first()
            if ord_obj:
                if ord_obj.status == "PENDING":
                    ord_obj.status = "SUCCESS"
                    ord_obj.utr = payment.utr or utr_to_check
                    db.commit()
                    linked_order = ord_obj
                    try:
                        send_telegram_order_status_reply(
                            telegram_message_id=ord_obj.telegram_message_id,
                            order_id=ord_obj.order_id,
                            status="SUCCESS",
                            utr=ord_obj.utr,
                            amount=ord_obj.amount,
                            sender_name=payment.sender_name or "UPI Customer",
                            target_chat_id=ord_obj.telegram_chat_id
                        )
                    except Exception as tg_e:
                        print(f"Telegram notify error: {tg_e}")
                elif ord_obj.status == "SUCCESS":
                    linked_order = ord_obj
        elif already_claimed:
            linked_order = already_claimed
        else:
            if payment.amount and payment.amount > 0:
                try:
                    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
                    p_order = db.query(Order).filter(
                        Order.status == "PENDING",
                        Order.amount >= payment.amount - 0.05,
                        Order.amount <= payment.amount + 0.05,
                        Order.created_at >= cutoff
                    ).order_by(Order.created_at.desc()).first()
                    if p_order:
                        p_order.status = "SUCCESS"
                        p_order.utr = payment.utr or utr_to_check
                        db.commit()
                        linked_order = p_order
                        try:
                            send_telegram_order_status_reply(
                                telegram_message_id=p_order.telegram_message_id,
                                order_id=p_order.order_id,
                                status="SUCCESS",
                                utr=p_order.utr,
                                amount=p_order.amount,
                                sender_name=payment.sender_name or "UPI Customer",
                                target_chat_id=p_order.telegram_chat_id
                            )
                        except Exception as tg_e:
                            print(f"Telegram notify error: {tg_e}")
                except Exception as link_err:
                    db.rollback()
                    print(f"Auto-link order error: {link_err}")

        return {
            "status": "success",
            "message": "Payment successful",
            "order_id": linked_order.order_id if linked_order else (already_claimed.order_id if already_claimed else None),
            "payment": {
                "id": payment.id,
                "utr": payment.utr,
                "amount": payment.amount,
                "sender": payment.sender,
                "subject": payment.subject,
                "date": payment.date,
                "recipient_name": payment.recipient_name,
                "sender_name": payment.sender_name,
                "purpose": payment.purpose,
                "created_at": payment.created_at
            }
        }
    else:
        raise HTTPException(
            status_code=404,
            detail="Payment not found or invalid UTR"
        )

_RECENT_ORDERS_CACHE = {}

def update_order_cache_status(order_id: str, status: str, utr = None):
    if order_id in _RECENT_ORDERS_CACHE:
        _RECENT_ORDERS_CACHE[order_id]["order_status"] = status
        if utr:
            _RECENT_ORDERS_CACHE[order_id]["utr"] = utr

@app.post("/autopay")
def create_autopay_order(payload: AutopayCreateRequest, request: Request, db: Session = Depends(get_db)):
    from security import enforce_order_rate_limit, get_client_ip, log_audit_event, sanitize_string

    client_ip = get_client_ip(request, payload)
    enforce_order_rate_limit(request, db, client_ip=client_ip)

    if payload.amount is None or math.isnan(payload.amount) or math.isinf(payload.amount):
        raise HTTPException(status_code=400, detail="Invalid payment amount: Numeric amount required")
    if payload.amount < 1.0 or payload.amount > 500000.0:
        raise HTTPException(status_code=400, detail="Amount out of bounds: Minimum amount is ₹1.00 and maximum is ₹5,00,000.00")

    clean_amount = round(float(payload.amount), 2)
    clean_name = sanitize_string(getattr(payload, 'customer_name', None), 60) if getattr(payload, 'customer_name', None) else None
    clean_mobile = sanitize_string(getattr(payload, 'customer_mobile', None), 20) if getattr(payload, 'customer_mobile', None) else None

    upi_id = os.environ.get("UPI_ID", "")
    order_id = f"ORD{int(time.time())}{random.randint(1000, 9999)}"

    upi_url = f"upi://pay?pa={upi_id}&pn=Payment&am={clean_amount:.2f}&cu=INR"
    encoded_upi = urllib.parse.quote_plus(upi_url)
    qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=260x260&data={encoded_upi}&qzone=1&margin=4"

    app_url = os.environ.get("APP_URL", "http://localhost:8001").rstrip("/")
    payment_url = f"{app_url}/checkout/{order_id}"

    tg_admin_chat = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
    tg_msg_id = send_telegram_order_created(order_id, payload.amount, upi_id, payment_url)

    db_order = Order(
        order_id=order_id,
        amount=payload.amount,
        upi_id=upi_id,
        status="PENDING",
        telegram_message_id=tg_msg_id,
        telegram_chat_id=tg_admin_chat
    )
    db.add(db_order)
    db.commit()

    now_utc_dt = datetime.datetime.now(datetime.timezone.utc)
    _RECENT_ORDERS_CACHE[order_id] = {
        "order_id": order_id,
        "amount": clean_amount,
        "upi_id": upi_id,
        "upi_url": upi_url,
        "qr_code_url": qr_code_url,
        "payment_url": payment_url,
        "order_status": "PENDING",
        "utr": None,
        "created_at_dt": now_utc_dt,
        "created_at": now_utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "created_ts": time.time(),
    }
    try:
        log_audit_event(db, "ORDER_CREATED", "INFO", f"Order {order_id} generated for ₹{clean_amount:.2f}", ip=client_ip)
    except Exception:
        pass
    try:
        from d1 import d1_insert_order
        d1_insert_order(order_id, payload.amount, upi_id, "PENDING")
    except Exception as d1_err:
        print(f"[D1 Sync] {d1_err}")

    threading.Thread(target=monitor_order_payment, args=(order_id,), daemon=True).start()

    now_ts = time.time()
    return {
        "status": "success",
        "order_id": order_id,
        "amount": payload.amount,
        "upi_id": upi_id,
        "upi_url": upi_url,
        "qr_code_url": qr_code_url,
        "payment_url": payment_url,
        "time_left": 600,
        "expires_at": int((now_ts + 600) * 1000)
    }

@app.get("/autopay/qr/{order_id}")
def get_autopay_qr(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    upi_url = f"upi://pay?pa={order.upi_id}&pn=Payment&am={order.amount:.2f}&cu=INR"
    encoded_url = urllib.parse.quote_plus(upi_url)
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&margin=20&data={encoded_url}"
    return RedirectResponse(url=qr_api_url)

@app.get("/autopay")
def get_autopay_order_info(request: Request, order_id: Optional[str] = None, db: Session = Depends(get_db)):
    accept = request.headers.get("accept", "").lower()
    if "text/html" in accept:
        if order_id:
            return RedirectResponse(url=f"/checkout/{urllib.parse.quote_plus(order_id)}")
        return RedirectResponse(url="/checkout")

    if not order_id:
        raise HTTPException(status_code=400, detail="Missing required query parameter: order_id")

    cached = _RECENT_ORDERS_CACHE.get(order_id)
    if cached:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        elapsed_sec = (now_utc - cached["created_at_dt"]).total_seconds()
        time_left = max(0, int(600 - elapsed_sec))
        expires_at_ms = int((cached["created_ts"] + 600) * 1000)
        eff_status = cached["order_status"]
        if eff_status == "PENDING" and time_left <= 0:
            eff_status = "EXPIRED"
            cached["order_status"] = "EXPIRED"
        return {
            "status": "success",
            "order_id": cached["order_id"],
            "amount": cached["amount"],
            "upi_id": cached["upi_id"],
            "upi_url": cached["upi_url"],
            "qr_code_url": cached["qr_code_url"],
            "order_status": eff_status,
            "utr": cached.get("utr"),
            "created_at": cached["created_at"],
            "time_left": time_left,
            "expires_at": expires_at_ms
        }

    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    upi_url = f"upi://pay?pa={order.upi_id}&pn=Payment&am={order.amount:.2f}&cu=INR"
    encoded_upi = urllib.parse.quote_plus(upi_url)
    qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=260x260&data={encoded_upi}&qzone=1&margin=4"

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if order.created_at:
        o_dt = order.created_at
        if o_dt.tzinfo is None:
            o_dt = o_dt.replace(tzinfo=datetime.timezone.utc)
        elapsed_sec = (now_utc - o_dt).total_seconds()
        created_ts = o_dt.timestamp()
    else:
        elapsed_sec = 0
        created_ts = now_utc.timestamp()

    time_left = max(0, int(600 - elapsed_sec))
    expires_at_ms = int((created_ts + 600) * 1000)

    effective_status = order.status
    if order.status == "PENDING" and time_left <= 0:
        effective_status = "EXPIRED"
        order.status = "EXPIRED"
        try:
            db.commit()
            send_telegram_order_status_reply(
                telegram_message_id=order.telegram_message_id,
                order_id=order.order_id,
                status="EXPIRED",
                amount=order.amount,
                target_chat_id=order.telegram_chat_id
            )
        except Exception as tg_err:
            db.rollback()
            print(f"[AutopayInfo Expiry] Telegram notify error: {tg_err}")

    return {
        "status": "success",
        "order_id": order.order_id,
        "amount": order.amount,
        "upi_id": order.upi_id,
        "upi_url": upi_url,
        "qr_code_url": qr_code_url,
        "order_status": effective_status,
        "utr": order.utr,
        "created_at": (order.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if order.created_at else None),
        "time_left": time_left,
        "expires_at": expires_at_ms
    }

def scan_and_match_for_order(db: Session, order: Order) -> bool:
    tolerance = 0.01
    try:
        from gmail import (
            get_gmail_service, get_message_details, decode_body,
            parse_payment_details, parse_email_metadata, is_received_payment,
            clean_email_text, send_webhook_notification
        )
        from db import save_payment as db_save_payment
        from datetime import timedelta

        cutoff_time = order.created_at - timedelta(seconds=60)
        existing_match = db.query(Payment).filter(
            Payment.amount != None,
            func.abs(Payment.amount - order.amount) <= tolerance,
            Payment.created_at >= cutoff_time
        ).all()

        for p in existing_match:
            linked_order = db.query(Order).filter(
                Order.utr == p.utr,
                Order.status == "SUCCESS"
            ).first()
            if not linked_order:
                db.refresh(order)
                if order.status == "SUCCESS":
                    return True

                order.status = "SUCCESS"
                order.utr = p.utr
                db.commit()

                send_telegram_order_status_reply(
                    telegram_message_id=order.telegram_message_id,
                    order_id=order.order_id,
                    status="SUCCESS",
                    utr=p.utr,
                    amount=order.amount,
                    sender_name=p.sender_name or "UPI Customer",
                    target_chat_id=order.telegram_chat_id
                )
                return True

        service = get_gmail_service()
        if not service:
            return False

        q = "is:unread (from:no-reply@famapp.in OR FamApp OR FamPay OR payment OR received)"
        results = service.users().messages().list(userId="me", q=q, maxResults=10).execute()
        messages = results.get("messages", [])

        for msg in messages:
            msg_id = msg["id"]

            existing = db.query(Payment).filter(Payment.message_id == msg_id).first()
            if existing:
                if (
                    existing.amount is not None
                    and abs(existing.amount - order.amount) <= tolerance
                    and existing.created_at >= order.created_at
                ):
                    order.status = "SUCCESS"
                    order.utr = existing.utr
                    db.commit()

                    send_telegram_order_status_reply(
                        telegram_message_id=order.telegram_message_id,
                        order_id=order.order_id,
                        status="SUCCESS",
                        utr=existing.utr,
                        amount=order.amount,
                        sender_name=existing.sender_name or "UPI Customer",
                        target_chat_id=order.telegram_chat_id
                    )
                    return True
                continue

            msg_detail = get_message_details(service, msg_id)
            headers = msg_detail.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
            sender  = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
            date    = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
            body    = decode_body(msg_detail.get("payload", {}))
            clean_b = clean_email_text(body)

            if not is_received_payment(subject, clean_b, sender):
                try:
                    service.users().messages().modify(
                        userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
                    ).execute()
                except Exception:
                    pass
                continue

            utr_found, amt_found = parse_payment_details(body)
            meta = parse_email_metadata(body)
            final_utr = meta.get("utr") or utr_found or f"MSG-{msg_id}"

            db_save_payment(
                db=db,
                utr=final_utr,
                message_id=msg_id,
                amount=amt_found,
                date=date,
                sender=sender,
                subject=subject,
                recipient_name=meta.get("recipient_name"),
                sender_name=meta.get("sender_name"),
                purpose=meta.get("purpose")
            )

            if amt_found is not None and abs(amt_found - order.amount) <= tolerance:
                db.expire(order)
                fresh_order = db.query(Order).filter(Order.order_id == order.order_id).first()
                already_notified = fresh_order and fresh_order.status == "SUCCESS"

                if not already_notified:
                    order.status = "SUCCESS"
                    order.utr = final_utr
                    db.commit()

                send_webhook_notification({
                    "message_id": msg_id,
                    "utr": final_utr,
                    "amount": amt_found,
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "recipient_name": meta.get("recipient_name"),
                    "sender_name": meta.get("sender_name"),
                    "purpose": meta.get("purpose")
                })

                if not already_notified:
                    send_telegram_order_status_reply(
                        telegram_message_id=order.telegram_message_id,
                        order_id=order.order_id,
                        status="SUCCESS",
                        utr=final_utr,
                        amount=order.amount,
                        sender_name=meta.get("sender_name") or "UPI Customer",
                        target_chat_id=order.telegram_chat_id
                    )
                return True
    except Exception as e:
        err_str = str(e)
        if "rateLimitExceeded" in err_str or "429" in err_str:
            time.sleep(8.0)
        else:
            print(f"[Monitor-{order.order_id}] Scan failed: {e}")
        return False
    return False

def monitor_order_payment(order_id: str):
    from db import SessionLocal, Order

    for cycle in range(300):
        db = SessionLocal()
        try:
            order = db.query(Order).filter(Order.order_id == order_id).first()
            if not order:
                break

            if order.status != "PENDING":
                break

            now_utc = datetime.datetime.utcnow()
            if order.created_at:
                t = order.created_at.replace(tzinfo=None) if order.created_at.tzinfo else order.created_at
                if (now_utc - t).total_seconds() >= 600:
                    order.status = "EXPIRED"
                    try:
                        db.commit()
                        send_telegram_order_status_reply(
                            telegram_message_id=order.telegram_message_id,
                            order_id=order.order_id,
                            status="EXPIRED",
                            amount=order.amount,
                            target_chat_id=order.telegram_chat_id
                        )
                    except Exception as tg_err:
                        db.rollback()
                        print(f"[Monitor-{order_id}] Telegram expiry notify error: {tg_err}")
                    break

            matched = scan_and_match_for_order(db, order)
            if matched:
                break
        except Exception as err:
            err_str = str(err)
            if "rateLimit" in err_str or "429" in err_str:
                time.sleep(4.0)
            else:
                time.sleep(2.0)
        finally:
            db.close()

        time.sleep(2.0)

    db = SessionLocal()
    try:
        final_order = db.query(Order).filter(Order.order_id == order_id).first()
        if final_order and final_order.status == "PENDING":
            final_order.status = "EXPIRED"
            db.commit()
            send_telegram_order_status_reply(
                telegram_message_id=final_order.telegram_message_id,
                order_id=final_order.order_id,
                status="EXPIRED",
                amount=final_order.amount,
                target_chat_id=final_order.telegram_chat_id
            )
    except Exception as e:
        print(f"[Monitor-{order_id}] Final check error: {e}")
    finally:
        db.close()

@app.post("/autopay/verify")
def autopay_verify_order(payload: AutopayVerifyRequest, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_id == payload.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == "SUCCESS":
        return {
            "status": "success",
            "order_id": order.order_id,
            "message": "Payment verified",
            "utr": order.utr,
            "amount": order.amount
        }

    if order.status in ("EXPIRED", "FAILED"):
        raise HTTPException(status_code=404, detail=f"Order is {order.status}")

    raise HTTPException(status_code=404, detail="Payment not yet received")

@app.post("/autopay/submit-utr")
def autopay_submit_utr(payload: AutopaySubmitUtrRequest, request: Request, db: Session = Depends(get_db)):
    from security import sanitize_order_id, sanitize_utr, get_client_ip, log_audit_event
    client_ip = get_client_ip(request)
    order_id = sanitize_order_id(payload.order_id)
    clean_utr = sanitize_utr(payload.utr)

    if not order_id:
        raise HTTPException(status_code=400, detail="Order ID cannot be empty")
    if not clean_utr or len(clean_utr) < 6:
        raise HTTPException(status_code=400, detail="Please enter a valid 12-digit UTR or Transaction ID (min 6 chars)")

    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == "SUCCESS":
        return {
            "status": "success",
            "message": "Payment is already verified for this order",
            "order_id": order.order_id,
            "utr": order.utr,
            "amount": order.amount
        }

    claimed = db.query(Order).filter(
        func.lower(Order.utr) == clean_utr.lower(),
        Order.status == "SUCCESS"
    ).first()
    if claimed and claimed.order_id != order.order_id:
        raise HTTPException(
            status_code=409,
            detail=f"This UTR has already been claimed for another order ({claimed.order_id})."
        )

    payment = db.query(Payment).filter(
        or_(
            func.lower(Payment.utr) == clean_utr.lower(),
            func.lower(Payment.purpose) == clean_utr.lower()
        )
    ).first()

    if not payment:
        try:
            service = get_gmail_service()
            if service:
                q = f'"{clean_utr}"'
                results = service.users().messages().list(userId="me", q=q, maxResults=5).execute()
                messages = results.get("messages", [])
                for msg in messages:
                    msg_id = msg["id"]
                    msg_detail = get_message_details(service, msg_id)
                    headers = msg_detail.get("payload", {}).get("headers", [])
                    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
                    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
                    date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
                    body = decode_body(msg_detail.get("payload", {}))
                    clean_b = clean_email_text(body)

                    if not is_received_payment(subject, clean_b, sender):
                        continue

                    meta = parse_email_metadata(body)
                    parsed_utr, parsed_amt = parse_payment_details(body)
                    found_utr = meta.get("utr") or parsed_utr
                    tx_id = meta.get("transaction_id")
                    cf = (found_utr or "").replace(" ", "").replace("-", "")
                    ctx = (tx_id or "").replace(" ", "").replace("-", "")

                    if (cf.lower() == clean_utr.lower()
                        or ctx.lower() == clean_utr.lower()
                        or clean_utr.lower() in clean_b.lower()):
                        amt_val = meta.get("amount") if meta.get("amount") is not None else parsed_amt
                        save_payment(
                            db=db,
                            message_id=msg_id,
                            utr=found_utr or clean_utr,
                            amount=amt_val,
                            sender=sender,
                            subject=subject,
                            date=date,
                            recipient_name=meta.get("recipient_name"),
                            sender_name=meta.get("sender_name"),
                            purpose=tx_id or meta.get("purpose")
                        )
                        payment = db.query(Payment).filter(
                            or_(
                                func.lower(Payment.utr) == (found_utr or clean_utr).lower(),
                                func.lower(Payment.purpose) == clean_utr.lower()
                            )
                        ).first()
                        break
        except Exception as scan_err:
            print(f"[SubmitUTR] Gmail search error: {scan_err}")

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment not found for this UTR yet. Please allow a few seconds for email delivery and try again."
        )

    if payment.amount is not None and order.amount is not None:
        if abs(payment.amount - order.amount) > 0.05:
            raise HTTPException(
                status_code=400,
                detail=f"Amount mismatch: Payment received is ₹{payment.amount:.2f}, but this order is for ₹{order.amount:.2f}."
            )

    order.status = "SUCCESS"
    order.utr = payment.utr or clean_utr
    db.commit()
    try:
        from d1 import d1_update_order_status
        d1_update_order_status(order.order_id, "SUCCESS", order.utr)
    except Exception:
        pass

    try:
        send_telegram_order_status_reply(
            telegram_message_id=order.telegram_message_id,
            order_id=order.order_id,
            status="SUCCESS",
            utr=order.utr,
            amount=order.amount,
            sender_name=payment.sender_name or "UPI Customer",
            target_chat_id=order.telegram_chat_id
        )
    except Exception as tg_err:
        print(f"Telegram notify error in submit_utr: {tg_err}")

    try:
        send_webhook_notification({
            "order_id": order.order_id,
            "message_id": payment.message_id,
            "utr": order.utr,
            "amount": payment.amount,
            "sender": payment.sender,
            "subject": payment.subject,
            "sender_name": payment.sender_name,
            "status": "SUCCESS"
        })
    except Exception as wh_err:
        print(f"Webhook error in submit_utr: {wh_err}")

    return {
        "status": "success",
        "message": "Payment verified and order approved successfully!",
        "order_id": order.order_id,
        "utr": order.utr,
        "amount": order.amount
    }

@app.get("/doc")
@app.get("/docs.html")
@app.get("/api-docs")
def get_documentation():
    return RedirectResponse(url="/docs")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_TOKEN_SECRET = os.environ.get("ADMIN_TOKEN_SECRET", "")

class AdminLoginRequest(BaseModel):
    username: str
    password: str

def verify_admin_token_header(request: Request):
    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    elif "token" in request.query_params:
        token = request.query_params["token"]

    expected_token = f"admin_session_{ADMIN_USERNAME}_{ADMIN_TOKEN_SECRET}"
    if not token or token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin session")
    return True

@app.post("/admin/login")
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    is_valid = False
    admin_user = payload.username.strip()

    try:
        from d1 import d1_is_enabled, d1_verify_admin_login
        if d1_is_enabled():
            is_valid = d1_verify_admin_login(admin_user, payload.password)
    except Exception as d1_err:
        print(f"[Admin Auth] D1 check note: {d1_err}")

    if not is_valid:
        try:
            db_admin = db.query(AdminUser).filter(AdminUser.username == admin_user).first()
            if db_admin and db_admin.password_hash == payload.password:
                is_valid = True
                db_admin.last_login = datetime.datetime.utcnow()
                db.commit()
        except Exception as db_err:
            print(f"[Admin Auth] DB check note: {db_err}")

    if not is_valid:
        if admin_user == ADMIN_USERNAME and payload.password == ADMIN_PASSWORD:
            is_valid = True

    if is_valid:
        token = f"admin_session_{ADMIN_USERNAME}_{ADMIN_TOKEN_SECRET}"
        return {
            "status": "success",
            "message": "Login successful",
            "token": token,
            "username": admin_user
        }
    raise HTTPException(status_code=401, detail="Invalid admin username or password")

def get_unified_data(db: Session):
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_utc = datetime.datetime.utcnow()

    orders_list = db.query(Order).order_by(Order.created_at.desc()).all()
    payments_list = db.query(Payment).order_by(Payment.created_at.desc()).all()

    need_commit = False
    for o in orders_list:
        if o.status == "PENDING" and o.created_at:
            if (now_utc - o.created_at).total_seconds() > 600:
                o.status = "EXPIRED"
                need_commit = True
                try:
                    send_telegram_order_status_reply(
                        telegram_message_id=o.telegram_message_id,
                        order_id=o.order_id,
                        status="EXPIRED",
                        amount=o.amount,
                        target_chat_id=o.telegram_chat_id
                    )
                except Exception as tg_err:
                    print(f"[UnifiedData Expiry] Telegram notify error: {tg_err}")
    if need_commit:
        try:
            db.commit()
        except:
            db.rollback()

    def to_ist(val):
        if not val:
            return None
        if isinstance(val, datetime.datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=datetime.timezone.utc).astimezone(ist_tz)
            return val.astimezone(ist_tz)
        val_str = str(val).strip()
        try:
            dt = email.utils.parsedate_to_datetime(val_str)
            return dt.astimezone(ist_tz)
        except Exception:
            pass
        try:
            dt = datetime.datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc).astimezone(ist_tz)
            return dt.astimezone(ist_tz)
        except Exception:
            pass
        return None

    def is_received_credit_payment(sender: str, subject: str, purpose: str = "", utr: str = "") -> bool:
        if not utr or utr.startswith("MSG-") or utr.startswith("MSG"):
            return False
        sender_str = (sender or "").lower()
        valid_senders = ["famapp", "fampay", "bank", "upi", "hdfc", "axis", "icici", "sbi", "paytm", "phonepe", "razorpay"]
        if not any(v in sender_str for v in valid_senders):
            return False
        s = (subject or "").lower()
        p = (purpose or "").lower()
        combined = f"{s} {p}"

        debit_keywords = [
            "your payment of", "payment of", "paid to", "sent to", "debited", "you paid",
            "spent", "transfer to", "money sent", "successful payment", "beneficiary added",
            "beneficiary", "order placed", "recharge of"
        ]
        if any(k in combined for k in debit_keywords):
            return False

        credit_keywords = [
            "you received", "received in your", "received from", "credited to",
            "amount credited", "added to your", "received rs", "received ₹"
        ]
        if any(k in combined for k in credit_keywords):
            return True

        if "received" in s and ("famx" in s or "fampay" in s or "account" in s or "₹" in s or "rs" in s):
            return True

        return False

    def is_sent_debit_payment(sender: str, subject: str, purpose: str = "", utr: str = "") -> bool:
        if not utr or utr.startswith("MSG-") or utr.startswith("MSG"):
            return False
        s = (subject or "").lower()
        p = (purpose or "").lower()
        combined = f"{s} {p}"
        debit_keywords = [
            "your payment of", "payment of", "paid to", "sent to", "debited", "you paid",
            "spent", "transfer to", "money sent", "successful payment"
        ]
        return any(k in combined for k in debit_keywords)

    seen_order_ids = set()
    seen_order_utrs = set()
    unified_orders = []

    for o in orders_list:
        if o.order_id in seen_order_ids:
            continue
        seen_order_ids.add(o.order_id)
        if o.utr:
            seen_order_utrs.add(o.utr)
        dt_ist = to_ist(o.created_at)
        raw_dt_str = o.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if o.created_at else ""
        date_str = dt_ist.strftime("%Y-%m-%d %H:%M:%S") if dt_ist else (o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else "-")
        unified_orders.append({
            "type": "ORDER",
            "direction": "RECEIVED",
            "id": o.order_id,
            "utr": o.utr or "-",
            "amount": float(o.amount or 0.0),
            "status": o.status,
            "sender_upi": o.upi_id,
            "date": date_str,
            "created_at": date_str,
            "raw_created_at": raw_dt_str,
            "created_at_dt": dt_ist,
            "details": f"UPI: {o.upi_id}"
        })

    seen_payment_utrs = set()
    unified_payments = []

    for p in payments_list:
        if not p.utr or p.utr.startswith("MSG-") or p.utr.startswith("MSG") or p.utr in seen_payment_utrs:
            continue
        seen_payment_utrs.add(p.utr)

        is_rec = is_received_credit_payment(p.sender, p.subject, p.purpose, p.utr)
        is_sent = is_sent_debit_payment(p.sender, p.subject, p.purpose, p.utr)
        if not is_rec and not is_sent:
            continue
        direction = "RECEIVED" if is_rec else "SENT"

        dt_ist = to_ist(p.date) or to_ist(p.created_at)
        raw_dt_str = p.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if p.created_at else (dt_ist.strftime("%Y-%m-%dT%H:%M:%SZ") if dt_ist else "")
        date_str = dt_ist.strftime("%Y-%m-%d %H:%M:%S") if dt_ist else (p.date or "-")

        unified_payments.append({
            "type": "PAYMENT",
            "direction": direction,
            "id": f"PAY-{p.id}",
            "utr": p.utr,
            "amount": float(p.amount or 0.0),
            "status": "SUCCESS" if is_rec else "SENT",
            "sender_upi": p.sender_name or p.sender or "Sync",
            "subject": p.subject or "",
            "date": date_str,
            "created_at": date_str,
            "raw_created_at": raw_dt_str,
            "created_at_dt": dt_ist,
            "details": f"[{direction}] Sender: {p.sender_name or p.sender or 'N/A'} | Purpose: {p.purpose or 'N/A'} | Subj: {p.subject or 'N/A'}"
        })

    return {
        "orders": unified_orders,
        "payments": unified_payments,
        "seen_order_utrs": seen_order_utrs,
        "is_received_credit_payment": is_received_credit_payment,
        "to_ist": to_ist,
        "ist_tz": ist_tz
    }

@app.get("/admin/stats")
def admin_stats(request: Request, db: Session = Depends(get_db)):
    verify_admin_token_header(request)

    data = get_unified_data(db)
    unified_orders = data["orders"]
    unified_payments = data["payments"]
    seen_order_utrs = data["seen_order_utrs"]
    ist_tz = data["ist_tz"]

    now_ist = datetime.datetime.now(ist_tz)
    today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start_ist = today_start_ist - datetime.timedelta(days=1)
    week_start_ist = today_start_ist - datetime.timedelta(days=now_ist.weekday())
    month_start_ist = today_start_ist.replace(day=1)

    today_orders = sum(1 for o in unified_orders if o["created_at_dt"] and o["created_at_dt"] >= today_start_ist)
    yesterday_orders = sum(1 for o in unified_orders if o["created_at_dt"] and yesterday_start_ist <= o["created_at_dt"] < today_start_ist)
    week_orders = sum(1 for o in unified_orders if o["created_at_dt"] and o["created_at_dt"] >= week_start_ist)
    month_orders = sum(1 for o in unified_orders if o["created_at_dt"] and o["created_at_dt"] >= month_start_ist)
    total_orders = len(unified_orders)

    success_orders_count = sum(1 for o in unified_orders if o["status"].upper() in ["SUCCESS", "APPROVED", "COMPLETED", "PAID"])
    pending_orders_count = sum(1 for o in unified_orders if o["status"].upper() == "PENDING")
    failed_orders_count = sum(1 for o in unified_orders if o["status"].upper() in ["FAILED", "EXPIRED"])

    today_rev = 0.0
    yesterday_rev = 0.0
    week_rev = 0.0
    month_rev = 0.0
    total_rev = 0.0
    orders_rev = 0.0
    payments_rev = 0.0

    monthly_map = {}

    for o in unified_orders:
        if o["status"].upper() in ["SUCCESS", "APPROVED", "COMPLETED", "PAID"]:
            amt = o["amount"]
            orders_rev += amt
            total_rev += amt
            ca = o["created_at_dt"]
            if ca:
                m_str = ca.strftime("%Y-%m")
                if m_str not in monthly_map:
                    monthly_map[m_str] = {"revenue": 0.0, "orders": 0, "payments": 0}
                monthly_map[m_str]["revenue"] += amt
                monthly_map[m_str]["orders"] += 1

                if ca >= today_start_ist:
                    today_rev += amt
                elif yesterday_start_ist <= ca < today_start_ist:
                    yesterday_rev += amt
                if ca >= week_start_ist:
                    week_rev += amt
                if ca >= month_start_ist:
                    month_rev += amt

    settled_payments_count = 0
    sent_payments_count = 0
    sent_payments_volume = 0.0

    for p in unified_payments:
        if p.get("direction") == "RECEIVED":
            if p["utr"] and p["utr"] in seen_order_utrs:
                continue
            amt = p["amount"]
            payments_rev += amt
            total_rev += amt
            settled_payments_count += 1
            ca = p["created_at_dt"]
            if ca:
                m_str = ca.strftime("%Y-%m")
                if m_str not in monthly_map:
                    monthly_map[m_str] = {"revenue": 0.0, "orders": 0, "payments": 0}
                monthly_map[m_str]["revenue"] += amt
                monthly_map[m_str]["payments"] += 1

                if ca >= today_start_ist:
                    today_rev += amt
                elif yesterday_start_ist <= ca < today_start_ist:
                    yesterday_rev += amt
                if ca >= week_start_ist:
                    week_rev += amt
                if ca >= month_start_ist:
                    month_rev += amt
        else:
            sent_payments_count += 1
            sent_payments_volume += p.get("amount", 0.0)

    daily_trend = []
    for d in range(13, -1, -1):
        day_start = today_start_ist - datetime.timedelta(days=d)
        day_end = day_start + datetime.timedelta(days=1)
        day_str = day_start.strftime("%Y-%m-%d")
        day_lbl = day_start.strftime("%d %b")

        d_orders = sum(1 for o in unified_orders if o["created_at_dt"] and day_start <= o["created_at_dt"] < day_end)
        d_success = sum(1 for o in unified_orders if o["created_at_dt"] and day_start <= o["created_at_dt"] < day_end and o["status"].upper() in ["SUCCESS", "APPROVED", "COMPLETED", "PAID"])
        d_expired = sum(1 for o in unified_orders if o["created_at_dt"] and day_start <= o["created_at_dt"] < day_end and o["status"].upper() in ["EXPIRED", "FAILED"])

        d_rev = 0.0
        for o in unified_orders:
            if o["status"].upper() in ["SUCCESS", "APPROVED", "COMPLETED", "PAID"] and o["created_at_dt"] and day_start <= o["created_at_dt"] < day_end:
                d_rev += o["amount"]
        for p in unified_payments:
            if p.get("direction") == "RECEIVED" and (not p["utr"] or p["utr"] not in seen_order_utrs) and p["created_at_dt"] and day_start <= p["created_at_dt"] < day_end:
                d_rev += p["amount"]

        daily_trend.append({
            "date": day_str,
            "label": day_lbl,
            "orders": d_orders,
            "revenue": round(d_rev, 2),
            "success": d_success,
            "failed": d_expired
        })

    monthly_list = [
        {
            "month": m,
            "label": datetime.datetime.strptime(m, "%Y-%m").strftime("%b %Y"),
            "revenue": round(data["revenue"], 2),
            "orders": data["orders"] + data["payments"],
            "orders_only": data["orders"],
            "payments_only": data["payments"],
            "count": data["orders"] + data["payments"]
        }
        for m, data in sorted(monthly_map.items(), reverse=True)
    ]

    total_tx_count = total_orders + settled_payments_count
    total_settled_count = success_orders_count + settled_payments_count
    success_rate = round((success_orders_count / total_orders * 100.0), 1) if total_orders > 0 else 100.0

    try:
        service = get_gmail_service()
        gmail_authenticated = service is not None
    except Exception:
        gmail_authenticated = False

    rev_rounded = round(total_rev, 2)
    return {
        "status": "success",
        "total_revenue": rev_rounded,
        "total_transactions": total_tx_count,
        "total_orders": total_orders,
        "settled_count": total_settled_count,
        "pending_orders_count": pending_orders_count,
        "expired_orders_count": failed_orders_count,
        "stats": {
            "total_revenue": rev_rounded,
            "orders_revenue": round(orders_rev, 2),
            "payments_revenue": round(payments_rev, 2),
            "today_revenue": round(today_rev, 2),
            "yesterday_revenue": round(yesterday_rev, 2),
            "this_week_revenue": round(week_rev, 2),
            "this_month_revenue": round(month_rev, 2),
            "current_month_revenue": round(month_rev, 2),
            "total_transactions": total_tx_count,
            "total_payments": len(unified_payments),
            "total_received_payments": settled_payments_count,
            "total_sent_payments_excluded": sent_payments_count,
            "sent_payments_volume_excluded": round(sent_payments_volume, 2),
            "total_orders": total_orders,
            "today_orders": today_orders,
            "yesterday_orders": yesterday_orders,
            "this_week_orders": week_orders,
            "this_month_orders": month_orders,
            "success_orders": success_orders_count,
            "settled_payments": settled_payments_count,
            "pending_orders": pending_orders_count,
            "failed_orders": failed_orders_count,
            "settled_count": total_settled_count,
            "success_rate": success_rate,
            "gmail_authenticated": gmail_authenticated,
            "daily_trend": daily_trend,
            "monthly_breakdown": monthly_list
        }
    }

@app.get("/admin/transactions")
def admin_transactions(
    request: Request,
    search: str = "",
    status: str = "ALL",
    type: str = "ALL",
    page: int = 1,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    verify_admin_token_header(request)

    data = get_unified_data(db)
    unified_orders = data["orders"]
    unified_payments = data["payments"]
    seen_order_utrs = data["seen_order_utrs"]

    req_type = (type or "ALL").strip().upper()

    items = []
    if req_type in ["ALL", "ORDER", "ORDERS", "RECEIVED"]:
        for o in unified_orders:
            items.append({
                "type": "ORDER",
                "direction": "RECEIVED",
                "id": o["id"],
                "utr": o["utr"],
                "amount": o["amount"],
                "status": o["status"],
                "sender_upi": o["sender_upi"],
                "date": o["date"],
                "created_at": o["created_at"],
                "raw_created_at": o["raw_created_at"],
                "details": o["details"]
            })

    if req_type in ["ALL", "PAYMENT", "PAYMENTS", "RECEIVED", "SENT"]:
        for p in unified_payments:
            if p["utr"] and p["utr"] in seen_order_utrs:
                continue
            p_dir = p.get("direction", "RECEIVED")
            if req_type == "RECEIVED" and p_dir != "RECEIVED":
                continue
            if req_type == "SENT" and p_dir != "SENT":
                continue
            items.append({
                "type": "PAYMENT",
                "direction": p_dir,
                "id": p["id"],
                "utr": p["utr"] or "-",
                "amount": p["amount"],
                "status": p.get("status", "SUCCESS"),
                "sender_upi": p["sender_upi"],
                "date": p["date"],
                "created_at": p["created_at"],
                "raw_created_at": p["raw_created_at"],
                "details": p["details"]
            })

    items.sort(key=lambda x: x.get("raw_created_at") or "", reverse=True)

    if search:
        s = search.strip().lower()
        items = [
            i for i in items
            if s in i["id"].lower()
            or s in i["utr"].lower()
            or s in str(i["amount"]).lower()
            or s in i["sender_upi"].lower()
            or s in i["details"].lower()
        ]

    if status and status.upper() != "ALL":
        items = [i for i in items if i["status"].upper() == status.upper()]

    total_count = len(items)
    start = (page - 1) * limit
    end = start + limit
    paginated_items = items[start:end]

    return {
        "status": "success",
        "total": total_count,
        "total_orders": len(unified_orders),
        "total_transactions": total_count,
        "page": page,
        "limit": limit,
        "transactions": paginated_items
    }

@app.post("/admin/scan")
def admin_manual_scan(request: Request, db: Session = Depends(get_db)):
    verify_admin_token_header(request)
    try:
        scanned = scan_unread_payments(db)
        return {"status": "success", "message": "Scanned unread payments successfully", "scanned": scanned}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")

@app.post("/admin/sync-all-gmail")
def admin_sync_all_gmail(request: Request, db: Session = Depends(get_db)):
    verify_admin_token_header(request)
    try:
        from gmail import scan_all_fampay_payments
        scanned = scan_all_fampay_payments(db, query="from:no-reply@famapp.in OR FamApp OR FamPay OR payment", max_results=500)
        return {
            "status": "success",
            "message": "Successfully synced payment logs from Gmail",
            "new_payments_imported": len(scanned),
            "payments": scanned
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail sync failed: {e}")

@app.get("/admin/database-status")
def admin_get_database_status(request: Request, db: Session = Depends(get_db)):
    verify_admin_token_header(request)
    from d1 import D1_DATABASE_ID, execute_d1_query, d1_is_enabled

    t0 = time.time()
    d1_status = "ONLINE"
    d1_error = None
    d1_records = 0

    try:
        res = db.execute(text("SELECT COUNT(*) FROM orders")).scalar()
        d1_records = int(res or 0)
        lat = round((time.time() - t0) * 1000, 1)
    except Exception as e:
        d1_status = "ERROR"
        d1_error = str(e)
        lat = round((time.time() - t0) * 1000, 1)

    cloud_sync = "Edge Sync Active" if d1_is_enabled() else "Local D1 Engine Active"

    database_info = {
        "id": "d1_database",
        "name": "Cloudflare D1 Database",
        "engine": "Cloudflare D1 (SQLite Edge)",
        "role": "PRIMARY DATABASE",
        "status": d1_status,
        "latency_ms": lat,
        "records": f"{d1_records} active orders ({cloud_sync})",
        "purpose": "Single database handling orders, payments, admin auth, rate limiting, and security logs.",
        "badge": "Primary D1",
        "error": d1_error
    }

    return {
        "status": "success",
        "database": database_info
    }

@app.get("/admin")
def get_admin_dashboard_info():
    return {
        "status": "success",
        "message": "Gateway Admin API. Use /admin/stats, /admin/transactions, etc. with authorization header."
    }

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "author": "enzosrs",
            "community": "https://t.me/devcommunityx"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unhealthy: {e}")

class AdminUnbanRequest(BaseModel):
    ip: str

class AdminBanRequest(BaseModel):
    ip: str
    reason: Optional[str] = "Manual administrator ban"
    hours: Optional[int] = 48

@app.get("/admin/logs")
def admin_get_logs(
    request: Request,
    page: int = 1,
    limit: int = 100,
    event: str = "ALL",
    status: str = "ALL",
    search: str = "",
    db: Session = Depends(get_db)
):
    verify_admin_token_header(request)

    query = db.query(AuditLog)

    if event and event.upper() != "ALL":
        query = query.filter(func.upper(AuditLog.event_type) == event.upper())

    if status and status.upper() != "ALL":
        query = query.filter(func.upper(AuditLog.status) == status.upper())

    if search and search.strip():
        s = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(AuditLog.ip).like(s),
                func.lower(AuditLog.details).like(s),
                func.lower(AuditLog.event_type).like(s)
            )
        )

    total = query.count()
    start = max(0, (page - 1) * limit)
    rows = query.order_by(AuditLog.id.desc()).offset(start).limit(limit).all()

    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "logs": [
            {
                "id": r.id,
                "ip": r.ip or "127.0.0.1",
                "event_type": r.event_type,
                "status": r.status,
                "details": r.details or "",
                "date": str(r.created_at) if r.created_at else "-",
                "created_at": str(r.created_at) if r.created_at else "-",
                "raw_created_at": str(r.created_at) if r.created_at else ""
            }
            for r in rows
        ]
    }

@app.get("/admin/banned-ips")
def admin_get_banned_ips(
    request: Request,
    db: Session = Depends(get_db)
):
    verify_admin_token_header(request)
    now_utc = datetime.datetime.utcnow()

    bans = db.query(IPBan).order_by(desc(IPBan.created_at)).all()
    out = []
    need_commit = False

    for b in bans:
        is_active = b.is_active
        if is_active and now_utc >= b.banned_until:
            is_active = False
            b.is_active = False
            need_commit = True

        remaining_hours = max(0.0, round((b.banned_until - now_utc).total_seconds() / 3600, 1))
        out.append({
            "id": b.id,
            "ip": b.ip,
            "reason": b.reason,
            "violations_count": b.violations_count,
            "banned_until": b.banned_until.strftime("%Y-%m-%d %H:%M:%S") if b.banned_until else "-",
            "remaining_hours": remaining_hours,
            "is_active": is_active,
            "date": b.created_at.strftime("%Y-%m-%d %H:%M:%S") if b.created_at else "-"
        })

    if need_commit:
        try:
            db.commit()
        except:
            db.rollback()

    return {
        "status": "success",
        "total": len(out),
        "banned_ips": out,
        "bans": out
    }

@app.post("/admin/unban-ip")
def admin_unban_ip(
    payload: AdminUnbanRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    verify_admin_token_header(request)
    from security import unban_ip_address
    success = unban_ip_address(db, payload.ip.strip())
    return {
        "status": "success" if success else "error",
        "message": f"IP {payload.ip} unbanned successfully" if success else "IP not found or already inactive"
    }

@app.post("/admin/ban-ip")
def admin_manual_ban_ip(
    payload: AdminBanRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    verify_admin_token_header(request)
    from security import ban_ip_address
    ban_ip_address(db, payload.ip.strip(), reason=payload.reason or "Manual ban", hours=payload.hours or 48)
    return {
        "status": "success",
        "message": f"IP {payload.ip} banned for {payload.hours or 48} hours"
    }

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("app:app", host=host, port=port, reload=True)
