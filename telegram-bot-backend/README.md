# Telegram Sales Bot Architecture (Starter)

Проектный каркас для Telegram-бота с продажей цифровых продуктов, воронками и webhook-платежами.

## Стек
- Python 3.11+
- aiogram 3.x
- PostgreSQL + SQLAlchemy 2 (async)
- Celery + Redis
- FastAPI (webhook и админ API)

## Структура
- `app/bot` — Telegram-бот, команды, меню, `/start` + deeplink
- `app/db` — async SQLAlchemy, модели и сессии
- `app/funnels` — исполнение шагов и субсообщений
- `app/services` — бизнес-логика по пользователям/воронкам/покупкам/планировщику
- `app/tasks` — Celery app + polling очереди `scheduled_tasks`
- `app/api` — FastAPI эндпоинты, включая платежный webhook
- `app/payments` — верификация подписи webhook

## Таблицы (реализованы моделями)
- `users`
- `user_tags`
- `user_funnel_state`
- `funnels`
- `funnel_steps`
- `step_messages`
- `step_buttons`
- `products`
- `purchases`
- `community_tracks`
- `scheduled_tasks`

## Ключевая логика
1. Дедупликация `/start`:
   - Проверяем `user_funnel_state` со статусом `active`.
   - Если активная воронка есть, новую не запускаем и отправляем: `Вы уже в нашей программе 🙌`.
2. Отложенные задачи:
   - После запуска/перехода шага пишем задачу в `scheduled_tasks`.
   - `Celery Beat` вызывает polling каждые 30 секунд.
3. Субсообщения шага:
   - Для задержек `< 5 мин` используется `asyncio.sleep`.
   - Для длинных задержек создается запись в `scheduled_tasks`.
4. Оплата webhook:
   - FastAPI принимает POST.
   - Проверяем подпись.
   - Обновляем `purchases`.
   - Назначаем тег в `user_tags`.
   - Ставим задачу на следующий шаг воронки.

## Сценарии из Промпта 2
- Deeplink `start=guide` запускает воронку `guide` (Сценарий А).
- Deeplink `start=product` запускает воронку `product` (Сценарий Б).
- A1: выдача гайда и тег `получил_гайд`.
- A2: тишина 48 часов.
- A3: шаг создан как опциональный (`enabled=false` по умолчанию), включает переход в `product`.
- B1: карточка продукта + кнопка оплаты + тег `видел_продукт_1`.
- B2: шаг ожидания оплаты (`wait_for_payment=true`).
- webhook оплаты выставляет статус `purchases`, тег оплаты и запускает B3.
- B3: выдача материала; затем запускается `community` через 24 часа.
- В1 (community): кнопки `Вступить` / `Есть сомнения`.
- Если нет клика X часов (по умолчанию 3) — запуск `dozhim`.
- При клике `Есть сомнения` назначается тег `есть_сомнения` и также стартует `dozhim` по таймеру.
- D2: кнопка консультации скрывается для пользователей с тегом `есть_сомнения`.

## Административная панель (Промпт 3)
- Стек панели: FastAPI + Jinja2 + TailwindCSS.
- Вход: `/admin/login`, авторизация по `ADMIN_USERNAME` + `ADMIN_PASSWORD_HASH`.
- Сессии через cookie (`SessionMiddleware`).
- Основная панель: `/admin`.

### Разделы панели
- Funnels: список, toggle активна/выключена, копирование, архивирование, просмотр шагов и счетчики по шагам.
- Step Editor: редактирование субсообщений и кнопок шага, HTML preview, тест-отправка себе в Telegram.
- Products: CRUD, архивирование.
- Community Tracks: CRUD и редактор payload.
- Users: таблица с фильтрами, карточка пользователя, теги, ручное сообщение, экспорт CSV.
- Broadcasts: предпросмотр сегмента и отправка в очередь Celery (`broadcast_dispatch`) с ограничением 30 msg/sec.
- Analytics: воронка по шагам, клики кнопок, финансы по продуктам.
- Settings: deeplink-и, support chat id, calendly, оферта/privacy, платежные ключи, bot token.

### Шифрование настроек
- Поля `payment_*` и `bot_token` хранятся в `bot_settings.value_text` в зашифрованном виде (`enc:*`) при наличии `SETTINGS_CRYPTO_KEY`.
- Для генерации ключа используйте Fernet (см. `.env.example`).

### Важные UX моменты
- Деструктивные действия подтверждаются в UI.
- Панель адаптивна и работает на мобильных ширинах.
- Переключатель темы есть в шапке панели (опциональная темная тема).
- В интерфейсе есть подсказка о том, что уже отправленные Telegram-сообщения изменить нельзя.

## Быстрый старт
```bash
cd telegram-bot-backend
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
```

## Docker запуск (рекомендуется для полного стека)
В этом режиме БД и Redis поднимаются контейнерами, локально ничего ставить не нужно.

1. Подготовьте env для Docker:
```bash
cp .env.docker.example .env
```

2. Заполните обязательные поля в `.env`:
- `SALES_BOT_TOKEN`
- `ADMIN_PASSWORD_HASH`
- `ADMIN_SESSION_SECRET`
- `SETTINGS_CRYPTO_KEY`
- реквизиты Robokassa

3. Запуск всего backend-стека:
```bash
docker compose up --build -d
```

4. Проверка:
- API health: `http://localhost:8000/health`
- Admin panel: `http://localhost:8000/admin/login`

5. Остановка:
```bash
docker compose down
```

6. Остановка с удалением volumes (сброс БД/Redis):
```bash
docker compose down -v
```

Запуск бота:
```bash
python -m app.bot.main
```

Запуск API:
```bash
uvicorn app.api.main:app --reload --port 8000
```

Запуск Celery worker:
```bash
celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
```

Запуск Celery beat:
```bash
celery -A app.tasks.celery_app.celery_app beat --loglevel=INFO
```

Заполнить БД стартовыми сценариями A/Б/В/Д:
```bash
python -m app.db.seed
```

## Что добавить следующим шагом
- Alembic-миграции для PostgreSQL
- Полноценную платежную верификацию под выбранного провайдера (ЮKassa/Robokassa)
- Админ-панель (FastAPI + Jinja2 или React)
- Ретрай-политику и dead-letter обработку ошибок задач
- Юнит и интеграционные тесты
