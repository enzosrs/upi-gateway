__author__ = "enzosrs"
__github__ = "https://github.com/enzosrs"
__community__ = "https://t.me/devcommunityx"

import re
import time
import datetime
import threading
from typing import Optional, Tuple, List, Dict, Any
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from db import SessionLocal, IPBan, AuditLog

_lock = threading.Lock()
_IP_ORDER_REQUESTS: Dict[str, List[float]] = {}
_IP_RATE_VIOLATIONS: Dict[str, List[float]] = {}
_RECENT_BANS_CACHE: Dict[str, float] = {}

def get_client_ip(request: Request, payload: Optional[Any] = None) -> str:
    SERVER_IPS = {"127.0.0.1", "::1", "localhost"}

    if payload:
        p_ip = getattr(payload, "client_ip", None) or (payload.get("client_ip") if isinstance(payload, dict) else None)
        if p_ip and isinstance(p_ip, str) and p_ip.strip() and p_ip.strip() not in SERVER_IPS:
            return p_ip.strip()

    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip and cf_ip.strip() and cf_ip.strip() not in SERVER_IPS:
        return cf_ip.strip()

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",")]
        valid_parts = [p for p in parts if p and p not in SERVER_IPS]
        if valid_parts:
            return valid_parts[0]
        elif parts and parts[0]:
            return parts[0]

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip() and real_ip.strip() not in SERVER_IPS:
        return real_ip.strip()

    query_ip = request.query_params.get("client_ip")
    if query_ip and query_ip.strip() and query_ip.strip() not in SERVER_IPS:
        return query_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"

def sanitize_string(val: Optional[str], max_len: int = 100) -> str:
    if not val:
        return ""
    cleaned = re.sub(r"<[^>]*>", "", str(val))
    cleaned = cleaned.replace("'", "").replace('"', "").replace(";", "")
    return cleaned.strip()[:max_len]

def sanitize_order_id(order_id: Optional[str]) -> str:
    if not order_id:
        return ""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(order_id).strip())[:50]

def sanitize_utr(utr: Optional[str]) -> str:
    if not utr:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(utr).strip())[:35]

def log_audit_event(
    db: Optional[Session] = None,
    event_type: str = "INFO",
    status: str = "INFO",
    details: str = "",
    ip: Optional[str] = None
):
    clean_ip = ip or "127.0.0.1"
    clean_details = sanitize_string(details, 300)

    session = db or SessionLocal()
    try:
        entry = AuditLog(
            ip=clean_ip,
            event_type=event_type,
            status=status,
            details=clean_details
        )
        session.add(entry)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[AuditLog Error] {e}")
    finally:
        if db is None:
            session.close()

    try:
        from d1 import d1_is_enabled, d1_write
        if d1_is_enabled():
            sql = "INSERT INTO audit_logs (ip, event_type, status, details, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
            d1_write(sql, [clean_ip, event_type, status, clean_details])
    except Exception:
        pass

def check_ip_ban(db: Session, ip: str) -> Tuple[bool, Optional[str]]:
    if ip in ["127.0.0.1", "::1", "localhost"]:
        return True, None

    now_utc = datetime.datetime.utcnow()

    with _lock:
        banned_until_cached = _RECENT_BANS_CACHE.get(ip)
        if banned_until_cached and time.time() < banned_until_cached:
            hours_left = max(0.1, round((banned_until_cached - time.time()) / 3600, 1))
            return False, f"Your IP ({ip}) has been blocked for order spam. Ban will automatically lift in {hours_left} hours."

    ban = db.query(IPBan).filter(IPBan.ip == ip, IPBan.is_active == True).first()
    if not ban:
        return True, None

    if now_utc >= ban.banned_until:
        ban.is_active = False
        try:
            db.commit()
        except:
            db.rollback()

        with _lock:
            _RECENT_BANS_CACHE.pop(ip, None)

        log_audit_event(db, "AUTO_UNBAN", "SUCCESS", "Ban expired after 48h. IP automatically unbanned.", ip)
        return True, None

    remaining_sec = (ban.banned_until - now_utc).total_seconds()
    hours_left = max(0.1, round(remaining_sec / 3600, 1))

    with _lock:
        _RECENT_BANS_CACHE[ip] = time.time() + remaining_sec

    msg = f"Your IP ({ip}) has been blocked for repeated order spam. Access restricted until {ban.banned_until.strftime('%Y-%m-%d %H:%M UTC')} ({hours_left}h left). Ban will automatically lift."
    return False, msg

def ban_ip_address(
    db: Session,
    ip: str,
    reason: str = "Persistent order spam",
    hours: int = 48
):
    now_utc = datetime.datetime.utcnow()
    if ip in ["127.0.0.1", "::1", "localhost"]:
        return
    banned_until = now_utc + datetime.timedelta(hours=hours)

    ban = db.query(IPBan).filter(IPBan.ip == ip).first()
    if ban:
        ban.is_active = True
        ban.reason = reason
        ban.violations_count += 1
        ban.banned_until = banned_until
        ban.created_at = now_utc
    else:
        ban = IPBan(
            ip=ip,
            reason=reason,
            violations_count=1,
            banned_until=banned_until,
            is_active=True,
            created_at=now_utc
        )
        db.add(ban)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[BanIP DB Error] {e}")

    with _lock:
        _RECENT_BANS_CACHE[ip] = time.time() + hours * 3600

    log_audit_event(db, "IP_BAN", "BLOCKED", f"IP banned for {hours}h. Reason: {reason}", ip)

    try:
        from d1 import d1_is_enabled, d1_write
        if d1_is_enabled():
            sql = "INSERT OR REPLACE INTO ip_bans (ip, reason, violations_count, banned_until, is_active, created_at) VALUES (?, ?, ?, ?, 1, datetime('now'))"
            d1_write(sql, [ip, reason, ban.violations_count if ban else 1, banned_until.strftime("%Y-%m-%d %H:%M:%S")])
    except Exception:
        pass

def unban_ip_address(db: Session, ip: str) -> bool:
    ban = db.query(IPBan).filter(IPBan.ip == ip).first()
    if ban:
        ban.is_active = False
        try:
            db.commit()
        except:
            db.rollback()
            return False

    with _lock:
        _RECENT_BANS_CACHE.pop(ip, None)
        _IP_ORDER_REQUESTS.pop(ip, None)
        _IP_RATE_VIOLATIONS.pop(ip, None)

    log_audit_event(db, "IP_UNBAN", "INFO", "IP unbanned by administrator", ip)

    try:
        from d1 import d1_is_enabled, d1_write
        if d1_is_enabled():
            sql = "UPDATE ip_bans SET is_active = 0 WHERE ip = ?"
            d1_write(sql, [ip])
    except Exception:
        pass

    return True

def enforce_order_rate_limit(request: Request, db: Session, client_ip: Optional[str] = None):
    ip = client_ip or get_client_ip(request)
    now = time.time()

    if ip in {"127.0.0.1", "::1", "localhost"}:
        return

    allowed, ban_reason = check_ip_ban(db, ip)
    if not allowed:
        log_audit_event(db, "ORDER_BLOCKED", "BLOCKED", f"Blocked request from banned IP: {ban_reason}", ip)
        raise HTTPException(status_code=403, detail=ban_reason)

    with _lock:
        req_list = [t for t in _IP_ORDER_REQUESTS.get(ip, []) if now - t < 60.0]
        req_list.append(now)
        _IP_ORDER_REQUESTS[ip] = req_list

        if len(req_list) > 6:
            violation_list = [t for t in _IP_RATE_VIOLATIONS.get(ip, []) if now - t < 300.0]
            violation_list.append(now)
            _IP_RATE_VIOLATIONS[ip] = violation_list

            if len(violation_list) >= 4:
                ban_ip_address(db, ip, reason="Auto-ban: Persistent spamming after rate limit warnings", hours=48)
                raise HTTPException(
                    status_code=403,
                    detail=f"Your IP ({ip}) has been blocked for 48 hours due to continuous order spam. Ban will automatically lift after 2 days."
                )

            log_audit_event(db, "RATE_LIMIT", "WARNING", f"Rate limit triggered: {len(req_list)} orders in 60s", ip)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded: You are creating orders too quickly. Please wait 60 seconds before trying again."
            )
