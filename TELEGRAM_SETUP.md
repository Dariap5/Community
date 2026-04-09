# Заявки с лендинга в Telegram

Токен бота **нельзя** вставлять в `community-landing.js` — его увидит любой. Нужен маленький бэкенд (ниже — готовый файл для Vercel).

## Что подготовить и прислать (для настройки)

1. **Токен бота** — строка вида `123456789:AAHxxx...` от [@BotFather](https://t.me/BotFather) после `/newbot`.  
   *В чат Cursor можно прислать только если потом сразу отозвать и выпустить новый токен в BotFather → /revoke.*

2. **Chat ID** — куда слать сообщения:
   - личка с вами: свой числовой `user_id` (удобно узнать у [@userinfobot](https://t.me/userinfobot) или [@getidsbot](https://t.me/getidsbot));
   - или ID группы/канала (часто отрицательный, для группы бот должен быть в группе).

3. **Публичный URL API** после деплоя, например:  
   `https://<имя-проекта>.vercel.app/api/together-join`  
   Его вставляете в `community-landing.js` в **`JOIN_NOTIFY_URL`**.

4. **Опционально — секрет** произвольная длинная строка: одно и то же значение в Vercel как `TOGETHER_WEBHOOK_SECRET` и в JS как **`JOIN_NOTIFY_SECRET`** (заголовок `Authorization: Bearer …`).

## Деплой на Vercel

1. Зарегистрируйтесь на [vercel.com](https://vercel.com), подключите репозиторий или залейте папку с проектом.
2. Убедитесь, что в корне репозитория есть каталог **`api/`** с файлом **`together-join.js`** (уже в этом проекте).
3. В проекте Vercel → **Settings → Environment Variables** добавьте:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - при желании `TOGETHER_WEBHOOK_SECRET`
4. Задеплойте. Скопируйте URL функции и пропишите в `JOIN_NOTIFY_URL` в `community-landing.js`.

## Настройка фронта

В `community-landing.js`:

```javascript
const JOIN_NOTIFY_URL = "https://ВАШ-ДОМЕН.vercel.app/api/together-join";
const JOIN_NOTIFY_SECRET = ""; // или тот же секрет, что в TOGETHER_WEBHOOK_SECRET
```

## Проверка бота

- Напишите боту **/start** в личку (если шлёте в личку) — иначе иногда первое сообщение от бота может не дойти до «разрешённого» чата.
- Для группы: добавьте бота в группу, при необходимости отключите privacy mode у BotFather (`/setprivacy` → Disable), чтобы бот мог писать в группу по `chat_id` группы.

## CORS

Функция отдаёт `Access-Control-Allow-Origin` с тем `Origin`, с которого пришёл запрос (или `*`). Лендинг на другом домене должен отправлять обычный `fetch` без куки — этого достаточно.

## Альтернативы Vercel

Любой свой сервер с HTTPS: метод **POST**, путь на ваше усмотрение, тело JSON как с лендинга (`firstName`, `lastName`, `phone`, `telegram`, `source`), дальше тот же вызов `https://api.telegram.org/bot<TOKEN>/sendMessage`.
