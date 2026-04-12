/**
 * Принимает JSON с лендинга и шлёт сообщение в Telegram.
 * Vercel: файл в api/ как serverless. Свой сервер: поднимаете server.js + nginx (см. TELEGRAM_SETUP.md).
 *
 * Переменные окружения:
 *   BOT_TOKEN или TELEGRAM_BOT_TOKEN — токен от @BotFather
 *   TELEGRAM_CHAT_ID — куда слать (user id или id группы)
 *   TOGETHER_WEBHOOK_SECRET — опционально; тогда в community-landing.js тот же JOIN_NOTIFY_SECRET
 */

function nextApplicationNumber() {
  const t = Date.now();
  const r = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `${t}-${r}`;
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

  const token = process.env.BOT_TOKEN || process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) {
    return res.status(500).json({ error: "Server missing BOT_TOKEN (or TELEGRAM_BOT_TOKEN) or TELEGRAM_CHAT_ID" });
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

  const first = String(body.firstName || "").trim();
  const last = String(body.lastName || "").trim();
  const phone = String(body.phone || "").trim();
  const tg = String(body.telegram || "")
    .replace(/^@+/, "")
    .trim();
  const calendlySlot = String(body.calendlySlot || "").trim();

  if (!first || !last || !phone || !tg) {
    return res.status(400).json({ error: "Missing fields" });
  }
  if (!calendlySlot) {
    return res.status(400).json({ error: "Missing calendlySlot" });
  }

  const applicationNumber = nextApplicationNumber();

  const text = [
    `Заявка #${applicationNumber}`,
    "",
    `Имя: ${first}`,
    `Фамилия: ${last}`,
    `Номер телефона: ${phone}`,
    `Телеграм: @${tg}`,
    `Запись в Calendly: ${calendlySlot}`,
  ].join("\n");

  let tgRes;
  let tgJson;
  try {
    tgRes = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        disable_web_page_preview: true,
      }),
    });
    tgJson = await tgRes.json().catch(() => ({}));
  } catch (err) {
    const code = err && err.cause && err.cause.code;
    console.error("[together-join] Telegram fetch failed:", code || err.message || err);
    return res.status(503).json({
      error: "Telegram unreachable",
      code: code || undefined,
    });
  }

  if (!tgRes.ok || !tgJson.ok) {
    return res.status(502).json({ error: "Telegram API error", details: tgJson });
  }

  return res.status(200).json({ ok: true, applicationNumber });
}
