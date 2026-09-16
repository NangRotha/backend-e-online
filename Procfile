# Render Procfile — ប្រើសម្រាប់ "New Web Service" (Manual) ឬបើ Render រក Procfile ឃើញ
#
# --workers 1        : ត្រូវការ Single Instance ព្រោះ WebSocket manager ស្ថិតក្នុង Memory
# --proxy-headers    : Render/Cloudflare ជា Reverse Proxy -> អាន X-Forwarded-* ត្រឹមត្រូវ
# --forwarded-allow-ips='*' : ទុកឱ្យ Proxy របស់ Render កំណត់ IP/Scheme ពិត
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips='*'
