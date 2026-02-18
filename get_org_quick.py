import requests
r = requests.get("https://api.tracker.yandex.net/v2/myself", headers={"Authorization": "OAuth y0__xDjle9cGLMrILWR66UW1e0yELKf9G3mwUX_r0ZQUYftRcs"}, timeout=10)
if r.status_code == 200:
    org_id = r.json().get("orgId")
    print(org_id)
    with open(".env", "r", encoding="utf-8") as f: content = f.read()
    content = content.replace("YOUR_ORG_ID_HERE", str(org_id))
    with open(".env", "w", encoding="utf-8") as f: f.write(content)
    print("OK")
