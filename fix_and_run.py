"""Исправление конфигурации и запуск"""
import subprocess
import sys

print("=" * 60)
print("ИСПРАВЛЕНИЕ И ЗАПУСК БОТА")
print("=" * 60)

# Шаг 1: Установка requests если нет
print("\n[1/4] Проверка requests...")
try:
    import requests
    print("✓ requests уже установлен")
except ImportError:
    print("Установка requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests
    print("✓ requests установлен")

# Шаг 2: Получение org_id
print("\n[2/4] Получение ID организации...")
token = "y0__xDjle9cGLMrILWR66UW1e0yELKf9G3mwUX_r0ZQUYftRcs"

try:
    response = requests.get(
        "https://api.tracker.yandex.net/v2/myself",
        headers={"Authorization": f"OAuth {token}"},
        timeout=10
    )
    
    if response.status_code == 200:
        org_id = response.json().get("orgId")
        print(f"✓ ID организации получен: {org_id}")
        
        # Обновляем .env
        with open(".env", "r", encoding="utf-8") as f:
            content = f.read()
        
        content = content.replace("YOUR_ORG_ID_HERE", str(org_id))
        
        with open(".env", "w", encoding="utf-8") as f:
            f.write(content)
        
        print("✓ ID организации сохранён в .env")
    else:
        print(f"✗ Ошибка: {response.status_code}")
        print(f"   Ответ: {response.text}")
        input("\nНажмите Enter для выхода...")
        sys.exit(1)
        
except Exception as e:
    print(f"✗ Ошибка: {e}")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

# Шаг 3: Установка остальных зависимостей
print("\n[3/4] Установка зависимостей бота...")
packages = [
    "python-telegram-bot==21.0",
    "python-dotenv==1.0.1"
]

for pkg in packages:
    print(f"  • {pkg}...", end=" ")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg],
        capture_output=True
    )
    if result.returncode == 0:
        print("✓")
    else:
        print("✗")

print("✓ Все зависимости установлены")

# Шаг 4: Запуск бота
print("\n[4/4] Запуск бота...")
print("=" * 60)
print()

try:
    subprocess.call([sys.executable, "bot.py"])
except KeyboardInterrupt:
    print("\n\nБот остановлен пользователем")
except Exception as e:
    print(f"\n\nОшибка запуска: {e}")
    input("\nНажмите Enter для выхода...")
