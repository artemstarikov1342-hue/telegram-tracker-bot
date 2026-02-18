"""
Автоматическое определение chat_id группы
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import config
import re

print("\n" + "="*60)
print("  АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ CHAT_ID")
print("="*60)
print("\n✅ Бот запущен и слушает сообщения...")
print("\n📱 ЧТО ДЕЛАТЬ:")
print("   1. Откройте группу в Telegram (где уже есть бот)")
print("   2. Отправьте ЛЮБОЕ сообщение в группу")
print("   3. Chat ID появится здесь автоматически!")
print("\n⏹  Для выхода: Ctrl+C")
print("="*60 + "\n")

detected_groups = {}

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик любого сообщения"""
    
    if not update.message or not update.effective_chat:
        return
    
    chat = update.effective_chat
    
    # Только групповые чаты
    if chat.type not in ['group', 'supergroup']:
        return
    
    # Если этот чат уже обработан, пропускаем
    if chat.id in detected_groups:
        return
    
    detected_groups[chat.id] = True
    
    print("\n" + "="*60)
    print("  ✅ ГРУППА ОБНАРУЖЕНА!")
    print("="*60)
    print(f"\n📋 ИНФОРМАЦИЯ О ГРУППЕ:")
    print(f"   Chat ID: {chat.id}")
    print(f"   Название: {chat.title or 'Без названия'}")
    print(f"   Тип: {chat.type}")
    
    print("\n" + "="*60)
    print("  📝 ДОБАВЬТЕ В CONFIG.PY:")
    print("="*60)
    print(f"""
PARTNER_CHAT_MAPPING = {{
    {chat.id}: {{
        'partner_name': '{chat.title or "Тестовый партнер"}',
        'queue': 'PART1',
    }},
}}
""")
    
    print("="*60)
    print("\n✅ Готово! Теперь:")
    print("   1. Скопируйте код выше")
    print("   2. Откройте config.py")
    print("   3. Найдите PARTNER_CHAT_MAPPING")
    print("   4. Замените на этот код")
    print("   5. Сохраните (Ctrl+S)")
    print("   6. Перезапустите бота")
    print("\n⏹  Нажмите Ctrl+C для выхода")
    print("="*60 + "\n")

async def main():
    """Запуск"""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_any_message))
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✅ Завершено!")
