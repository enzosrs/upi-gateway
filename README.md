# FamPay UPI Payment Gateway 🇮🇳 ⚡

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Database](https://img.shields.io/badge/Cloudflare_D1-Single_DB-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)](https://developers.cloudflare.com/d1/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Transaction Fee](https://img.shields.io/badge/Transaction_Fee-0%25_FREE-brightgreen?style=for-the-badge)](#why-use-this-upi-gateway)
[![UPI 2.0](https://img.shields.io/badge/UPI_2.0-Instant_Settlement-orange?style=for-the-badge)](#supported-upi-apps)
[![Telegram Support](https://img.shields.io/badge/Telegram-Community-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/devcommunityx)

> **Free, Automated & Zero-Fee UPI Payment Gateway for Indian Developers, Startups & Telegram Bots.**  
> Accept payments directly into your **FamPay / FamApp** or any personal/business bank account with **0% transaction charges**, instant dynamic UPI QR codes, real-time Gmail UTR verification, and automated webhook delivery.

---

## 📌 Table of Contents

- [Why Use This UPI Gateway?](#why-use-this-upi-gateway)
- [How It Works](#how-it-works)
- [Supported UPI Apps](#supported-upi-apps)
- [Key Features](#key-features)
- [Quick Start & Installation](#quick-start--installation)
- [Environment Configuration (.env)](#environment-configuration-env)
- [Complete API Reference](#complete-api-reference)
  - [1. Create Autopay Order](#1-create-autopay-order-post-autopay)
  - [2. Check Order Status](#2-check-order-status-get-autopay)
  - [3. Verify Payment Status](#3-verify-payment-status-post-autopayverify)
  - [4. Customer Submit UTR](#4-customer-submit-utr-post-autopaysubmit-utr)
  - [5. Backend UTR Verification](#5-backend-utr-verification-post-verifypayment)
  - [6. Admin Authentication](#6-admin-authentication-post-adminlogin)
  - [7. Analytics Dashboard](#7-analytics-dashboard-get-adminstats)
  - [8. Transaction History](#8-transaction-history-get-admintransactions)
  - [9. Database Health Status](#9-database-health-status-get-admindatabase-status)
  - [10. Webhook Notification](#10-webhook-notification-payload)
- [JavaScript Client SDK (use.js)](#javascript-client-sdk-usejs)
- [Telegram Bot Admin Commands](#telegram-bot-admin-commands)
- [Frequently Asked Questions (FAQ)](#frequently-asked-questions-faq)
- [Cloudflare D1 Deployment](#cloudflare-d1-deployment)
- [License & Support](#license--support)

---

## 💡 Why Use This UPI Gateway?

Traditional Indian payment gateways (Razorpay, Cashfree, PayU, Paytm PG) require registered business documentation (GST, MCA, MSME), charge **2% to 3% fee + 18% GST per transaction**, hold payouts for **T+2 or T+3 days**, and frequently freeze developer accounts.

| Feature | Traditional Gateways (Razorpay / Cashfree) | FamPay UPI Gateway (Self-Hosted) |
| :--- | :---: | :---: |
| **Transaction Fees** | 2% – 3% + 18% GST | **0% (100% Free Forever)** |
| **Settlement Time** | T+2 or T+3 Days | **Instant Direct-to-Bank** |
| **GST / Business Docs** | Mandatory | **No GST or Business Docs Needed** |
| **Supported Accounts** | Current Accounts Only | **FamPay, Savings, Current & Wallets** |
| **Setup Cost** | ₹0 – ₹5000 Setup Fees | **Free & Open-Source (MIT)** |
| **Account Freeze Risk** | High (KYC rejection) | **Zero (You own your server & DB)** |
| **Payment Verification** | Webhook via aggregator | **Sub-second via Real-Time Mail UTR** |

---

## ⚡ How It Works

```
1. Customer initiates checkout on your website / Telegram bot
      │
      ▼
2. Gateway generates dynamic UPI link (`upi://pay?pa=...`) & QR code with exact order amount
      │
      ▼
3. Customer scans & pays via FamPay, PhonePe, Google Pay, Paytm, CRED, etc.
      │
      ▼
4. Bank sends instant payment confirmation email to your connected Gmail
      │
      ▼
5. Background scanner extracts 12-digit UPI UTR & Transaction Amount (< 2 seconds)
      │
      ▼
6. Gateway verifies payment, updates order to SUCCESS, triggers Webhook & sends Telegram alert
```

---

## 📲 Supported UPI Apps

Works seamlessly across all NPCI-authorized UPI payment applications in India:

- **FamApp / FamPay (FamX Card & UPI)**
- **PhonePe**
- **Google Pay (GPay)**
- **Paytm UPI**
- **BHIM UPI**
- **CRED UPI**
- **Amazon Pay UPI**
- **All Major Indian Banks** (HDFC, SBI, ICICI, Axis, Kotak, PNB, Bank of Baroda)

---

## 🚀 Key Features

- **0% Transaction Cost**: Keep 100% of your earnings. Zero mediator deductions.
- **Dynamic QR & Intent URL**: Generates instant QR codes (`api.qrserver.com`) and click-to-pay links (`upi://pay?pa=...`).
- **Single D1 Database Engine**: Clean, single-database architecture compatible with local SQLite (`d1.db`) and Cloudflare D1 edge.
- **Sub-Second UTR Verification**: Real-time Gmail inbox monitoring with automated 12-digit UTR and amount matching.
- **Anti-Fraud & Replay Protection**: Prevents duplicate UTR submissions and replay attacks across orders.
- **Built-in Rate Limiting & Anti-DDoS**: Automatic 429 cooldowns and 48-hour auto-ban for repeated order spam.
- **Telegram Admin Bot**: Create orders, verify UTRs, force-approve, and view real-time revenue right from Telegram chat.
- **HMAC SHA-256 Webhooks**: Secure signatures ensuring notifications come genuinely from your gateway.
- **Node.js Client SDK (`use.js`)**: Copy-paste functions for instant integration with backend web applications.

---

## 🛠️ Quick Start & Installation

### 1. Clone the Repository

```bash
git clone https://github.com/enzosrs/upi-gateway.git
cd upi-gateway
```

### 2. Setup Python Virtual Environment

```bash
python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Setup Environment File

```bash
cp .env.example .env
```

Open `.env` and fill in your UPI ID, Google OAuth credentials, and admin passwords.

### 5. Run the Gateway Server

```bash
uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

The gateway will start on **`http://localhost:8001`**.  
Interactive Swagger API documentation is available at **`http://localhost:8001/docs`**.

### 6. Connect Gmail Account

Open your browser and navigate to:
```
http://localhost:8001/auth
```
Sign in with the Gmail account that receives payment notification emails from your bank or FamPay. Once authenticated, credentials are saved locally, and the background payment scanner starts automatically.

---

## ⚙️ Environment Configuration (.env)

Here is the complete reference for all `.env` configuration keys:

```env
# ==============================================================================
# Google Cloud Console OAuth 2.0 Credentials (Gmail API)
# Get from: https://console.cloud.google.com/apis/credentials
# ==============================================================================
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8001/auth/google/callback
OAUTHLIB_RELAX_TOKEN_SCOPE=1

# ==============================================================================
# Gateway Server Settings
# ==============================================================================
APP_URL=http://localhost:8001
HOST=0.0.0.0
PORT=8001

# ==============================================================================
# UPI Merchant / Receiver Configuration
# Your FamPay VPA or Bank UPI ID where money is deposited
# ==============================================================================
UPI_ID=yourname@fam

# ==============================================================================
# Single Database Configuration (Local D1 SQLite)
# ==============================================================================
DATABASE_URL=sqlite:///d1.db

# ==============================================================================
# Cloudflare D1 Database (Optional - for Cloudflare Edge Replication)
# ==============================================================================
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
D1_DATABASE_ID=

# ==============================================================================
# Gateway API Authentication (Backend-to-Backend Security)
# ==============================================================================
GATEWAY_API_KEY=your_secure_api_key
GATEWAY_CLIENT_NAME=your_client_app_name

# ==============================================================================
# Admin Dashboard Authentication
# ==============================================================================
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourStrongPassword#2026
ADMIN_TOKEN_SECRET=your_random_secret_token_key

# ==============================================================================
# Telegram Bot Alerts & Remote Administration (Optional)
# Create bot via @BotFather on Telegram
# ==============================================================================
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=

# ==============================================================================
# Webhook Dispatch Settings (Optional)
# ==============================================================================
WEBHOOK_URL=http://localhost:8001/webhook
WEBHOOK_SECRET=your_webhook_hmac_secret
```

---

## 📖 Complete API Reference

All requests and responses use JSON. For secure endpoints, pass `GATEWAY_API_KEY` or `Bearer <ADMIN_TOKEN>`.

---

### 1. Create Autopay Order (`POST /autopay`)

Generates a new payment session. Returns unique `order_id`, UPI intent link, QR code image URL, and web checkout URL. Valid for 10 minutes.

- **URL**: `POST /autopay`
- **Headers**: `Content-Type: application/json`

#### Request Payload:
```json
{
  "amount": 299.00,
  "customer_name": "Aman Verma",
  "customer_mobile": "9876543210",
  "note": "Pro Membership Upgrade"
}
```

#### Success Response (200 OK):
```json
{
  "status": "success",
  "order_id": "ORD17000000001234",
  "amount": 299.0,
  "upi_id": "yourname@fam",
  "upi_url": "upi://pay?pa=yourname@fam&pn=Payment&am=299.00&cu=INR",
  "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=upi%3A%2F%2Fpay...",
  "payment_url": "http://localhost:8001/checkout/ORD17000000001234",
  "time_left": 600,
  "expires_at": 1700000600000
}
```

#### cURL Example:
```bash
curl -X POST http://localhost:8001/autopay \
  -H "Content-Type: application/json" \
  -d '{"amount": 299.00, "customer_name": "Aman Verma", "customer_mobile": "9876543210"}'
```

---

### 2. Check Order Status (`GET /autopay`)

Fetches metadata, live status (`PENDING`, `SUCCESS`, `EXPIRED`), linked UTR, and remaining time.

- **URL**: `GET /autopay?order_id=ORD17000000001234`
- **Headers**: `Accept: application/json`

#### Success Response:
```json
{
  "status": "success",
  "order_id": "ORD17000000001234",
  "amount": 299.0,
  "upi_id": "yourname@fam",
  "upi_url": "upi://pay?pa=yourname@fam&pn=Payment&am=299.00&cu=INR",
  "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=...",
  "order_status": "SUCCESS",
  "utr": "412345678901",
  "created_at": "2026-11-18T08:00:00Z",
  "time_left": 420,
  "expires_at": 1700000600000
}
```

#### cURL Example:
```bash
curl "http://localhost:8001/autopay?order_id=ORD17000000001234"
```

---

### 3. Verify Payment Status (`POST /autopay/verify`)

Frontend polling endpoint. Returns `200 OK` once payment is detected and verified, or `404` while waiting for funds.

- **URL**: `POST /autopay/verify`
- **Headers**: `Content-Type: application/json`

#### Request Payload:
```json
{
  "order_id": "ORD17000000001234"
}
```

#### Success Response (Verified):
```json
{
  "status": "success",
  "order_id": "ORD17000000001234",
  "message": "Payment verified",
  "utr": "412345678901",
  "amount": 299.0
}
```

#### Pending Response (HTTP 404):
```json
{
  "detail": "Payment not yet received"
}
```

#### cURL Example:
```bash
curl -X POST http://localhost:8001/autopay/verify \
  -H "Content-Type: application/json" \
  -d '{"order_id": "ORD17000000001234"}'
```

---

### 4. Customer Submit UTR (`POST /autopay/submit-utr`)

Allows customers to enter the 12-digit UTR from their UPI transaction receipt directly on the checkout screen. Matches against local records and queries Gmail instantly.

- **URL**: `POST /autopay/submit-utr`
- **Headers**: `Content-Type: application/json`

#### Request Payload:
```json
{
  "order_id": "ORD17000000001234",
  "utr": "412345678901"
}
```

#### Success Response:
```json
{
  "status": "success",
  "message": "Payment verified and order approved successfully!",
  "order_id": "ORD17000000001234",
  "utr": "412345678901",
  "amount": 299.0
}
```

#### cURL Example:
```bash
curl -X POST http://localhost:8001/autopay/submit-utr \
  -H "Content-Type: application/json" \
  -d '{"order_id": "ORD17000000001234", "utr": "412345678901"}'
```

---

### 5. Backend UTR Verification (`POST /verify/payment`)

Secure server-side API to verify if a specific UTR has deposited into your bank account. Includes tolerance matching for expected amount and anti-replay guards.

- **URL**: `POST /verify/payment`
- **Headers**: `Content-Type: application/json`

#### Request Payload:
```json
{
  "key": "your_gateway_api_key",
  "name": "your_client_name",
  "utr": "412345678901",
  "amount": 299.00,
  "order_id": "ORD17000000001234"
}
```

#### Success Response:
```json
{
  "status": "success",
  "message": "Payment successful",
  "order_id": "ORD17000000001234",
  "payment": {
    "id": 1,
    "utr": "412345678901",
    "amount": 299.0,
    "sender": "no-reply@famapp.in",
    "subject": "You received ₹299.00 from Aman",
    "date": "Wed, 18 Nov 2026 08:00:00 +0530",
    "recipient_name": "Merchant",
    "sender_name": "Aman",
    "purpose": "UPI Payment",
    "created_at": "2026-11-18T08:00:05"
  }
}
```

#### cURL Example:
```bash
curl -X POST http://localhost:8001/verify/payment \
  -H "Content-Type: application/json" \
  -d '{"key": "your_api_key", "name": "your_client", "utr": "412345678901", "amount": 299.0}'
```

---

### 6. Admin Authentication (`POST /admin/login`)

Authenticates administrator credentials and returns session token.

- **URL**: `POST /admin/login`
- **Headers**: `Content-Type: application/json`

#### Request Payload:
```json
{
  "username": "admin",
  "password": "YourStrongPassword#2026"
}
```

#### Success Response:
```json
{
  "status": "success",
  "message": "Login successful",
  "token": "admin_session_admin_your_token_secret",
  "username": "admin"
}
```

#### cURL Example:
```bash
curl -X POST http://localhost:8001/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "YourStrongPassword#2026"}'
```

---

### 7. Analytics Dashboard (`GET /admin/stats`)

Returns total revenue, today's income, weekly numbers, monthly statistics, conversion success rates, and 14-day daily chart trends.

- **URL**: `GET /admin/stats`
- **Headers**: `Authorization: Bearer <ADMIN_TOKEN>`

#### Success Response:
```json
{
  "status": "success",
  "total_revenue": 45890.0,
  "total_transactions": 340,
  "total_orders": 362,
  "settled_count": 340,
  "pending_orders_count": 14,
  "expired_orders_count": 8,
  "stats": {
    "total_revenue": 45890.0,
    "today_revenue": 4200.0,
    "yesterday_revenue": 3800.0,
    "this_week_revenue": 21500.0,
    "this_month_revenue": 45890.0,
    "today_orders": 28,
    "success_orders": 340,
    "success_rate": 93.9,
    "gmail_authenticated": true,
    "daily_trend": [
      {
        "date": "2026-11-18",
        "label": "18 Nov",
        "orders": 28,
        "revenue": 4200.0,
        "success": 26,
        "failed": 2
      }
    ]
  }
}
```

#### cURL Example:
```bash
curl http://localhost:8001/admin/stats \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

---

### 8. Transaction History (`GET /admin/transactions`)

Paginated list of orders and received payment logs with filtering and text search.

- **URL**: `GET /admin/transactions?status=ALL&page=1&limit=50&search=Aman`
- **Headers**: `Authorization: Bearer <ADMIN_TOKEN>`

#### Success Response:
```json
{
  "status": "success",
  "total": 1,
  "total_orders": 362,
  "total_transactions": 340,
  "page": 1,
  "limit": 50,
  "transactions": [
    {
      "type": "ORDER",
      "direction": "RECEIVED",
      "id": "ORD17000000001234",
      "utr": "412345678901",
      "amount": 299.0,
      "status": "SUCCESS",
      "sender_upi": "yourname@fam",
      "date": "2026-11-18 13:30:00",
      "created_at": "2026-11-18 13:30:00",
      "details": "UPI: yourname@fam"
    }
  ]
}
```

---

### 9. Database Health Status (`GET /admin/database-status`)

Returns single D1 database status, connection latency, and active record counts.

- **URL**: `GET /admin/database-status`
- **Headers**: `Authorization: Bearer <ADMIN_TOKEN>`

#### Success Response:
```json
{
  "status": "success",
  "database": {
    "id": "d1_database",
    "name": "Cloudflare D1 Database",
    "engine": "Cloudflare D1 (SQLite Edge)",
    "role": "PRIMARY DATABASE",
    "status": "ONLINE",
    "latency_ms": 1.2,
    "records": "340 active orders (Local D1 Engine Active)",
    "badge": "Primary D1"
  }
}
```

---

### 10. Webhook Notification Payload

When an order payment is successfully verified, the gateway immediately dispatches an HTTP POST request to your configured `WEBHOOK_URL`.

#### Headers Sent:
```http
Content-Type: application/json
X-Webhook-Secret: <your_webhook_secret>
X-Gateway-Signature: <hmac_sha256_hex_digest>
```

#### JSON Payload:
```json
{
  "order_id": "ORD17000000001234",
  "message_id": "18f9103bac4b31bd",
  "utr": "412345678901",
  "amount": 299.0,
  "sender": "no-reply@famapp.in",
  "sender_name": "Aman Verma",
  "subject": "You received ₹299.00 from Aman Verma",
  "status": "SUCCESS"
}
```

---

## 💻 JavaScript Client SDK (`use.js`)

Import lightweight functions from `use.js` directly into your Node.js or Express.js backend:

```javascript
const {
  createOrder,
  getOrderStatus,
  verifyOrder,
  submitUtr,
  verifyPaymentByUtr
} = require("./use.js");

async function checkoutExample() {
  // 1. Create a payment session
  const order = await createOrder(499.00, "Vikram Singh", "9988776655");
  console.log("Pay URL:", order.payment_url);
  console.log("UPI Intent Link:", order.upi_url);
  console.log("QR Image:", order.qr_code_url);

  // 2. Customer submits UTR manually from receipt
  await submitUtr(order.order_id, "412345678901");

  // 3. Verify order status
  try {
    const verified = await verifyOrder(order.order_id);
    console.log("Payment Confirmed! UTR:", verified.utr);
  } catch (err) {
    console.log("Waiting for confirmation...");
  }
}

checkoutExample();
```

---

## 🤖 Telegram Bot Admin Commands

If `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_CHAT_ID` are set, manage your gateway directly inside Telegram:

| Command | Action | Example |
| :--- | :--- | :--- |
| `/stats` | View real-time revenue, order stats & conversion rates | `/stats` |
| `/create <amount>` | Create a dynamic UPI payment QR card in chat | `/create 500` |
| `/verify <utr>` | Check if a UTR was received in bank or Gmail | `/verify 412345678901` |
| `/approve <order_id> [utr]` | Manually force-approve any order | `/approve ORD12345 412345678901` |
| `/logs` | Display 5 most recent payment transactions | `/logs` |
| `/help` | Show list of available commands | `/help` |

---

## ❓ Frequently Asked Questions (FAQ)

#### Q1: Is this UPI gateway really 0% fee?
**Yes.** Unlike Razorpay or Paytm that charge 2% to 3% plus GST, payments made through this gateway go directly into your bank or FamPay account via standard peer-to-peer (P2P/P2M) UPI transfer. There is no middleman and zero transaction fee.

#### Q2: Do I need GST or a business current account?
**No.** You can use your personal UPI ID, FamPay account, savings account, or current account. No business registration or GST certificate is needed.

#### Q3: Does it work with all UPI apps?
**Yes.** Customers can scan the QR code or click the UPI payment button using **PhonePe, Google Pay, Paytm, BHIM, CRED, FamApp**, or any mobile banking app.

#### Q4: How fast is payment verification?
Verification happens in **1 to 3 seconds**. When a user makes a payment, the bank sends an email confirmation. The gateway background listener reads the unread email, matches the amount and UTR, marks the order `SUCCESS`, and notifies your webhook.

#### Q5: Can a user fake a payment by submitting a random UTR?
**No.** When a user submits a UTR via `/autopay/submit-utr`, the gateway checks the email inbox and local database. The order is only marked `SUCCESS` if a genuine bank credit email exists with that exact UTR and matching amount. Replay attacks are also prevented.

---

## ☁️ Cloudflare D1 Deployment

To initialize the single D1 database schema on Cloudflare:

```bash
# Execute schema on Cloudflare D1
npx wrangler d1 execute upi_gateway --file=schema.sql

# Deploy worker
npx wrangler deploy
```

---

## 📄 License & Community Support

- **License**: [MIT License](LICENSE) — free for personal and commercial projects.
- **Developer Community**: Join our Telegram for support and updates: [t.me/devcommunityx](https://t.me/devcommunityx)
- **Author**: [enzosrs](https://github.com/enzosrs)

---

### ⭐ Star the Repository
If you find this project helpful, please star the repository on GitHub to support open-source development!
