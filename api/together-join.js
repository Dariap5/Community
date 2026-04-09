/**
 * Vercel Serverless Function: принимает JSON с лендинга и шлёт сообщение в Telegram.
 *
 * Переменные окружения в Vercel (Settings → Environment Variables):
 *   TELEGRAM_BOT_TOKEN  — токен от @BotFather
 *   TELEGRAM_CHAT_ID    — куда слать (ваш user id или id группы)
 *   TOGETHER_WEBHOOK_SECRET — опционально; тогда в community-landing.js задайте тот же JOIN_NOTIFY_SECRET
 */

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export default async function handler(req, res) {
  const allowOrigin = req.headers.origin || "*";
  res.setHeader("Access-Control-Allow-Origin", allowOrigin);
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const serverSecret = process.env.TOGETHER_WEBHOOK_SECRET;
  if (serverSecret) {
    const auth = req.headers.authorization || "";
    if (auth !== "Bearer " + serverSecret) {
      return res.status(401).json({ error: "Unauthorized" });
    }
  }

  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) {
    return res.status(500).json({ error: "Server missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID" });
  }

  let body = req.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch {
      return res.status(400).json({ error: "Invalid JSON" });
    }
  }
  if (!body || typeof body !== "object") {
    return res.status(400).json({ error: "Invalid body" });
  }

  const first = escapeHtml(body.firstName);
  const last = escapeHtml(body.lastName);
  const phone = escapeHtml(body.phone);
  const tg = escapeHtml(String(body.telegram || "").replace(/^@+/, ""));

  if (!first || !last || !phone || !tg) {
    return res.status(400).json({ error: "Missing fields" });
  }

  const text = [
    "<b>Новая заявка Together</b>",
    "",
    `Имя: ${first} ${last}`,
    `Телефон: ${phone}`,
    `Telegram: @${tg}`,
  ].join("\n");

  const tgRes = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
    }),
  });

  const tgJson = await tgRes.json().catch(() => ({}));
  if (!tgRes.ok || !tgJson.ok) {
    return res.status(502).json({ error: "Telegram API error", details: tgJson });
  }

  return res.status(200).json({ ok: true });
}
