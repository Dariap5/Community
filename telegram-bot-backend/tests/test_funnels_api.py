from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import FunnelStatus, User, UserFunnelState
from app.config import get_settings
from app.schemas.step_config import StepConfig


def _strip_ids(value):
    if isinstance(value, dict):
        return {key: _strip_ids(item) for key, item in value.items() if key != "id"}
    if isinstance(value, list):
        return [_strip_ids(item) for item in value]
    return value


def _step_config(message_text: str, *, with_button: bool = False) -> dict:
    blocks = [{"type": "text", "content_text": message_text}]
    if with_button:
        blocks.append(
            {
                "type": "buttons",
                "buttons": [
                    {
                        "text": "Перейти",
                        "action": {"type": "url", "value": "https://example.com"},
                    }
                ],
            }
        )
    return StepConfig(blocks=blocks).model_dump(mode="json")


async def _seed_active_user_state(funnel_id: str, step_id: str) -> int:
    user_id = 900000000000 + int(uuid4().int % 1_000_000_000)
    engine = create_async_engine(get_settings().postgres_dsn, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            User(
                telegram_id=user_id,
                first_name="pytest",
                username=f"pytest_{user_id}",
            )
        )
        session.add(
            UserFunnelState(
                user_id=user_id,
                funnel_id=UUID(funnel_id),
                current_step_id=UUID(step_id),
                status=FunnelStatus.active,
            )
        )
        await session.commit()
    await engine.dispose()
    return user_id


async def _cleanup_user(user_id: int) -> None:
    engine = create_async_engine(get_settings().postgres_dsn, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(delete(User).where(User.telegram_id == user_id))
        await session.commit()
    await engine.dispose()


def _create_funnel(admin_client, *, name_prefix: str = "Test Funnel", entry_key: str | None = None) -> dict:
    suffix = uuid4().hex[:8]
    payload = {
        "name": f"{name_prefix} {suffix}",
        "entry_key": entry_key or f"entry_{suffix}",
        "notes": "pytest",
    }
    response = admin_client.post("/api/funnels", json=payload)
    assert response.status_code == 201
    return response.json()


def _create_step(admin_client, funnel_id: str, *, order: int | None, label: str, with_button: bool = False) -> dict:
    suffix = uuid4().hex[:8]
    payload = {
        "name": f"{label} {suffix}",
        "step_key": f"{label.lower().replace(' ', '_')}_{suffix}",
        "is_active": True,
        "config": _step_config(label, with_button=with_button),
    }
    if order is not None:
        payload["order"] = order

    response = admin_client.post(f"/api/funnels/{funnel_id}/steps", json=payload)
    assert response.status_code == 201
    return response.json()


def test_list_funnels_returns_seed_data(admin_client) -> None:
    response = admin_client.get("/api/funnels")
    assert response.status_code == 200

    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 4
    assert all(item["steps_count"] >= 0 for item in payload)
    assert all("active_users_count" in item for item in payload)


def test_create_and_get_funnel_detail(admin_client) -> None:
    created = _create_funnel(admin_client, name_prefix="Detail Funnel")
    try:
        assert created["steps_count"] == 0
        assert created["active_users_count"] == 0

        response = admin_client.get(f"/api/funnels/{created['id']}")
        assert response.status_code == 200

        payload = response.json()
        assert payload["id"] == created["id"]
        assert payload["name"] == created["name"]
        assert payload["steps"] == []
        assert payload["steps_count"] == 0
    finally:
        assert admin_client.delete(f"/api/funnels/{created['id']}").status_code == 204


def test_create_funnel_duplicate_entry_key_returns_409(admin_client) -> None:
    list_response = admin_client.get("/api/funnels")
    assert list_response.status_code == 200
    existing_entry_key = next(item["entry_key"] for item in list_response.json() if item["entry_key"])

    response = admin_client.post(
        "/api/funnels",
        json={"name": f"Duplicate Entry {uuid4().hex[:8]}", "entry_key": existing_entry_key},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "conflict"
    assert payload["error"]["details"]["field"] == "entry_key"


def test_update_archive_and_restore_funnel(admin_client) -> None:
    created = _create_funnel(admin_client, name_prefix="Lifecycle Funnel")
    updated_name = f"Lifecycle Funnel Updated {uuid4().hex[:8]}"
    try:
        update_response = admin_client.patch(
            f"/api/funnels/{created['id']}",
            json={
                "name": updated_name,
                "notes": "updated",
                "is_active": False,
            },
        )
        assert update_response.status_code == 200

        detail_response = admin_client.get(f"/api/funnels/{created['id']}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["name"] == updated_name
        assert detail["is_active"] is False

        archive_response = admin_client.delete(f"/api/funnels/{created['id']}")
        assert archive_response.status_code == 204

        archived = admin_client.get(f"/api/funnels/{created['id']}").json()
        assert archived["is_archived"] is True
        assert archived["is_active"] is False

        restore_response = admin_client.post(f"/api/funnels/{created['id']}/restore")
        assert restore_response.status_code == 200

        restored = admin_client.get(f"/api/funnels/{created['id']}").json()
        assert restored["is_archived"] is False
        assert restored["is_active"] is True
    finally:
        assert admin_client.delete(f"/api/funnels/{created['id']}").status_code == 204


def test_duplicate_funnel_creates_all_steps(admin_client) -> None:
    source = _create_funnel(admin_client, name_prefix="Source Funnel")
    duplicate_id = None
    try:
        first_step = _create_step(admin_client, source["id"], order=1, label="Source Step 1")
        second_step = _create_step(admin_client, source["id"], order=2, label="Source Step 2", with_button=True)
        source_steps = admin_client.get(f"/api/funnels/{source['id']}/steps").json()

        response = admin_client.post(f"/api/funnels/{source['id']}/duplicate")
        assert response.status_code == 201
        duplicate = response.json()
        duplicate_id = duplicate["id"]

        duplicate_steps = admin_client.get(f"/api/funnels/{duplicate_id}/steps").json()

        assert duplicate["entry_key"] is None
        assert duplicate["steps_count"] == 2
        assert len(duplicate["steps"]) == 2
        assert duplicate["name"].startswith(source["name"])
        assert _strip_ids(duplicate_steps[0]["config"]) == _strip_ids(source_steps[0]["config"])
        assert _strip_ids(duplicate_steps[1]["config"]) == _strip_ids(source_steps[1]["config"])
        assert duplicate_steps[0]["config"] != source_steps[0]["config"]
        assert duplicate_steps[1]["config"] != source_steps[1]["config"]
    finally:
        if duplicate_id is not None:
            assert admin_client.delete(f"/api/funnels/{duplicate_id}").status_code == 204
        assert admin_client.delete(f"/api/funnels/{source['id']}").status_code == 204


def test_duplicate_step_keeps_config_and_reorders(admin_client) -> None:
    source = _create_funnel(admin_client, name_prefix="Step Copy Funnel")
    try:
        first_step = _create_step(admin_client, source["id"], order=1, label="Copy Source", with_button=True)
        second_step = _create_step(admin_client, source["id"], order=2, label="Copy Tail")

        duplicate_response = admin_client.post(f"/api/funnels/{source['id']}/steps/{first_step['id']}/duplicate")
        assert duplicate_response.status_code == 201
        duplicate = duplicate_response.json()

        steps = admin_client.get(f"/api/funnels/{source['id']}/steps").json()
        assert len(steps) == 3
        assert [step["order"] for step in steps] == [1, 2, 3]
        assert steps[0]["id"] == first_step["id"]
        assert steps[1]["id"] == duplicate["id"]
        assert steps[2]["id"] == second_step["id"]
        assert _strip_ids(steps[0]["config"]) == _strip_ids(steps[1]["config"])
        assert steps[0]["config"] != steps[1]["config"]
        assert steps[1]["step_key"].startswith(f"{first_step['step_key']}_copy_")
    finally:
        assert admin_client.delete(f"/api/funnels/{source['id']}").status_code == 204


def test_create_step_with_invalid_config_returns_422(admin_client) -> None:
    source = _create_funnel(admin_client, name_prefix="Invalid Config Funnel")
    try:
        response = admin_client.post(
            f"/api/funnels/{source['id']}/steps",
            json={
                "name": "Invalid Step",
                "step_key": f"invalid_step_{uuid4().hex[:8]}",
                "order": 1,
                "config": {
                    "blocks": [
                        {
                            "type": "buttons",
                            "buttons": [
                                {
                                    "text": "Broken",
                                    "action": {"type": "unknown", "value": "x"},
                                }
                            ],
                        }
                    ]
                },
            },
        )

        assert response.status_code == 422
        payload = response.json()
        assert payload["error"]["code"] == "validation_error"
        assert payload["error"]["details"]
    finally:
        assert admin_client.delete(f"/api/funnels/{source['id']}").status_code == 204


def test_update_step_with_invalid_config_returns_422(admin_client) -> None:
    source = _create_funnel(admin_client, name_prefix="Invalid Update Funnel")
    try:
        created = _create_step(admin_client, source["id"], order=1, label="Invalid Update Step")
        response = admin_client.put(
            f"/api/funnels/{source['id']}/steps/{created['id']}",
            json={
                "name": "Invalid Update Step",
                "step_key": f"invalid_update_{uuid4().hex[:8]}",
                "is_active": True,
                "config": {
                    "blocks": [
                        {
                            "type": "buttons",
                            "buttons": [
                                {
                                    "text": "Broken",
                                    "action": {"type": "unknown", "value": "x"},
                                }
                            ],
                        }
                    ]
                },
            },
        )

        assert response.status_code == 422
        payload = response.json()
        assert payload["error"]["code"] == "validation_error"
        assert payload["error"]["details"]
    finally:
        assert admin_client.delete(f"/api/funnels/{source['id']}").status_code == 204


def test_update_step_preserves_config_integrity(admin_client) -> None:
    source = _create_funnel(admin_client, name_prefix="Editable Step Funnel")
    try:
        created = _create_step(admin_client, source["id"], order=1, label="Editable Step", with_button=True)
        new_config = _step_config("Updated body", with_button=True)
        response = admin_client.put(
            f"/api/funnels/{source['id']}/steps/{created['id']}",
            json={
                "name": "Editable Step Updated",
                "step_key": f"editable_step_updated_{uuid4().hex[:8]}",
                "is_active": False,
                "config": new_config,
            },
        )
        assert response.status_code == 200

        updated = admin_client.get(f"/api/funnels/{source['id']}/steps/{created['id']}").json()
        assert updated["name"] == "Editable Step Updated"
        assert updated["is_active"] is False
        assert updated["config"] == new_config
        assert updated["config"]["blocks"][0]["content_text"] == "Updated body"
    finally:
        assert admin_client.delete(f"/api/funnels/{source['id']}").status_code == 204


def test_delete_step_with_active_users_returns_409(admin_client) -> None:
    source = _create_funnel(admin_client, name_prefix="Delete Guard Funnel")
    user_id = None
    try:
        created = _create_step(admin_client, source["id"], order=1, label="Protected Step")
        user_id = asyncio.run(_seed_active_user_state(source["id"], created["id"]))

        response = admin_client.delete(f"/api/funnels/{source['id']}/steps/{created['id']}")
        assert response.status_code == 409
        payload = response.json()
        assert payload["error"]["code"] == "conflict"
        assert payload["error"]["details"]["step_id"] == created["id"]
    finally:
        if user_id is not None:
            asyncio.run(_cleanup_user(user_id))
        assert admin_client.delete(f"/api/funnels/{source['id']}").status_code == 204


def test_reorder_steps_updates_order(admin_client) -> None:
    source = _create_funnel(admin_client, name_prefix="Reorder Funnel")
    try:
        step_one = _create_step(admin_client, source["id"], order=1, label="Step One")
        step_two = _create_step(admin_client, source["id"], order=2, label="Step Two")
        step_three = _create_step(admin_client, source["id"], order=3, label="Step Three")

        reorder_response = admin_client.post(
            f"/api/funnels/{source['id']}/steps/reorder",
            json={"step_ids_in_order": [step_three["id"], step_two["id"], step_one["id"]]},
        )
        assert reorder_response.status_code == 200

        steps = reorder_response.json()
        assert [step["id"] for step in steps] == [step_three["id"], step_two["id"], step_one["id"]]
        assert [step["order"] for step in steps] == [1, 2, 3]

        list_response = admin_client.get(f"/api/funnels/{source['id']}/steps")
        assert list_response.status_code == 200
        assert [step["id"] for step in list_response.json()] == [step_three["id"], step_two["id"], step_one["id"]]
    finally:
        assert admin_client.delete(f"/api/funnels/{source['id']}").status_code == 204