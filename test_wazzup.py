# test_wazzup.py
from dotenv import load_dotenv

# --- ИСПРАВЛЕНИЕ: СНАЧАЛА ЗАГРУЖАЕМ .ENV ---
# Это должно быть первым действием, до всех импортов наших модулей
print("Запуск теста отправки Wazzup...")
load_dotenv()

# --- ТЕПЕРЬ ИМПОРТИРУЕМ НАШ СЕРВИС ---
from src.services import wazzup_service

def run_test():
    """
    Вызывает тестовую отправку сообщения.
    """
    # --- ВАЖНО: УКАЖИТЕ ВАШИ ДАННЫЕ ДЛЯ ТЕСТА ---
    test_phone_number = "+79614401264" # <-- ЗАМЕНИТЕ НА СВОЙ НОМЕР WHATSAPP
    test_message = "Это тестовое сообщение от бота. Если вы его видите, значит, интеграция с Wazzup работает!"
    # ----------------------------------------------------

    if test_phone_number == "79990001122":
        print("\n!!! ПОЖАЛУЙСТА, ОТКРОЙТЕ ФАЙЛ test_wazzup.py И УКАЖИТЕ СВОЙ РЕАЛЬНЫЙ НОМЕР ТЕЛЕФОНА ДЛЯ ТЕСТА !!!\n")
        return

    success = wazzup_service.send_message(test_phone_number, test_message)

    if success:
        print("\nТест завершен успешно!")
    else:
        print("\nТест провалился. Проверьте ошибки в консоли выше.")


if __name__ == "__main__":
    run_test()