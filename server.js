/**
 * API для лендинга на своём сервере (без Vercel).
 * Запуск: npm install && npm start
 * Переменные: файл .env в корне (см. TELEGRAM_SETUP.md) или systemd EnvironmentFile.
 * Nginx: proxy_pass на PORT (по умолчанию 3001), путь /api/together-join.
 */
import "dotenv/config";
import express from "express";
import togetherJoin from "./api/together-join.js";

const app = express();
app.use(express.json({ limit: "48kb" }));

app.all("/api/together-join", (req, res) => {
  togetherJoin(req, res);
});

const PORT = Number(process.env.PORT || 3001);
const HOST = process.env.HOST || "127.0.0.1";

app.listen(PORT, HOST, () => {
  console.log(`Together API http://${HOST}:${PORT}/api/together-join`);
});
