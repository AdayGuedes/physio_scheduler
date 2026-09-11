# Convenciones de Nomenclatura — Physio Scheduler

Documento vivo. Objetivo: que Aday (DB), Diego (backend) y Vitor (frontend) usen
siempre el mismo nombre para la misma cosa, sin tener que preguntarse entre sí.
Cualquier cambio a este documento se comenta en el grupo antes de aplicarse.

## 1. Reglas generales

- **Idioma:** inglés para todo lo que sea código (tablas, columnas, funciones,
  variables). Español solo en comentarios y en la documentación en sí.
- **Casing por capa:**
  - Tablas y columnas (SQL/SQLAlchemy) → `snake_case`
  - Funciones y variables Python → `snake_case`
  - Nombres de tabla → **plural** (`users`, no `user`)
- **Nunca usar palabras reservadas de SQL como nombre de columna**
  (`end`, `order`, `group`, `select`...). Si dudáis, añadid un sufijo
  descriptivo (`end_time`, no `end`).

## 2. Tablas (capa de base de datos — Aday)

| Tabla | Columnas | Notas |
|---|---|---|
| `users` | `id`, `email`, `password_hash`, `name`, `role` | `role` = `physio` \| `client` |
| `resources` | `id`, `type`, `name`, `total_quantity` | `type` = `bed`, `gameready_feet`, `gameready_thighs`, `compression_lower_body`, `heat`, `cold`, `ice_bath` |
| `appointments` | `id`, `client_id` (FK → `users.id`), `start_time`, `end_time`, `reason`, `physio_notes`, `status` | Renombrado `start`/`end` → `start_time`/`end_time` (palabras reservadas en SQL) |
| `appointment_resources` | `id`, `appointment_id` (FK → `appointments.id`), `resource_id` (FK → `resources.id`), `quantity` | Tabla puente |

**Regla de foreign keys:** `<tabla_singular>_id`. Ojo con `client_id`: apunta a
`users.id`, pero se llama `client_id` porque describe el rol semántico (quién
reserva la cita), no el nombre literal de la tabla destino. Es intencional,
no un error.

## 3. Funciones (lógica de negocio — principalmente Diego, pero Aday también
escribirá funciones a nivel de modelo/DB)

**Patrón:** `verbo_sustantivo`, `snake_case`.

| Verbo | Significado |
|---|---|
| `get_` | Lee y devuelve datos, no modifica nada |
| `create_` | Inserta un registro nuevo |
| `update_` | Modifica un registro existente |
| `cancel_` | Baja lógica (cambia `status`, no borra la fila) |
| `check_` | Valida una condición, devuelve resultado, no persiste |

### Funciones núcleo (a completar según avance el desarrollo)

| Función | Descripción |
|---|---|
| `check_availability(start_time, end_time, requested_resources)` | Función central del sistema (disponibilidad de fisio + equipo) |
| `create_appointment(client_id, start_time, end_time, reason, resources)` | Llama a `check_availability` antes de guardar |
| `cancel_appointment(appointment_id)` | Baja lógica de una cita |
| `get_appointments_by_client(client_id)` | Vista "mis citas" del estudiante |
| `get_daily_agenda(date)` | Dashboard de la fisioterapeuta |
| `update_physio_notes(appointment_id, notes)` | Notas clínicas por sesión |
| `update_resource_quantity(resource_id, new_quantity)` | Gestión de inventario |
| `register_user(email, password, name)` | Alta de usuario |
| `authenticate_user(email, password)` | Login |

## 4. Blueprints y rutas Flask (Diego expone, Vitor consume con `url_for()`)

Se usan **Blueprints** para que cada módulo viva en su propio archivo Python
y evitar conflictos de merge entre los tres. Cada Blueprint agrupa las rutas
de un contexto del sistema.

| Blueprint | Archivo | Prefijo URL |
|---|---|---|
| `auth` | `auth.py` | `/auth` |
| `student` | `student.py` | `/student` |
| `physio` | `physio.py` | `/physio` |
| `api` | `api.py` | `/api` |

### Rutas por Blueprint

**`auth`** — Registro, login, logout

| Método | URL | Endpoint (`url_for`) | Qué hace |
|---|---|---|---|
| GET/POST | `/auth/register` | `auth.register` | Formulario de registro + procesamiento |
| GET/POST | `/auth/login` | `auth.login` | Formulario de login + procesamiento |
| GET | `/auth/logout` | `auth.logout` | Cierra sesión y redirige |

**`student`** — Todo lo que ve el estudiante

| Método | URL | Endpoint (`url_for`) | Qué hace |
|---|---|---|---|
| GET | `/student/appointments` | `student.my_appointments` | Lista "mis citas" |
| GET | `/student/appointments/new` | `student.new_appointment` | Formulario de reserva |
| POST | `/student/appointments` | `student.create_appointment` | Procesa la reserva |
| POST | `/student/appointments/<id>/cancel` | `student.cancel_appointment` | Cancela una cita |

**`physio`** — Dashboard y gestión de la fisioterapeuta

| Método | URL | Endpoint (`url_for`) | Qué hace |
|---|---|---|---|
| GET | `/physio/dashboard` | `physio.dashboard` | Agenda diaria + vista semanal/mensual |
| GET | `/physio/appointments/<id>` | `physio.appointment_detail` | Detalle de una cita |
| POST | `/physio/appointments/<id>/edit` | `physio.edit_appointment` | Editar una cita |
| POST | `/physio/appointments/<id>/notes` | `physio.update_notes` | Guardar notas clínicas |
| GET | `/physio/inventory` | `physio.inventory` | Ver inventario |
| POST | `/physio/inventory/<id>/edit` | `physio.update_resource` | Cambiar cantidad de un recurso |

**`api`** — Endpoints JSON (solo para FullCalendar)

| Método | URL | Endpoint (`url_for`) | Qué hace |
|---|---|---|---|
| GET | `/api/events` | `api.events` | Feed JSON de citas para FullCalendar |

### Regla para `url_for()` con parámetros

En las plantillas de Vitor, cuando la ruta lleva `<id>`:
```
{{ url_for('physio.appointment_detail', id=appointment.id) }}
{{ url_for('student.cancel_appointment', id=appointment.id) }}
```
El nombre del parámetro en `url_for()` **tiene que coincidir exactamente**
con el nombre entre `< >` en la definición de la ruta. Si Diego define
`/appointments/<appointment_id>`, Vitor escribe `id=` y falla silenciosamente
con una URL rota. Por eso fijamos `<id>` como estándar en todas las rutas —
corto, consistente, sin ambigüedad porque el Blueprint ya dice de qué entidad
se trata.

## 5. Variables de contexto (`render_template`) — el contrato Diego → Vitor

Estas son las variables que Diego pasa a cada plantilla. Vitor las usa en
Jinja2 con `{{ variable }}`. Si el nombre no coincide exactamente, Jinja2
no da error — renderiza vacío.

| Endpoint | Template | Variables que recibe |
|---|---|---|
| `auth.register` | `auth/register.html` | `errors` (lista de strings, opcional) |
| `auth.login` | `auth/login.html` | `errors` (lista de strings, opcional) |
| `student.my_appointments` | `student/my_appointments.html` | `appointments` (lista de objetos Appointment con sus resources) |
| `student.new_appointment` | `student/new_appointment.html` | `resources` (lista de objetos Resource), `errors` (opcional) |
| `physio.dashboard` | `physio/dashboard.html` | `appointments` (lista del día), `selected_date` (objeto date) |
| `physio.appointment_detail` | `physio/appointment_detail.html` | `appointment` (objeto Appointment con client y resources) |
| `physio.inventory` | `physio/inventory.html` | `resources` (lista de objetos Resource) |

**Regla:** el nombre de la variable es siempre el nombre de la tabla
(en plural si es una lista, en singular si es un solo objeto). No inventar
sinónimos — `appointments`, no `agenda`, no `bookings`, no `citas`.

**Variable global disponible en todas las plantillas:** `current_user`
(inyectada automáticamente por Flask-Login). Vitor puede usarla para
mostrar el nombre del usuario logueado, condicionar menús por rol, etc.

## 6. Formato JSON para FullCalendar.js

FullCalendar necesita un array de objetos con claves específicas. El
endpoint `api.events` traduce nuestro modelo a ese formato. Esta
traducción se hace **una sola vez**, en ese endpoint — ni Diego ni Vitor
usan estos nombres en ningún otro sitio.

```json
[
  {
    "id": 42,
    "title": "Dolor en el tobillo derecho",
    "start": "2026-10-05T10:00:00",
    "end": "2026-10-05T10:30:00",
    "status": "confirmed",
    "url": "/physio/appointments/42"
  }
]
```

| Clave FullCalendar | Viene de (nuestro modelo) | Nota |
|---|---|---|
| `id` | `appointments.id` | Sin cambio |
| `title` | `appointments.reason` | Renombrado: FullCalendar muestra `title` en el calendario |
| `start` | `appointments.start_time` | Renombrado + formato ISO 8601 |
| `end` | `appointments.end_time` | Renombrado + formato ISO 8601 |
| `status` | `appointments.status` | Para colorear eventos por estado |
| `url` | generado con `url_for(...)` | Click en el evento → detalle de la cita |

## 7. Estructura de carpetas del proyecto

```
physio-scheduler/
│
├── .claude/                          ← Contexto del proyecto para Claude Code
│   └── settings.json
│
├── .github/
│   └── workflows/                    ← CI (linting, tests)
│
├── docs/                             ← Documentación (este documento vive aquí)
│   └── convenciones-nombres.md
│
├── app/                              ← Paquete principal de Flask
│   ├── __init__.py                   ← App factory (create_app)
│   ├── models.py                     ← Modelos SQLAlchemy         — ADAY
│   ├── seed.py                       ← Seed del inventario inicial — ADAY
│   ├── auth.py                       ← Blueprint auth             — DIEGO
│   ├── student.py                    ← Blueprint student           — DIEGO
│   ├── physio.py                     ← Blueprint physio            — DIEGO
│   ├── api.py                        ← Blueprint api (FullCalendar)— DIEGO
│   │
│   ├── templates/                    ← Plantillas Jinja2           — VITOR
│   │   ├── base.html                 ← Layout base (navbar, Bootstrap, scripts)
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── register.html
│   │   ├── student/
│   │   │   ├── my_appointments.html
│   │   │   └── new_appointment.html
│   │   └── physio/
│   │       ├── dashboard.html
│   │       ├── appointment_detail.html
│   │       └── inventory.html
│   │
│   └── static/                       ← CSS, JS, imágenes          — VITOR
│       ├── css/
│       ├── js/
│       └── img/
│
├── tests/                            ← Tests (todos)
├── config.py                         ← Configuración (SECRET_KEY, DB URI, etc.)
├── run.py                            ← Punto de entrada: python run.py
├── requirements.txt
└── README.md
```

### Por qué `app/` y no `src/db` + `src/backend` + `src/frontend`

Flask busca `templates/` y `static/` dentro del paquete de la aplicación.
Si separáis en tres carpetas hermanas, tendréis que sobreescribir rutas por
defecto en cada Blueprint y los imports entre capas se complican. Con esta
estructura, todo es `from app.models import Appointment` — limpio y estándar.

La separación de responsabilidades no es por carpetas de primer nivel,
es por archivos:

| Persona | Sus archivos | Toca archivos de otro |
|---|---|---|
| Aday (DB) | `models.py`, `seed.py`, migraciones | No |
| Diego (backend) | `auth.py`, `student.py`, `physio.py`, `api.py` | No |
| Vitor (frontend) | `templates/**`, `static/**`, `base.html` | No |

Misma ventaja de cero conflictos de merge, pero respetando las convenciones
de Flask.

## 8. Valores de `status` y transiciones válidas

| Valor | Significado |
|---|---|
| `confirmed` | Cita reservada y validada por el sistema |
| `cancelled_by_client` | Cancelada por el estudiante |
| `cancelled_by_physio` | Cancelada por la fisioterapeuta |
| `completed` | La cita ya tuvo lugar (la fisio la marca como completada) |
| `no_show` | El estudiante no se presentó |

### Transiciones permitidas

```
confirmed → cancelled_by_client    (estudiante cancela)
confirmed → cancelled_by_physio    (fisio cancela)
confirmed → completed              (fisio marca como completada)
confirmed → no_show                (fisio marca como no presentado)
```

Ningún otro cambio de estado es válido. Una cita cancelada o completada
**no vuelve atrás** — si hubo un error, se crea una cita nueva. Esto
simplifica mucho la lógica y protege el historial.

**Implicación para la disponibilidad:** `check_availability` solo cuenta
como "ocupadas" las citas con `status = confirmed`. Las canceladas, completadas
y no-show no bloquean recursos.

## 9. Formato de errores de `check_availability`

Cuando la reserva no es posible, `check_availability` devuelve un diccionario
con esta estructura fija. Vitor puede confiar en estos nombres para mostrar
los mensajes en la plantilla.

```python
# Reserva exitosa
{"available": True}

# Fisio ocupada en ese horario
{
    "available": False,
    "reason": "physio_busy",
    "message": "The physiotherapist already has an appointment in that time slot."
}

# Equipo insuficiente
{
    "available": False,
    "reason": "resource_unavailable",
    "message": "Not enough GameReady boots (feet) available.",
    "detail": {
        "resource_name": "GameReady boots (feet)",
        "requested": 2,
        "available_units": 0
    }
}
```

| Campo | Tipo | Siempre presente | Descripción |
|---|---|---|---|
| `available` | `bool` | Sí | `True` si se puede reservar |
| `reason` | `str` | Solo si `available=False` | `physio_busy` o `resource_unavailable` |
| `message` | `str` | Solo si `available=False` | Mensaje legible para mostrar al usuario |
| `detail` | `dict` | Solo si `reason=resource_unavailable` | Qué recurso falla y cuántas unidades quedan |

## 10. Pendiente para la siguiente iteración

- **Reglas de negocio pendientes de confirmar con la entrenadora:** horario
  de atención (¿lunes a viernes? ¿horas?), duración de las citas (¿fija o
  variable?), inventario real (confirmar tipos y cantidades).
- **Formato de los emails** de confirmación y recordatorio (Flask-Mail).
- **Estrategia de testing:** qué se testea, quién testea qué, convenciones
  de nombres para los tests.