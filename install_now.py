import subprocess
import sys

print("Installing packages...")

# Install each package
packages = [
    "requests",
    "python-telegram-bot==21.0", 
    "python-dotenv==1.0.1"
]

for pkg in packages:
    print(f"Installing {pkg}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

print("\nDone! Now getting org ID...")

# Get org ID
import requests

token = "y0__xDjle9cGLMrILWR66UW1e0yELKf9G3mwUX_r0ZQUYftRcs"
response = requests.get(
    "https://api.tracker.yandex.net/v2/myself",
    headers={"Authorization": f"OAuth {token}"},
    timeout=10
)

if response.status_code == 200:
    org_id = response.json().get("orgId")
    print(f"Org ID: {org_id}")
    
    # Update .env
    with open(".env", "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("YOUR_ORG_ID_HERE", str(org_id))
    with open(".env", "w", encoding="utf-8") as f:
        f.write(content)
    
    print("Setup complete!")
else:
    print(f"Error: {response.status_code}")

print("\nNext: Edit config.py and add your partners")
print("Then run: python bot.py")
