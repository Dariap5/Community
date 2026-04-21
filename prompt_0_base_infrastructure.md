# Промпт 0 — Миграция на JSON-модель шага и базовая инфраструктура

## Роль

Ты senior Python backend-разработчик с опытом работы с Telegram-ботами на aiogram 3, FastAPI, SQLAlchemy 2 async и PostgreSQL. Ты делаешь архитектурный рефакторинг существующего проекта, сохраняя работающие части и переделывая фундамент. Код пишешь чисто, с type hints, docstrings на ключевых функциях, без лишних слоёв абстракции.

## Контекст проекта

Существует проект Telegram-бота в репозитории `telegram-bot-backend`. Стек:
- Python 3.11+
- aiogram 3.x для бота
- PostgreSQL + SQLAlchemy 2 (async) для хранения данных
- Celery + Redis для отложенных задач
- FastAPI для админ-панели и webhook оплаты
- Jinja2 + TailwindCSS + vanilla JS для UI админки

Проект бота для продажи цифровых продуктов через настраиваемые воронки. В существующей реализации шаг воронки хранится в трёх таблицах: `FunnelStep`, `StepMessage`, `StepButton`. Это создаёт проблемы:
- Тест-отправка сообщения в админке не соответствует боевой отправке, потому что они читают данные разными путями
- UI-редактор работает как набор CRUD-операций по разным таблицам, что делает его фрагментированным
- Preview не привязан к реальному шагу
- Добавление нового типа контента требует миграций

## Цель этого промпта

Переделать модель хранения шага: вместо трёх таблиц — одна таблица `FunnelStep` с полем `config` типа JSONB, в котором лежит весь контент шага и его логика. Это фундаментальное изменение, от которого зависят все последующие промпты.

Помимо модели, нужно настроить или проверить базовую инфраструктуру: структуру проекта, систему миграций, общие утилиты, конфиги.

## Конкретные задачи

### 1. Ревизия существующего кода

Перед началом работы проверь состояние следующих файлов в проекте:

```
app/db/models.py
app/db/session.py
app/funnels/engine.py
app/api/routes/admin.py
app/bot/main.py
app/tasks/celery_app.py
app/db/seed.py
```

Если чего-то нет — создай. Если есть — пойми, что делает, и аккуратно встрой изменения.

### 2. Новая модель FunnelStep

Переделай модель `FunnelStep` в `app/db/models.py`. Старую схему удали полностью (таблицы `step_messages` и `step_buttons` больше не нужны).

Новая схема:

```python
class FunnelStep(Base):
    __tablename__ = "funnel_steps"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    funnel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funnels.id", ondelete="CASCADE"))
    order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    step_key: Mapped[str] = mapped_column(String(100))  # техническое имя для переходов
    is_active: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict] = mapped_column(JSONB)  # см. схему ниже
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    
    funnel: Mapped["Funnel"] = relationship(back_populates="steps")
    
    __table_args__ = (
        UniqueConstraint("funnel_id", "step_key", name="uq_funnel_step_key"),
        Index("ix_funnel_steps_funnel_order", "funnel_id", "order"),
    )
```

### 3. Pydantic-схема для config

Создай файл `app/schemas/step_config.py` с Pydantic-моделями для валидации содержимого `config`. Это критически важно, потому что JSONB без валидации превращается в помойку.

Структура:

```python
# app/schemas/step_config.py

from typing import Literal, Optional, List, Union
from pydantic import BaseModel, Field, field_validator
from uuid import UUID, uuid4

class Delay(BaseModel):
    value: int = Field(ge=0)
    unit: Literal["seconds", "minutes", "hours", "days"]

class TriggerCondition(BaseModel):
    type: Literal["always", "has_tags", "not_has_tags"] = "always"
    tags: List[str] = []

class VisibilityCondition(BaseModel):
    has_tags: List[str] = []
    not_has_tags: List[str] = []

# Типы действий кнопок — ЗАКРЫТЫЙ список
class ButtonActionUrl(BaseModel):
    type: Literal["url"]
    value: str  # URL

class ButtonActionPayProduct(BaseModel):
    type: Literal["pay_product"]
    value: str  # product_id (UUID as string)

class ButtonActionGotoStep(BaseModel):
    type: Literal["goto_step"]
    value: str  # step_key целевого шага

class ButtonActionAddTag(BaseModel):
    type: Literal["add_tag"]
    value: str  # название тега

class ButtonActionOpenTrack(BaseModel):
    type: Literal["open_track"]
    value: str  # track_id

class ButtonActionSignal(BaseModel):
    type: Literal["signal"]
    value: str  # предопределённый callback (например "support_question")

ButtonAction = Union[
    ButtonActionUrl,
    ButtonActionPayProduct,
    ButtonActionGotoStep,
    ButtonActionAddTag,
    ButtonActionOpenTrack,
    ButtonActionSignal,
]

class Button(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    text: str = Field(min_length=1, max_length=64)  # Telegram limit
    action: ButtonAction
    visible_if: VisibilityCondition = VisibilityCondition()

# Типы контентных сообщений
class MessageContent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: Literal["text", "photo", "document", "video", "video_note", "voice"]
    content_text: Optional[str] = None  # для text — основной текст, для медиа — caption
    file_id: Optional[str] = None
    parse_mode: Literal["HTML", "Markdown"] = "HTML"
    delay_after: int = Field(ge=0, default=0)  # секунды

class ButtonGroup(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: Literal["buttons"]
    buttons: List[Button] = []

Block = Union[MessageContent, ButtonGroup]

class AfterStep(BaseModel):
    add_tags: List[str] = []
    next_step: str = "auto"  # "auto" | step_key | "end"
    dozhim_if_no_click_hours: Optional[int] = None

class StepConfig(BaseModel):
    delay_before: Delay = Delay(value=0, unit="seconds")
    trigger_condition: TriggerCondition = TriggerCondition()
    wait_for_payment: bool = False
    linked_product_id: Optional[UUID] = None
    blocks: List[Block] = []
    after_step: AfterStep = AfterStep()

    @field_validator("blocks")
    @classmethod
    def validate_blocks_order(cls, v):
        # Блок кнопок должен быть последним в списке (Telegram показывает 
        # кнопки только под последним сообщением)
        # Это soft-warning — не запрещаем, но логируем
        return v
```

### 4. Модели остальных сущностей

В `app/db/models.py` помимо `FunnelStep` должны быть модели согласно финальной спецификации (раздел 6 спецификации MVP):

- `Funnel` — с полями `id`, `name`, `entry_key`, `is_active`, `is_archived`, `cross_entry_behavior` (enum), `notes`, `created_at`, `updated_at`
- `Product` — `id`, `name`, `price`, `description`, `photo_file_id`, `is_active`, `created_at`, `updated_at`
- `Track` — `id`, `name`, `is_active`, `config` (JSONB — такая же структура как у шага, но без after_step), `created_at`, `updated_at`
- `User` — `telegram_id` (bigint, PK), `username`, `first_name`, `last_name`, `source_deeplink`, `selected_track_id` (nullable FK → tracks), `created_at`, `last_activity_at`
- `UserFunnelState` — `id`, `user_id`, `funnel_id`, `current_step_id`, `status` (enum: active/paused/completed), `started_at`, `updated_at`
- `UserTag` — `user_id`, `tag`, `assigned_at`, PK (user_id, tag)
- `Purchase` — `id`, `user_id`, `product_id`, `amount`, `status` (enum), `payment_provider_id`, `created_at`, `paid_at`
- `ScheduledTask` — `id`, `user_id`, `task_type` (enum), `payload` (JSONB), `execute_at`, `status` (enum), `created_at`
- `BotSetting` — `key` (PK), `value_text`, `is_encrypted` (bool), `updated_at`

Для enum полей используй Python Enum + SQLAlchemy `Enum`, либо String с валидацией на уровне приложения — второе проще для миграций, выбирай его.

### 5. Миграция данных

Создай скрипт `scripts/migrate_to_json_config.py`, который:

1. Читает все существующие `FunnelStep` вместе с их `StepMessage` и `StepButton` (если старые таблицы ещё существуют)
2. Собирает из них JSON согласно новой схеме `StepConfig`
3. Пишет результат в поле `config` новой таблицы
4. Валидирует результат через Pydantic
5. Логирует результат (сколько шагов смигрировано, какие ошибки)

Если старые таблицы уже удалены или проект только стартует — скрипт просто выводит сообщение "Миграция не требуется" и завершается успехом.

Скрипт должен быть идемпотентным — можно запустить повторно без вреда.

### 6. Alembic-миграции

Настрой Alembic для управления миграциями. Структура:

```
alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 001_initial_schema.py
```

Первая миграция создаёт все таблицы новой схемы. Если старые таблицы `step_messages` и `step_buttons` существуют — вторая миграция их удаляет (но только после выполнения скрипта миграции данных).

### 7. Настройки проекта

В `app/config.py` (создай если нет) — загрузка настроек через pydantic-settings:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # База
    database_url: str
    
    # Redis
    redis_url: str
    
    # Telegram
    bot_token: str
    
    # Admin
    admin_username: str
    admin_password_hash: str
    admin_session_secret: str
    
    # Шифрование настроек
    settings_crypto_key: str
    
    # Платёжка
    payment_provider: Literal["robokassa", "yookassa"] = "robokassa"
    robokassa_login: Optional[str] = None
    robokassa_password1: Optional[str] = None
    robokassa_password2: Optional[str] = None
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### 8. Утилита шифрования

Создай `app/utils/crypto.py` для шифрования чувствительных настроек (токены, API-ключи):

```python
from cryptography.fernet import Fernet
from app.config import settings

_fernet = Fernet(settings.settings_crypto_key.encode())

def encrypt(value: str) -> str:
    return "enc:" + _fernet.encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    if not value.startswith("enc:"):
        return value
    return _fernet.decrypt(value[4:].encode()).decode()
```

### 9. Seed-скрипт

Перепиши `app/db/seed.py` так, чтобы он создавал стартовые воронки (Гайд, Продукт, Комьюнити, Дожим) согласно сценариям из финальной спецификации, используя новую JSON-схему. Этот скрипт нужен для первого запуска и для тестирования.

Каждая воронка должна быть рабочим примером для пользователя админки — открыл и сразу понятно, как устроены шаги.

### 10. README.md — обновление

Обнови README проекта. Опиши:
- Новую архитектуру (JSON-модель шага)
- Как запускать проект с нуля
- Как применять миграции (включая миграцию данных)
- Как запускать seed для первого наполнения
- Структуру папок

## Файлы, которые нужно создать или изменить

```
Создать:
- app/schemas/step_config.py
- app/schemas/__init__.py (если нет)
- app/utils/crypto.py
- app/utils/__init__.py (если нет)
- app/config.py (если нет)
- scripts/migrate_to_json_config.py
- alembic/env.py (если нет)
- alembic/versions/001_initial_schema.py
- alembic.ini (если нет)

Изменить или переписать:
- app/db/models.py (полная переработка модели FunnelStep, удаление StepMessage и StepButton)
- app/db/seed.py (под новую схему)
- README.md

Не трогать в этом промпте (будут переделаны в следующих):
- app/funnels/engine.py (переделается в Промпте 2)
- app/api/routes/admin.py (переделается в Промптах 1, 3-10)
- app/bot/ (переделается в Промптах 2, 9, 11)
```

## Acceptance criteria

1. После применения миграций в БД существуют все необходимые таблицы с правильными колонками, индексами и foreign keys
2. Старые таблицы `step_messages` и `step_buttons` удалены (либо не существуют с самого начала)
3. Pydantic-схема `StepConfig` валидирует пример из спецификации и отклоняет невалидные данные (проверь тестовым примером)
4. Скрипт миграции `scripts/migrate_to_json_config.py` выполняется без ошибок в двух сценариях: когда есть старые данные и когда их нет
5. Seed-скрипт создаёт четыре воронки со всеми шагами согласно сценарию
6. После запуска seed в таблице `funnel_steps` все записи имеют валидный JSON в поле `config`, прошедший валидацию через Pydantic
7. README актуален и описывает новую архитектуру
8. Проект запускается без ошибок: `docker compose up` поднимает все сервисы
9. Все существующие тесты (если есть) проходят или явно помечены как устаревшие

## Важные замечания

- НЕ создавай отдельные таблицы для `messages` и `buttons`. Всё живёт в `config`.
- НЕ добавляй в этот промпт никакой UI, API-эндпоинты или логику бота. Это инфраструктурный промпт.
- Блок кнопок должен быть представлен как один тип блока в массиве `blocks`, а не как отдельное поле `buttons` на уровне шага. Это даст возможность в будущем иметь несколько групп кнопок или кнопки в середине шага, если Telegram это поддержит.
- Все UUID поля в Pydantic сериализуются как строки при передаче в JSON.
- Используй `JSONB`, не `JSON` — `JSONB` индексируется и быстрее.
- Все миграции должны быть реверсируемыми (downgrade функция).

## Как проверить результат

Запусти следующую последовательность команд в чистом окружении:

```bash
docker compose up -d postgres redis
alembic upgrade head
python scripts/migrate_to_json_config.py
python -m app.db.seed
```

После этого подключись к БД и убедись:
- Таблица `funnel_steps` содержит записи с JSON в поле `config`
- Все JSON-объекты валидны и соответствуют схеме `StepConfig`
- Воронки Гайд, Продукт, Комьюнити, Дожим присутствуют

Приоритет: корректность схемы данных важнее всего остального в этом промпте.
