"""Получить свой логин в Яндекс.Трекере"""
import os
from dotenv import load_dotenv
import requests

load_dotenv()

TOKEN = os.getenv('YANDEX_TRACKER_TOKEN')
ORG_ID = os.getenv('YANDEX_ORG_ID')

headers = {
    'Authorization': f'OAuth {TOKEN}',
    'X-Org-ID': ORG_ID,
    'Content-Type': 'application/json'
}

print("\n" + "="*60)
print("  ПОЛУЧЕНИЕ ИНФОРМАЦИИ О ТЕКУЩЕМ ПОЛЬЗОВАТЕЛЕ")
print("="*60 + "\n")

# Получаем информацию о себе
url = 'https://api.tracker.yandex.net/v2/myself'
response = requests.get(url, headers=headers, timeout=10)

if response.status_code == 200:
    user_info = response.json()
    
    print("✅ Информация о тебе в Яндекс.Трекере:\n")
    print(f"🆔 ID:       {user_info.get('id')}")
    print(f"👤 Login:    {user_info.get('login')}")
    print(f"📧 Email:    {user_info.get('email')}")
    print(f"📝 Display:  {user_info.get('display')}")
    print(f"🌐 Cloud UID: {user_info.get('cloudUid')}")
    print(f"📍 PassportUID: {user_info.get('passportUid')}")
    
    print("\n" + "="*60)
    print("  ИСПОЛЬЗУЙ ЭТОТ ЛОГИН В config.py:")
    print("="*60)
    print(f"\nDEFAULT_PARTNER_ASSIGNEE = '{user_info.get('login')}'")
    print(f"\nPARTNER_ASSIGNEES = {{")
    print(f"    '2': '{user_info.get('login')}',")
    print(f"    '3': '{user_info.get('login')}',")
    print(f"}}")
    print("\n" + "="*60 + "\n")
    
else:
    print(f"❌ Ошибка {response.status_code}: {response.text}\n")
