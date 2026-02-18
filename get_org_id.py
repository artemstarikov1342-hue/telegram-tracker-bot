"""
Скрипт для получения ID организации из Яндекс.Трекера
"""
import requests

token = "y0__xDjle9cGLMrILWR66UW1e0yELKf9G3mwUX_r0ZQUYftRcs"

headers = {
    'Authorization': f'OAuth {token}',
    'Content-Type': 'application/json'
}

try:
    print("Получаю информацию о пользователе...")
    response = requests.get(
        'https://api.tracker.yandex.net/v2/myself',
        headers=headers,
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        org_id = data.get('orgId')
        print(f"✓ ID организации: {org_id}")
        
        # Сохраняем в .env
        with open('.env', 'r', encoding='utf-8') as f:
            content = f.read()
        
        content = content.replace('YANDEX_ORG_ID=YOUR_ORG_ID_HERE', f'YANDEX_ORG_ID={org_id}')
        
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✓ ID организации сохранён в .env")
    else:
        print(f"✗ Ошибка: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"✗ Ошибка: {e}")
