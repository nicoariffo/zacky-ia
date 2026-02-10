# PLAN DE TRABAJO TÉCNICO
## MVP — Asistente IA para Soporte (Zendesk)

**Cliente:** E-commerce / Retail
**Sprint:** 4 semanas | 1 desarrollador full-time
**Fecha:** Febrero 2026 — v2.0 (supuestos resueltos)

---

## 1. Contexto y Supuestos Resueltos

Este plan de trabajo está construido sobre decisiones concretas, no supuestos. A continuación se documenta cada variable resuelta que condiciona la arquitectura, el alcance y los tiempos.

### 1.1 Variables Confirmadas

| Variable | Decisión | Impacto en el plan |
|----------|----------|--------------------|
| Fuente de datos | API de Zendesk (key disponible) | Se construye ingesta directa via API, no parser CSV. Backfill + incremental |
| Volumen de tickets | 5,000 a 50,000 tickets | Cabe en memoria para clustering. No se requiere infra distribuida (Spark). Embeddings procesables en horas, no días |
| Idioma | Solo español | Sin pipeline multilingüe. Embeddings y prompts optimizados para español. Sin detección de idioma |
| Infraestructura | GCP (proyecto existente) | BigQuery + Cloud Run + Cloud Storage. Sin setup de cuenta. Terraform directo |
| Equipo | 1 persona full-time | Plan secuencial estricto. Sin paralelización. Cada fase debe terminar antes de iniciar la siguiente |
| Deadline | 4 semanas | Scope agresivo. Se priorizan entregables de mayor valor. Se recortan nice-to-haves |
| Proveedor IA | OpenAI (key disponible) | text-embedding-3-small para embeddings. GPT-4o-mini para generación (costo/velocidad). GPT-4o para calidad si el budget lo permite |
| Destinatario | Cliente específico (e-commerce) | Prompts y políticas adaptados a retail: pedidos, envíos, devoluciones, pagos |
| Canales | Email + RRSS | Dos pipelines de limpieza distintos (email tiene firmas/quoted replies, RRSS es más corto y con jerga) |
| Tags existentes | Sí, pero inconsistentes | Tags como señal complementaria, no como fuente de verdad. El clustering semántico es el approach principal |
| UI esperada | Streamlit / dashboard simple | Sin React custom. Streamlit reduce tiempo de UI de 2 semanas a 3-4 días |
| Validación humana | 1-2 agentes del cliente | Se necesita coordinar sesión de etiquetado (semana 2) y validación de sugerencias (semana 3-4) |

> ⚠️ **Restricción crítica: 4 semanas / 1 persona**
> Este timeline requiere disciplina extrema en scope. Se definirán cortes explícitos en cada fase. Lo que no entre en 4 semanas pasa a backlog post-MVP, no se negocia durante el sprint.

---

## 2. Arquitectura Técnica Definitiva

### 2.1 Stack confirmado

| Capa | Tecnología | Justificación |
|------|------------|---------------|
| Lenguaje | Python 3.11+ | Ecosistema ML, FastAPI, Streamlit. Todo en un lenguaje |
| API | FastAPI | Async, tipado, docs auto-generadas. Liviano para 1 persona |
| Storage principal | BigQuery | Ya disponible en GCP. SQL para análisis. Sin administrar DB |
| Storage metadata | Cloud SQL (PostgreSQL) o Firestore | Para feedback, sesiones, estado de jobs. Evaluar según complejidad |
| Embeddings | OpenAI text-embedding-3-small | 1536 dims, $0.02/1M tokens. Para 50K tickets ~$2-5 total |
| Generación | GPT-4o-mini (default) + GPT-4o (calidad) | Mini para iteración rápida ($0.15/1M). 4o para producción ($2.50/1M) |
| Clustering | HDBSCAN + UMAP | No requiere definir K. Maneja ruido. UMAP mejora calidad |
| UI | Streamlit | Prototipado rápido, componentes built-in, deploy en Cloud Run |
| Hosting | Cloud Run | Serverless, auto-scale, sin ops. API + Streamlit como servicios separados |
| CI/CD | GitHub Actions | Build, test, deploy a Cloud Run automático |
| Observabilidad | Cloud Logging + BigQuery logs | Sin herramientas extra. Queries sobre logs en BQ |

### 2.2 Esquema de datos (BigQuery)

| Tabla | Campos principales | Fase |
|-------|-------------------|------|
| `raw_tickets` | ticket_id, subject, description, comments_json, created_at, updated_at, tags, channel, assignee, status, priority, requester_email | Fase 1 |
| `clean_tickets` | ticket_id, text_full, text_customer_only, text_agent_only, channel, word_count, has_pii_redacted | Fase 2 |
| `embeddings` | ticket_id, embedding_vector (FLOAT64 REPEATED), model_version, created_at | Fase 3 |
| `clusters` | ticket_id, cluster_id, distance_to_centroid, is_noise, umap_x, umap_y | Fase 3 |
| `intents` | intent_id, cluster_id, name, description, volume, avg_resolution_time, repetition_score, risk_level, composite_score, status (active/inactive) | Fase 3-4 |
| `suggestions` | suggestion_id, ticket_id, intent_id, response_text, confidence_score, similar_ticket_ids, prompt_version, created_at | Fase 5 |
| `feedback` | feedback_id, suggestion_id, ticket_id, agent_id, action (accept/edit/reject), edited_text, rejection_reason, created_at | Fase 6 |

### 2.3 Estructura del repositorio

| Directorio | Contenido |
|------------|-----------|
| `src/ingestion/` | zendesk_client.py, backfill.py, incremental.py |
| `src/processing/` | cleaner.py, pii_redactor.py, pipeline.py |
| `src/intents/` | embeddings.py, clustering.py, labeling.py, scoring.py |
| `src/generation/` | response_generator.py, prompt_manager.py, confidence.py |
| `src/api/` | main.py, routes/, models/, middleware/ |
| `src/ui/` | app.py (Streamlit), pages/ (multi-page) |
| `prompts/` | system.txt, intents/*.yaml (template + política por intent) |
| `infra/` | terraform/, Dockerfile.api, Dockerfile.ui, docker-compose.yml |
| `tests/` | test_ingestion/, test_processing/, test_intents/, test_api/ |
| `notebooks/` | 01_eda.ipynb, 02_clustering_exploration.ipynb |
| `scripts/` | setup_bq.py, seed_data.py, run_backfill.sh |

---

## 3. Plan Semanal Detallado

El plan está organizado en 4 semanas de 5 días hábiles cada una (40 horas/semana). Cada día tiene un entregable verificable.

---

### Semana 1 — Fundamentos: Setup + Ingesta + Limpieza

**Objetivo:** Tener tickets limpios, sin PII, listos para generar embeddings. Al final de esta semana debes poder ejecutar un query en BigQuery que retorne tickets limpios.

| Día | Bloque | Tareas específicas | Entregable verificable |
|-----|--------|--------------------|----------------------|
| L (1) | Setup proyecto | Crear repo, estructura de carpetas, pyproject.toml, Docker base, docker-compose con PG local. Terraform: BQ datasets (raw, clean, features), Cloud Storage bucket, service accounts | Repo con estructura completa. `make setup` funciona. BQ datasets creados |
| M (2) | Ingesta Zendesk | Implementar zendesk_client.py: auth, paginación cursor-based, rate limiting con backoff. Job de backfill con checkpoint. Escribir a raw_tickets en BQ | Backfill ejecutado: N tickets en raw_tickets. Log de progreso visible |
| X (3) | Ingesta + limpieza básica | AM: Job incremental + tests de ingesta. PM: Inicio de cleaner.py: consolidar texto, separar mensajes cliente/agente, eliminar HTML, URLs de tracking, quoted replies | Incremental corriendo. Primeros 100 tickets limpios revisados manualmente |
| J (4) | Limpieza completa | Limpieza de firmas de email (regex + heurísticas), templates de respuesta automática. Pipeline de limpieza específico para RRSS (texto más corto, emojis, menciones) | Pipeline limpieza ejecutado sobre dataset completo. clean_tickets poblada |
| V (5) | PII + validación | Implementar pii_redactor.py: regex para emails, teléfonos (+56 X XXXX XXXX), RUTs. Validación: muestra de 100 tickets revisada, reporte de calidad | QA report: % PII detectada, % falsos positivos. Dataset limpio validado |

**Decisiones técnicas Semana 1:**
- Checkpoint de backfill: guardar cursor en archivo local. Si falla, retomar desde último cursor
- Limpieza de firmas: empezar con regex (líneas que empiezan con `--`, `Enviado desde`, etc.). No usar ML para esto en MVP
- PII: solo regex en MVP. spaCy NER queda como enhancement post-MVP (agrega complejidad y dependencia pesada)
- Canal RRSS: normalizar menciones (@usuario) y hashtags. No eliminar emojis (pueden ser señal de sentiment)

---

### Semana 2 — Core: Embeddings + Clustering + Intents

**Objetivo:** Tener un catálogo de intents etiquetados y priorizados. Esta es la semana más crítica del proyecto.

> 🔴 **Hito clave: sesión de etiquetado con el cliente**
> El jueves o viernes de esta semana se necesita una sesión de 1-2 horas con alguien del equipo de soporte del cliente para validar y nombrar los clusters. Coordinar esto al inicio de la semana.

| Día | Bloque | Tareas específicas | Entregable verificable |
|-----|--------|--------------------|----------------------|
| L (6) | Embeddings | Implementar embeddings.py: batch processing con OpenAI API, rate limiting, escritura a BQ. Procesar dataset completo. Para 50K tickets: ~2-4 horas de procesamiento | Tabla embeddings poblada. Costo de API registrado |
| M (7) | UMAP + HDBSCAN | Reducción dimensional con UMAP (1536 → 25 dims). Clustering con HDBSCAN. Experimentar con min_cluster_size (3-5% del dataset). Generar visualización 2D | Clusters generados. Visualización 2D de clusters. Métricas: N clusters, % noise, silhouette score |
| X (8) | Análisis de clusters | Para cada cluster: extraer 5 tickets representativos (más cercanos al centroide). Generar resumen automático con GPT-4o-mini. Calcular métricas: tamaño, cohesión, overlap con tags existentes | Reporte de clusters: top 15-20 con resumen, tamaño, ejemplos. Listo para revisión humana |
| J (9) | Etiquetado + scoring | Sesión con cliente para etiquetar clusters. Implementar scoring: volumen, tiempo resolución, repetición semántica, riesgo (input del cliente). Fórmula de score compuesto | Catálogo de intents nombrados. Top 3-5 intents priorizados con scores |
| V (10) | Consolidación + tests | Persistir intents en BQ. Mapping ticket-intent. Tests de estabilidad del clustering. Documentar decisiones de parámetros. Preparar para Semana 3 | Tablas intents y clusters finales. Notebook de documentación |

**Decisiones técnicas Semana 2:**
- Embeddings: usar text-embedding-3-small (no ada-002). Mejor calidad, mismo precio. Embedding sobre `text_customer_only` (solo mensajes del cliente, no respuestas del agente)
- UMAP params: n_neighbors=15, min_dist=0.1, n_components=25 para clustering (no 2D, eso es solo para visualización)
- HDBSCAN: min_cluster_size = max(20, 3% del dataset). min_samples = 5. Esto evita micro-clusters
- Si hay >20 clusters: agrupar manualmente los que representan el mismo intent con formulación diferente
- Tags de Zendesk: usar como validación cruzada, no como input. Si un cluster se alinea con un tag existente, es buena señal

---

### Semana 3 — Generación IA + API

**Objetivo:** Tener la API funcionando y generando respuestas sugeridas con score de confianza para los intents priorizados.

| Día | Bloque | Tareas específicas | Entregable verificable |
|-----|--------|--------------------|----------------------|
| L (11) | Prompt engineering | Diseñar prompt templates para top 3-5 intents. System prompt con tono de marca. Política por intent (qué puede/no puede decir). Few-shot examples de tickets reales del cluster | Archivos `prompts/intents/*.yaml` con template + política + examples |
| M (12) | Motor de generación | response_generator.py: detectar intent (distancia al centroide más cercano), seleccionar prompt, inyectar contexto, llamar API, parsear respuesta. Confidence score basado en distancia al centroide | Script que dado un ticket_id retorna: intent, respuesta, confianza. Probado con 10 tickets |
| X (13) | API Core | FastAPI: GET /tickets, GET /tickets/{id}/suggestion, POST /tickets/{id}/feedback, GET /intents, GET /metrics/summary. Auth con API key. CORS. Deploy a Cloud Run staging | API en Cloud Run con docs Swagger accesibles. Endpoints probados con curl |
| J (14) | Evaluación + tuning | Evaluar calidad de respuestas sobre 30-50 tickets por intent. Iterar prompts. Ajustar confidence thresholds. Agregar justificación (tickets similares) | Reporte de evaluación: % respuestas aceptables por intent. Prompts v2 mejorados |
| V (15) | Cache + robustez | Cachear sugerencias ya generadas (no regenerar). Manejo de errores (API down, ticket sin intent claro, confianza muy baja). Tests de API. Variables dinámicas (placeholders) | API robusta con error handling. Tests pasando. Cache funcional |

**Decisiones técnicas Semana 3:**
- Detección de intent en producción: calcular embedding del ticket nuevo, encontrar centroide más cercano. Si distancia > threshold, clasificar como `no_intent` (sin sugerencia)
- Confidence score: normalizar distancia al centroide a escala 0-1. Umbral sugerido: >0.75 alta, 0.5-0.75 media, <0.5 no sugerir
- Prompt structure: system (tono/marca) + intent_policy (restricciones) + few_shot (3 ejemplos) + ticket_context (texto limpio)
- GPT-4o-mini para generación en producción (costo). GPT-4o solo si la calidad de mini no es suficiente en evaluación
- No auto-envío: la API solo retorna sugerencias, nunca escribe en Zendesk automáticamente

---

### Semana 4 — UI + Dashboard + Validación

**Objetivo:** Entregar el MVP completo: interfaz usable por agentes, dashboard de métricas, y validación con usuarios reales.

> 🔴 **Hito clave: validación con agentes reales**
> Jueves o viernes: sesión con 1-2 agentes del cliente usando el sistema con tickets reales. Esto genera los primeros datos de feedback y valida la usabilidad.

| Día | Bloque | Tareas específicas | Entregable verificable |
|-----|--------|--------------------|----------------------|
| L (16) | Streamlit - Vista tickets | Page 1: lista de tickets con filtros (canal, fecha, intent, con/sin sugerencia). Vista de detalle: conversación completa, intent detectado, sugerencia con confianza | App Streamlit corriendo local con datos reales |
| M (17) | Streamlit - HITL | Componentes de feedback: botones aceptar/editar/rechazar. Modal de edición. Razón de rechazo. Todo escribe a tabla feedback via API. Panel de confianza visual (verde/amarillo/rojo) | Flujo completo: ver ticket → ver sugerencia → dar feedback. Datos en BQ |
| X (18) | Dashboard métricas | Page 2: KPIs cards (tickets con sugerencia, tasa aceptación, horas ahorradas). Gráficos: distribución por intent, confianza promedio, timeline de feedback. Tabla de intents con métricas | Dashboard con datos reales (o simulados si no hay feedback aún) |
| J (19) | Deploy + validación | Deploy Streamlit a Cloud Run. Configurar acceso para agentes del cliente. Sesión de validación: agentes procesan 20-30 tickets reales con el sistema. Recoger feedback | Sistema en producción. Primeros datos de feedback reales |
| V (20) | Ajustes + entrega | Fixes de la sesión de validación. Ajustar prompts si hay patrones de rechazo. Documentación de uso. Exportar primeras métricas. Preparar presentación de resultados | MVP entregado. Documentación. Métricas iniciales. Backlog post-MVP |

**Decisiones técnicas Semana 4:**
- Streamlit multi-page: app.py como entry point, `pages/` con `1_Tickets.py`, `2_Dashboard.py`, `3_Intents.py`
- Feedback loop: cada acción del agente se guarda con timestamp, agent_id, y contexto. Esto permite calcular métricas reales desde día 1
- Horas ahorradas = tickets aceptados × tiempo_promedio_resolución_del_intent. Es una estimación, pero da un número concreto al cliente
- Deploy: Cloud Run con 2 servicios: api (FastAPI) + ui (Streamlit). Streamlit llama a la API internamente
- Acceso: Streamlit con autenticación básica (usuario/contraseña) o IAP de GCP si el cliente lo tiene

---

## 4. Cronograma Consolidado

| Semana | Foco principal | Días | Entregable de cierre |
|--------|---------------|------|---------------------|
| Semana 1 | Setup + Ingesta + Limpieza + PII | 5 días | Dataset limpio en BigQuery, validado, sin PII |
| Semana 2 | Embeddings + Clustering + Intents + Scoring | 5 días | Catálogo de 3-5 intents priorizados y etiquetados |
| Semana 3 | Generación IA + API + Evaluación | 5 días | API en Cloud Run generando sugerencias con confianza |
| Semana 4 | Streamlit UI + Dashboard + Validación | 5 días | MVP completo desplegado y validado con agentes reales |

### 4.1 Dependencias entre semanas

- Semana 2 depende de: dataset limpio de Semana 1
- Semana 3 depende de: catálogo de intents de Semana 2
- Semana 4 depende de: API funcional de Semana 3
- **Dependencia externa:** sesión de etiquetado con cliente (coordinar en Semana 1 para ejecutar en Semana 2)
- **Dependencia externa:** acceso de agentes al sistema (coordinar en Semana 3 para validación en Semana 4)

---

## 5. Métricas de Éxito del MVP

### 5.1 Métricas técnicas (controlables)

| Métrica | Target | Cómo se mide |
|---------|--------|--------------|
| Tickets ingestados sin error | 100% | Count en raw_tickets vs total en Zendesk |
| Cobertura de limpieza | 100% de raw procesados | Count clean_tickets / count raw_tickets |
| PII redactada | <1% falsos negativos | QA manual sobre muestra de 100 tickets |
| Intents identificados | 3-5 intents activos | Count en tabla intents con status=active |
| Cobertura de intents | >40% del volumen total | Sum volumen de intents activos / total tickets |
| API response time | <3 segundos por sugerencia | Logs de API (p95 latency) |
| Uptime del sistema | >99% en semana de validación | Cloud Run health checks |

### 5.2 Métricas de negocio (validación con cliente)

| Métrica | Target | Cómo se mide |
|---------|--------|--------------|
| Tickets con sugerencia IA | >40% en intents seleccionados | Count sugerencias generadas / tickets en intents activos |
| Tasa de aceptación | >60% (aceptar + editar mínimo) | Count (accept + edit) / total feedback |
| Tasa de rechazo | <40% | Count reject / total feedback |
| Horas ahorradas estimadas | Cálculo visible en dashboard | Tickets aceptados × tiempo_promedio_resolución |
| Feedback del equipo | Positivo en sesión de validación | Cualitativo: encuesta post-sesión |

---

## 6. Riesgos y Plan de Mitigación

| Riesgo | Prob. | Impacto | Mitigación | Plan B |
|--------|-------|---------|------------|--------|
| Datos muy sucios | Alta | Alto | QA manual día 5. Si >30% inutilizable, recortar a subset limpio | Trabajar solo con tickets de email (suelen ser más limpios) |
| Clustering no produce intents claros | Media | Alto | Probar 3+ configs de HDBSCAN. Reducir min_cluster_size. Visualizar manualmente | Usar tags existentes como seed + clustering como refinamiento |
| Cliente no disponible para etiquetado | Media | Alto | Coordinar desde día 1. Tener fecha bloqueada para semana 2 | Auto-etiquetar con LLM y validar asincrónicamente por email |
| Respuestas IA de baja calidad | Media | Medio | Few-shot examples. Prompt tuning día 14. Políticas estrictas por intent | Reducir a 2-3 intents simples y descartar los más complejos |
| Rate limits OpenAI | Baja | Medio | Batch processing. Cache agresivo. Backoff exponencial | Reducir batch size. Procesar en horarios de baja demanda |
| No alcanza el tiempo | Alta | Alto | Cortar features no-core cada viernes. Priorizar flujo completo sobre perfección | Entregar semana 3 sin UI bonita (demo via API + notebook) |

---

## 7. Qué Queda Fuera del MVP (Backlog Post-MVP)

Es tan importante definir qué no se hace como qué sí. Estos items quedan explícitamente fuera de las 4 semanas:

| Feature | Razón de exclusión | Prioridad post-MVP |
|---------|-------------------|-------------------|
| Auto-reply (envío automático) | Requiere confianza validada + aprobación del cliente. Riesgo reputacional | Alta — siguiente iteración |
| Integración con estados de pedido | Requiere acceso a ERP/OMS del cliente. Scope de integración aparte | Alta — habilita variables dinámicas |
| Detección de PII con ML (spaCy NER) | Regex cubre 80%+ de casos. NER agrega dependencia pesada y complejidad | Media — enhancement |
| Multicanal (WhatsApp, chat en vivo) | MVP cubre email + RRSS. Otros canales requieren conectores adicionales | Media — roadmap |
| Optimización por CSAT | Requiere datos de satisfacción + correlación. No hay suficiente feedback en MVP | Media — post validación |
| Multi-tenant (múltiples clientes) | Este MVP es para un cliente. Arquitectura multi-tenant es otro proyecto | Alta — si se convierte en producto |
| React UI custom | Streamlit cubre la necesidad del MVP. React solo si se necesita UX avanzada | Baja — solo si Streamlit limita |
| CI/CD completo con staging | Se deployará directo a producción con feature flags. Pipeline básico | Media — profesionalizar post-MVP |
| Modelo de pricing por impacto | Primero validar que funciona. Pricing viene después | Alta — comercial |
| Re-entrenamiento automático | El feedback se acumula pero el re-clustering es manual en MVP | Media — automatizar post-MVP |

---

## 8. Costos Estimados de Infraestructura y APIs

Estimación para 4 semanas de desarrollo + operación inicial con ~30,000 tickets:

| Concepto | Estimación | Notas |
|----------|------------|-------|
| OpenAI — Embeddings | $2 - $5 USD | text-embedding-3-small. ~30K tickets × ~500 tokens promedio |
| OpenAI — Generación | $10 - $30 USD | GPT-4o-mini para desarrollo. ~1000 generaciones de prueba + producción |
| BigQuery | $0 - $5 USD | Primer TB de queries gratis. Dataset pequeño. Storage mínimo |
| Cloud Run | $5 - $20 USD | 2 servicios (API + UI). Tráfico bajo en MVP. Scale to zero |
| Cloud Storage | <$1 USD | Solo para artefactos y backups |
| **Total estimado (4 semanas)** | **$20 - $60 USD** | Sin contar horas de desarrollo |

---

## 9. Checklist Pre-Arranque (Día 0)

Antes de escribir la primera línea de código, confirmar que todo esto está resuelto:

| Item | Estado | Responsable | Notas |
|------|--------|-------------|-------|
| API key de Zendesk con permisos de lectura | Pendiente | Tú / Cliente | Necesita read access a tickets, users, comments |
| Proyecto GCP con billing activo | Confirmado | Tú | Verificar que BQ, Cloud Run, Cloud Storage están habilitados |
| API key de OpenAI con créditos | Confirmado | Tú | Verificar rate limits del plan actual |
| Repositorio Git creado | Pendiente | Tú | GitHub o GitLab. Definir branching strategy |
| Fecha de sesión de etiquetado (semana 2) | Pendiente | Tú + Cliente | Bloquear 2 horas en agenda del equipo de soporte |
| Fecha de validación con agentes (semana 4) | Pendiente | Tú + Cliente | Bloquear 2-3 horas con 1-2 agentes |
| Acceso a datos de ejemplo (5-10 tickets) | Pendiente | Cliente | Para validar formato antes del backfill masivo |
| Contacto técnico del cliente | Pendiente | Tú | Quién responde dudas sobre datos, procesos, tono de marca |

---

## 10. Próximos Pasos

Con los supuestos resueltos, el camino es claro:

- Resolver todos los items del checklist de Día 0
- Iniciar Semana 1, Día 1: setup del repositorio e infraestructura
- Coordinar con el cliente la sesión de etiquetado para Semana 2
- Ejecutar el plan día a día, cortando scope si es necesario cada viernes

**Criterio de corte semanal:** cada viernes, evaluar si el entregable de cierre de semana se cumplió. Si no, recortar el scope de la semana siguiente para compensar. Nunca acumular deuda. Lo que no entra, va al backlog post-MVP.
