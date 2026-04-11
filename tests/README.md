# MCPSec Test

## Kurulum

`test-mcp-config.json` dosyasındaki `command` ve `cwd` alanları absolute path kullanır. Klonladıktan sonra kendi path'inize göre guncelleyin:

```json
"command": "/PROJE/YOLU/.venv/bin/python",
"cwd": "/PROJE/YOLU"
```

## Gmail MCP Kurulumu

Her kullanicinin bir kez yapmasi gerekir.

### 1. Google Cloud (proje sahibi bir kez yapar)

- [Google Cloud Console](https://console.cloud.google.com/) -> yeni proje olustur
- Gmail API'yi etkinlestir
- OAuth 2.0 Client ID olustur -> tur: "Desktop app"
- JSON'u indir, `~/.gmail-mcp/gcp-oauth.keys.json` olarak kaydet

### 2. OAuth yetkilendirme (her kullanici yapar)

```bash
mkdir -p ~/.gmail-mcp
cp gcp-oauth.keys.json ~/.gmail-mcp/gcp-oauth.keys.json

npx @shinzolabs/gmail-mcp auth
```

Scope'lar: `gmail.readonly` + `gmail.send` (test senaryolari icin ikisi de lazim).

Basarili olursa `~/.gmail-mcp/credentials.json` olusur.

### 3. Config

`mcpsec-config.yaml`'da Gmail backend zaten tanimli. Ekstra bir sey yapmana gerek yok.

## Test Calistirma

```bash
python tests/runner.py PI-001
```

Senaryolar `tests/scenarios/` altinda YAML dosyalari olarak tanimlidir.
