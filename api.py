import requests
import json

# FIX 1: was just the bare domain root ("https://erp-odoo.aala-tech.com"),
# which hits Odoo's WEBSITE homepage (CSRF-protected), not the REST API
# controller at all - that's why you got a full HTML "400: Bad Request /
# Session expired (invalid CSRF token)" page back instead of JSON. The
# actual endpoint is at /rest/login.
url = "https://erp-odoo.aala-tech.com/rest/login"

payload = json.dumps({
    # FIX 2: type='json' routes in Odoo expect the full JSON-RPC 2.0
    # envelope (jsonrpc + method + params), not just a bare "params" key
    # on its own.
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
        "username": "demo@aala-tech.com",
        "password": "demo@123",
        "db": "aala_tech_production",
    },
})
headers = {
    "Content-Type": "application/json",
}

response = requests.post(url, headers=headers, data=payload)

print(response.status_code)
print(response.text)