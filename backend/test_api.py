"""Quick API test script."""
import urllib.request
import json
import sys

def get(url):
    try:
        r = urllib.request.urlopen(url)
        return json.loads(r.read()), r.status
    except Exception as e:
        return str(e), 0

endpoints = [
    "http://localhost:8000/api/health",
    "http://localhost:8000/api/dashboard/summary",
    "http://localhost:8000/api/dashboard/leakage-breakdown",
    "http://localhost:8000/api/dashboard/high-priority?limit=10",
    "http://localhost:8000/api/dashboard/response-leakage",
    "http://localhost:8000/api/dashboard/recovery-pipeline",
]

for url in endpoints:
    print(f"\n=== GET {url} ===")
    data, status = get(url)
    print(f"Status: {status}")
    if isinstance(data, dict):
        print(json.dumps(data, indent=2, default=str)[:500])
    elif isinstance(data, list):
        print(f"List with {len(data)} items")
        if data:
            print(json.dumps(data[0], indent=2, default=str)[:500])
    else:
        print(str(data)[:500])
