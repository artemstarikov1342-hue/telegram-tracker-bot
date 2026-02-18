import requests
token = "y0__xDjle9cGLMrILWR66UW1e0yELKf9G3mwUX_r0ZQUYftRcs"
r = requests.get("https://api.tracker.yandex.net/v2/myself", headers={"Authorization": f"OAuth {token}"})
if r.status_code == 200:
    org_id = r.json().get("orgId")
    print(f"ORG_ID={org_id}")
    with open(".env", "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("YOUR_ORG_ID_HERE", str(org_id))
    with open(".env", "w", encoding="utf-8") as f:
        f.write(content)
    print("Updated!")
else:
    print(f"Error: {r.status_code}")
    print(r.text)
