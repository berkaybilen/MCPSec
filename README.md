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

## Gmail MCP Kurulumu (test ortamı)

Her kullanıcının bir kez yapması gerekir.

### 1. Google Cloud (proje sahibi bir kez yapar)

- [Google Cloud Console](https://console.cloud.google.com/) → yeni proje oluştur
- Gmail API'yi etkinleştir
- OAuth 2.0 Client ID oluştur → tür: "Desktop app"
- JSON'u indir, `~/.gmail-mcp/gcp-oauth.keys.json` olarak kaydet

### 2. OAuth yetkilendirme (her kullanıcı yapar)

```bash
# gcp-oauth.keys.json dosyasını kopyala (proje sahibinden al)
mkdir -p ~/.gmail-mcp
cp gcp-oauth.keys.json ~/.gmail-mcp/gcp-oauth.keys.json

# yetkilendir — tarayıcı açılır, Gmail erişimine izin ver
npx @shinzolabs/gmail-mcp auth
```

Scope'lar: `gmail.readonly` + `gmail.send` (test senaryoları için ikisi de lazım).

Başarılı olursa `~/.gmail-mcp/credentials.json` oluşur.

### 3. Config

`mcpsec-config.yaml`'da Gmail backend zaten tanımlı. Ekstra bir şey yapmana gerek yok.

## Test

`test-mcp-config.json` dosyasındaki `command` ve `cwd` alanları absolute path kullanır. Klonladıktan sonra kendi path'inize göre güncelleyin:

```json
"command": "/PROJE/YOLU/.venv/bin/python",
"cwd": "/PROJE/YOLU"
```

```bash
python tests/runner.py --scenario PI-001
```

Detaylar: [docs/roadmap.md](docs/roadmap.md)
