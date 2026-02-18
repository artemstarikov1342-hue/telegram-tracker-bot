"""
Автоматическая настройка одного партнера
"""
from dotenv import load_dotenv
load_dotenv()

import requests
import config
import re

def print_header(text):
    """Красивый заголовок"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def create_queue(queue_key, queue_name):
    """Создать очередь в Трекере"""
    
    print(f"📤 Создаю очередь {queue_key}...")
    
    url = 'https://api.tracker.yandex.net/v2/queues'
    
    headers = {
        'Authorization': f'OAuth {config.YANDEX_TRACKER_TOKEN}',
        'X-Org-ID': config.YANDEX_ORG_ID,
        'Content-Type': 'application/json'
    }
    
    data = {
        'key': queue_key,
        'name': queue_name,
        'lead': None,
        'defaultType': 'task',
        'defaultPriority': 'critical',
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 201:
            print(f"✅ Очередь {queue_key} создана!")
            print(f"   Ссылка: https://tracker.yandex.ru/{queue_key}")
            return True
        elif response.status_code == 409:
            print(f"✅ Очередь {queue_key} уже существует!")
            return True
        elif response.status_code == 403:
            print(f"⚠️  Нет прав для автоматического создания очереди.")
            print(f"\n📝 СОЗДАЙТЕ ВРУЧНУЮ:")
            print(f"   1. Откройте: https://tracker.yandex.ru/")
            print(f"   2. Нажмите '+ Создать очередь'")
            print(f"   3. Ключ: {queue_key}")
            print(f"   4. Название: {queue_name}")
            print(f"   5. Шаблон: Базовая разработка")
            
            input("\n✅ Нажмите Enter после создания очереди...")
            return True
        else:
            print(f"❌ Ошибка {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def get_chat_id():
    """Получить chat_id от пользователя"""
    
    print("\n📱 КАК ПОЛУЧИТЬ CHAT_ID:")
    print("   1. Откройте чат с партнером в Telegram")
    print("   2. Добавьте в чат: @myidbot")
    print("   3. Отправьте команду: /getgroupid")
    print("   4. Скопируйте ID (с минусом!)")
    print("   5. Вставьте сюда")
    
    while True:
        chat_id = input("\n➡️  Введите chat_id: ").strip()
        
        # Проверка формата
        if re.match(r'^-?\d+$', chat_id):
            return int(chat_id)
        else:
            print("❌ Неправильный формат! ID должен быть числом (с минусом)")
            print("   Пример: -1001234567890")

def update_config(chat_id, partner_name, queue_key):
    """Обновить config.py"""
    
    print(f"\n📝 Обновляю config.py...")
    
    try:
        # Читаем config.py
        with open('config.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем PARTNER_CHAT_MAPPING
        pattern = r'PARTNER_CHAT_MAPPING: Dict\[int, Dict\[str, str\]\] = \{[^}]*\}'
        
        new_mapping = f"""PARTNER_CHAT_MAPPING: Dict[int, Dict[str, str]] = {{
    {chat_id}: {{
        'partner_name': '{partner_name}',
        'queue': '{queue_key}',
    }},
}}"""
        
        # Заменяем
        new_content = re.sub(pattern, new_mapping, content, flags=re.DOTALL)
        
        # Сохраняем
        with open('config.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ config.py обновлён!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении config.py: {e}")
        return False

def main():
    """Главная функция"""
    
    print_header("АВТОМАТИЧЕСКАЯ НАСТРОЙКА ПАРТНЕРА")
    
    # Проверяем токены
    if config.YANDEX_TRACKER_TOKEN == 'YOUR_YANDEX_TRACKER_TOKEN':
        print("❌ Ошибка: токен Трекера не настроен!")
        return
    
    if config.YANDEX_ORG_ID == 'YOUR_ORG_ID':
        print("❌ Ошибка: ID организации не настроен!")
        return
    
    # ШАГ 1: Создать очередь
    print_header("ШАГ 1: СОЗДАНИЕ ОЧЕРЕДИ")
    
    partner_name = input("➡️  Введите название партнера (например 'Партнер Альфа'): ").strip()
    if not partner_name:
        partner_name = "Тестовый партнер"
    
    queue_key = "PART1"
    
    if not create_queue(queue_key, partner_name):
        print("\n❌ Не удалось создать очередь. Попробуйте вручную.")
        return
    
    # ШАГ 2: Получить chat_id
    print_header("ШАГ 2: ПОЛУЧЕНИЕ CHAT_ID")
    
    chat_id = get_chat_id()
    print(f"✅ Chat ID получен: {chat_id}")
    
    # ШАГ 3: Обновить config
    print_header("ШАГ 3: ОБНОВЛЕНИЕ КОНФИГУРАЦИИ")
    
    if not update_config(chat_id, partner_name, queue_key):
        print("\n❌ Не удалось обновить config.py")
        print("\n📝 ДОБАВЬТЕ ВРУЧНУЮ:")
        print(f"\n    {chat_id}: {{")
        print(f"        'partner_name': '{partner_name}',")
        print(f"        'queue': '{queue_key}',")
        print(f"    }},")
        return
    
    # ГОТОВО!
    print_header("✅ НАСТРОЙКА ЗАВЕРШЕНА!")
    
    print("📋 ЧТО НАСТРОЕНО:")
    print(f"   • Партнер: {partner_name}")
    print(f"   • Очередь: {queue_key}")
    print(f"   • Chat ID: {chat_id}")
    
    print("\n🚀 СЛЕДУЮЩИЕ ШАГИ:")
    print("   1. Перезапустите бота (закройте и запустите ЗАПУСК.cmd)")
    print("   2. Откройте чат с партнером в Telegram")
    print("   3. Напишите: #задача Тестовая задача")
    print("   4. Бот создаст задачи в MNG и PART1")
    
    print("\n" + "="*60)
    input("\nНажмите Enter для выхода...")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Отменено пользователем")
    except Exception as e:
        print(f"\n\n❌ Ошибка: {e}")
        input("\nНажмите Enter для выхода...")
