# Telegram Bot Backend

## Новая архитектура (JSON-модель шага)
Шаги воронки теперь хранятся в формате JSON в единой таблице `FunnelStep`.
Отдельных таблиц для кнопок и сообщений больше нет, вся логика шага, контент и задержки лежат в `FunnelStep.config` с Pydantic валидацией. 

## Запуск
1. `docker compose up -d postgres redis`
2. Применение миграций схемы: `alembic upgrade head`
3. Миграция данных (если были старые таблицы): `python scripts/migrate_to_json_config.py`
4. Стартовое наполнение БД воронками: `python -m app.db.seed`

## Структура
- `app/db/models.py`: SQLAlchemy модели
- `app/schemas/step_config.py`: Pydantic схема шага
- `app/config.py`: Настройки проекта (pydantic-settings)
- `alembic/`: Миграции базы данных
