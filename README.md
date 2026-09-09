# svc-cotizacion

Servicio síncrono de **Cotización y Rating** (pod en GKE). Calcula la prima y las
condiciones de cobertura de un producto de seguro en línea y devuelve una cotización
con vigencia limitada.

- Historia funcional: **BITS-95** "Solicitar cotización".
- NFR asociados: **BITS-79** (latencia), **BITS-81** (escalabilidad), **BITS-124** (disponibilidad).
- Molde de arquitectura: `bff-web` (hexagonal — `domain` / `ports` / `services` / `adapters`).

## Correr en local

Requiere Python 3.12+.

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash);  Linux/Mac: source .venv/bin/activate
pip install -e ".[dev]"

uvicorn app.main:app --reload --port 8080
```

- Salud: <http://localhost:8080/health> · Docs: <http://localhost:8080/docs>

## Pruebas

```bash
pytest
pytest --cov=app --cov-report=term-missing    # con cobertura (gate 80%)
```

## Variables de entorno (prefijo `COT_`)

| Variable | Default | Notas |
|---|---|---|
| `COT_ADAPTERS` | `fake` | `fake` \| `sql` \| `http` — se implementan por fase |
| `COT_ENVIRONMENT` | `local` | |

## Estado

Fase A (esqueleto). Solo expone `/health`. La ruta `POST /v1/cotizaciones` y el resto
se agregan en las fases siguientes.
