# mock-perfilamiento — Perfilamiento simulado para EXP-02

WireMock haciendo de servicio de **Perfilamiento**. `svc-cotizacion` (en modo `http`)
le pega a `POST /perfiles`; acá inyectamos las fallas del spec de EXP-02.

## Levantar

```bash
docker compose -f mock-perfilamiento/docker-compose.yml up --build
```

- `svc-cotizacion` → <http://localhost:8080>
- WireMock → <http://localhost:8089> (admin en `/__admin`)

Arranca en modo **normal**: `POST /perfiles` responde `200` en ~40 ms con un perfil válido
(`mappings/perfil-normal.json`).

## Sin Docker (más rápido para probar)

```bash
docker run --rm -p 8089:8080 -v "${PWD}/mock-perfilamiento/mappings:/home/wiremock/mappings:ro" wiremock/wiremock:3.10.0
```

En otra terminal, con el venv activo:

```bash
COT_ADAPTERS=http uvicorn app.main:app --port 8080
```

(`COT_PERFILAMIENTO_BASE_URL` ya apunta a `http://localhost:8089` por defecto.)

## Cambiar de escenario (en caliente, sin reiniciar)

Cada escenario es un mapping que gana por prioridad. Aplicar uno:

```bash
curl -s -X POST http://localhost:8089/__admin/mappings --data @mock-perfilamiento/escenarios/lento-timeout.json
```

Volver a **normal**:

```bash
curl -s -X POST http://localhost:8089/__admin/mappings/reset
```

| Escenario | Archivo | Qué hace | Efecto esperado en svc-cotizacion |
|---|---|---|---|
| Normal | (por defecto) | 200 en ~40 ms | cotización **personalizada** |
| Lento leve | `escenarios/lento-leve.json` | 200 en 300 ms | personalizada, pero p95 E2E sube |
| Lento (timeout) | `escenarios/lento-timeout.json` | 200 en 900 ms | timeout 700 ms → **fallback** a tarifa estándar |
| Error 503 | `escenarios/error-503.json` | 503 | reintento (si hay) → **fallback** |
| Error 500 | `escenarios/error-500.json` | 500 | **fallback** |
| Desconexión | `escenarios/desconexion.json` | corta la conexión | **fallback**; tras 5 fallos abre el circuit breaker |

## Verificación rápida

```bash
curl -s -X POST http://localhost:8080/cotizaciones \
  -H "X-Cliente-Id: cli-123" -H "content-type: application/json" \
  -d '{"datosCredito":{"valorCredito":150000000,"plazoMeses":240,"edad":38,"entidadAcreedora":"Banco X","saldoInsoluto":140000000},"cuestionarioHabitos":{"consumeTabaco":false,"actividadFisica":"REGULAR","condicionesPreexistentes":false,"dependientesEconomicos":2}}'
```

Con escenario normal → `"personalizado": true`. Con cualquier escenario degradado → `"personalizado": false`.
