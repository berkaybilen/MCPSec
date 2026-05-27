# MCPSec Demo Tests

Bu klasordeki test altyapisi tamamen local calisir. Dis servis, OAuth, Gmail MCP
ya da Claude CLI gerekmez.

## Ne test ediyor?

- guvenli tool call'larin gecmesi
- prompt injection response flag'lenmesi
- credential leak redaction
- path traversal request block
- `U -> S -> E` zincirinin block edilmesi

## Hızlı calistirma

```bash
./.venv/bin/python -m pytest -q tests/test_demo_scenarios.py
```

## Senaryo raporu ile calistirma

```bash
./.venv/bin/python tests/runner.py
```

Tek bir senaryo:

```bash
./.venv/bin/python tests/runner.py DEMO-005
```

## Bilesenler

- `tests/mock_mcp_server.py`
  Demo icin yerel stdio MCP backend
- `tests/harness.py`
  Proxy process'ini baslatan ve MCP mesajlarini gonderen test harness
- `tests/test_demo_scenarios.py`
  Pytest senaryolari
- `tests/scenarios/DEMO-*.yaml`
  Senaryo tanimlari

## Not

`tests/scenarios/PI-001_email_injection.yaml` dosyasi eski dis-bagimli ornek
senaryodur. Varsayilan test akisinin parcasi degildir.
