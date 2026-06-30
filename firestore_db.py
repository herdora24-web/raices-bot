"""
================================================================
FIRESTORE_DB.PY - Modulo de integracion con Firebase Firestore
Reemplaza el registro en Google Sheets para Raices.
Maneja: guardar pedidos/reservas, consultar y actualizar disponibilidad
de mesas por franja horaria, y cambiar estados desde el dashboard.
================================================================
"""
import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore

TZ_COLOMBIA = ZoneInfo("America/Bogota")

def _hoy_co():
    """Fecha actual de Colombia (sin hora), para comparar contra fechas guardadas."""
    return datetime.now(TZ_COLOMBIA).date()

# ----------------------------------------------------------------
# Capacidad maxima por franja horaria (en personas)
# ----------------------------------------------------------------
CAPACIDAD_MAXIMA = 60

FRANJAS = {
    "almuerzo": {"inicio": "12:00", "fin": "15:00", "label": "almuerzo (12:00 PM - 3:00 PM)"},
    "cena":     {"inicio": "18:00", "fin": "22:00", "label": "cena (6:00 PM - 10:00 PM)"},
}

_app = None
_db = None


def _init():
    """Inicializa la app de Firebase una sola vez (singleton)."""
    global _app, _db
    if _app is not None:
        return _db
    cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
    if not cred_json:
        print("FIREBASE_CREDENTIALS_JSON no configurada. Firestore deshabilitado.")
        return None
    try:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        _app = firebase_admin.initialize_app(cred)
        _db = firestore.client()
        print("Firestore inicializado correctamente.")
        return _db
    except Exception as e:
        print("Error inicializando Firestore:", e)
        return None


def db():
    """Devuelve el cliente de Firestore, inicializando si es necesario."""
    global _db
    if _db is None:
        return _init()
    return _db


# ----------------------------------------------------------------
# Utilidades de franja horaria
# ----------------------------------------------------------------

def determinar_franja(hora_str):
    """
    Dado un string de hora tipo '13:30', '1:30 PM', '19:00', etc,
    determina si cae en franja 'almuerzo', 'cena', o None (fuera de horario).
    Devuelve None si no se puede interpretar la hora.
    """
    hora_norm = _normalizar_hora(hora_str)
    if hora_norm is None:
        return None
    for nombre, datos in FRANJAS.items():
        if datos["inicio"] <= hora_norm <= datos["fin"]:
            return nombre
    return None


def _normalizar_hora(hora_str):
    """Convierte distintos formatos de hora a 'HH:MM' en 24 horas. Devuelve None si no se puede parsear."""
    if not hora_str:
        return None
    s = str(hora_str).strip().upper()
    formatos = ["%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"]
    for fmt in formatos:
        try:
            t = datetime.strptime(s, fmt)
            return t.strftime("%H:%M")
        except ValueError:
            continue
    return None


def _normalizar_fecha(fecha_str):
    """Convierte fechas tipo '25/06/2026', '2026-06-25', '25-06-2026' a 'YYYY-MM-DD'. Devuelve None si falla."""
    if not fecha_str:
        return None
    s = str(fecha_str).strip()
    formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]
    for fmt in formatos:
        try:
            d = datetime.strptime(s, fmt)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ----------------------------------------------------------------
# Consulta y actualizacion de disponibilidad
# ----------------------------------------------------------------

def consultar_disponibilidad(fecha_str, hora_str, personas):
    """
    Consulta si hay cupo para una reserva en la fecha/hora dadas.
    Devuelve un dict:
      {
        "ok": True/False,                  -> si se pudo interpretar fecha/hora
        "franja": "almuerzo"/"cena"/None,
        "disponible": True/False,          -> si hay cupo para 'personas' adicionales
        "cupo_restante": int,
        "alternativa": "almuerzo"/"cena"/None  -> otra franja con cupo el mismo dia, si la solicitada esta llena
      }
    """
    fecha = _normalizar_fecha(fecha_str)
    franja = determinar_franja(hora_str)
    personas = int(personas) if str(personas).isdigit() else 1

    if not fecha or not franja:
        return {"ok": False, "franja": franja, "disponible": True, "cupo_restante": CAPACIDAD_MAXIMA, "alternativa": None}

    firestore_db = db()
    if firestore_db is None:
        # Si Firestore no esta disponible, no bloqueamos la reserva (fail-open)
        return {"ok": True, "franja": franja, "disponible": True, "cupo_restante": CAPACIDAD_MAXIMA, "alternativa": None}

    ocupacion_actual = _obtener_ocupacion(firestore_db, fecha, franja)
    cupo_restante = CAPACIDAD_MAXIMA - ocupacion_actual
    disponible = cupo_restante >= personas

    alternativa = None
    if not disponible:
        otra_franja = "cena" if franja == "almuerzo" else "almuerzo"
        ocupacion_otra = _obtener_ocupacion(firestore_db, fecha, otra_franja)
        if (CAPACIDAD_MAXIMA - ocupacion_otra) >= personas:
            alternativa = otra_franja

    return {
        "ok": True,
        "franja": franja,
        "disponible": disponible,
        "cupo_restante": max(cupo_restante, 0),
        "alternativa": alternativa,
    }


def _obtener_ocupacion(firestore_db, fecha, franja):
    """Lee el contador de personas ya reservadas para esa fecha+franja."""
    doc_id = f"{fecha}_{franja}"
    doc = firestore_db.collection("disponibilidad").document(doc_id).get()
    if doc.exists:
        return doc.to_dict().get("personas_reservadas", 0)
    return 0


def _incrementar_ocupacion(firestore_db, fecha, franja, personas):
    """Suma 'personas' al contador de ocupacion de esa fecha+franja (crea el documento si no existe)."""
    doc_id = f"{fecha}_{franja}"
    ref = firestore_db.collection("disponibilidad").document(doc_id)
    ref.set({
        "fecha": fecha,
        "franja": franja,
        "personas_reservadas": firestore.Increment(personas),
        "capacidad_maxima": CAPACIDAD_MAXIMA,
    }, merge=True)


def _decrementar_ocupacion(firestore_db, fecha, franja, personas):
    """Resta 'personas' del contador (usado si se cancela una reserva)."""
    doc_id = f"{fecha}_{franja}"
    ref = firestore_db.collection("disponibilidad").document(doc_id)
    ref.set({
        "personas_reservadas": firestore.Increment(-personas),
    }, merge=True)


# ----------------------------------------------------------------
# Guardar pedido / reserva
# ----------------------------------------------------------------

def guardar_pedido(datos, ahora_co_dt):
    """
    Guarda un pedido o reserva en Firestore. Si es tipo RESERVA, ademas
    incrementa el contador de ocupacion de la franja correspondiente.
    'ahora_co_dt' es un datetime con la hora actual de Colombia (timezone-aware).
    Devuelve el ID del documento creado, o None si Firestore no esta disponible.
    """
    firestore_db = db()
    if firestore_db is None:
        print("Firestore no disponible, pedido no guardado:", datos.get("nombre"))
        return None

    doc = dict(datos)
    doc["estado"] = doc.get("estado", "PENDIENTE")
    doc["fecha_creacion"] = ahora_co_dt.strftime("%d/%m/%Y")
    doc["hora_creacion"] = ahora_co_dt.strftime("%H:%M")
    doc["timestamp"] = firestore.SERVER_TIMESTAMP

    try:
        ref = firestore_db.collection("pedidos_reservas").document()
        ref.set(doc)

        if doc.get("tipo") == "RESERVA":
            fecha = _normalizar_fecha(doc.get("fecha_reserva", ""))
            franja = determinar_franja(doc.get("hora_reserva", ""))
            personas = int(doc.get("personas", 1)) if str(doc.get("personas", "1")).isdigit() else 1
            if fecha and franja:
                _incrementar_ocupacion(firestore_db, fecha, franja, personas)

        print("Pedido/reserva guardado en Firestore:", ref.id, "-", doc.get("nombre"))
        return ref.id
    except Exception as e:
        print("Error guardando en Firestore:", e)
        return None


def actualizar_estado(doc_id, nuevo_estado):
    """Actualiza el campo 'estado' de un pedido/reserva. Usado por el dashboard."""
    firestore_db = db()
    if firestore_db is None:
        return False
    try:
        ref = firestore_db.collection("pedidos_reservas").document(doc_id)
        doc = ref.get()
        if not doc.exists:
            return False
        datos = doc.to_dict()
        estado_anterior = datos.get("estado")
        ref.update({"estado": nuevo_estado})

        # Si se cancela una reserva que estaba contando contra el cupo, liberar el espacio
        if nuevo_estado == "CANCELADO" and estado_anterior != "CANCELADO" and datos.get("tipo") == "RESERVA":
            fecha = _normalizar_fecha(datos.get("fecha_reserva", ""))
            franja = determinar_franja(datos.get("hora_reserva", ""))
            personas = int(datos.get("personas", 1)) if str(datos.get("personas", "1")).isdigit() else 1
            if fecha and franja:
                _decrementar_ocupacion(firestore_db, fecha, franja, personas)
        return True
    except Exception as e:
        print("Error actualizando estado:", e)
        return False


def limpiar_completados():
    """
    Borra automaticamente los pedidos PARA_LLEVAR y reservas que ya quedaron en estado
    ENTREGADO y cuya fecha relevante (fecha_creacion para PARA_LLEVAR, fecha_reserva para
    RESERVA) ya paso (es anterior a hoy). Esto evita que el dashboard se sature con
    registros viejos ya completados. Se ejecuta de forma perezosa cada vez que se listan
    los pedidos, sin necesidad de un cron aparte.
    """
    firestore_db = db()
    if firestore_db is None:
        return
    try:
        hoy = _hoy_co()
        docs = firestore_db.collection("pedidos_reservas").where("estado", "==", "ENTREGADO").stream()
        for d in docs:
            datos = d.to_dict()
            campo_fecha = datos.get("fecha_reserva") if datos.get("tipo") == "RESERVA" else datos.get("fecha_creacion")
            fecha_normalizada = _normalizar_fecha(campo_fecha)
            if not fecha_normalizada:
                continue
            try:
                fecha_dt = datetime.strptime(fecha_normalizada, "%Y-%m-%d").date()
            except ValueError:
                continue
            if fecha_dt < hoy:
                firestore_db.collection("pedidos_reservas").document(d.id).delete()
    except Exception as e:
        print("Error limpiando pedidos completados:", e)


def listar_pedidos(limite=100):
    """Devuelve los pedidos/reservas mas recientes, para el dashboard."""
    limpiar_completados()
    firestore_db = db()
    if firestore_db is None:
        return []
    try:
        docs = (
            firestore_db.collection("pedidos_reservas")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limite)
            .stream()
        )
        resultado = []
        for d in docs:
            item = d.to_dict()
            item["id"] = d.id
            # timestamp de Firestore no es serializable directo a JSON, lo convertimos
            if "timestamp" in item and item["timestamp"] is not None:
                try:
                    item["timestamp"] = item["timestamp"].isoformat()
                except Exception:
                    item["timestamp"] = str(item["timestamp"])
            resultado.append(item)
        return resultado
    except Exception as e:
        print("Error listando pedidos:", e)
        return []
