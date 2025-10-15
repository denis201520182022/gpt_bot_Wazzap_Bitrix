# src/app.py
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()

from services import bitrix_service
from utils import parse_form_data

# --- ЗАГРУЖАЕМ ВСЕ НАШИ НАСТРОЙКИ ИЗ .ENV ---
TARGET_FUNNEL_ID = os.getenv("TARGET_FUNNEL_ID")
WELCOME_STAGE_ID = f"C{TARGET_FUNNEL_ID}:NEW" 
TOUCH_TODAY_STAGE_ID = os.getenv("TOUCH_TODAY_STAGE_ID")
NEW_LOT_STAGE_ID = os.getenv("NEW_LOT_STAGE_ID")
# --- НОВАЯ ПЕРЕМЕННАЯ ---
NOMINALS_STAGE_ID = os.getenv("NOMINALS_STAGE_ID") # ID стадии для исключения
TEST_ACTIVITY_STAGE_ID = os.getenv("TEST_ACTIVITY_STAGE_ID")


app = FastAPI(title="Bitrix Wazzup Bot")

# ... (код @app.get("/") остается без изменений) ...
@app.get("/")
def read_root(): return {"status": "ok", "message": "Bot is running"}

@app.post("/webhook/bitrix")
async def handle_bitrix_webhook(request: Request):
    form_data = await request.form()
    data = parse_form_data(form_data)
    
    if data.get("event") != "ONCRMDEALUPDATE":
        return {"status": "ok", "message": "Event ignored"}

    deal_id = int(data.get("data", {}).get("FIELDS", {}).get("ID"))
    if not deal_id: return {"status": "error", "message": "No deal ID"}
    
    deal_details = bitrix_service.get_deal_details(deal_id)
    if not deal_details: return {"status": "error", "message": "Failed to get deal details"}

    current_funnel_id = deal_details.get("CATEGORY_ID")
    current_stage = deal_details.get("STAGE_ID")
    
    if current_funnel_id == TARGET_FUNNEL_ID:
        print(f"Сделка {deal_id} в нужной воронке. Стадия: {current_stage}")

        if current_stage == NOMINALS_STAGE_ID:
            print(f"⚠️ Сделка {deal_id} на стадии 'Номиналы'. Обработка прекращена.")
            return {"status": "ok", "message": "Ignored due to Nominals stage"}

        contact_id = deal_details.get("CONTACT_ID")
        manager_id = int(deal_details.get("ASSIGNED_BY_ID"))
        client_name, manager_name = "Уважаемый клиент", "Ваш менеджер"
        if contact_id:
            contact = bitrix_service.get_contact_details(contact_id)
            if contact and contact.get("NAME"): client_name = contact.get("NAME")
        if manager_id:
            manager = bitrix_service.get_user_details(manager_id)
            if manager:
                full_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip()
                if full_name: manager_name = full_name

        if current_stage == WELCOME_STAGE_ID:
            message = (f"Здравствуйте, {client_name}! Это {manager_name}, ваш менеджер по сопровождению...")
            print_formatted_message("ПРИВЕТСТВИЕ", deal_id, client_name, manager_name, message)

        elif current_stage == TOUCH_TODAY_STAGE_ID:
            message = (f"Здравствуйте, {client_name}! Это {manager_name}. Как проходит работа по вашим текущим делам? ...")
            print_formatted_message("КАСАНИЕ СЕГОДНЯ", deal_id, client_name, manager_name, message)

        # --- ОБНОВЛЕННАЯ ЛОГИКА ДЛЯ НОВОГО ЛОТА ---
        elif current_stage == NEW_LOT_STAGE_ID:
            # 1. Получаем последнее дело для сделки
            latest_activity = bitrix_service.get_latest_activity_for_deal(deal_id)
            
            # 2. Проверяем, что дело найдено и у него есть описание
            if latest_activity and latest_activity.get("DESCRIPTION"):
                lot_description = latest_activity.get("DESCRIPTION")
                
                # 3. Формируем сообщение с реальным описанием
                message = (f"Здравствуйте, {client_name}! Это {manager_name}. У нас появились новые лоты по должнику: '{lot_description}'. "
                           f"Расскажите пожалуйста, можем ли мы поработать по данному должнику? "
                           f"Я могу прямо сейчас оформить заявку на открытие спецсчетов.")
                print_formatted_message("НОВЫЙ ЛОТ", deal_id, client_name, manager_name, message)
            else:
                # Если дело не найдено или описание пустое, просто логируем это
                print(f"ОШИБКА СЦЕНАРИЯ: Сделка {deal_id} перешла на стадию 'Новый лот', но не найдено подходящего дела с описанием.")
        elif current_stage == TEST_ACTIVITY_STAGE_ID:
            print(f"Тестовый триггер: Сделка {deal_id} перешла на стадию 'В ожидании'. Создаем дело...")
            
            if manager_id:
                # Формируем тему и описание для тестового дела
                subject = f"Тестовая задача от бота для сделки №{deal_id}"
                description = "Это тестовое дело, созданное автоматически для проверки функции эскалации."
                
                # Вызываем нашу новую функцию
                bitrix_service.create_activity_for_deal(
                    deal_id=deal_id,
                    responsible_id=manager_id,
                    subject=subject,
                    description=description
                )
            else:
                print("ОШИБКА: Не удалось создать дело, т.к. у сделки нет ответственного менеджера.")

    return {"status": "ok", "message": "Webhook processed"}


def print_formatted_message(scenario: str, deal_id, client_name, manager_name, message: str):
    # ... (эта функция остается без изменений) ...
    print("="*50)
    print(f"✅ СЦЕНАРИЙ '{scenario}' ДЛЯ СДЕЛКИ {deal_id}")
    print(f"  - Клиент: {client_name}")
    print(f"  - Менеджер: {manager_name}")
    print("\n--- ГОТОВЫЙ ТЕКСТ ДЛЯ WAZZUP ---")
    print(message)
    print("="*50)