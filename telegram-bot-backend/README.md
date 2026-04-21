# Telegram Bot Backend

## Новая архитектура (JSON-модель шага)
Шаги воронки теперь хранятся в формате JSON в единой таблице `FunnelStep`.
Отдельных таблиц для кнопок и сообщений больше нет, вся логика шага, контент и задержки лежат в `FunnelStep.config` с Pydantic валидацией. 

## Запуск
1. `bash scripts/deploy.sh`
2. Скрипт поднимает `db` и `redis`, ждёт PostgreSQL и Redis, применяет Alembic, прогоняет legacy-миграцию и seed, затем запускает `api`, `bot`, `worker` и `beat`.

## Структура
- `app/db/models.py`: SQLAlchemy модели
- `app/schemas/step_config.py`: Pydantic схема шага
- `app/config.py`: Настройки проекта (pydantic-settings)
- `alembic/`: Миграции базы данных
