# MCPSec

MCP (Model Context Protocol) sunucuları için güvenlik proxy'si. Tool call'ları ve response'ları gerçek zamanlı analiz eder, şüpheli aktiviteyi tespit eder ve engeller.

## Gereksinimler

| Bileşen | Minimum Sürüm | Notlar |
|---|---|---|
| Python | 3.11+ | 3.9/3.10 çalışmaz |
| Node.js | 18+ | Dashboard ve MCP backend'leri için |
| npm | 8+ | Dashboard bağımlılıkları için |

## Kurulum

### 1. Python ortamı

```bash
cd mcpsec/
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
```

`sentence-transformers` isteğe bağlıdır. Yüklü değilse Toxic Flow semantik benzerlik skoru atlanır, sistem yine de çalışır.

### 2. Dashboard

```bash
cd dashboard/
npm install
```

---

## Çalıştırma

### Proxy + API

```bash
cd mcpsec/
source .venv/bin/activate
python -m mcpsec --config ../mcpsec-config.yaml
```

Proxy `stdio` üzerinden dinler, REST API `localhost:8080` üzerinde açılır.

**Seçenekler:**

```
--config PATH         Config dosyası (default: mcpsec-config.yaml)
--log-level LEVEL     DEBUG / INFO / WARNING / ERROR (default: INFO)
--log-file PATH       Log dosyasına yaz (Claude Code ile kullanım için)
--no-api              REST API'yi başlatma
--no-backends         Backend process'lerini başlatma (API-only mod)
```

### Dashboard

```bash
cd dashboard/
npm run dev
```

Tarayıcıda `http://localhost:5173` aç.

> Proxy'nin çalışıyor olması gerekir. Dashboard, API üzerinden veri çeker ve WebSocket üzerinden canlı event alır.

---

## Yapılandırma

Ana dosya: `mcpsec-config.yaml`

```yaml
backends:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

enforcement:
  default_mode: alert      # block | alert | log
  rules_file: rules.yaml   # Per-flag kural overrides

chain_tracking:
  enabled: true
  normal_window_size: 10   # Son N call izlenir (NORMAL modda)
  policies:
    USE:
      on_u_seen: LOG
      on_us_seen: ALERT
      on_complete: BLOCK   # U→S→E tamamlandığında engelle

session:
  alert_timeout_minutes: 30
```

### Enforcement kuralları (`rules.yaml`)

Her flag için ayrı mod ve redact ayarı tanımlanabilir:

```yaml
- id: rule-credential-leak
  flag: credential_leak
  mode: alert
  redact: true        # Değeri [REDACTED] ile maskeler
  enabled: true
```

---

## Mimari

```
Claude Code / LLM Agent
        ↓ (stdio)
   MCPSec Proxy
        ↓
  ┌─────────────────────────────┐
  │  1. Regex Filter            │  Path traversal, SQL injection,
  │                             │  credential leak, prompt injection
  ├─────────────────────────────┤
  │  2. Chain Tracker           │  U→S→E label zinciri takibi
  │                             │  (Untrusted → Sensitive → External)
  ├─────────────────────────────┤
  │  3. Enforcement Engine      │  BLOCK / ALERT / LOG / redact
  └─────────────────────────────┘
        ↓
  Backend MCP Servers (filesystem, gmail, vb.)
```

**Startup analizi:**

```
Tool Discovery → Toxic Flow Analyzer → Chain Tracker (label map yüklenir)
```

---

## Dashboard

`http://localhost:5173` adresinde 4 ekran:

| Ekran | İçerik |
|---|---|
| **Monitor** | Canlı event akışı (WebSocket), session listesi, chain state, routing table |
| **Threats** | Toxic Flow sonuçları — tehlikeli U→S→E path'leri, tool label'ları |
| **Rules** | Enforcement kuralları — ekle, aç/kapat, sil |
| **Backends** | Backend sunucu listesi, Rescan butonu |

**Monitor — Event renkleri:**

| Renk | Karar |
|---|---|
| Kırmızı | BLOCK — tool call engellendi |
| Sarı | ALERT — şüpheli, kaydedildi |
| Mavi | LOG — kaydedildi, geçti |
| Gri | PASS — temiz |

---

## API

Proxy çalışırken `http://localhost:8080` üzerinde:

```
GET  /api/sessions                        Oturumlar
GET  /api/sessions/{id}/chain-state       Zincir takip durumu
GET  /api/events                          Eventler (filtreli)
GET  /api/events/stats                    Özet istatistikler
GET  /api/routing-table                   Tool → backend eşleşmesi
GET  /api/toxic-flow                      Toxic Flow analiz sonucu
GET  /api/rules                           Enforcement kuralları
POST /api/rules                           Kural ekle
PUT  /api/rules/{id}                      Kural güncelle
DELETE /api/rules/{id}                    Kural sil
GET  /api/backends                        Backend listesi
POST /api/rescan                          Yeniden tara
WS   /ws/events                           Canlı event stream
```

---

## Demo Testleri

Taşınabilir demo testleri ek bir servis, OAuth ya da Claude CLI gerektirmez.
Yerel bir mock MCP backend ile çalışır ve MCPSec'in request/response kontrolünü,
redaction davranışını ve chain blocking mantığını doğrular.

### Hızlı doğrulama

```bash
./.venv/bin/python -m pytest -q tests/test_demo_scenarios.py
```

### Senaryo çıktısı ile çalıştırma

```bash
./.venv/bin/python tests/runner.py
```

Örnek senaryolar:

- `DEMO-001` güvenli tool call
- `DEMO-002` prompt injection tespiti
- `DEMO-003` credential leak redaction
- `DEMO-004` path traversal block
- `DEMO-005` tehlikeli `U -> S -> E` zincirinin block edilmesi

### Dashboard ile demo akışı

1. Proxy + API'yi demo config ile başlat:

```bash
./.venv/bin/python -m mcpsec --config mcpsec-demo-config.yaml
```

2. Dashboard'ı aç:

```bash
cd dashboard/
npm run dev
```

3. Başka bir terminalde bir senaryo çalıştır:

```bash
./.venv/bin/python tests/runner.py DEMO-005
```

Dashboard üzerinde yeni session'ı, event akışını ve block kararını canlı görebilirsin.

---

## Gmail MCP (isteğe bağlı)

Gmail backend'ini kullanmak için OAuth kurulumu:

```bash
# 1. Google Cloud Console'dan OAuth credentials indir
mkdir -p ~/.gmail-mcp
cp gcp-oauth.keys.json ~/.gmail-mcp/

# 2. Yetkilendir (tarayıcı açılır)
npx @shinzolabs/gmail-mcp auth
```

`~/.gmail-mcp/credentials.json` oluştuktan sonra `mcpsec-config.yaml`'daki gmail backend aktif olur.
