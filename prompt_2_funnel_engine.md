# Промпт 2 — Движок выполнения шагов воронки (бот-сторона)

## Роль

Ты senior Python разработчик Telegram-ботов на aiogram 3 с опытом построения state-machine движков и систем отложенных задач. Пишешь надёжный production-код: с обработкой ошибок, идемпотентностью, ретраями. Знаешь особенности Telegram API (rate limits, parse_mode, file_id, различие между sendMessage/sendPhoto/sendVideoNote).

## Контекст проекта

Telegram-бот на базе aiogram 3 + PostgreSQL + Celery + Redis. Промпты 0 и 1 выполнены:

- Шаги воронки хранятся в `FunnelStep.config` как JSONB с Pydantic-валидацией (`app/schemas/step_config.py`)
- REST API для управления воронками работает на `/api/funnels`
- База данных содержит 4 seed-воронки (Гайд, Продукт 490, Комьюнити, Дожим)

Существующий код в проекте:
- `app/funnels/engine.py` — старый движок, работавший со старой трёхтабличной моделью. **Нужно полностью переписать** под новую JSON-модель
- `app/bot/main.py` — точка входа бота
- `app/bot/handlers/` — обработчики команд (посмотри, что там есть)
- `app/tasks/celery_app.py` — Celery-приложение
- `app/services/` — сервисы (уже есть `funnels.py` из Промпта 1)

## Цель этого промпта

Реализовать **движок выполнения шагов воронки** — код, который умеет:

1. Принимать решение "запустить воронку для пользователя"
2. Отправлять пользователю сообщения шага в правильном порядке с правильными задержками
3. Строить клавиатуру для шага из блока кнопок
4. Обрабатывать нажатия кнопок (все 6 типов действий)
5. Переходить к следующему шагу
6. Работать с отложенными задачами (Celery) для длинных задержек
7. Правильно вести себя при пересечении воронок (cross_entry_behavior)

## Архитектурные принципы

### 1. Engine как единая точка истины для отправки

Один и тот же код движка используется для:
- Боевой отправки пользователям
- Тест-отправки администратору ("отправить себе" из админки)
- Автоматических триггеров (по таймеру, по оплате)

Разница только во входных параметрах (кому, с какими условиями, фильтровать кнопки по тегам или нет).

### 2. Идемпотентность

Если один и тот же триггер сработал дважды (например, Celery повторил задачу) — пользователь не должен получить сообщения дважды. У каждого выполнения есть уникальный `execution_id`, который помечает прохождение шага.

### 3. Fail-safe отправка

Если одно из сообщений в шаге не отправилось (Telegram вернул ошибку) — движок логирует, но не обрушивает весь шаг. Пользователь получает следующие сообщения. Если критическая ошибка — помечает шаг как failed и не идёт к следующему.

### 4. Rate limiting

Telegram ограничивает: не более ~30 сообщений/сек, не более ~1 сообщения/сек одному пользователю. Движок соблюдает эти лимиты на уровне сервиса, чтобы бот не упёрся в 429 Too Many Requests.

### 5. Task queue для задержек

- Задержка < 60 секунд — `asyncio.sleep()` внутри задачи
- Задержка ≥ 60 секунд — создаётся `ScheduledTask` в БД с `execute_at`, Celery Beat её подхватывает и в нужный момент вызывает движок

## Конкретные задачи

### Задача 1 — Структура модуля

Создай файлы:

```
app/funnels/
  __init__.py
  engine.py              # главный класс FunnelEngine
  keyboard_builder.py    # построение InlineKeyboardMarkup из ButtonGroup
  message_sender.py      # отправка одного сообщения (text/photo/video_note/...)
  condition_checker.py   # проверка условий (trigger, visibility)
  cross_entry.py         # логика при пересечении воронок
  actions/
    __init__.py
    url.py               # обработка кнопки type=url
    pay_product.py       # обработка type=pay_product
    goto_step.py         # обработка type=goto_step
    add_tag.py           # обработка type=add_tag
    open_track.py        # обработка type=open_track
    signal.py            # обработка type=signal
```

### Задача 2 — Ядро: FunnelEngine

Файл `app/funnels/engine.py`:

```python
# app/funnels/engine.py

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4
from typing import Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Funnel, FunnelStep, User, UserFunnelState, FunnelStatus
from app.schemas.step_config import StepConfig
from app.funnels.message_sender import send_block
from app.funnels.keyboard_builder import build_keyboard_for_step
from app.funnels.condition_checker import (
    should_execute_step,
    get_user_tags,
)
from app.funnels.cross_entry import resolve_cross_entry

logger = logging.getLogger(__name__)

THRESHOLD_INLINE_DELAY_SECONDS = 60


@dataclass
class ExecutionContext:
    """Контекст выполнения шага для одного пользователя."""
    user: User
    funnel: Funnel
    step: FunnelStep
    execution_id: UUID
    is_test: bool = False  # Для тест-отправки из админки
    emulated_tags: Optional[list[str]] = None  # Для preview с эмуляцией


class FunnelEngine:
    """
    Главный оркестратор выполнения шагов воронки.
    
    Используется для:
    - Запуска воронки при /start с deeplink
    - Отправки текущего шага пользователю
    - Перехода к следующему шагу
    - Обработки нажатий кнопок
    """
    
    def __init__(self, bot: Bot, db: AsyncSession):
        self.bot = bot
        self.db = db
    
    async def start_funnel(
        self,
        user: User,
        funnel: Funnel,
    ) -> Optional[UserFunnelState]:
        """
        Запустить воронку для пользователя.
        
        Поведение:
        1. Проверить, есть ли уже активные воронки у пользователя
        2. Применить cross_entry_behavior новой воронки
        3. Если допущен запуск — создать UserFunnelState, запустить первый шаг
        4. Вернуть созданное состояние или None (если не запущено)
        """
        # Получить активные состояния пользователя
        # Через cross_entry.resolve_cross_entry понять, что делать
        # Создать или обновить состояния
        # Запустить первый шаг через execute_step_for_user
        ...
    
    async def execute_step_for_user(
        self,
        user: User,
        step: FunnelStep,
    ) -> None:
        """
        Выполнить один шаг для пользователя: отправить все сообщения и кнопки.
        
        Шаги:
        1. Валидировать step.config через Pydantic
        2. Проверить trigger_condition — если не выполнено, пропустить (перейти к next_step)
        3. Обработать delay_before:
           - если < 60 сек — asyncio.sleep
           - если >= 60 сек — создать ScheduledTask, выйти
        4. Пройти по config.blocks, отправить каждый (через send_block)
        5. Между блоками применить delay_after
        6. Обработать after_step:
           - add_tags
           - dozhim_if_no_click_hours — создать ScheduledTask
           - next_step — определить и запустить
        7. Обновить UserFunnelState.current_step_id
        """
        ...
    
    async def run_test_for_admin(
        self,
        admin_telegram_id: int,
        step: FunnelStep,
        emulated_tags: Optional[list[str]] = None,
    ) -> None:
        """
        Тест-отправка шага администратору.
        
        Отличия от боевого запуска:
        - delay_before игнорируется (всегда 0)
        - delay_after максимум 2 секунды (чтобы увидеть порядок)
        - trigger_condition игнорируется
        - wait_for_payment игнорируется
        - after_step игнорируется (не переходим к следующему шагу)
        - Кнопки фильтруются по emulated_tags (если указаны) или показываются все
        """
        ...
    
    async def run_full_funnel_test_for_admin(
        self,
        admin_telegram_id: int,
        funnel: Funnel,
    ) -> None:
        """
        Прогон всей воронки подряд для тестирования администратором.
        
        Отличия:
        - Все шаги выполняются по порядку (по FunnelStep.order)
        - Между шагами небольшая пауза (3 сек для читаемости)
        - delay_before/delay_after сокращены
        - Кнопки показываются все, но действия на них не выполняются (только отображение)
        """
        ...
    
    async def handle_button_click(
        self,
        user: User,
        step: FunnelStep,
        button_id: UUID,
        callback_data: str,  # Telegram callback data
    ) -> None:
        """
        Обработать нажатие кнопки inline-клавиатуры.
        
        1. Найти кнопку в step.config по button_id
        2. Определить action.type
        3. Вызвать соответствующий обработчик из app/funnels/actions/
        4. Если действие требует перехода — вызвать execute_step_for_user для следующего
        """
        ...
    
    async def continue_after_payment(
        self,
        user: User,
        funnel: Funnel,
    ) -> None:
        """
        Вызывается webhook оплаты.
        
        1. Найти текущий шаг с wait_for_payment=True
        2. Продолжить после этого шага — перейти на next_step
        """
        ...
    
    async def trigger_dozhim(
        self,
        user: User,
        step: FunnelStep,
    ) -> None:
        """
        Запустить дожим для пользователя, если он не нажал кнопку за dozhim_if_no_click_hours.
        
        1. Проверить, что пользователь действительно не нажал ни одну кнопку из этого шага
        2. Проверить, что текущий шаг пользователя = этот шаг (не продвинулся)
        3. Запустить воронку "Дожим" (или указанную в step.config)
        """
        ...
```

### Задача 3 — Отправка блоков: message_sender.py

```python
# app/funnels/message_sender.py

from __future__ import annotations

import logging
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from app.schemas.step_config import MessageContent

logger = logging.getLogger(__name__)


async def send_block(
    bot: Bot,
    chat_id: int,
    message: MessageContent,
    reply_markup=None,
    retry_count: int = 3,
) -> bool:
    """
    Отправить один контентный блок (MessageContent) в чат.
    
    - Выбор метода отправки по message.type
    - При TelegramRetryAfter — ждёт и повторяет
    - При другой TelegramBadRequest — логирует и возвращает False
    - При успехе — возвращает True
    """
    for attempt in range(retry_count):
        try:
            if message.type == "text":
                await bot.send_message(
                    chat_id=chat_id,
                    text=message.content_text or "",
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            elif message.type == "photo":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=message.file_id,
                    caption=message.content_text,
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            elif message.type == "document":
                await bot.send_document(
                    chat_id=chat_id,
                    document=message.file_id,
                    caption=message.content_text,
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            elif message.type == "video":
                await bot.send_video(
                    chat_id=chat_id,
                    video=message.file_id,
                    caption=message.content_text,
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            elif message.type == "video_note":
                # video_note НЕ поддерживает caption и parse_mode
                await bot.send_video_note(
                    chat_id=chat_id,
                    video_note=message.file_id,
                    reply_markup=reply_markup,
                )
            elif message.type == "voice":
                await bot.send_voice(
                    chat_id=chat_id,
                    voice=message.file_id,
                    caption=message.content_text,
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            return True
        except TelegramRetryAfter as e:
            logger.warning(f"Rate limited, sleeping {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except TelegramBadRequest as e:
            logger.error(f"Bad request sending to {chat_id}: {e}")
            return False
    return False
```

### Задача 4 — Построение клавиатуры

```python
# app/funnels/keyboard_builder.py

from __future__ import annotations

from typing import Optional
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.schemas.step_config import Button, ButtonGroup, StepConfig, VisibilityCondition


def check_visibility(condition: VisibilityCondition, user_tags: set[str]) -> bool:
    """Проверка, должна ли кнопка быть видимой при данных тегах."""
    if condition.has_tags and not all(t in user_tags for t in condition.has_tags):
        return False
    if condition.not_has_tags and any(t in user_tags for t in condition.not_has_tags):
        return False
    return True


def build_callback_data(button: Button, step_id: UUID) -> str:
    """
    Собрать строку callback_data для Telegram.
    
    Формат: 'btn:{step_id}:{button_id}'
    Telegram имеет лимит 64 байт на callback_data, это укладывается.
    """
    return f"btn:{step_id}:{button.id}"


def build_keyboard_for_step(
    config: StepConfig,
    step_id: UUID,
    user_tags: Optional[set[str]] = None,
    ignore_visibility: bool = False,
) -> Optional[InlineKeyboardMarkup]:
    """
    Построить inline-клавиатуру из первого ButtonGroup в step.config.
    
    Если нет ButtonGroup — возвращает None.
    Если есть, но после фильтрации по видимости не осталось кнопок — возвращает None.
    
    user_tags и ignore_visibility:
    - ignore_visibility=True — все кнопки (для тест-отправки без эмуляции)
    - user_tags + ignore_visibility=False — фильтровать по условиям (боевой режим)
    """
    # Найти первый ButtonGroup в blocks
    button_group = None
    for block in config.blocks:
        if isinstance(block, ButtonGroup):
            button_group = block
            break
    
    if not button_group or not button_group.buttons:
        return None
    
    # Построить клавиатуру
    user_tags = user_tags or set()
    rows = []
    
    for button in button_group.buttons:
        if not ignore_visibility and not check_visibility(button.visible_if, user_tags):
            continue
        
        # Тип кнопки зависит от action
        if button.action.type == "url":
            kb_button = InlineKeyboardButton(text=button.text, url=button.action.value)
        else:
            # Для всех остальных — callback
            kb_button = InlineKeyboardButton(
                text=button.text,
                callback_data=build_callback_data(button, step_id),
            )
        rows.append([kb_button])
    
    if not rows:
        return None
    
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

### Задача 5 — Проверка условий

```python
# app/funnels/condition_checker.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import User, UserTag
from app.schemas.step_config import TriggerCondition


async def get_user_tags(db: AsyncSession, user_id: int) -> set[str]:
    """Получить все теги пользователя как set."""
    result = await db.execute(
        select(UserTag.tag).where(UserTag.user_id == user_id)
    )
    return {row[0] for row in result}


def should_execute_step(
    trigger: TriggerCondition,
    user_tags: set[str],
) -> bool:
    """
    Проверить, должен ли шаг выполниться для пользователя с данными тегами.
    """
    if trigger.type == "always":
        return True
    if trigger.type == "has_tags":
        return all(t in user_tags for t in trigger.tags)
    if trigger.type == "not_has_tags":
        return not any(t in user_tags for t in trigger.tags)
    return True
```

### Задача 6 — Логика пересечения воронок

```python
# app/funnels/cross_entry.py

from __future__ import annotations

from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Funnel, FunnelCrossEntryBehavior, UserFunnelState, FunnelStatus


class CrossEntryResult(Enum):
    """Что делать при запуске воронки, если у пользователя уже есть активные воронки."""
    ALLOW = "allow"  # Запустить параллельно
    DENY = "deny"    # Не запускать


async def resolve_cross_entry(
    db: AsyncSession,
    user_id: int,
    new_funnel: Funnel,
) -> CrossEntryResult:
    """
    Определить, что делать при запуске новой воронки для пользователя.
    
    Логика:
    1. Найти все активные состояния пользователя (status='active')
    2. Если таких нет — ALLOW (свободный запуск)
    3. Если есть, и new_funnel.cross_entry_behavior:
       - 'allow' — ALLOW (запустить параллельно)
       - 'deny' — DENY (не запускать, пользователь уже в воронке)
    """
    result = await db.execute(
        select(UserFunnelState).where(
            UserFunnelState.user_id == user_id,
            UserFunnelState.status == FunnelStatus.active,
        )
    )
    active_states = result.scalars().all()
    
    if not active_states:
        return CrossEntryResult.ALLOW
    
    if new_funnel.cross_entry_behavior == FunnelCrossEntryBehavior.allow:
        return CrossEntryResult.ALLOW
    else:
        return CrossEntryResult.DENY
```

### Задача 7 — Обработчики действий кнопок

Шесть файлов в `app/funnels/actions/`, каждый обрабатывает свой тип действия. Вот примеры:

```python
# app/funnels/actions/add_tag.py

from app.db.models import User, UserTag
from app.schemas.step_config import ButtonActionAddTag


async def handle_add_tag(db, user: User, action: ButtonActionAddTag) -> None:
    """Добавить тег пользователю. Если уже есть — ничего не делать."""
    existing = await db.execute(
        select(UserTag).where(UserTag.user_id == user.telegram_id, UserTag.tag == action.value)
    )
    if existing.scalar_one_or_none():
        return
    db.add(UserTag(user_id=user.telegram_id, tag=action.value))
    await db.commit()
```

```python
# app/funnels/actions/pay_product.py

from app.db.models import Product, Purchase, PaymentStatus
from app.schemas.step_config import ButtonActionPayProduct
from app.payments.provider import create_payment_invoice


async def handle_pay_product(db, bot, user, action: ButtonActionPayProduct) -> None:
    """
    Создать инвойс для оплаты продукта.
    
    1. Найти продукт по ID
    2. Создать запись Purchase со статусом pending
    3. Получить URL оплаты у провайдера
    4. Отправить пользователю сообщение с кнопкой оплаты
       (или использовать Telegram Payments invoice)
    """
    ...
```

Аналогично для `goto_step`, `open_track`, `signal`, `url` (хотя url-кнопки обрабатываются Telegram самостоятельно и не вызывают callback).

### Задача 8 — Интеграция с Celery

В `app/tasks/celery_app.py` и `app/tasks/funnel_tasks.py`:

```python
# app/tasks/funnel_tasks.py

from celery import shared_task
from uuid import UUID


@shared_task(bind=True, max_retries=3)
def execute_step_task(self, user_id: int, step_id: str, execution_id: str):
    """
    Celery-задача для выполнения шага после задержки.
    
    Вызывается Celery Beat или напрямую при откладывании.
    """
    import asyncio
    from app.db.session import AsyncSessionLocal
    from app.bot.main import bot
    from app.funnels.engine import FunnelEngine
    from app.db.models import User, FunnelStep
    
    async def _run():
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            step = await db.get(FunnelStep, UUID(step_id))
            if not user or not step:
                return
            
            engine = FunnelEngine(bot=bot, db=db)
            await engine.execute_step_for_user(user, step)
    
    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task
def process_scheduled_tasks():
    """
    Celery Beat-задача: ищет ScheduledTask со status='pending' и execute_at <= now().
    Для каждой вызывает соответствующий обработчик и помечает как 'done' или 'failed'.
    """
    ...
```

В `app/tasks/celery_app.py` настрой Beat schedule:

```python
celery_app.conf.beat_schedule = {
    'process-scheduled-every-30-seconds': {
        'task': 'app.tasks.funnel_tasks.process_scheduled_tasks',
        'schedule': 30.0,
    },
}
```

### Задача 9 — Обновление /start обработчика

В `app/bot/handlers/start.py` (или где у тебя `/start`):

```python
from aiogram import Router, types
from aiogram.filters import CommandStart, CommandObject

router = Router()


@router.message(CommandStart(deep_link=True))
async def handle_start_with_deeplink(message: types.Message, command: CommandObject, ...):
    """
    /start с deeplink-параметром.
    
    1. Получить параметр из command.args
    2. Найти воронку с entry_key = параметр
    3. Если найдена — запустить через engine.start_funnel
    4. Если не найдена — отправить сообщение "воронка не найдена" + запустить дефолтную
    """
    deeplink = command.args
    # Создать/обновить пользователя с source_deeplink=deeplink
    # Найти воронку
    # Вызвать engine.start_funnel
    ...


@router.message(CommandStart())
async def handle_plain_start(message: types.Message, ...):
    """
    /start без параметра.
    
    1. Создать/обновить пользователя (source_deeplink=None)
    2. Запустить дефолтную воронку (из BotSetting 'default_funnel_id')
    """
    ...
```

### Задача 10 — Обработчик callback-кнопок

```python
# app/bot/handlers/callbacks.py

from aiogram import Router, types
from aiogram.filters import StateFilter

router = Router()


@router.callback_query(lambda c: c.data.startswith("btn:"))
async def handle_button_callback(callback: types.CallbackQuery, ...):
    """
    Обработать callback от inline-кнопки.
    
    1. Парсинг callback_data: 'btn:{step_id}:{button_id}'
    2. Найти шаг и кнопку
    3. Вызвать engine.handle_button_click
    4. Ответить Telegram через callback.answer() (обязательно, иначе пользователь видит loader)
    """
    await callback.answer()  # Убрать loader сразу
    
    parts = callback.data.split(":")
    if len(parts) != 3:
        return
    _, step_id_str, button_id_str = parts
    # ...
```

### Задача 11 — Тесты

Создай `tests/test_engine.py` с тестами:

```python
@pytest.mark.asyncio
async def test_execute_simple_text_step():
    # Создать тестовый шаг с одним текстовым сообщением
    # Вызвать engine.execute_step_for_user
    # Проверить, что bot.send_message был вызван с правильными аргументами
    ...

@pytest.mark.asyncio
async def test_delay_less_than_60_uses_sleep():
    # step с delay_before=30s, delay_after=15s
    # Проверить, что задержки применились через asyncio.sleep (mock)
    # Проверить, что ScheduledTask НЕ создан
    ...

@pytest.mark.asyncio
async def test_delay_more_than_60_creates_scheduled_task():
    # step с delay_before=2h
    # Проверить, что ScheduledTask создан с правильным execute_at
    # Проверить, что сообщения НЕ отправлены в этот момент
    ...

@pytest.mark.asyncio
async def test_button_visibility_filtering():
    # step с двумя кнопками: одна требует tag=X, другая без условий
    # Пользователь без тегов → клавиатура с одной кнопкой
    # Пользователь с тегом X → клавиатура с двумя кнопками
    ...

@pytest.mark.asyncio
async def test_trigger_condition_skips_step():
    # step с trigger={type: has_tags, tags: [paid]}
    # Пользователь без тегов → шаг пропущен, сразу переход к next
    ...

@pytest.mark.asyncio
async def test_cross_entry_deny_blocks_start():
    # Пользователь уже в воронке A
    # Попытка запустить воронку B с cross_entry_behavior=deny
    # Проверить, что B не запущена, пользователь остался в A
    ...

@pytest.mark.asyncio
async def test_button_click_add_tag():
    # Нажатие кнопки с action={type: add_tag, value: "test_tag"}
    # Проверить, что UserTag создан
    ...

@pytest.mark.asyncio
async def test_pay_product_creates_pending_purchase():
    # Нажатие кнопки с action={type: pay_product, value: <product_id>}
    # Проверить, что создан Purchase со status=pending
    ...

@pytest.mark.asyncio
async def test_wait_for_payment_doesnt_advance():
    # step с wait_for_payment=True
    # После отправки сообщений — следующий шаг НЕ запущен
    ...

@pytest.mark.asyncio
async def test_continue_after_payment():
    # У пользователя step с wait_for_payment=True, в статусе pending
    # Вызов engine.continue_after_payment
    # Проверить, что следующий шаг запущен
    ...
```

## Файлы, которые нужно создать или изменить

```
Создать:
- app/funnels/__init__.py
- app/funnels/engine.py (полностью переписать, старый удалить)
- app/funnels/keyboard_builder.py
- app/funnels/message_sender.py
- app/funnels/condition_checker.py
- app/funnels/cross_entry.py
- app/funnels/actions/__init__.py
- app/funnels/actions/url.py
- app/funnels/actions/pay_product.py
- app/funnels/actions/goto_step.py
- app/funnels/actions/add_tag.py
- app/funnels/actions/open_track.py
- app/funnels/actions/signal.py
- app/bot/handlers/callbacks.py
- app/tasks/funnel_tasks.py
- tests/test_engine.py

Изменить:
- app/funnels/engine.py (если был старый — полностью переписать)
- app/bot/handlers/start.py (обновить с поддержкой deeplink)
- app/tasks/celery_app.py (добавить beat schedule)
- app/bot/main.py (зарегистрировать новые роутеры)

Не трогать:
- app/api/routes/funnels.py (из Промпта 1)
- app/db/models.py, app/schemas/step_config.py
- app/static/, templates/ (UI в следующих промптах)
```

## Acceptance criteria

1. `from app.funnels.engine import FunnelEngine` импортируется без ошибок
2. Все тесты в `tests/test_engine.py` проходят (минимум 10 тестов)
3. Запуск бота `python -m app.bot.main` не падает с ошибками
4. При отправке `/start guide` в тестовом боте — пользователь получает сообщения первого шага воронки "Гайд"
5. Кнопка с action=url открывает ссылку (Telegram обрабатывает сам)
6. Кнопка с action=add_tag добавляет тег в БД
7. Кнопка с action=goto_step переходит на указанный шаг
8. Celery Beat раз в 30 сек проверяет ScheduledTask — это видно в логах
9. При задержке < 60 сек — шаг выполняется в той же корутине (нет записи в scheduled_tasks)
10. При задержке ≥ 60 сек — создаётся ScheduledTask со status=pending

## Как проверить результат

После завершения работы:

```bash
# 1. Тесты движка
pytest tests/test_engine.py -v

# 2. Весь набор тестов — регрессии не должно быть
pytest tests/ -v

# 3. Запуск бота (в отдельном терминале)
python -m app.bot.main

# 4. В Telegram — найти своего бота, отправить /start guide
# Ожидается: пользователь получает сообщения из первого шага воронки "Гайд"

# 5. Запуск Celery
celery -A app.tasks.celery_app worker --loglevel=INFO &
celery -A app.tasks.celery_app beat --loglevel=INFO &

# 6. Через 30 секунд — в логах Celery должна быть запись о выполнении process_scheduled_tasks
```

Покажи реальный вывод каждой команды. Если что-то падает — покажи ошибку.

## Важные замечания

- **Pydantic-дискриминация блоков.** `StepConfig.blocks` содержит `Union[MessageContent, ButtonGroup]`. Pydantic должен правильно определить тип каждого блока при парсинге. Если это не работает из коробки — добавь discriminator на поле `type`.

- **Исключения Telegram.** `TelegramBadRequest` может означать: неверный file_id, пользователь заблокировал бота, сообщение слишком длинное. Разные ситуации — разная обработка. Минимум: если пользователь заблокировал бота — пометить UserFunnelState как paused.

- **Идемпотентность.** Каждое выполнение шага имеет `execution_id`. Если ScheduledTask была выполнена, но Celery повторил — проверить по execution_id и не выполнять повторно.

- **Не усложняй message_sender.** Простая функция, одна задача — отправить. Вся логика принятия решений — в engine.

- **callback_data лимит 64 байта.** `btn:{step_id}:{button_id}` = 4+36+1+36 = 77 байт. Это превышает лимит! Используй **короткие UUID**: либо первые 8 символов button_id, либо отдельный короткий ID кнопки. Предлагаю генерировать короткие callback-кеи в keyboard_builder и сохранять маппинг в Redis на время сессии (TTL 24 часа).

- **Порядок блоков в config.blocks.** По спецификации: `ButtonGroup` должен быть последним блоком. Но формально это не запрещено. Если в шаге два ButtonGroup — используй первый, второй игнорируй (с warning в логах).

- **Тест-отправка для админки.** Метод `run_test_for_admin` должен существовать и работать, потому что на него будет ссылаться Промпт 3 (редактор шага).

Приоритет: корректность поведения > производительность. Этот движок — ядро бота, его надёжность важнее всего.
