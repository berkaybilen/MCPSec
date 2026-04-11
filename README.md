# MCPSec

MCP (Model Context Protocol) sunucuları için güvenlik proxy'si. Tool call'ları ve response'ları analiz eder, şüpheli aktiviteyi tespit eder.

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Node.js 18+ gerekli (MCP backend'leri için).

## Çalıştırma

```bash
python3 -m mcpsec.main --config mcpsec-config.yaml
```

Proxy + API aynı process'te başlar. API default `localhost:8080`.

## Test

Test senaryoları ve çalıştırma talimatları için: [tests/README.md](tests/README.md)
