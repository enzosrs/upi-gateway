const WATERMARK = Object.freeze({
  author: "enzosrs",
  github: "https://github.com/enzosrs",
  community: "https://t.me/devcommunityx"
});

const BASE_URL = process.env.GATEWAY_URL || "http://localhost:8001";
const API_KEY = process.env.GATEWAY_API_KEY || "";
const CLIENT_NAME = process.env.GATEWAY_CLIENT_NAME || "";

// Create UPI order with amount & customer info
async function createOrder(amount, customerName = "User", customerMobile = "") {
  const res = await fetch(`${BASE_URL}/autopay`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount, customer_name: customerName, customer_mobile: customerMobile })
  });
  return await res.json();
}

// Get order details & current status
async function getOrderStatus(orderId) {
  const res = await fetch(`${BASE_URL}/autopay?order_id=${encodeURIComponent(orderId)}`);
  return await res.json();
}

// Verify order status after customer payment
async function verifyOrder(orderId) {
  const res = await fetch(`${BASE_URL}/autopay/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order_id: orderId })
  });
  if (!res.ok) throw new Error("Payment pending");
  return await res.json();
}

// Submit 12-digit UTR manually for an order
async function submitUtr(orderId, utr) {
  const res = await fetch(`${BASE_URL}/autopay/submit-utr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order_id: orderId, utr })
  });
  return await res.json();
}

// Direct backend verification using UTR
async function verifyPaymentByUtr(utr, amount = null, orderId = null) {
  const res = await fetch(`${BASE_URL}/verify/payment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: API_KEY, name: CLIENT_NAME, utr, amount, order_id: orderId })
  });
  return await res.json();
}

// Admin login to get session token
async function adminLogin(username, password) {
  const res = await fetch(`${BASE_URL}/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });
  const data = await res.json();
  return data.token;
}

// Fetch admin revenue & order statistics
async function getAdminStats(token) {
  const res = await fetch(`${BASE_URL}/admin/stats`, {
    headers: { "Authorization": `Bearer ${token}` }
  });
  return await res.json();
}

// Fetch transaction history
async function getAdminTransactions(token, status = "ALL", page = 1, limit = 50) {
  const res = await fetch(`${BASE_URL}/admin/transactions?status=${status}&page=${page}&limit=${limit}`, {
    headers: { "Authorization": `Bearer ${token}` }
  });
  return await res.json();
}

// Trigger Gmail payment scan
async function triggerGmailScan() {
  const res = await fetch(`${BASE_URL}/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: API_KEY, name: CLIENT_NAME })
  });
  return await res.json();
}

// Webhook listener template
function handleWebhook(req, res) {
  const event = req.body;
  console.log("Payment received:", event.order_id, event.utr, event.amount);
  res.json({ status: "ok" });
}

module.exports = {
  WATERMARK,
  createOrder,
  getOrderStatus,
  verifyOrder,
  submitUtr,
  verifyPaymentByUtr,
  adminLogin,
  getAdminStats,
  getAdminTransactions,
  triggerGmailScan,
  handleWebhook
};
