"""
Скрипт для получения chat_id
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import config

print("\n" + "="*60)
print("  ОПРЕДЕЛЕНИЕ CHAT_ID")
print("="*60)
print("\nБот запущен и ждёт сообщений...")
print("\n📱 ЧТО ДЕЛАТЬ:")
print("1. Откройте чат с партнером в Telegram")
print("2. Отправьте в чат любое сообщение")
print("3. Chat ID появится здесь автоматически")
print("\nДля выхода: Ctrl+C")
print("="*60 + "\n")

chat_ids = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех сообщений"""
    chat = update.effective_chat
    message = update.message
    
    if chat.id not in chat_ids:
        chat_ids[chat.id] = True
        
        print("\n" + "="*60)
        print(f"✅ ПОЛУЧЕН CHAT ID!")
        print("="*60)
        print(f"Chat ID: {chat.id}")
        print(f"Тип чата: {chat.type}")
        if chat.title:
            print(f"Название: {chat.title}")
        print("\n📋 ДОБАВЬТЕ В config.py:")
        print("-"*60)
        print(f"""
    {chat.id}: {{
        'partner_name': '{chat.title or "Тестовый партнер"}',
        'queue': 'PART1',
    }},
""")
        print("="*60 + "\n")

async def main():
    """Запуск бота"""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Обработчик всех сообщений
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    
    # Запуск
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✅ Завершено!")
