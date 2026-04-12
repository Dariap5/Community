# Заявки с лендинга в Telegram

Токен бота **нельзя** вставлять в `community-landing.js` — его увидит любой. Нужен маленький бэкенд (ниже — готовый файл для Vercel).

## Что подготовить и прислать (для настройки)

1. **Токен бота** — строка вида `123456789:AAHxxx...` от [@BotFather](https://t.me/BotFather) после `/newbot`.  
   *В чат Cursor можно прислать только если потом сразу отозвать и выпустить новый токен в BotFather → /revoke.*

2. **Chat ID** — куда слать сообщения:
   - личка с вами: свой числовой `user_id` (удобно узнать у [@userinfobot](https://t.me/userinfobot) или [@getidsbot](https://t.me/getidsbot));
   - или ID группы/канала (часто отрицательный, для группы бот должен быть в группе).

3. **Публичный URL API** после деплоя (Vercel или ваш домен с nginx), например  
   `https://dariyap.ru/api/together-join`  
   На своём домене с прокси на Node оставьте в `community-landing.js` **`JOIN_NOTIFY_URL = ""`** — тогда запрос пойдёт на тот же хост + `/api/together-join`. Иначе укажите полный URL.

4. **Опционально — секрет** произвольная длинная строка: одно и то же значение в окружении как `TOGETHER_WEBHOOK_SECRET` и в JS как **`JOIN_NOTIFY_SECRET`** (заголовок `Authorization: Bearer …`).

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
// Свой домен + nginx → Node: пустая строка (запрос на тот же origin + /api/together-join)
const JOIN_NOTIFY_URL = "";
// Vercel или другой хост:
// const JOIN_NOTIFY_URL = "https://ваш-проект.vercel.app/api/together-join";
const JOIN_NOTIFY_SECRET = ""; // или тот же секрет, что в TOGETHER_WEBHOOK_SECRET
```

В **`index.html`** задан `<meta name="together-api-origin" content="https://dariyap.ru">`: если `window.location` не даёт обычный `https:` (встроенный браузер, предпросмотр), заявка всё равно уйдёт на этот хост + `/api/together-join`. Смените `content`, если основной домен другой.

## Проверка бота

- Напишите боту **/start** в личку (если шлёте в личку) — иначе иногда первое сообщение от бота может не дойти до «разрешённого» чата.
- Для группы: добавьте бота в группу, при необходимости отключите privacy mode у BotFather (`/setprivacy` → Disable), чтобы бот мог писать в группу по `chat_id` группы.

## CORS

Функция отдаёт `Access-Control-Allow-Origin` с тем `Origin`, с которого пришёл запрос (или `*`). Лендинг на другом домене должен отправлять обычный `fetch` без куки — этого достаточно.

## Свой сервер (Ubuntu, nginx, без Vercel)

1. На сервере в каталоге сайта, например `/var/www/Community`:
   ```bash
   cd /var/www/Community
   git pull origin main
   npm install
   ```
2. Создайте файл **`.env`** в этом каталоге (в git не коммитится):
   ```env
   TELEGRAM_BOT_TOKEN=ваш_токен
   TELEGRAM_CHAT_ID=ваш_chat_id
   PORT=3001
   ```
   При необходимости добавьте `TOGETHER_WEBHOOK_SECRET` и тот же секрет в `JOIN_NOTIFY_SECRET` в `community-landing.js`.

3. В **блок `server { … }` с SSL** для вашего домена добавьте **до** `location / {`:
   ```nginx
   location /api/together-join {
       proxy_pass http://127.0.0.1:3001;
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```
   Затем: `sudo nginx -t && sudo systemctl reload nginx`

4. Запуск API через **systemd**. В репозитории есть шаблон **`deploy/together-api.service`** — скопируйте его в systemd (или создайте тот же файл вручную):
   ```bash
   sudo cp /var/www/Community/deploy/together-api.service /etc/systemd/system/together-api.service
   ```
   Установите Node 20+ (`node -v`). Если `node` не в `/usr/bin/node`, выполните `which node` и отредактируйте строку `ExecStart=` в `/etc/systemd/system/together-api.service`.
   Команды:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now together-api.service
   sudo systemctl status together-api
   ```

5. Если в браузере **502** на `POST …/api/together-join`: чаще всего это не «сломался nginx», а ответ API при **ошибке Telegram** (неверный токен, неверный `chat_id`, бот не запущен в личке через `/start`). Проверьте шаг 6 и логи `journalctl -u together-api -n 50`.

6. Проверка с сервера:
   ```bash
   curl -sS -X POST "https://dariyap.ru/api/together-join" \
     -H "Content-Type: application/json" \
     -d '{"firstName":"Т","lastName":"Т","phone":"+79990000000","telegram":"test","calendlySlot":"тест"}'
   ```
   Ожидается JSON с `"ok":true`.

В `community-landing.js` для этого сценария: **`JOIN_NOTIFY_URL = ""`**.

## Таймаут до `api.telegram.org` (в логах `UND_ERR_CONNECT_TIMEOUT`, `Connect Timeout Error`)

Процесс Node **должен** уметь открыть исходящее HTTPS-соединение к хостам Telegram (в логах часто видны `149.154.x.x` и/или IPv6 `2001:67c:4e8:…`).

1. С самого VPS проверьте, что соединение вообще устанавливается (не обязательно 200 OK):
   ```bash
   curl -4 -I --max-time 15 https://api.telegram.org/
   ```
   Если здесь таймаут — проблема **сети/файрвола у хостера**, а не токена бота. Часто режут исходящий трафик в сторону Telegram; тогда имеет смысл вынести `api/together-join` на **Vercel** или другой хост с нормальным выходом в интернет.
2. Если **IPv4** отвечает, а **IPv6** «висит», заставьте Node сначала пробовать IPv4. В **`/etc/systemd/system/together-api.service`** в секции `[Service]` добавьте строку:
   ```ini
   Environment=NODE_OPTIONS=--dns-result-order=ipv4first
   ```
   Затем: `sudo systemctl daemon-reload && sudo systemctl restart together-api`.

## Альтернативы Vercel

Любой свой сервер с HTTPS: метод **POST**, путь **`/api/together-join`** (или свой, но тогда поменяйте путь в nginx и в `server.js`), тело JSON как с лендинга (`firstName`, `lastName`, `phone`, `telegram`, `calendlySlot`, опционально `source`), дальше тот же вызов `https://api.telegram.org/bot<TOKEN>/sendMessage`.
