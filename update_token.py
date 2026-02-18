"""
Обновление OAuth токена в .env
"""
import os
import re

print("\n" + "="*60)
print("  ОБНОВЛЕНИЕ OAUTH ТОКЕНА")
print("="*60)

print("\n📝 У вас есть новый токен?")
print("   (Если нет, смотрите файл: КАК_ПОЛУЧИТЬ_ТОКЕН.txt)")
print()

new_token = input("➡️  Введите новый OAuth токен: ").strip()

if not new_token:
    print("\n❌ Токен не введён!")
    input("\nНажмите Enter...")
    exit(1)

# Проверка формата
if not new_token.startswith('y0_'):
    print("\n⚠️  Внимание: токен должен начинаться с 'y0_'")
    confirm = input("   Продолжить всё равно? (y/n): ").strip().lower()
    if confirm != 'y':
        print("\n❌ Отменено")
        input("\nНажмите Enter...")
        exit(1)

# Читаем .env
try:
    with open('.env', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Заменяем токен
    new_content = re.sub(
        r'YANDEX_TRACKER_TOKEN=.*',
        f'YANDEX_TRACKER_TOKEN={new_token}',
        content
    )
    
    # Сохраняем
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("\n✅ Токен обновлён в .env!")
    print("\n🚀 СЛЕДУЮЩИЕ ШАГИ:")
    print("   1. Запустите: ПРОВЕРКА_API.cmd")
    print("   2. Если всё OK, запустите: ЗАПУСК.cmd")
    
except Exception as e:
    print(f"\n❌ Ошибка: {e}")

print("\n" + "="*60)
input("\nНажмите Enter...")
