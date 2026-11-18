__author__ = "enzosrs"
__github__ = "https://github.com/enzosrs"
__community__ = "https://t.me/devcommunityx"

import os
import asyncio
import datetime
import httpx
import time
from typing import Optional, Dict, Any

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

async def _send_api_request(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{TELEGRAM_API_BASE}/{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.json()
    except Exception as e:
        print(f"Telegram API Request Error ({endpoint}): {e}")
        return {"ok": False, "description": str(e)}

def _send_sync_api_request(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{TELEGRAM_API_BASE}/{endpoint}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            return resp.json()
    except Exception as e:
        print(f"Telegram Sync API Request Error ({endpoint}): {e}")
        return {"ok": False, "description": str(e)}

def send_telegram_order_created(order_id: str, amount: float, upi_id: str, payment_url: str = None, target_chat_id: str = None) -> Optional[int]:
    chat_id = target_chat_id or TELEGRAM_ADMIN_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return None

    if not payment_url:
        app_url = os.environ.get("APP_URL", "http://localhost:8001").rstrip("/")
        payment_url = f"{app_url}/checkout/{order_id}"

    text = (
        f'<tg-emoji emoji-id="6053362469311617342">👀</tg-emoji> <b>NEW ORDER CREATED</b> <tg-emoji emoji-id="6339306810465327721">🆕</tg-emoji>\n'
        f'────────────────────────\n'
        f'<tg-emoji emoji-id="6136663351427603393">📌</tg-emoji> <b>Order ID:</b> <code>{order_id}</code>\n'
        f'<tg-emoji emoji-id="4958926882994127612">💰</tg-emoji> <b>Amount:</b> ₹{amount:.2f} \n'
        f'<tg-emoji emoji-id="5276137490846075469">👛</tg-emoji> <b>UPI ID:</b> <code>{upi_id}</code> \n'
        f'<tg-emoji emoji-id="6339037614800117523">🔜</tg-emoji> <b>Status:</b> <i>Pending</i> <tg-emoji emoji-id="6053354746960419401">⁉️</tg-emoji>\n'
    )
    if payment_url:
        text += f'<tg-emoji emoji-id="6052886672834566125">🔗</tg-emoji> <b>Payment Link:</b> <a href="{payment_url}"><b>Click to Pay</b></a>\n'
    text += f'────────────────────────\n'
    text += f'<tg-emoji emoji-id="6224079155810537724">⏰</tg-emoji> <b>Time:</b> {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} <tg-emoji emoji-id="5316994904847560645">🔥</tg-emoji>'

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "💳 Pay Now (Autopay)", "url": payment_url}
                ]
            ]
        }
    }
    
    res = _send_sync_api_request("sendMessage", payload)
    if res.get("ok") and "result" in res:
        return res["result"].get("message_id")
    return None

def send_telegram_order_status_reply(
    telegram_message_id: Optional[int],
    order_id: str,
    status: str,
    utr: str = None,
    amount: float = None,
    sender_name: str = None,
    target_chat_id: str = None
):
    chat_id = target_chat_id or TELEGRAM_ADMIN_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return

    status_upper = status.upper()
    if status_upper == "SUCCESS":
        text = (
            f'<tg-emoji emoji-id="5318832678403846713">🔥</tg-emoji> <b>PAYMENT VERIFIED SUCCESS</b> <tg-emoji emoji-id="5318832678403846713">🔥</tg-emoji>\n'
            f'────────────────────────\n'
            f'<tg-emoji emoji-id="6136663351427603393">📌</tg-emoji> <b>Order ID:</b> <code>{order_id}</code>\n'
            f'<tg-emoji emoji-id="5445353829304387411">💳</tg-emoji> <b>UTR Number:</b> <code>{utr or "N/A"}</code>\n'
        )
        if amount:
            text += f'<tg-emoji emoji-id="6053104294532487625">💵</tg-emoji> <b>Amount Verified:</b> ₹{amount:.2f}\n'
        if sender_name:
            text += f'<tg-emoji emoji-id="6267071898702583835">🎄</tg-emoji> <b>Sender Name:</b> <code>{sender_name}</code>\n'
        text += f'<tg-emoji emoji-id="6264695922794435129">👁</tg-emoji> <b>Status:</b> <b><i>Successful</i></b> <tg-emoji emoji-id="6266827283135207188">✅</tg-emoji> \n'
        text += f'────────────────────────\n'
        text += f'<tg-emoji emoji-id="6109510576772222821">🎉</tg-emoji> <i>Order verified automatically from Mail Data </i><i><tg-emoji emoji-id="6053178490092525561">‼️</tg-emoji></i>'

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if telegram_message_id:
            payload["reply_to_message_id"] = telegram_message_id
        _send_sync_api_request("sendMessage", payload)

    elif status_upper == "EXPIRED":
        text = (
            f'<tg-emoji emoji-id="6053315100117309042">⌛</tg-emoji> <b>ORDER EXPIRED</b> <tg-emoji emoji-id="6053315100117309042">⌛</tg-emoji>\n'
            f'────────────────────────\n'
            f'<tg-emoji emoji-id="6136663351427603393">📌</tg-emoji> <b>Order ID:</b> <code>{order_id}</code>\n'
        )
        if amount:
            text += f'<tg-emoji emoji-id="4958926882994127612">💰</tg-emoji> <b>Amount:</b> ₹{amount:.2f}\n'
        text += f'<tg-emoji emoji-id="6224079155810537724">⏰</tg-emoji> <b>Status:</b> <i>Expired — No payment received in 10 minutes</i>\n'
        text += f'────────────────────────\n'
        text += '⚠️ <i>Order window timed out. Link is now closed.</i>'

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if telegram_message_id:
            payload["reply_to_message_id"] = telegram_message_id
        _send_sync_api_request("sendMessage", payload)

        if telegram_message_id:
            try:
                _send_sync_api_request("editMessageReplyMarkup", {
                    "chat_id": chat_id,
                    "message_id": telegram_message_id,
                    "reply_markup": {"inline_keyboard": []}
                })
            except Exception:
                pass

    elif status_upper == "FAILED":
        text = (
            f"❌ <b>ORDER FAILED</b>\n"
            f"────────────────────────\n"
            f"📌 <b>Order ID:</b> <code>{order_id}</code>\n"
        )
        if amount:
            text += f"💰 <b>Amount:</b> ₹{amount:.2f}\n"
        text += "⏱️ <b>Status:</b> FAILED\n"
        text += "────────────────────────\n"
        text += "⚠️ Payment was not received."

        if telegram_message_id:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_to_message_id": telegram_message_id
            }
            _send_sync_api_request("sendMessage", payload)

    else:
        text = (
            f"ℹ️ <b>ORDER UPDATE: {status_upper}</b>\n"
            f"Order ID: <code>{order_id}</code>"
        )
        if telegram_message_id:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_to_message_id": telegram_message_id
            }
            _send_sync_api_request("sendMessage", payload)

def send_admin_log(title: str, details: str, level: str = "INFO"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        return

    icon = '<tg-emoji emoji-id="4958529074533238201">ℹ️</tg-emoji>'
    if level.upper() == "SUCCESS":
        icon = '<tg-emoji emoji-id="4958920483492857102">🟢</tg-emoji>'
    elif level.upper() == "WARNING":
        icon = '<tg-emoji emoji-id="4956611513369494230">⚠️</tg-emoji>'
    elif level.upper() == "ERROR":
        icon = '<tg-emoji emoji-id="4956368164817470478">❗</tg-emoji>'

    text = (
        f"{icon} <b>LOG MONITOR [{level.upper()}]</b>\n"
        f'<tg-emoji emoji-id="6136663351427603393">📌</tg-emoji> <b>Event:</b> <code>{title}</code>\n'
        f'<tg-emoji emoji-id="4958621433509970793">🔖</tg-emoji> <b>Details:</b> {details}\n'
        f'<tg-emoji emoji-id="6224079155810537724">⏰</tg-emoji> <b>Time:</b> {datetime.datetime.now().strftime("%H:%M:%S")}'
    )

    payload = {
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    _send_sync_api_request("sendMessage", payload)

def get_advanced_stats_markdown(db_session) -> str:
    from db import Payment, Order
    import email.utils
    import datetime

    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = datetime.datetime.now(ist_tz)
    
    today_str = now_ist.strftime("%Y-%m-%d")
    current_month_str = now_ist.strftime("%Y-%m")
    
    if now_ist.month == 1:
        last_month_year = now_ist.year - 1
        last_month_num = 12
    else:
        last_month_year = now_ist.year
        last_month_num = now_ist.month - 1
    last_month_str = f"{last_month_year:04d}-{last_month_num:02d}"

    payments = db_session.query(Payment).all()
    payments.sort(key=lambda x: x.created_at or datetime.datetime.min, reverse=True)

    total_revenue = 0.0
    this_month_revenue = 0.0
    last_month_revenue = 0.0
    today_revenue = 0.0
    total_payments_count = 0
    today_payments_count = 0
    
    last_3_payments = []

    def is_actual_credit_payment(subject: str) -> bool:
        if not subject:
            return False
        subj_lower = subject.lower()
        if any(k in subj_lower for k in ["payment of", "successful payment", "paid to", "sent to", "debited", "you paid", "spent"]):
            return False
        if any(k in subj_lower for k in ["received", "credited", "added", "received ₹", "received rs", "credit"]):
            return True
        return False

    for p in payments:
        if not is_actual_credit_payment(p.subject):
            continue
        
        amt = p.amount or 0.0
        total_revenue += amt
        total_payments_count += 1
        
        if len(last_3_payments) < 3:
            last_3_payments.append(p)

        p_date_ist = None
        if p.date:
            try:
                dt = email.utils.parsedate_to_datetime(p.date)
                p_date_ist = dt.astimezone(ist_tz)
            except Exception:
                pass
        
        if p_date_ist is None and p.created_at:
            p_date_ist = p.created_at.replace(tzinfo=datetime.timezone.utc).astimezone(ist_tz)
            
        if p_date_ist:
            p_day_str = p_date_ist.strftime("%Y-%m-%d")
            p_month_str = p_date_ist.strftime("%Y-%m")
            
            if p_day_str == today_str:
                today_revenue += amt
                today_payments_count += 1
            if p_month_str == current_month_str:
                this_month_revenue += amt
            elif p_month_str == last_month_str:
                last_month_revenue += amt

    today_start_ist = datetime.datetime(now_ist.year, now_ist.month, now_ist.day) - datetime.timedelta(hours=5, minutes=30)
    today_orders_count = db_session.query(Order).filter(Order.created_at >= today_start_ist).count()
    today_success_orders_count = db_session.query(Order).filter(Order.created_at >= today_start_ist, Order.status == "SUCCESS").count()
    today_pending_orders_count = db_session.query(Order).filter(Order.created_at >= today_start_ist, Order.status == "PENDING").count()
    today_failed_orders_count = db_session.query(Order).filter(Order.created_at >= today_start_ist, Order.status.in_(["FAILED", "EXPIRED"])).count()

    today_success_rate = 100.0
    if today_orders_count > 0:
        today_success_rate = round((today_success_orders_count / today_orders_count) * 100.0, 1)

    total_orders_count = db_session.query(Order).count()
    success_orders_count = db_session.query(Order).filter(Order.status == "SUCCESS").count()
    pending_orders_count = db_session.query(Order).filter(Order.status == "PENDING").count()
    failed_orders_count = db_session.query(Order).filter(Order.status.in_(["FAILED", "EXPIRED"])).count()

    success_rate = 100.0
    if total_orders_count > 0:
        success_rate = round((success_orders_count / total_orders_count) * 100.0, 1)

    try:
        from gmail import get_gmail_service
        service = get_gmail_service()
        gmail_auth = "<tg-emoji emoji-id=\"6053400449707416241\">🟢</tg-emoji> Connected &amp; Active" if service else "🔴 Not Authenticated"
    except Exception:
        gmail_auth = "🔴 Needs OAuth Login"

    last_3_items = []
    for p in last_3_payments:
        last_3_items.append(f'  <tg-emoji emoji-id="5197434882321567830">➡️</tg-emoji> <b>₹{p.amount or 0.0:,.2f}</b>')
    last_3_payments_str = "\n".join(last_3_items) + "\n" if last_3_items else "  <i>No payments yet</i>\n"

    stats_text = (
        f'<tg-emoji emoji-id="6053061091456457277">⚡️</tg-emoji> <b>UPI Gateway Stats</b> <tg-emoji emoji-id="6053061091456457277">⚡️</tg-emoji>\n'
        f'=============================\n'
        f'<tg-emoji emoji-id="6053104294532487625">💵</tg-emoji> <b>Today\'s Revenue:</b> ₹{today_revenue:,.2f}\n'
        f'<tg-emoji emoji-id="5429651785352501917">🗓</tg-emoji> <b>This Month Revenue:</b> ₹{this_month_revenue:,.2f}\n'
        f'<tg-emoji emoji-id="5429651785352501917">🗓</tg-emoji> <b>Last Month Revenue:</b> ₹{last_month_revenue:,.2f}\n'
        f'<tg-emoji emoji-id="4958926882994127612">💰</tg-emoji> <b>Total Revenue:</b> ₹{total_revenue:,.2f}\n'
        f'─────────────────────────────\n'
        f'<b>Last 3 Received Payments:</b>\n'
        f'{last_3_payments_str}'
        f'─────────────────────────────\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>Today\'s Orders Created:</b> <code>{today_orders_count}</code>\n'
        f'<tg-emoji emoji-id="4958610528588008305">✅</tg-emoji> <b>Today\'s Successful Orders:</b> <code>{today_success_orders_count}</code>\n'
        f'<tg-emoji emoji-id="5319190934510904031">⏳</tg-emoji> <b>Today\'s Pending Orders:</b> <code>{today_pending_orders_count}</code>\n'
        f'<tg-emoji emoji-id="4956612582816351459">❌</tg-emoji> <b>Today\'s Failed/Expired:</b> <code>{today_failed_orders_count}</code>\n'
        f'<tg-emoji emoji-id="5310278924616356636">🎯</tg-emoji> <b>Today\'s Success Rate:</b> <code>{today_success_rate}%</code>\n'
        f'─────────────────────────────\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>All-Time Orders Created:</b> <code>{total_orders_count}</code>\n'
        f'<tg-emoji emoji-id="4958610528588008305">✅</tg-emoji> <b>All-Time Successful:</b> <code>{success_orders_count}</code>\n'
        f'<tg-emoji emoji-id="5319190934510904031">⏳</tg-emoji> <b>All-Time Pending:</b> <code>{pending_orders_count}</code>\n'
        f'<tg-emoji emoji-id="4956612582816351459">❌</tg-emoji> <b>All-Time Failed/Expired:</b> <code>{failed_orders_count}</code>\n'
        f'<tg-emoji emoji-id="5310278924616356636">🎯</tg-emoji> <b>All-Time Success Rate:</b> <code>{success_rate}%</code>\n'
        f'─────────────────────────────\n'
        f'<tg-emoji emoji-id="5443127283898405358">📥</tg-emoji> <b>Received Logs:</b> <code>{total_payments_count}</code> (Today: <code>{today_payments_count}</code>)\n'
        f' <tg-emoji emoji-id="5321244246705989720">🔍</tg-emoji><b>Gmail Auth:</b> {gmail_auth}\n'
        f' <tg-emoji emoji-id="4985708576770097801">🖥</tg-emoji> <b>Database Status:</b> <tg-emoji emoji-id="5039928501612839813">🟢</tg-emoji> Connected\n'
        f'=============================\n'
        f'<tg-emoji emoji-id="5382194935057372936">⏰</tg-emoji> <b>Updated (IST):</b> {now_ist.strftime("%Y-%m-%d %H:%M:%S")}<tg-emoji emoji-id="5208540237524911208">✅</tg-emoji>'
    )
    return stats_text

def start_telegram_bot_loop():
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram Bot Token missing. Skipping bot listener.")
        return

    offset = 0
    from db import get_db, Payment, Order

    while True:
        try:
            url = f"{TELEGRAM_API_BASE}/getUpdates?offset={offset}&timeout=10"
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url)
                data = resp.json()

            if data.get("ok") and "result" in data:
                for update in data["result"]:
                    offset = update["update_id"] + 1
                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    chat_id = str(chat.get("id"))
                    text_content = message.get("text", "").strip()
                    message_id = message.get("message_id")

                    if TELEGRAM_ADMIN_CHAT_ID and chat_id != str(TELEGRAM_ADMIN_CHAT_ID):
                        continue

                    if not text_content:
                        continue

                    cmd = text_content.split()[0].lower()
                    db = next(get_db())
                    try:
                        if cmd in ["/stats", "/stat"]:
                            stats_md = get_advanced_stats_markdown(db)
                            _send_sync_api_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": stats_md,
                                "parse_mode": "HTML",
                                "reply_to_message_id": message_id
                            })

                        elif cmd in ["/start", "/help"]:
                            help_md = (
                                f'<tg-emoji emoji-id="4956770654792713082">🥸</tg-emoji> <b>PAYMENT GATEWAY ADMIN BOT</b>\n'
                                f'─────────────────────────\n'
                                f'Available Admin Commands:\n'
                                f'<tg-emoji emoji-id="4958920483492857102">🟢</tg-emoji> <code>/stats</code> - View real-time revenue & order metrics\n'
                                f'<tg-emoji emoji-id="4958920483492857102">🟢</tg-emoji> <code>/create &lt;amount&gt;</code> - Create a new Autopay order\n'
                                f'<tg-emoji emoji-id="4958920483492857102">🟢</tg-emoji> <code>/verify &lt;utr&gt;</code> - Manually verify a transaction UTR\n'
                                f'<tg-emoji emoji-id="4958920483492857102">🟢</tg-emoji> <code>/approve &lt;order_id&gt; [utr]</code> - Force approve any order ID\n'
                                f'<tg-emoji emoji-id="4958920483492857102">🟢</tg-emoji> <code>/logs</code> - Show recent received payment logs\n'
                                f'<tg-emoji emoji-id="4958920483492857102">🟢</tg-emoji> <code>/help</code> - Show this menu\n'
                                f'─────────────────────────\n'
                                f'👨‍💻 <b>Developer:</b> @enzosrs | <b>Community:</b> @devcommunityx'
                            )
                            _send_sync_api_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": help_md,
                                "parse_mode": "HTML",
                                "reply_to_message_id": message_id
                            })

                        elif cmd in ["/create", "/pay"]:
                            parts = text_content.split()
                            if len(parts) < 2:
                                _send_sync_api_request("sendMessage", {
                                    "chat_id": chat_id,
                                    "text": '<tg-emoji emoji-id="4956611513369494230">⚠️</tg-emoji> Usage: <code>/create &lt;amount&gt;</code> (e.g. <code>/create 100</code>)',
                                    "parse_mode": "HTML",
                                    "reply_to_message_id": message_id
                                })
                            else:
                                try:
                                    amt = float(parts[1])
                                    import random, urllib.parse
                                    upi_id = os.environ.get("UPI_ID", "")
                                    order_id = f"ORD{int(time.time())}{random.randint(1000, 9999)}"
                                    db_order = Order(order_id=order_id, amount=amt, upi_id=upi_id, status="PENDING", telegram_chat_id=chat_id, telegram_message_id=message_id)
                                    db.add(db_order)
                                    db.commit()

                                    app_url = os.environ.get("APP_URL", "http://localhost:8001").rstrip("/")
                                    payment_url = f"{app_url}/autopay?order_id={order_id}"

                                    upi_url = f"upi://pay?pa={upi_id}&pn=Payment&am={amt:.2f}&cu=INR"
                                    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&margin=20&data={urllib.parse.quote_plus(upi_url)}"

                                    card_text = (
                                        f'<tg-emoji emoji-id="6136663351427603393">📌</tg-emoji> <b>AUTOPAY ORDER CREATED</b>\n'
                                        f'─────────────────────────\n'
                                        f'<tg-emoji emoji-id="6136663351427603393">📌</tg-emoji> <b>Order ID:</b> <code>{order_id}</code>\n'
                                        f'<tg-emoji emoji-id="4958926882994127612">💰</tg-emoji> <b>Amount:</b> ₹{amt:.2f}\n'
                                        f'<tg-emoji emoji-id="5276137490846075469">👛</tg-emoji> <b>UPI ID:</b> <code>{upi_id}</code>\n'
                                        f'<tg-emoji emoji-id="6052886672834566125">🔗</tg-emoji> <b>Payment Link:</b> <a href="{payment_url}"><b>Click to Pay</b></a>\n'
                                        f'<tg-emoji emoji-id="6339037614800117523">🔜</tg-emoji> <b>Status:</b> PENDING\n'
                                        f'─────────────────────────\n'
                                        f'Scan QR code below or click the button to pay.'
                                    )

                                    reply_markup = {
                                        "inline_keyboard": [
                                            [
                                                {"text": "💳 Pay Now (Autopay)", "url": payment_url}
                                            ]
                                        ]
                                    }

                                    sent_msg = _send_sync_api_request("sendPhoto", {
                                        "chat_id": chat_id,
                                        "photo": qr_url,
                                        "caption": card_text,
                                        "parse_mode": "HTML",
                                        "reply_to_message_id": message_id,
                                        "reply_markup": reply_markup
                                    })
                                    if sent_msg.get("ok") and "result" in sent_msg:
                                        db_order.telegram_message_id = sent_msg["result"].get("message_id")
                                        db.commit()
                                except ValueError:
                                    _send_sync_api_request("sendMessage", {
                                        "chat_id": chat_id,
                                        "text": '<tg-emoji emoji-id="4956612582816351459">❌</tg-emoji> Invalid amount. Please specify a numeric amount.',
                                        "parse_mode": "HTML",
                                        "reply_to_message_id": message_id
                                    })

                        elif cmd == "/logs":
                            payments = db.query(Payment).order_by(Payment.created_at.desc()).limit(5).all()
                            if not payments:
                                msg = "No payments recorded yet."
                            else:
                                logs_list = []
                                for p in payments:
                                    logs_list.append(f'• UTR: <code>{p.utr or "N/A"}</code> | ₹{p.amount or 0.0} | <code>{p.sender_name or "Sync"}</code>')
                                msg = '<tg-emoji emoji-id="5443127283898405358">📥</tg-emoji> <b>RECENT RECEIVED PAYMENTS</b>\n─────────────────────────\n' + "\n".join(logs_list)
                            _send_sync_api_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": msg,
                                "parse_mode": "HTML",
                                "reply_to_message_id": message_id
                            })

                        elif cmd == "/verify":
                            parts = text_content.split()
                            if len(parts) < 2:
                                _send_sync_api_request("sendMessage", {
                                    "chat_id": chat_id,
                                    "text": '<tg-emoji emoji-id="4956611513369494230">⚠️</tg-emoji> Usage: <code>/verify &lt;utr&gt;</code>',
                                    "parse_mode": "HTML",
                                    "reply_to_message_id": message_id
                                })
                            else:
                                from sqlalchemy import or_, func
                                utr_check = parts[1].strip().replace(" ", "").replace("-", "")
                                payment = db.query(Payment).filter(
                                    or_(
                                        func.lower(Payment.utr) == utr_check.lower(),
                                        func.lower(Payment.purpose) == utr_check.lower()
                                    )
                                ).first()

                                if not payment:
                                    try:
                                        from gmail import get_gmail_service, get_message_details, decode_body, parse_payment_details, parse_email_metadata, is_received_payment, clean_email_text
                                        from db import save_payment
                                        service = get_gmail_service()
                                        if service:
                                            q = f'"{utr_check}"'
                                            results = service.users().messages().list(userId="me", q=q, maxResults=3).execute()
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
                                                if (cf.lower() == utr_check.lower() or ctx.lower() == utr_check.lower() or utr_check.lower() in clean_b.lower()):
                                                    amt_val = meta.get("amount") if meta.get("amount") is not None else parsed_amt
                                                    save_payment(
                                                        db=db,
                                                        message_id=msg_id,
                                                        utr=found_utr or utr_check,
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
                                                            func.lower(Payment.utr) == (found_utr or utr_check).lower(),
                                                            func.lower(Payment.purpose) == utr_check.lower()
                                                        )
                                                    ).first()
                                                    break
                                    except Exception as e:
                                        print(f"[TelegramVerify] Gmail search error: {e}")

                                if payment:
                                    linked_order = db.query(Order).filter(func.lower(Order.utr) == utr_check.lower()).first()
                                    order_info = f'\n• Linked Order: <code>{linked_order.order_id}</code> ({linked_order.status})' if linked_order else ''
                                    res_text = (
                                        f'<tg-emoji emoji-id="4958610528588008305">✅</tg-emoji> <b>UTR VERIFIED</b>\n'
                                        f'• UTR: <code>{payment.utr}</code>\n'
                                        f'• Amount: ₹{payment.amount or 0.0:.2f}\n'
                                        f'• Sender: <code>{payment.sender_name or payment.sender}</code>\n'
                                        f'• Date: <code>{payment.date or "-"}</code>'
                                        f'{order_info}'
                                    )
                                else:
                                    res_text = f'<tg-emoji emoji-id="4956612582816351459">❌</tg-emoji> UTR <code>{utr_check}</code> not found in received payments or Gmail.'
                                _send_sync_api_request("sendMessage", {
                                    "chat_id": chat_id,
                                    "text": res_text,
                                    "parse_mode": "HTML",
                                    "reply_to_message_id": message_id
                                })

                        elif cmd == "/approve":
                            parts = text_content.split()
                            if len(parts) < 2:
                                _send_sync_api_request("sendMessage", {
                                    "chat_id": chat_id,
                                    "text": '<tg-emoji emoji-id="4956611513369494230">⚠️</tg-emoji> Usage: <code>/approve &lt;order_id&gt; [utr]</code>',
                                    "parse_mode": "HTML",
                                    "reply_to_message_id": message_id
                                })
                            else:
                                target_order_id = parts[1].strip()
                                manual_utr = parts[2].strip() if len(parts) > 2 else "MANUAL"

                                order = db.query(Order).filter(Order.order_id == target_order_id).first()
                                if order:
                                    if order.status == "SUCCESS":
                                        _send_sync_api_request("sendMessage", {
                                            "chat_id": chat_id,
                                            "text": f'✅ Order <code>{target_order_id}</code> is already SUCCESS.',
                                            "parse_mode": "HTML",
                                            "reply_to_message_id": message_id
                                        })
                                    else:
                                        order.status = "SUCCESS"
                                        order.utr = manual_utr
                                        db.commit()

                                        send_telegram_order_status_reply(
                                            telegram_message_id=order.telegram_message_id,
                                            order_id=order.order_id,
                                            status="SUCCESS",
                                            utr=manual_utr,
                                            amount=order.amount,
                                            sender_name="Admin Manual",
                                            target_chat_id=order.telegram_chat_id
                                        )

                                        _send_sync_api_request("sendMessage", {
                                            "chat_id": chat_id,
                                            "text": f'🎉 Order <code>{target_order_id}</code> (₹{order.amount:.2f}) approved successfully!',
                                            "parse_mode": "HTML",
                                            "reply_to_message_id": message_id
                                        })
                                else:
                                    _send_sync_api_request("sendMessage", {
                                        "chat_id": chat_id,
                                        "text": f'❌ Order <code>{target_order_id}</code> not found in database.',
                                        "parse_mode": "HTML",
                                        "reply_to_message_id": message_id
                                    })
                    finally:
                        db.close()

        except Exception as err:
            print(f"Telegram Bot Poller Loop Error: {err}")
            time.sleep(3.0)

        time.sleep(1.0)
