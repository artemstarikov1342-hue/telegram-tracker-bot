#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Получение org_id и обновление .env"""
import requests

print("Получаю ID организации...")

token = "y0__xDjle9cGLMrILWR66UW1e0yELKf9G3mwUX_r0ZQUYftRcs"

try:
    response = requests.get(
        "https://api.tracker.yandex.net/v2/myself",
        headers={"Authorization": f"OAuth {token}"},
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        org_id = data.get("orgId")
        
        print(f"✓ ID организации получен: {org_id}")
        
        # Обновляем .env
        with open(".env", "r", encoding="utf-8") as f:
            content = f.read()
        
        content = content.replace("YOUR_ORG_ID_HERE", str(org_id))
        
        with open(".env", "w", encoding="utf-8") as f:
            f.write(content)
        
        print("✓ Файл .env обновлён!")
        print()
        print("Теперь запустите бота заново!")
        
    else:
        print(f"✗ Ошибка: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"✗ Ошибка: {e}")

input("\nНажмите Enter...")
