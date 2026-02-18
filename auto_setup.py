"""
Автоматическая установка и настройка бота
"""
import subprocess
import sys
import os

def install_packages():
    """Установка зависимостей"""
    print("=" * 50)
    print("АВТОМАТИЧЕСКАЯ УСТАНОВКА")
    print("=" * 50)
    print()
    
    packages = [
        'python-telegram-bot==21.0',
        'requests==2.31.0',
        'python-dotenv==1.0.1'
    ]
    
    print("Установка зависимостей...")
    for package in packages:
        print(f"  Устанавливаю {package}...")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
            print(f"  ✓ {package} установлен")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Ошибка установки {package}: {e}")
            return False
    
    print()
    print("✓ Все зависимости установлены!")
    return True

def check_env():
    """Проверка .env файла"""
    print()
    print("=" * 50)
    print("ПРОВЕРКА КОНФИГУРАЦИИ")
    print("=" * 50)
    print()
    
    if not os.path.exists('.env'):
        print("✗ Файл .env не найден!")
        return False
    
    with open('.env', 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'YOUR_TOKEN_HERE' in content or 'YOUR_ORG_ID_HERE' in content:
        print("⚠ Файл .env создан, но не заполнен!")
        print()
        print("Откройте файл .env и заполните 3 поля:")
        print("  1. TELEGRAM_BOT_TOKEN - токен от @BotFather")
        print("  2. YANDEX_TRACKER_TOKEN - OAuth токен Яндекса")
        print("  3. YANDEX_ORG_ID - ID организации")
        print()
        print("После заполнения запустите: python bot.py")
        return False
    
    print("✓ Файл .env настроен!")
    return True

def main():
    # Установка пакетов
    if not install_packages():
        print()
        input("Нажмите Enter для выхода...")
        return
    
    # Проверка конфигурации
    env_ok = check_env()
    
    print()
    print("=" * 50)
    print("УСТАНОВКА ЗАВЕРШЕНА")
    print("=" * 50)
    print()
    
    if env_ok:
        print("✓ Всё готово! Запускаю бота...")
        print()
        try:
            subprocess.call([sys.executable, 'bot.py'])
        except KeyboardInterrupt:
            print("\nБот остановлен")
    else:
        print("Следующие шаги:")
        print("  1. Откройте файл .env")
        print("  2. Заполните 3 токена")
        print("  3. Запустите: python bot.py")
    
    print()
    input("Нажмите Enter для выхода...")

if __name__ == '__main__':
    main()
