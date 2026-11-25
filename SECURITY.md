# Matriz breve de amenazas y controles

Esta matriz delimita los riesgos cubiertos por la demo y enlaza cada control con una
prueba contractual ejecutable. Todos los comandos de evidencia de la tabla se ejecutan
offline, sin credenciales ni variables secretas.

| ID | Amenaza | Control | Evidencia ejecutable offline |
| --- | --- | --- | --- |
| `prompt-injection` | Instrucciones hostiles dentro del contenido de entrada intentan cambiar el comportamiento del agente. | El contenido se trata como datos no confiables y la extracción por reglas descarta instrucciones en vez de ejecutarlas. | `python3 -m pytest -q tests/test_service.py::test_prompt_injection_message_is_not_executed_or_extracted` |
| `sensitive-data` | Credenciales, identificadores privados o salidas generadas terminan en artefactos publicables. | El preflight recorre archivos versionables, detecta secretos plausibles y exige placeholders y exclusión de artefactos de runtime. | `python3 -m pytest -q tests/test_preflight.py` |
| `least-privilege` | El proceso del contenedor obtiene permisos de root o propiedad amplia sobre sus archivos. | La imagen crea un UID/GID fijo no privilegiado, copia los archivos con esa propiedad y cambia de usuario antes del comando de runtime. | `python3 -m pytest -q tests/test_dockerfile.py::test_runtime_uses_fixed_non_root_user_with_owned_app_files` |
| `vulnerable-dependencies` | Una dependencia de runtime con vulnerabilidades conocidas llega al build. | CI ejecuta `pip-audit --strict` como gate bloqueante antes de construir la imagen, sin excepciones silenciosas. | `python3 -m pytest -q tests/test_ci_workflow.py::test_dependency_audit_is_a_blocking_gate_before_container_build` |
| `container-isolation` | El smoke test expone puertos o permite conectividad externa innecesaria. | CI inicia el contenedor sin publicar puertos y con `--network none`; comprueba salud únicamente desde dentro del contenedor y lo elimina al finalizar. | `python3 -m pytest -q tests/test_ci_workflow.py::test_container_smoke_gate_runs_once_between_build_and_pytest` |

La matriz describe controles verificables de esta demo; no sustituye una evaluación de
riesgos de producción ni afirma cubrir amenazas fuera de este alcance.
