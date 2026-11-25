# Bao Agent Demo

> Public portfolio project by Josef González (`@ZephBuilds`). All messages, identities, IDs, and outputs
> in this repository are fictional and sanitized.

Agente público y sanitizado que lee mensajes, identifica tareas pendientes y genera un reporte JSON validado. El proyecto convierte una operación real de Bao/OpenClaw en una demostración reproducible sin exponer conversaciones, credenciales ni datos privados.

## Problema que resuelve

Los compromisos escritos en canales de trabajo se pierden entre conversaciones. Este agente los transforma en tareas estructuradas y deja evidencia auditable de cada etapa, incluidos latencia, errores, tokens y costo estimado.

## Lo que demuestra

- Integración read-only con Discord mediante API REST.
- Extracción estructurada con Pydantic y Anthropic, con modo offline reproducible.
- API FastAPI y CLI sobre el mismo servicio de dominio.
- Observabilidad JSONL por etapa: estado, latencia, volumen, tokens y costo.
- Validación, manejo explícito de errores y pruebas sin dependencias externas.
- Tratamiento del contenido de mensajes como datos no confiables.
- Extracción offline de fechas relativas en español (`hoy`, `mañana`, días de la semana).
- Pipeline de CI y contenedor Docker reproducible.
- Gate de vulnerabilidades conocidas en dependencias de runtime con `pip-audit`.

## Arquitectura

For an English portfolio overview, see the [case study](docs/case-study.md) and
the [architecture and trust boundaries](docs/architecture.md).

```text
Fixture JSON ─┐
              ├─> MessageSource ─> Agent service ─> TaskExtractor ─> TaskReport JSON
Discord API ──┘                         │                  │
                                       └──── JSONL trace ─┘
                                             latency · errors · tokens · cost
```

## Inicio rápido

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python cli.py
```

El modo predeterminado usa datos ficticios y reglas deterministas, por lo que no necesita token ni acceso de red. El reporte queda en `output/report.json` y las trazas en `logs/trace.jsonl`.

Salida resumida esperada:

```json
{
  "tasks": [
    {
      "title": "preparar el resumen del incidente para hoy; es urgente.",
      "owner": "Ana",
      "due_date": "2026-11-02",
      "priority": "high",
      "source_message_id": "demo-001"
    }
  ],
  "messages_analyzed": 5,
  "extractor": "rules-v1"
}
```

Si el sistema no dispone de `python3-venv`, puede verificarse sin `sudo` instalando dependencias dentro del propio proyecto:

```bash
python3 -m pip install --target .deps -r requirements-dev.txt
PYTHONPATH=.deps:. python3 -m pytest -q
PYTHONPATH=.deps:. python3 cli.py
```

Para levantar la API:

```bash
.venv/bin/uvicorn app.main:app --reload
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/runs -H 'content-type: application/json' -d '{"source":"fixture","extractor":"rules","limit":5}'
```

La documentación interactiva queda disponible en `http://127.0.0.1:8000/docs`.

### Contrato de errores de `POST /runs`

Los errores operacionales tienen un cuerpo estable y no incluyen mensajes internos, secretos, IDs,
rutas, URLs ni tracebacks:

- Configuración o entrada incompleta detectada al iniciar el run: HTTP `400` con
  `{"detail":{"code":"invalid_run_configuration"}}`.
- Fallo de red o del proveedor reportado por `httpx`: HTTP `502` con
  `{"detail":{"code":"upstream_provider_unavailable"}}`.

### Docker

La imagen ejecuta la API con un usuario no privilegiado fijo (`10001:10001`) y deja los
artefactos de runtime bajo esa misma propiedad.

```bash
docker build -t bao-agent-demo .
docker run --rm -p 8000:8000 bao-agent-demo
```

## Uso opcional con Anthropic

```bash
cp .env.example .env
# Añadir ANTHROPIC_API_KEY únicamente en .env
.venv/bin/python cli.py --extractor anthropic
```

## Uso opcional con Discord

El adaptador Discord solo ejecuta `GET /channels/{channel_id}/messages`. Reintenta de forma acotada respuestas HTTP 429 y 5xx con backoff limitado; los demás errores 4xx fallan inmediatamente. La traza JSONL emite un evento estructurado por intento y otro final con intento, máximo, estado HTTP y decisión de reintento. Estos eventos usan campos permitidos y nunca incluyen token, ID de canal, URL, payload ni mensajes de excepción. Use un bot de pruebas con acceso a un canal ficticio y permisos mínimos de lectura.

### Política operacional Discord y evidencia

| Señal del proveedor | Comportamiento verificado | Test ejecutable |
| --- | --- | --- |
| 2xx con respuesta válida | Procesa la lectura en un intento, sin espera, y registra eventos sanitizados en orden. | `test_discord_run_persists_sanitized_events_in_operation_order` |
| 2xx con respuesta inválida | No reintenta; registra `invalid_response` y propaga el error de decodificación o tipo. | `test_discord_run_traces_invalid_200_response_once_without_private_data` |
| 4xx permanente | Falla en el primer intento, sin espera, y no expone datos privados en la traza. | `test_discord_run_traces_permanent_4xx_once_without_private_data` |
| 429 | Reintenta con backoff acotado y puede continuar al recibir después una respuesta válida. | `test_discord_run_retries_429_with_capped_backoff_and_sanitized_trace` |
| 5xx transitorio | Reintenta con backoff y puede recuperarse al recibir después una respuesta válida. | `test_discord_run_recovers_from_transient_5xx_with_sanitized_trace` |
| Error de transporte | No reintenta; registra el fallo sanitizado y propaga el error de conexión. | `test_discord_run_traces_transport_error_once_without_private_data` |

Para ejecutar únicamente esta matriz de resiliencia:

```bash
.venv/bin/pytest -q \
  tests/test_service.py::test_discord_run_persists_sanitized_events_in_operation_order \
  tests/test_service.py::test_discord_run_traces_invalid_200_response_once_without_private_data \
  tests/test_service.py::test_discord_run_traces_permanent_4xx_once_without_private_data \
  tests/test_service.py::test_discord_run_retries_429_with_capped_backoff_and_sanitized_trace \
  tests/test_service.py::test_discord_run_recovers_from_transient_5xx_with_sanitized_trace \
  tests/test_service.py::test_discord_run_traces_transport_error_once_without_private_data
```

```bash
.venv/bin/python cli.py --source discord --channel-id ID_DE_CANAL
```

Las variables vacías `DISCORD_BOT_TOKEN` y `DISCORD_CHANNEL_ID` de `.env.example` son placeholders:
complete solo el `.env` local, que está excluido del repositorio.

Nunca incluya `.env`, tokens, IDs privados ni trazas de conversaciones reales en el repositorio.

## Verificación

```bash
.venv/bin/python scripts/preflight.py
.venv/bin/ruff check .
.venv/bin/pytest -q
```

La [matriz de amenazas y controles](SECURITY.md) se puede verificar completa, sin red ni
secretos, con un solo comando fail-fast desde la raíz del proyecto:

```bash
python3 scripts/security_check.py
```

El comando ejecuta primero el preflight y, solo si pasa, los contratos de la matriz, el
contenedor y CI usando el mismo intérprete de Python.

CI ejecuta exactamente el mismo comando canónico local: `python3 scripts/security_check.py`.

El preflight local no usa red ni dependencias externas: falla si un archivo publicable contiene
credenciales o IDs reales de Discord, si aparecen `.env` o salidas generadas no ignoradas, o si el
README pierde los placeholders sanitizados de configuración. También examina tests y fixtures; una
credencial ficticia que deliberadamente imite una real debe llevar `preflight: allow-test-data` en
la misma línea para que la excepción quede visible en revisión.

En CI, después del preflight y antes de construir la imagen, `pip-audit` consulta vulnerabilidades
conocidas para `requirements.txt`. El gate usa su código de salida predeterminado (reforzado con
`--strict`), por lo que bloquea el build si encuentra una vulnerabilidad o no puede completar la
auditoría; no necesita secretos. El test contractual del workflow es offline y fija este orden sin
consultar servicios externos.

Los tests cubren extracción, fechas, validación, trazas, prompt injection, API, reintentos Discord y el rechazo de una ejecución Discord incompleta. No llaman APIs externas, no esperan tiempos reales ni requieren secretos.

Una salida y una traza sanitizadas están versionadas en `examples/` para revisión rápida.

## Decisiones y límites

- El modo `rules` permite revisar el proyecto sin pagar ni crear cuentas.
- El modo `anthropic` demuestra salida tipada; el costo registrado es una estimación, no una factura.
- La demo no publica tareas, no responde mensajes y no modifica Discord.
- Para producción faltan persistencia duradera, autenticación de API, colas y métricas agregadas.

## Próxima iteración

Publicar una demo desplegada y añadir capturas o un GIF breve. El RAG queda fuera de esta pieza para mantenerla enfocada en extracción estructurada y observabilidad.
