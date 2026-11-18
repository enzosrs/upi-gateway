__author__ = "enzosrs"
__github__ = "https://github.com/enzosrs"
__community__ = "https://t.me/devcommunityx"

import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, or_, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

DB_PATH = os.environ.get("D1_DB_PATH", os.path.join(os.path.dirname(__file__), "d1.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    utr = Column(String, unique=True, index=True, nullable=True)
    message_id = Column(String, unique=True, index=True, nullable=False)
    amount = Column(Float, nullable=True)
    date = Column(String, nullable=True)
    sender = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    recipient_name = Column(String, nullable=True)
    sender_name = Column(String, nullable=True)
    purpose = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    upi_id = Column(String, nullable=False)
    status = Column(String, default="PENDING")
    utr = Column(String, unique=True, index=True, nullable=True)
    telegram_message_id = Column(Integer, nullable=True)
    telegram_chat_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class FlowState(Base):
    __tablename__ = "flow_states"

    state = Column(String, primary_key=True, index=True)
    code_verifier = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AdminUser(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="superadmin")
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class IPBan(Base):
    __tablename__ = "ip_bans"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, unique=True, index=True, nullable=False)
    reason = Column(String, default="Order spam violation")
    violations_count = Column(Integer, default=1)
    banned_until = Column(DateTime, nullable=False, index=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, index=True, nullable=True)
    event_type = Column(String, index=True, nullable=False)
    status = Column(String, default="INFO")
    details = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

def save_flow_state(state: str, code_verifier: str):
    db = SessionLocal()
    try:
        db.query(FlowState).filter(FlowState.state == state).delete()
        flow_state = FlowState(state=state, code_verifier=code_verifier)
        db.add(flow_state)
        db.commit()
    finally:
        db.close()

def pop_flow_state(state: str) -> str | None:
    db = SessionLocal()
    try:
        flow_state = db.query(FlowState).filter(FlowState.state == state).first()
        if flow_state:
            verifier = flow_state.code_verifier
            db.delete(flow_state)
            db.commit()
            return verifier
        return None
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin_user = os.environ.get("ADMIN_USERNAME", "admin")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "")
        if admin_user and admin_pass:
            admin = db.query(AdminUser).filter(AdminUser.username == admin_user).first()
            if not admin:
                admin = AdminUser(username=admin_user, password_hash=admin_pass, role="superadmin")
                db.add(admin)
                db.commit()
            else:
                admin.password_hash = admin_pass
                db.commit()
    except Exception as e:
        db.rollback()
        print(f"[DB] Notice: {e}")
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def save_payment(db: Session, utr: str, message_id: str, amount: float, date: str, sender: str, subject: str, recipient_name: str = None, sender_name: str = None, purpose: str = None) -> bool:
    if amount is None or amount <= 0:
        return False

    clean_utr = utr.strip().replace(" ", "").replace("-", "") if utr else None
    if clean_utr and not clean_utr.startswith("MSG-"):
        exists_utr = db.query(Payment).filter(
            or_(
                func.lower(Payment.utr) == clean_utr.lower(),
                func.lower(Payment.purpose) == clean_utr.lower()
            )
        ).first()
        if exists_utr:
            return False

    exists_msg = db.query(Payment).filter(Payment.message_id == message_id).first()
    if exists_msg:
        return False

    payment = Payment(
        utr=clean_utr if clean_utr else None,
        message_id=message_id,
        amount=amount,
        date=date,
        sender=sender,
        subject=subject,
        recipient_name=recipient_name,
        sender_name=sender_name,
        purpose=purpose
    )
    db.add(payment)
    try:
        db.commit()
        db.refresh(payment)

        try:
            from d1 import d1_write, d1_is_enabled
            if d1_is_enabled():
                d1_write(
                    "INSERT OR REPLACE INTO payments (utr, amount, sender, sender_name, date, subject, purpose, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                    [clean_utr or f"MSG-{message_id}", amount, sender, sender_name, date, subject, purpose]
                )
        except Exception:
            pass

        if amount and amount > 0:
            tolerance = 0.05
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
            pending_order = db.query(Order).filter(
                Order.status == "PENDING",
                Order.amount >= amount - tolerance,
                Order.amount <= amount + tolerance,
                Order.created_at >= cutoff
            ).order_by(Order.created_at.desc()).first()

            if pending_order:
                pending_order.status = "SUCCESS"
                pending_order.utr = utr
                db.commit()

                try:
                    from d1 import d1_update_order_status
                    d1_update_order_status(pending_order.order_id, "SUCCESS", utr)
                except Exception:
                    pass

                try:
                    from telegram import send_telegram_order_status_reply
                    send_telegram_order_status_reply(
                        telegram_message_id=pending_order.telegram_message_id,
                        order_id=pending_order.order_id,
                        status="SUCCESS",
                        utr=utr,
                        amount=amount,
                        sender_name=sender_name or sender,
                        target_chat_id=pending_order.telegram_chat_id
                    )
                except Exception as tg_err:
                    print(f"Failed to send Telegram status reply: {tg_err}")

        return True
    except Exception as e:
        db.rollback()
        print(f"Error committing payment to database: {e}")
        return False
