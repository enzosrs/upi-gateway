__author__ = "enzosrs"
__github__ = "https://github.com/enzosrs"
__community__ = "https://t.me/devcommunityx"

import os
import json
import time
import threading
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
D1_DATABASE_ID = os.environ.get("D1_DATABASE_ID", os.environ.get("D1_PRIMARY_ID", ""))

_D1_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 3.0
_cache_lock = threading.Lock()

def _get_from_cache(cache_key: str) -> Optional[Any]:
    with _cache_lock:
        if cache_key in _D1_CACHE:
            entry = _D1_CACHE[cache_key]
            if time.time() - entry["ts"] < _CACHE_TTL_SECONDS:
                return entry["data"]
            del _D1_CACHE[cache_key]
    return None

def _set_in_cache(cache_key: str, data: Any):
    with _cache_lock:
        _D1_CACHE[cache_key] = {
            "ts": time.time(),
            "data": data
        }

def _clear_cache_pattern(pattern: str = ""):
    with _cache_lock:
        if not pattern:
            _D1_CACHE.clear()
        else:
            keys_to_del = [k for k in _D1_CACHE if pattern in k]
            for k in keys_to_del:
                del _D1_CACHE[k]

def execute_d1_query(database_id: Optional[str] = None, sql: str = "", params: Optional[List[Any]] = None) -> Dict[str, Any]:
    db_id = database_id or D1_DATABASE_ID
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN or not db_id:
        return {"success": False, "error": "Cloudflare credentials not configured in environment"}

    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/database/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    body = {"sql": sql}
    if params:
        body["params"] = params

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            if data.get("success"):
                results = data.get("result", [{}])[0].get("results", [])
                return {"success": True, "results": results}
            return {"success": False, "errors": data.get("errors", [])}
    except Exception as e:
        return {"success": False, "error": str(e)}

def d1_write(sql: str, params: Optional[List[Any]] = None):
    _clear_cache_pattern()
    return execute_d1_query(D1_DATABASE_ID, sql, params)

def d1_read(sql: str, params: Optional[List[Any]] = None, cache_key: Optional[str] = None) -> List[Dict[str, Any]]:
    if cache_key:
        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

    res = execute_d1_query(D1_DATABASE_ID, sql, params)
    if res.get("success"):
        results = res.get("results", [])
        if cache_key:
            _set_in_cache(cache_key, results)
        return results
    return []

def d1_get_order(order_id: str) -> Optional[Dict[str, Any]]:
    cache_key = f"order_{order_id}"
    rows = d1_read("SELECT * FROM orders WHERE order_id = ? LIMIT 1", [order_id], cache_key=cache_key)
    return rows[0] if rows else None

def d1_get_payment_by_utr(utr: str) -> Optional[Dict[str, Any]]:
    cache_key = f"payment_utr_{utr}"
    rows = d1_read("SELECT * FROM payments WHERE utr = ? LIMIT 1", [utr], cache_key=cache_key)
    return rows[0] if rows else None

def d1_verify_admin_login(username: str, password_raw: str) -> bool:
    try:
        rows = d1_read("SELECT * FROM admins WHERE username = ? LIMIT 1", [username])
        if rows:
            admin = rows[0]
            if admin.get("password_hash") == password_raw:
                d1_write("UPDATE admins SET last_login = datetime('now') WHERE username = ?", [username])
                return True
        return False
    except Exception:
        return False

def d1_is_enabled() -> bool:
    return bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN and D1_DATABASE_ID)

def d1_insert_order(order_id: str, amount: float, upi_id: str, status: str = "PENDING"):
    if not d1_is_enabled():
        return
    sql = "INSERT OR REPLACE INTO orders (order_id, amount, upi_id, status, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
    d1_write(sql, [order_id, amount, upi_id, status])

def d1_update_order_status(order_id: str, status: str, utr: Optional[str] = None):
    if not d1_is_enabled():
        return
    if utr:
        sql = "UPDATE orders SET status = ?, utr = ? WHERE order_id = ?"
        d1_write(sql, [status, utr, order_id])
    else:
        sql = "UPDATE orders SET status = ? WHERE order_id = ?"
        d1_write(sql, [status, order_id])
