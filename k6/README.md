# k6 — EXP-02 (resiliencia)

Carga `POST /cotizaciones` a ritmo constante y mide la latencia E2E y cuántas
respuestas salieron degradadas (precio estándar).

## Requisitos

- k6 instalado (`winget install k6` · `choco install k6` · <https://k6.io/docs/get-started/installation/>)
- El montaje corriendo:
  ```
  docker compose -f mock-perfilamiento/docker-compose.yml up --build
  ```

## Correr

```
k6 run k6/exp-02-resiliencia.js
```

Config por env: `-e URL_BASE=http://localhost:8080 -e RATE=30 -e DURACION=3m`.

## Qué mide (lo que k6 imprime al final)

| Métrica | Qué es | Objetivo |
|---|---|---|
| `cotizacion_latencia_e2e` p(95) / p(99) | latencia de la cotización de punta a punta | p95 ≤ 400 ms, p99 ≤ 800 ms (BITS-80) |
| `http_req_failed` | % de respuestas que NO fueron 201 | ~0 — el servicio no debe romperse |
| `cotizacion_degradadas` / `cotizacion_personalizadas` | conteo por tipo de respuesta | normal: 0 degradadas |
| `http_reqs` (rate) | throughput real | debe ser el mismo en todas las corridas |

Para archivar los datos crudos: `k6 run --out json=resultados/escenario-N.json k6/exp-02-resiliencia.js`

## Procedimiento — los 6 escenarios (D6)

**Entre cada escenario:** `curl -X POST http://localhost:8089/__admin/mappings/reset`
y reiniciá el servicio para que el circuit breaker vuelva a cerrado:
```
docker compose -f mock-perfilamiento/docker-compose.yml restart svc-cotizacion
```

| # | Escenario | Setup (después del reset) | Qué esperás ver |
|---|---|---|---|
| 1 | Normal | — | p95 bajo, 0 degradadas |
| 2 | Lento leve (300 ms) | `curl -X POST http://localhost:8089/__admin/mappings --data @mock-perfilamiento/escenarios/lento-leve.json` | p95 sube pero < 400 ms; 0 degradadas |
| 3 | Lento timeout (900 ms) | `... --data @mock-perfilamiento/escenarios/lento-timeout.json` | primeras ~5 req a 700 ms, luego el circuito abre → rápido; casi todo degradado |
| 4 | Error 503 | `... --data @mock-perfilamiento/escenarios/error-503.json` | todo degradado; p95 bajo (falla rápido) |
| 5 | Error 500 | `... --data @mock-perfilamiento/escenarios/error-500.json` | todo degradado; p95 bajo |
| 6 | Desconexión | `... --data @mock-perfilamiento/escenarios/desconexion.json` | todo degradado; el circuito abre |

Anotá para cada uno: **p95, p99, % degradadas, tasa de error**. Esa tabla es la
"interpretación de resultados" de EXP-02 en Confluence.

### Opcional — aislar timeout vs circuit breaker (escenario 3)

Corré `lento-timeout` dos veces:
- con `COT_CIRCUIT_FAIL_MAX=5` (default) → se ve el circuit breaker actuar
- con `COT_CIRCUIT_FAIL_MAX=999999` → se ve solo el costo de timeout + fallback (700 ms por request)

La diferencia entre las dos p95 muestra cuánto aporta cada mecanismo.
