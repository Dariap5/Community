import json
from app.schemas.step_config import StepConfig
from uuid import uuid4

c_p1_dict = StepConfig(blocks=[
    {"type": "text", "content_text": "Оплатите продукт"},
    {"type": "buttons", "buttons": [{"text": "Оплатить", "action": {"type": "pay_product", "value": str(uuid4())}}]}
], wait_for_payment=True).model_dump(mode="json")
print("Воронка:", "Продукт 490")
print("Шаг:", "prod_1", "(Оплата)")
print("JSONB Config:\n", json.dumps(c_p1_dict, indent=2, ensure_ascii=False))

c_com1_dict = StepConfig(blocks=[
    {"type": "text", "content_text": "Приглашение"},
    {"type": "buttons", "buttons": [{"text": "Вступить", "action": {"type": "url", "value": "https://t.me"}}, {"text": "Есть сомнения", "action": {"type": "goto_step", "value": "doubt"}}]}
]).model_dump(mode="json")
print("\nВоронка:", "Комьюнити")
print("Шаг:", "com_1", "(Приветствие)")
print("JSONB Config:\n", json.dumps(c_com1_dict, indent=2, ensure_ascii=False))

