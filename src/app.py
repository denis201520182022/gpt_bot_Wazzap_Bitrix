# src/app.py
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()

from services import bitrix_service, wazzup_service, llm_service
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

# src/app.py

# Убедитесь, что вверху файла импортируются ОБА сервиса
from services import bitrix_service, wazzup_service

# ... (остальные импорты и переменные .env)

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

        contact_id = int(deal_details.get("CONTACT_ID"))
        manager_id = int(deal_details.get("ASSIGNED_BY_ID"))
        client_name, manager_name = "Уважаемый клиент", "Ваш менеджер"
        contact_details = None

        if contact_id:
            contact_details = bitrix_service.get_contact_details(contact_id)
            if contact_details and contact_details.get("NAME"):
                client_name = contact_details.get("NAME")

        if manager_id:
            manager = bitrix_service.get_user_details(manager_id)
            if manager:
                full_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip()
                if full_name: manager_name = full_name
        
        message_to_send = None # Будем хранить здесь готовое сообщение
        scenario_name = "Неизвестный"

        # --- РОУТЕР СЦЕНАРИЕВ: ТЕПЕРЬ ОН ТОЛЬКО ГОТОВИТ СООБЩЕНИЕ ---

        if current_stage == WELCOME_STAGE_ID:
            scenario_name = "ПРИВЕТСТВИЕ"
            message_to_send = (
                f"Здравствуйте, {client_name}! Это {manager_name}, ваш менеджер по сопровождению. "
                f"Теперь при возникновении каких либо затруднений при работе с банком, "
                f"либо при необходимости открытия счетов по должникам в наших банках партнерах, "
                f"Вы можете писать мне. Сохраните пожалуйста мой номер телефона."
            )

        elif current_stage == TOUCH_TODAY_STAGE_ID:
            scenario_name = "КАСАНИЕ СЕГОДНЯ"
            message_to_send = (
                f"Здравствуйте, {client_name}! Это {manager_name}. Как проходит работа по вашим текущим делам? "
                f"Если есть новые должники или вопросы, сообщите. "
                f"Также напоминаем о возможности привлечения ваших коллег по программе «Приведи друга»."
            )

        elif current_stage == NEW_LOT_STAGE_ID:
            scenario_name = "НОВЫЙ ЛОТ"
            latest_activity = bitrix_service.get_latest_activity_for_deal(deal_id)
            if latest_activity and latest_activity.get("DESCRIPTION"):
                lot_description = latest_activity.get("DESCRIPTION")
                message_to_send = (
                    f"Здравствуйте, {client_name}! Это {manager_name}. У нас появились новые лоты по должнику: '{lot_description}'. "
                    f"Расскажите пожалуйста, можем ли мы поработать по данному должнику? "
                    f"Я могу прямо сейчас оформить заявку на открытие спецсчетов."
                )
            else:
                print(f"ОШИБКА СЦЕНАРИЯ: Сделка {deal_id} перешла на стадию 'Новый лот', но не найдено подходящего дела с описанием.")

        elif current_stage == TEST_ACTIVITY_STAGE_ID:
            # Этот сценарий остается без отправки, он только для теста создания дел
            print(f"Тестовый триггер: Сделка {deal_id} перешла на стадию 'В ожидании'. Создаем дело...")
            if manager_id:
                subject = f"Тестовая задача от бота для сделки №{deal_id}"
                description = "Это тестовое дело, созданное автоматически для проверки функции эскалации."
                bitrix_service.create_activity_for_deal(deal_id=deal_id, responsible_id=manager_id, subject=subject, description=description)
            else:
                print("ОШИБКА: Не удалось создать дело, т.к. у сделки нет ответственного менеджера.")

        # --- ЕДИНЫЙ БЛОК ОТПРАВКИ СООБЩЕНИЯ ---
        # Если для сценария было сформировано сообщение, отправляем его
        if message_to_send:
            print_formatted_message(scenario_name, deal_id, client_name, manager_name, message_to_send)
            
            if contact_details and contact_details.get("PHONE"):
                phone_info = contact_details["PHONE"][0]
                phone_number = phone_info.get("VALUE")
                
                print(f"Найден номер телефона клиента: {phone_number}. Попытка отправки через Wazzup...")
                wazzup_service.send_message(phone_number, message_to_send)
            else:
                print(f"⚠️ Не удалось отправить сообщение: у контакта для сделки {deal_id} не найден номер телефона.")

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



# src/app.py

@app.post("/webhook/wazzup")
async def handle_wazzup_webhook(request: Request):
    print("\n" + "="*50)
    print(">>> ПОЛУЧЕН ВХОДЯЩИЙ ВЕБХУК ОТ WAZZUP!")
    
    data = await request.json()
    
    if data.get("test") is True:
        print("   Это тестовый запрос от Wazzup. Отвечаем 200 OK.")
        print("="*50 + "\n")
        return {"status": "ok"}

    if "messages" in data and data["messages"]:
        first_message = data["messages"][0]
        
        # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: ЗАЩИТА ОТ ЭХО ---
        # Wazzup присылает нам наши же отправленные сообщения. Это 'эхо'.
        # Если isEcho равно True, это наше собственное сообщение, и мы должны его игнорировать.
        if first_message.get("isEcho") is True:
            print("   Это наше собственное 'эхо'-сообщение. Игнорируем.")
            print("="*50 + "\n")
            return {"status": "ok", "message": "Echo message ignored"}
        # ----------------------------------------

        client_text = first_message.get("text")
        client_phone = first_message.get("chatId")
        
        if client_text and client_phone:
            ai_response = await llm_service.generate_manager_response(client_text, manager_name="Алексей")
            
            if ai_response:
                print(f"Отправка сгенерированного ответа клиенту {client_phone}...")
                wazzup_service.send_message(client_phone, ai_response)
            else:
                print("Не удалось сгенерировать ответ от LLM. Отправка отменена.")

    print("="*50 + "\n")
    return {"status": "ok", "message": "Wazzup webhook processed"}