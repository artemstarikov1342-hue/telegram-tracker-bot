"""
Быстрая настройка бота - установка всего необходимого
"""
import subprocess
import sys
import os

def run_command(cmd, description):
    """Запуск команды"""
    print(f"\n{description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            print(f"✓ {description} - Готово")
            return True
        else:
            print(f"✗ Ошибка: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        return False

print("=" * 60)
print("БЫСТРАЯ УСТАНОВКА TELEGRAM TRACKER BOT")
print("=" * 60)

# Шаг 1: Установка requests (нужен для получения org_id)
print("\n[1/4] Установка библиотеки requests...")
subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], 
               capture_output=True)
print("✓ requests установлен")

# Шаг 2: Получение org_id
print("\n[2/4] Получение ID организации из Яндекс.Трекера...")
try:
    import requests
    
    token = "y0__xDjle9cGLMrILWR66UW1e0yELKf9G3mwUX_r0ZQUYftRcs"
    headers = {
        'Authorization': f'OAuth {token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.get(
        'https://api.tracker.yandex.net/v2/myself',
        headers=headers,
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        org_id = data.get('orgId')
        print(f"✓ ID организации получен: {org_id}")
        
        # Обновляем .env
        with open('.env', 'r', encoding='utf-8') as f:
            content = f.read()
        
        content = content.replace('YOUR_ORG_ID_HERE', str(org_id))
        
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✓ ID организации сохранён в .env")
    else:
        print(f"✗ Ошибка получения org_id: {response.status_code}")
        print(f"   {response.text}")
        
except Exception as e:
    print(f"✗ Ошибка: {e}")

# Шаг 3: Установка остальных зависимостей
print("\n[3/4] Установка зависимостей бота...")
packages = [
    'python-telegram-bot==21.0',
    'python-dotenv==1.0.1'
]

for pkg in packages:
    print(f"  • {pkg}...", end=' ')
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', pkg],
        capture_output=True
    )
    if result.returncode == 0:
        print("✓")
    else:
        print("✗")

print("✓ Все зависимости установлены")

# Шаг 4: Проверка конфигурации
print("\n[4/4] Проверка конфигурации...")

with open('.env', 'r', encoding='utf-8') as f:
    env_content = f.read()

issues = []
if 'YOUR_TOKEN_HERE' in env_content:
    issues.append("Не заполнен TELEGRAM_BOT_TOKEN")
if 'YOUR_ORG_ID_HERE' in env_content:
    issues.append("Не заполнен YANDEX_ORG_ID")

if issues:
    print("⚠ Найдены проблемы:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("✓ Конфигурация в порядке")

print("\n" + "=" * 60)
print("УСТАНОВКА ЗАВЕРШЕНА!")
print("=" * 60)

print("\nТеперь настройте партнеров в config.py:")
print("  1. Получите ID чатов (@myidbot -> /getgroupid)")
print("  2. Создайте очереди в Яндекс.Трекере")
print("  3. Заполните PARTNER_CHAT_MAPPING в config.py")
print("\nЗатем запустите бота: python bot.py")

input("\nНажмите Enter...")
