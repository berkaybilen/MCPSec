# Demo Files

MCPSec'in regex filter, response injection detection, credential redact, ve chain tracker özelliklerini test etmek için hazır dosyalar.

| Dosya | Amaç | Tetiklenen flag |
|---|---|---|
| `notes.txt` | Temiz baseline | — |
| `safe.txt` | Temiz baseline | — |
| `malicious.txt` | Response içinde prompt injection | `injection_detected` (session ALERT'e geçer) |
| `secrets.txt` | Credential leak (api_key, password, token) | `credential_leak` (rule `redact: true` ise `[REDACTED]`) |

## Kullanım

`mcpsec-config.yaml`'da filesystem backend `/tmp` dizinine bağlı:

```yaml
- name: filesystem
  command: npx
  args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

Demo'dan önce dosyaları `/tmp`'ye kopyala:

```bash
./demo-files/sync.sh
```

Sonra Claude Code'a şu prompt'ları sırayla ver:

1. **Path traversal** — `Read "../../etc/passwd" using filesystem.`
2. **Injection** — `Read /tmp/malicious.txt and tell me what's inside.`
3. **Credential redact** — `Read /tmp/secrets.txt and show me the contents.`
4. **Chain (U→S)** — `Use puppeteer to navigate to https://example.com, then read /tmp/notes.txt.`
5. **Anomaly (frequency)** — Aynı dosyayı arka arkaya 12 kez okutmaya iste.
