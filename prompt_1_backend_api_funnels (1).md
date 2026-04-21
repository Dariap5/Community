# Промпт 1 — Бэкенд API для управления воронками и шагами

## Роль

Ты senior Python backend-разработчик. Специализация — FastAPI, SQLAlchemy 2 async, чистые REST API. Пишешь код без лишних слоёв абстракции, используешь type hints и Pydantic для валидации. Каждый эндпоинт имеет понятный контракт: что принимает, что возвращает, какие ошибки выдаёт.

## Контекст проекта

Telegram-бот для продажи цифровых продуктов. Промпт 0 уже выполнен — в проекте есть:

- БД PostgreSQL с 10 таблицами, управляемая через Alembic
- Модели в `app/db/models.py` (Funnel, FunnelStep, Product, Track, User, UserTag, UserFunnelState, Purchase, ScheduledTask, BotSetting)
- Pydantic-схема `app/schemas/step_config.py` для валидации поля `FunnelStep.config` (JSONB)
- Сессия БД настроена в `app/db/session.py`
- Конфиг в `app/config.py`
- Работающий FastAPI-скелет в `app/api/` (проверь точное расположение main.py через `find app/api -name "main.py"`)

Старый код админ-API существует в `app/api/routes/admin.py` — его нужно **частично** переиспользовать, частично переписать. Подробности ниже.

## Цель этого промпта

Создать чистый, полный, типизированный REST API для управления воронками и шагами. Этот API будет использоваться админ-панелью (Промпты 3 и 4) и частично движком бота (Промпт 2).

## Архитектурные принципы

### 1. Один шаг = один атомарный объект

Шаг читается и обновляется **целиком**. Нет отдельных эндпоинтов для сообщений внутри шага или кнопок. Есть:
- `GET /api/funnels/{funnel_id}/steps/{step_id}` — возвращает весь шаг, включая config
- `PUT /api/funnels/{funnel_id}/steps/{step_id}` — перезаписывает весь шаг

Это главное отличие от старой модели. Больше НЕТ:
- `POST /steps/{id}/messages`
- `PATCH /messages/{id}`
- `POST /steps/{id}/buttons`
- `PATCH /buttons/{id}`

Если в текущем `admin.py` такие эндпоинты есть — **удалить полностью**.

### 2. Валидация через Pydantic на всех входах

Каждый POST/PUT принимает Pydantic-модель. При попытке записать невалидный JSON в `config` — 422 Unprocessable Entity с детальной ошибкой от Pydantic. Никаких сырых dict в теле запросов.

### 3. Консистентные ошибки

Единый формат ошибки:
```json
{"error": {"code": "string_code", "message": "Human readable", "details": {}}}
```

Типы ошибок: `not_found`, `validation_error`, `conflict` (дубликат ключа), `bad_request`.

### 4. Read-модели отдельно от write-моделей

Для GET возвращается расширенная модель с вычисляемыми полями (например, `users_count` — сколько пользователей в шаге). Для PUT — только изменяемые поля.

### 5. Авторизация

Все эндпоинты под `/api/funnels/*` и `/api/steps/*` требуют аутентификации админа. Используй существующий механизм сессии из `admin.py`. Если его нет — создай простую зависимость `Depends(require_admin)`, которая проверяет cookie-сессию.

## Конкретные задачи

### Задача 1 — Ревизия существующего admin.py

Перед началом прочитай `app/api/routes/admin.py` и составь список:
- Какие эндпоинты там есть
- Какие из них относятся к funnels/steps (их переделать или удалить)
- Какие относятся к другим сущностям (products, users, settings) — их НЕ ТРОГАТЬ, они будут переделаны в следующих промптах

Выведи этот список перед началом работы, чтобы я понимала, что ты нашёл.

### Задача 2 — Pydantic-схемы API

Создай файл `app/schemas/api.py` со всеми моделями запросов и ответов.

```python
# app/schemas/api.py

from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.step_config import StepConfig

# ===== Воронки =====

class FunnelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    entry_key: Optional[str] = Field(default=None, max_length=120, pattern=r"^[a-z0-9_]+$")
    cross_entry_behavior: Literal["allow", "deny"] = "allow"
    notes: Optional[str] = None

class FunnelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    entry_key: Optional[str] = Field(default=None, max_length=120, pattern=r"^[a-z0-9_]+$")
    is_active: Optional[bool] = None
    is_archived: Optional[bool] = None
    cross_entry_behavior: Optional[Literal["allow", "deny"]] = None
    notes: Optional[str] = None

class FunnelStepSummary(BaseModel):
    """Краткая информация о шаге для списка внутри воронки"""
    id: UUID
    order: int
    name: str
    step_key: str
    is_active: bool
    messages_count: int  # вычисляется из config.blocks
    buttons_count: int  # вычисляется из config.blocks
    delay_before_hours: float  # вычисляется из config.delay_before для отображения

class FunnelRead(BaseModel):
    id: UUID
    name: str
    entry_key: Optional[str]
    is_active: bool
    is_archived: bool
    cross_entry_behavior: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    steps_count: int
    active_users_count: int  # пользователей со статусом active в этой воронке
    steps: List[FunnelStepSummary] = []  # опционально, только в detail-endpoint

    model_config = {"from_attributes": True}

class FunnelListItem(BaseModel):
    id: UUID
    name: str
    entry_key: Optional[str]
    is_active: bool
    is_archived: bool
    steps_count: int
    active_users_count: int

    model_config = {"from_attributes": True}

# ===== Шаги =====

class StepCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    step_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    order: Optional[int] = None  # если None — добавляется в конец
    is_active: bool = True
    config: StepConfig = StepConfig()

class StepUpdate(BaseModel):
    """Полная замена шага. Используется как PUT."""
    name: str = Field(min_length=1, max_length=255)
    step_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    is_active: bool
    config: StepConfig

class StepReorder(BaseModel):
    """Перестановка шагов в воронке"""
    step_ids_in_order: List[UUID]

class StepRead(BaseModel):
    id: UUID
    funnel_id: UUID
    order: int
    name: str
    step_key: str
    is_active: bool
    config: StepConfig
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# ===== Ошибки =====

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None

class ErrorResponse(BaseModel):
    error: ErrorDetail
```

### Задача 3 — Роутер воронок

Создай `app/api/routes/funnels.py`:

```python
# app/api/routes/funnels.py

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from app.schemas.api import (
    FunnelCreate, FunnelUpdate, FunnelRead, FunnelListItem,
    StepCreate, StepUpdate, StepReorder, StepRead,
    ErrorResponse,
)
# ... импорт зависимостей БД и аутентификации

router = APIRouter(prefix="/api/funnels", tags=["funnels"])

@router.get("", response_model=list[FunnelListItem])
async def list_funnels(
    include_archived: bool = False,
    # db: AsyncSession = Depends(get_db), admin: Admin = Depends(require_admin)
):
    """Список всех воронок. По умолчанию без архивных."""
    ...

@router.post("", response_model=FunnelRead, status_code=201)
async def create_funnel(data: FunnelCreate, ...):
    """Создать воронку. entry_key должен быть уникален."""
    ...

@router.get("/{funnel_id}", response_model=FunnelRead)
async def get_funnel(funnel_id: UUID, ...):
    """Детальная информация о воронке со списком шагов."""
    ...

@router.patch("/{funnel_id}", response_model=FunnelRead)
async def update_funnel(funnel_id: UUID, data: FunnelUpdate, ...):
    """Обновить воронку. Частичное обновление."""
    ...

@router.delete("/{funnel_id}", status_code=204)
async def archive_funnel(funnel_id: UUID, ...):
    """Архивировать воронку (soft delete). is_archived=true, is_active=false."""
    ...

@router.post("/{funnel_id}/restore", response_model=FunnelRead)
async def restore_funnel(funnel_id: UUID, ...):
    """Восстановить из архива."""
    ...

@router.post("/{funnel_id}/duplicate", response_model=FunnelRead, status_code=201)
async def duplicate_funnel(funnel_id: UUID, ...):
    """Создать копию воронки со всеми шагами. 
    Новое имя: '{old_name} (копия)'. 
    Новый entry_key: None (чтобы не было конфликта).
    """
    ...

# ===== Шаги внутри воронки =====

@router.get("/{funnel_id}/steps", response_model=list[StepRead])
async def list_steps(funnel_id: UUID, ...):
    """Все шаги воронки в порядке order."""
    ...

@router.post("/{funnel_id}/steps", response_model=StepRead, status_code=201)
async def create_step(funnel_id: UUID, data: StepCreate, ...):
    """Создать шаг. Если order не указан — в конец."""
    ...

@router.get("/{funnel_id}/steps/{step_id}", response_model=StepRead)
async def get_step(funnel_id: UUID, step_id: UUID, ...):
    """Один шаг с полным config."""
    ...

@router.put("/{funnel_id}/steps/{step_id}", response_model=StepRead)
async def update_step(funnel_id: UUID, step_id: UUID, data: StepUpdate, ...):
    """Полная замена шага. Валидация через Pydantic (StepConfig)."""
    ...

@router.delete("/{funnel_id}/steps/{step_id}", status_code=204)
async def delete_step(funnel_id: UUID, step_id: UUID, ...):
    """Удалить шаг. 
    Проверить: есть ли активные пользователи на этом шаге? 
    Если да — вернуть 409 conflict с сообщением.
    """
    ...

@router.post("/{funnel_id}/steps/{step_id}/duplicate", response_model=StepRead, status_code=201)
async def duplicate_step(funnel_id: UUID, step_id: UUID, ...):
    """Скопировать шаг сразу после исходного.
    Новое имя: '{old_name} (копия)'.
    Новый step_key: '{old_key}_copy_N', где N — найденный свободный номер.
    """
    ...

@router.post("/{funnel_id}/steps/reorder", response_model=list[StepRead])
async def reorder_steps(funnel_id: UUID, data: StepReorder, ...):
    """Массовая перестановка шагов. 
    Принимает список UUID в новом порядке.
    Обновляет order у всех.
    """
    ...
```

### Задача 4 — Вспомогательные функции в services

Создай `app/services/funnels.py` с бизнес-логикой, чтобы роутер был тонким:

```python
# app/services/funnels.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from app.db.models import Funnel, FunnelStep, UserFunnelState, FunnelStatus
from app.schemas.step_config import StepConfig

async def get_funnel_with_stats(db: AsyncSession, funnel_id: UUID) -> dict:
    """Воронка + подсчёты: steps_count, active_users_count."""
    ...

async def compute_step_summary(step: FunnelStep) -> dict:
    """Из config вычисляет messages_count, buttons_count, delay_before_hours."""
    config = StepConfig(**step.config)
    messages_count = sum(1 for b in config.blocks if b.type != "buttons")
    buttons_count = sum(len(b.buttons) for b in config.blocks if b.type == "buttons")
    
    delay = config.delay_before
    hours_map = {"seconds": 1/3600, "minutes": 1/60, "hours": 1, "days": 24}
    delay_hours = delay.value * hours_map[delay.unit]
    
    return {
        "messages_count": messages_count,
        "buttons_count": buttons_count,
        "delay_before_hours": delay_hours,
    }

async def get_next_step_order(db: AsyncSession, funnel_id: UUID) -> int:
    """Следующий свободный order внутри воронки."""
    ...

async def ensure_unique_step_key(db: AsyncSession, funnel_id: UUID, step_key: str, exclude_id: UUID | None = None) -> bool:
    """Проверка уникальности step_key внутри воронки."""
    ...

async def has_active_users_on_step(db: AsyncSession, step_id: UUID) -> bool:
    """Есть ли пользователи со статусом active на этом шаге?"""
    ...

async def duplicate_funnel_with_steps(db: AsyncSession, funnel_id: UUID) -> Funnel:
    """Создать копию воронки со всеми шагами."""
    ...

async def duplicate_step_in_funnel(db: AsyncSession, funnel_id: UUID, step_id: UUID) -> FunnelStep:
    """Создать копию шага сразу после исходного. 
    Сдвинуть order у всех последующих шагов на +1.
    """
    ...

async def reorder_funnel_steps(db: AsyncSession, funnel_id: UUID, ordered_ids: list[UUID]) -> list[FunnelStep]:
    """Установить новый порядок шагов.
    Проверка: все ID принадлежат этой воронке, список не содержит дубликатов, 
    количество совпадает с текущим.
    """
    ...
```

### Задача 5 — Обработчики ошибок

В `app/api/main.py` (или где у тебя корневое приложение FastAPI) добавь глобальные обработчики:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

app = FastAPI()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": "Invalid request data", "details": exc.errors()}}
    )

@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    # Например, дубликат entry_key или step_key
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "conflict", "message": "Resource already exists", "details": {"error": str(exc.orig)}}}
    )
```

В роутере при not_found бросай `HTTPException(404, detail={"code": "not_found", "message": "..."})`.

### Задача 6 — Регистрация роутера

В корневом приложении FastAPI зарегистрируй роутер:

```python
from app.api.routes.funnels import router as funnels_router
app.include_router(funnels_router)
```

### Задача 7 — Простые интеграционные тесты

Создай `tests/test_funnels_api.py` с минимальным набором тестов:

```python
# tests/test_funnels_api.py

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_and_get_funnel(client: AsyncClient):
    # создать → получить → проверить поля
    ...

@pytest.mark.asyncio
async def test_create_funnel_duplicate_entry_key_returns_409():
    ...

@pytest.mark.asyncio
async def test_create_step_with_invalid_config_returns_422():
    # Передать config с невалидным button action type
    ...

@pytest.mark.asyncio
async def test_update_step_preserves_config_integrity():
    # Обновить шаг, проверить что config валиден и сохранился
    ...

@pytest.mark.asyncio
async def test_delete_step_with_active_users_returns_409():
    ...

@pytest.mark.asyncio
async def test_reorder_steps():
    ...

@pytest.mark.asyncio
async def test_duplicate_funnel_creates_all_steps():
    ...
```

Фикстуры (`client`, `db_session`, пересоздание БД на тест) — в `tests/conftest.py`. Если нет pytest-asyncio и httpx — добавь в зависимости проекта.

## Файлы, которые нужно создать или изменить

```
Создать:
- app/schemas/api.py
- app/api/routes/funnels.py
- app/services/funnels.py
- app/services/__init__.py (если нет)
- tests/test_funnels_api.py
- tests/conftest.py (если нет)

Изменить:
- app/api/main.py (или app/api/app.py) — добавить обработчики ошибок и регистрацию роутера
- app/api/routes/admin.py — УДАЛИТЬ старые эндпоинты для funnels/steps/messages/buttons. Не трогать эндпоинты products/users/settings.

Не трогать в этом промпте:
- app/funnels/engine.py (Промпт 2)
- app/bot/ (Промпты 2, 9)
- admin UI в app/static/ и templates/ (Промпт 3)
```

## Acceptance criteria

1. `uvicorn app.api.main:app --reload` запускается без ошибок
2. `GET /api/funnels` возвращает список из 4 воронок, созданных в seed
3. `POST /api/funnels` создаёт воронку, возвращает 201 и FunnelRead
4. `POST /api/funnels` с существующим entry_key возвращает 409 с кодом `conflict`
5. `GET /api/funnels/{id}` возвращает детали со списком шагов. `steps_count` и `active_users_count` корректные
6. `PUT /api/funnels/{id}/steps/{step_id}` с валидным StepConfig обновляет шаг
7. `PUT /api/funnels/{id}/steps/{step_id}` с невалидным config (например, `buttons.action.type: "unknown"`) возвращает 422 с деталями ошибки
8. `POST /api/funnels/{id}/steps/reorder` меняет порядок шагов
9. `POST /api/funnels/{id}/duplicate` создаёт копию со всеми шагами
10. `DELETE /api/funnels/{id}/steps/{step_id}` с активными пользователями на этом шаге возвращает 409
11. Все тесты в `tests/test_funnels_api.py` проходят
12. Swagger UI по адресу `/docs` показывает все эндпоинты с моделями

## Как проверить результат

После завершения работы выполни последовательность и покажи мне реальный вывод каждой команды:

```bash
# 1. Запуск сервера
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 &
sleep 3

# 2. Список воронок
curl -s http://localhost:8000/api/funnels | python -m json.tool

# 3. Создание воронки с дубликатом entry_key
curl -s -X POST http://localhost:8000/api/funnels \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "entry_key": "guide"}' | python -m json.tool
# Должно вернуть 409

# 4. Получение детали воронки (возьми ID из пункта 2)
FUNNEL_ID=$(curl -s http://localhost:8000/api/funnels | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
curl -s http://localhost:8000/api/funnels/$FUNNEL_ID | python -m json.tool

# 5. Тесты
pytest tests/test_funnels_api.py -v
```

Если где-то упало — не иди дальше, покажи ошибку и исправь.

## Важные замечания

- Поле `FunnelStep.config` в БД — это `dict`, а не Pydantic-модель. При записи делай `config_model.model_dump(mode="json")`. При чтении — `StepConfig(**step.config)`.
- При создании копии шага через `duplicate_step_in_funnel` все UUID внутри config (в blocks, buttons) должны быть **перегенерированы**, иначе получишь дубликаты ID в разных шагах.
- `entry_key` и `step_key` — нижний регистр + цифры + подчёркивания, никаких пробелов. Валидация через регулярку в Pydantic.
- При reorder не делай N отдельных UPDATE, используй bulk update или транзакцию.
- Не забудь про индексы и EXPLAIN — для `active_users_count` может понадобиться подзапрос или отдельный JOIN, не делай N+1.
- Не используй deprecated-методы SQLAlchemy 2 (`query()`, `session.execute(Model.select())`). Только `select()` из `sqlalchemy`.
- Используй `from __future__ import annotations` в начале каждого файла, чтобы type hints работали без импорт-проблем.
- Все роуты должны требовать авторизацию админа. Если `Depends(require_admin)` ещё не реализован — реализуй простейшую cookie-сессию или временно HTTP Basic.

Приоритет: правильность контрактов API и валидация. Лучше меньше эндпоинтов, но все работают чисто, чем много с багами.
