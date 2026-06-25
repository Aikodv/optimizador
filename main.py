# =============================================================================
# API REST Dummy - Sistema de Backoffice para Optimizacion de Rutas
# =============================================================================
#
# DESCRIPCION:
#   Simula los endpoints externos de un sistema de backoffice que alimenta
#   un servicio de optimizacion de rutas. Todos los datos son ficticios y
#   se generan en memoria al iniciar el servidor.
#
# INSTALACION DE DEPENDENCIAS:
#   pip install fastapi uvicorn faker
#
# EJECUCION DEL SERVIDOR:
#   uvicorn main:app --reload --port 8000
#
#   La documentacion interactiva estara disponible en:
#     - Swagger UI: http://127.0.0.1:8000/docs
#     - ReDoc:      http://127.0.0.1:8000/redoc
# =============================================================================

import random
import uuid
from datetime import date, timedelta
from typing import Optional

from faker import Faker
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =============================================================================
# CONFIGURACION INICIAL
# =============================================================================

# Inicializamos Faker con locale espanol de Chile para datos mas realistas
fake = Faker("es_CL")
random.seed(42)   # Semilla fija para reproducibilidad de los datos mock
Faker.seed(42)

app = FastAPI(
    title="Backoffice API - Optimizacion de Rutas",
    description=(
        "API REST dummy que simula el sistema de backoffice para "
        "alimentar un servicio de optimizacion de rutas en Santiago, Chile."
    ),
    version="1.0.0",
)

# Permitimos cualquier origen para facilitar pruebas desde frontends locales
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# ENUMS Y CONSTANTES
# =============================================================================

TIPOS_TECNICO = ["interno", "externo"]

TIPOS_OT = [
    "instalacion_simple",
    "instalacion_con_corte",
    "mantencion",
    "retiro",
]

ESTADOS_OT = [
    "por_revisar",
    "por_asignar",
    "asignacion_por_confirmar",
    "asignada",
    "en_terreno",
    "finalizada",
    "enviada_cobranza",
]

# Zonas reales de Santiago de Chile
ZONAS_SANTIAGO = [
    "Santiago Centro",
    "Providencia",
    "Las Condes",
    "Vitacura",
    "Nunoa",
    "La Florida",
    "Maipu",
    "Pudahuel",
    "Quilicura",
    "Penalolen",
    "La Reina",
    "Macul",
    "San Miguel",
    "La Cisterna",
    "El Bosque",
    "Puente Alto",
    "San Bernardo",
    "Lo Barnechea",
    "Cerrillos",
    "Estacion Central",
]

ZONAS_COORDENADAS = {
    "Santiago Centro": (-33.4429, -70.6540),
    "Providencia": (-33.4289, -70.6080),
    "Las Condes": (-33.3937, -70.5840),
    "Vitacura": (-33.3999, -70.5731),
    "Nunoa": (-33.4520, -70.6120),
    "La Florida": (-33.4930, -70.5863),
    "Maipu": (-33.4865, -70.7602),
    "Pudahuel": (-33.4584, -70.7838),
    "Quilicura": (-33.3752, -70.7715),
    "Penalolen": (-33.4750, -70.5709),
    "La Reina": (-33.4688, -70.5507),
    "Macul": (-33.4804, -70.6224),
    "San Miguel": (-33.5034, -70.7097),
    "La Cisterna": (-33.5193, -70.6529),
    "El Bosque": (-33.5431, -70.6675),
    "Puente Alto": (-33.6142, -70.5755),
    "San Bernardo": (-33.6002, -70.7243),
    "Lo Barnechea": (-33.3559, -70.5250),
    "Cerrillos": (-33.5028, -70.7425),
    "Estacion Central": (-33.4578, -70.6676),
}

# Calles reales de Santiago para direcciones mas autenticas
CALLES_SANTIAGO = [
    "Avenida Libertador Bernardo O Higgins",
    "Avenida Providencia",
    "Avenida Apoquindo",
    "Avenida Vitacura",
    "Avenida Las Condes",
    "Calle Huerfanos",
    "Calle Agustinas",
    "Avenida Irarrazaval",
    "Avenida Grecia",
    "Calle Merced",
    "Paseo Ahumada",
    "Avenida Americo Vespucio",
    "Avenida Tobalaba",
    "Avenida Vicuna Mackenna",
    "Avenida Recoleta",
    "Calle San Antonio",
    "Avenida Matta",
    "Calle Condell",
    "Avenida El Golf",
    "Calle Estado",
]


def generar_direccion_santiago() -> tuple[str, str]:
    """Genera una direccion ficticia y su zona asociada en Santiago, Chile."""
    calle = random.choice(CALLES_SANTIAGO)
    numero = random.randint(100, 9999)
    piso_o_depto = ""
    if random.random() > 0.5:
        tipo = random.choice(["Depto", "Of", "Piso"])
        num = random.randint(1, 20)
        piso_o_depto = f", {tipo}. {num}"
    zona = random.choice(ZONAS_SANTIAGO)
    direccion = f"{calle} #{numero}{piso_o_depto}, {zona}, Santiago, Chile"
    return direccion, zona


def generar_coordenadas_por_zona(zona: str) -> tuple[float, float]:
    """Genera coordenadas aleatorias dentro de la zona seleccionada."""
    base = ZONAS_COORDENADAS.get(zona, (-33.45, -70.66))
    lat = base[0] + random.uniform(-0.008, 0.008)
    lon = base[1] + random.uniform(-0.008, 0.008)
    return lat, lon


# =============================================================================
# GENERACION DE LA BASE DE DATOS EN MEMORIA
# =============================================================================

def generar_tecnicos(n: int = 20) -> list:
    """
    Genera una lista de tecnicos con datos ficticios.

    Args:
        n: Numero de tecnicos a generar.

    Returns:
        Lista de diccionarios representando tecnicos.
    """
    tecnicos = []
    for _ in range(n):
        tecnico = {
            "id": str(uuid.uuid4()),
            "nombre": fake.first_name(),
            "apellidos": f"{fake.last_name()} {fake.last_name()}",
            "tipo": random.choice(TIPOS_TECNICO),
            "zona": random.choice(ZONAS_SANTIAGO),
        }
        tecnicos.append(tecnico)
    return tecnicos


def generar_disponibilidades(tecnicos: list, dias: int = 14) -> list:
    """
    Genera disponibilidades para cada tecnico en un rango de dias.

    Args:
        tecnicos: Lista de tecnicos existentes.
        dias: Cuantos dias hacia adelante generar disponibilidad.

    Returns:
        Lista de diccionarios representando disponibilidades.
    """
    disponibilidades = []
    hoy = date.today()

    for tecnico in tecnicos:
        for offset in range(dias):
            fecha = hoy + timedelta(days=offset)
            # Los fines de semana tienen menor probabilidad de disponibilidad
            es_fin_de_semana = fecha.weekday() >= 5  # 5=Sabado, 6=Domingo
            prob_disponible = 0.3 if es_fin_de_semana else 0.8

            disponibilidad = {
                "id": str(uuid.uuid4()),
                "tecnico_id": tecnico["id"],
                "fecha": fecha.isoformat(),
                "disponible": random.random() < prob_disponible,
            }
            disponibilidades.append(disponibilidad)

    return disponibilidades


def generar_ordenes_trabajo(tecnicos: list, n: int = 200) -> list:
    """
    Genera una lista de ordenes de trabajo con datos ficticios.
    Todas las OTs se generan en estado por_asignar y sin técnico asignado.

    Args:
        tecnicos: Lista de tecnicos para usar en la generación de datos.
        n: Numero de ordenes de trabajo a generar.

    Returns:
        Lista de diccionarios representando ordenes de trabajo.
    """
    ordenes = []
    hoy = date.today()

    for i in range(1, n + 1):
        direccion, zona = generar_direccion_santiago()
        latitud, longitud = generar_coordenadas_por_zona(zona)
        orden = {
            # Formato "OT-XXXX" con padding de ceros a la izquierda
            "id": f"OT-{i:04d}",
            "tipo": random.choice(TIPOS_OT),
            "estado": "por_asignar",
            "tecnico_id": None,
            "direccion_instalacion": direccion,
            "latitud": latitud,
            "longitud": longitud,
            "fecha_programada": None,
            "hora_programada": None,
        }
        ordenes.append(orden)

    return ordenes


# Generamos los datos al arrancar la aplicacion (base de datos en memoria)
DB_TECNICOS = generar_tecnicos(n=4)
DB_DISPONIBILIDADES = generar_disponibilidades(DB_TECNICOS, dias=14)
DB_ORDENES = generar_ordenes_trabajo(DB_TECNICOS, n=10)


# =============================================================================
# MODELOS PYDANTIC (para validacion de request/response bodies)
# =============================================================================

class AsignarTecnicoRequest(BaseModel):
    """Body esperado para el endpoint PATCH /ordenes/{id}/tecnico."""
    tecnico_id: str


# =============================================================================
# ENDPOINTS
# =============================================================================

# --- Raiz ---

@app.get("/", tags=["Root"])
def root():
    """Endpoint raiz con informacion basica de la API."""
    return {
        "mensaje": "API Dummy - Sistema de Backoffice para Optimizacion de Rutas",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints_disponibles": [
            "GET  /api/tecnicos",
            "GET  /api/ordenes",
            "PATCH /api/ordenes/{id}/tecnico",
            "GET  /api/disponibilidad",
        ],
    }


# --- Tecnicos ---

@app.get(
    "/api/tecnicos",
    tags=["Tecnicos"],
    summary="Obtener lista de tecnicos",
    response_description="Lista completa de tecnicos registrados en el sistema.",
)
def get_tecnicos():
    """
    Retorna la lista completa de tecnicos disponibles en el sistema.

    Cada tecnico incluye:
    - **id**: Identificador unico (UUID)
    - **nombre**: Nombre del tecnico
    - **apellidos**: Apellidos del tecnico
    - **tipo**: interno o externo
    - **zona**: Zona de Santiago asignada al tecnico
    """
    return DB_TECNICOS


# --- Ordenes de Trabajo ---

@app.get(
    "/api/ordenes",
    tags=["Ordenes de Trabajo"],
    summary="Obtener lista de ordenes de trabajo",
    response_description="Lista de ordenes de trabajo (OTs), opcionalmente filtrada por estado.",
)
def get_ordenes(
    estado: Optional[str] = Query(
        default=None,
        description=(
            "Filtra las OTs por estado. Valores validos: "
            "por_revisar | por_asignar | asignacion_por_confirmar | "
            "asignada | en_terreno | finalizada | enviada_cobranza"
        ),
        example="por_asignar",
    )
):
    """
    Retorna la lista de ordenes de trabajo (OTs) del sistema.

    Acepta un query parameter opcional **estado** para filtrar los resultados:
    - Sin `estado`: retorna todas las OTs.
    - Con `estado` (ej: `?estado=por_asignar`): retorna solo las OTs con ese estado.

    Estados validos: por_revisar | por_asignar | asignacion_por_confirmar |
    asignada | en_terreno | finalizada | enviada_cobranza

    Cada OT incluye:
    - **id**: Identificador en formato OT-XXXX
    - **tipo**: Tipo de servicio (instalacion_simple, instalacion_con_corte, mantencion, retiro)
    - **estado**: Estado actual del flujo de trabajo
    - **tecnico_id**: UUID del tecnico asignado (puede ser null)
    - **direccion_instalacion**: Direccion del trabajo en Santiago, Chile
    - **fecha_programada**: Fecha en formato ISO 8601 (puede ser null)
    - **hora_programada**: Hora en formato HH:MM (puede ser null)
    """
    if estado is None:
        # Sin filtro: devolvemos todas las OTs
        return DB_ORDENES

    # Validamos que el estado sea uno de los valores permitidos por el enum
    if estado not in ESTADOS_OT:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El estado '{estado}' no es valido. "
                f"Valores permitidos: {', '.join(ESTADOS_OT)}"
            ),
        )

    # Filtramos las OTs por el estado indicado
    return [o for o in DB_ORDENES if o["estado"] == estado]


@app.patch(
    "/api/ordenes/{id}/tecnico",
    tags=["Ordenes de Trabajo"],
    summary="Asignar tecnico a una orden de trabajo",
    response_description="La orden de trabajo actualizada con el nuevo tecnico asignado.",
)
def asignar_tecnico(id: str, body: AsignarTecnicoRequest):
    """
    Simula la asignacion de un tecnico a una orden de trabajo especifica.

    - Busca la OT por su id (ej: OT-0001).
    - Valida que el tecnico_id del body corresponda a un tecnico existente.
    - Actualiza la OT en memoria con el nuevo tecnico_id.
    - Cambia el estado de la OT a asignacion_por_confirmar si estaba pendiente.
    - Retorna la OT actualizada.

    Body esperado: {"tecnico_id": "uuid-del-tecnico"}
    """
    # Buscamos la OT por id
    orden = next((o for o in DB_ORDENES if o["id"] == id), None)
    if orden is None:
        raise HTTPException(
            status_code=404,
            detail=f"Orden de trabajo con id '{id}' no encontrada.",
        )

    # Validamos que el tecnico exista en nuestra base de datos en memoria
    tecnico = next((t for t in DB_TECNICOS if t["id"] == body.tecnico_id), None)
    if tecnico is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tecnico con id '{body.tecnico_id}' no encontrado.",
        )

    # Actualizamos la OT en memoria
    orden["tecnico_id"] = body.tecnico_id

    # Si la OT estaba sin asignar, la movemos al siguiente estado logico
    if orden["estado"] in ("por_revisar", "por_asignar"):
        orden["estado"] = "asignacion_por_confirmar"

    return orden


# --- Disponibilidad ---

@app.get(
    "/api/disponibilidad",
    tags=["Disponibilidad"],
    summary="Obtener disponibilidades de tecnicos",
    response_description="Lista de disponibilidades, opcionalmente filtrada por fecha.",
)
def get_disponibilidad(
    fecha: Optional[str] = Query(
        default=None,
        description="Filtra las disponibilidades por fecha. Formato: YYYY-MM-DD",
        example="2026-06-20",
    )
):
    """
    Retorna la lista de disponibilidades de todos los tecnicos.

    Acepta un query parameter opcional fecha para filtrar los resultados:
    - Sin fecha: retorna todas las disponibilidades del rango generado (14 dias).
    - Con fecha (ej: ?fecha=2026-06-20): retorna solo las disponibilidades de ese dia.

    Cada entrada incluye:
    - **id**: Identificador unico (UUID)
    - **tecnico_id**: UUID del tecnico al que pertenece la disponibilidad
    - **fecha**: Fecha en formato ISO 8601
    - **disponible**: true si el tecnico esta disponible ese dia, false si no
    """
    if fecha is None:
        # Sin filtro: devolvemos todas las disponibilidades
        return DB_DISPONIBILIDADES

    # Validamos que el parametro tenga el formato correcto
    try:
        date.fromisoformat(fecha)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El parametro 'fecha' tiene un formato invalido: '{fecha}'. "
                "Use el formato YYYY-MM-DD (ej: 2026-06-20)."
            ),
        )

    # Filtramos por la fecha indicada
    resultado = [d for d in DB_DISPONIBILIDADES if d["fecha"] == fecha]

    return resultado
