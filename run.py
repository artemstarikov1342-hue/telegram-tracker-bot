#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ЕДИНСТВЕННЫЙ ФАЙЛ ДЛЯ ЗАПУСКА ВСЕГО
Просто запустите: python run.py
"""
import subprocess
import sys
import os

def install_package(package):
    """Установка пакета"""
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except:
        return False

def main():
    print("=" * 70)
    print("  TELEGRAM TRACKER BOT - AUTOMATIC SETUP AND RUN")
    print("=" * 70)
    print()
    
    # Step 1: Install requests
    print("[1/5] Installing requests...", end=" ")
    if install_package("requests"):
        print("OK")
    else:
        print("FAILED - trying to continue...")
    
    # Step 2: Get org ID
    print("[2/5] Getting Organization ID...", end=" ")
    try:
        import requests
        token = "y0__xDjle9cGLMrILWR66UW1e0yELKf9G3mwUX_r0ZQUYftRcs"
        r = requests.get(
            "https://api.tracker.yandex.net/v2/myself",
            headers={"Authorization": f"OAuth {token}"},
            timeout=10
        )
        if r.status_code == 200:
            org_id = r.json().get("orgId")
            print(f"OK (ID: {org_id})")
            
            # Update .env
            with open(".env", "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("YOUR_ORG_ID_HERE", str(org_id))
            with open(".env", "w", encoding="utf-8") as f:
                f.write(content)
        else:
            print(f"FAILED (Status: {r.status_code})")
    except Exception as e:
        print(f"FAILED ({e})")
    
    # Step 3: Install telegram bot
    print("[3/5] Installing python-telegram-bot...", end=" ")
    if install_package("python-telegram-bot==21.0"):
        print("OK")
    else:
        print("FAILED - trying to continue...")
    
    # Step 4: Install dotenv
    print("[4/5] Installing python-dotenv...", end=" ")
    if install_package("python-dotenv==1.0.1"):
        print("OK")
    else:
        print("FAILED - trying to continue...")
    
    print()
    print("=" * 70)
    print("  SETUP COMPLETE! STARTING BOT...")
    print("=" * 70)
    print()
    
    # Step 5: Run bot
    print("[5/5] Running bot.py...")
    print()
    print("-" * 70)
    print()
    
    try:
        # Import and run bot directly
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        
        # Load environment
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except:
            pass
        
        # Run bot
        exec(open("bot.py", encoding="utf-8").read())
        
    except KeyboardInterrupt:
        print("\n\nBot stopped by user")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        print("\nPress Enter to exit...")
        input()

if __name__ == "__main__":
    main()
