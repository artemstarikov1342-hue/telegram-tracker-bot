"""
Автоматическое получение OAuth токена
"""
import webbrowser
import time
import re

print("\n" + "="*60)
print("  АВТОМАТИЧЕСКОЕ ПОЛУЧЕНИЕ OAUTH ТОКЕНА")
print("="*60)

print("\n📋 ЧТО СЕЙЧАС ПРОИЗОЙДЁТ:")
print("   1. Откроется браузер с Яндекс OAuth")
print("   2. Вы нажмёте 'Разрешить'")
print("   3. Скопируете токен из адресной строки")
print("   4. Вставите его сюда")
print("   5. Скрипт автоматически обновит .env")

input("\n✅ Нажмите Enter, чтобы открыть браузер...")

# Открываем браузер
url = "https://oauth.yandex.ru/authorize?response_type=token&client_id=c0ebe342af7d48fbbbfcf2d2eedb8f9e&force_confirm=yes&scope=tracker:read%20tracker:write"

print("\n🌐 Открываю браузер...")
webbrowser.open(url)

time.sleep(2)

print("\n" + "="*60)
print("  ИНСТРУКЦИЯ")
print("="*60)
print("\n1. В браузере нажмите 'Разрешить'")
print("\n2. Вас перебросит на страницу, в адресной строке будет:")
print("   https://oauth.yandex.ru/...#access_token=ТОКЕН&...")
print("\n3. Скопируйте ВЕСЬ текст после 'access_token=' до '&'")
print("   Это будет длинная строка, начинающаяся с y0_")
print("\n4. Вставьте токен ниже")
print("="*60 + "\n")

while True:
    token = input("➡️  Вставьте токен: ").strip()
    
    if not token:
        print("❌ Токен не введён!")
        continue
    
    # Очищаем токен от возможных лишних символов
    token = token.replace('access_token=', '')
    token = token.split('&')[0]
    token = token.strip()
    
    if len(token) < 20:
        print("❌ Токен слишком короткий! Скопируйте полностью.")
        continue
    
    if not (token.startswith('y0_') or token.startswith('y0__')):
        print("⚠️  Токен должен начинаться с y0_ или y0__")
        confirm = input("   Продолжить? (y/n): ").lower()
        if confirm != 'y':
            continue
    
    break

# Обновляем .env
print("\n📝 Обновляю .env...")

try:
    with open('.env', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Заменяем токен
    new_content = re.sub(
        r'YANDEX_TRACKER_TOKEN=.*',
        f'YANDEX_TRACKER_TOKEN={token}',
        content
    )
    
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Токен обновлён!")
    
    # Тестируем
    print("\n🔍 Проверяю токен...")
    
    from dotenv import load_dotenv
    load_dotenv()
    import requests
    import config
    
    # Перезагружаем config
    import importlib
    importlib.reload(config)
    
    url = 'https://api.tracker.yandex.net/v2/myself'
    headers = {
        'Authorization': f'OAuth {token}',
        'X-Org-ID': config.YANDEX_ORG_ID
    }
    
    r = requests.get(url, headers=headers, timeout=10)
    
    if r.status_code == 200:
        print("✅ ТОКЕН РАБОТАЕТ!")
        data = r.json()
        print(f"   Пользователь: {data.get('display')}")
        
        print("\n🚀 СЛЕДУЮЩИЙ ШАГ:")
        print("   Запустите бота: ЗАПУСК.cmd")
        
    elif r.status_code == 401:
        print("❌ Токен недействителен или истёк")
        print("   Попробуйте получить новый токен")
    elif r.status_code == 403:
        print("❌ Токен не имеет нужных прав")
        print("   Нужны права: tracker:read и tracker:write")
    else:
        print(f"❌ Ошибка {r.status_code}: {r.text[:200]}")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")

print("\n" + "="*60)
input("\nНажмите Enter...")
