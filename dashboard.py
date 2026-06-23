"""
================================================================
DASHBOARD.PY - Panel de administracion de pedidos y reservas
Raices Ancestrales del Pacifico Gastro Bar
Blueprint de Flask: vista de pedidos/reservas en tiempo real
(via polling) con cambio de estado, protegido con login compartido.
================================================================
"""
import os
from functools import wraps
from flask import Blueprint, request, jsonify, render_template_string, Response

import firestore_db

dashboard_bp = Blueprint("dashboard", __name__)


# ----------------------------------------------------------------
# Autenticacion basica (usuario y contrasena compartidos)
# ----------------------------------------------------------------

def _credenciales_validas(usuario, password):
    user_ok = os.environ.get("DASHBOARD_USER", "raices")
    pass_ok = os.environ.get("DASHBOARD_PASSWORD", "Raices2026!")
    return usuario == user_ok and password == pass_ok


def requiere_login(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        auth = request.authorization
        if not auth or not _credenciales_validas(auth.username, auth.password):
            return Response(
                "Acceso restringido. Ingrese usuario y contrasena.", 401,
                {"WWW-Authenticate": 'Basic realm="Dashboard Raices"'}
            )
        return f(*args, **kwargs)
    return decorada


# ----------------------------------------------------------------
# Estados validos de un pedido/reserva
# ----------------------------------------------------------------
ESTADOS_VALIDOS = ["PENDIENTE", "CONFIRMADO", "EN_PREPARACION", "ENTREGADO", "CANCELADO"]


# ----------------------------------------------------------------
# Rutas
# ----------------------------------------------------------------

@dashboard_bp.route("/dashboard")
@requiere_login
def dashboard_home():
    return render_template_string(DASHBOARD_PAGE)


@dashboard_bp.route("/dashboard/api/pedidos")
@requiere_login
def api_listar_pedidos():
    pedidos = firestore_db.listar_pedidos(limite=200)
    return jsonify({"pedidos": pedidos})


@dashboard_bp.route("/dashboard/api/pedidos/<doc_id>/estado", methods=["POST"])
@requiere_login
def api_actualizar_estado(doc_id):
    data = request.get_json(silent=True) or {}
    nuevo_estado = data.get("estado", "")
    if nuevo_estado not in ESTADOS_VALIDOS:
        return jsonify({"ok": False, "error": "Estado invalido"}), 400
    ok = firestore_db.actualizar_estado(doc_id, nuevo_estado)
    return jsonify({"ok": ok})


@dashboard_bp.route("/dashboard/api/disponibilidad")
@requiere_login
def api_disponibilidad():
    fecha = request.args.get("fecha", "")
    if not fecha:
        return jsonify({"ok": False, "error": "Falta parametro fecha"}), 400
    resultado = {}
    for franja in firestore_db.FRANJAS.keys():
        db = firestore_db.db()
        ocupacion = firestore_db._obtener_ocupacion(db, fecha, franja) if db else 0
        resultado[franja] = {
            "ocupacion": ocupacion,
            "capacidad": firestore_db.CAPACIDAD_MAXIMA,
            "disponible": firestore_db.CAPACIDAD_MAXIMA - ocupacion,
        }
    return jsonify({"ok": True, "fecha": fecha, "franjas": resultado})


# ----------------------------------------------------------------
# HTML del dashboard (Tailwind via CDN, vanilla JS, sin build step)
# ----------------------------------------------------------------

DASHBOARD_PAGE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard - Raices Gastro Bar</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/tailwindcss/2.2.19/tailwind.min.css"></script>
<style>
body{font-family:Arial,sans-serif;background:#F5F0E8}
.card{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.1)}
.badge{font-size:11px;padding:3px 10px;border-radius:12px;font-weight:600}
.b-PENDIENTE{background:#FFF3CD;color:#92750A}
.b-CONFIRMADO{background:#D4EDDA;color:#1E7E34}
.b-EN_PREPARACION{background:#CCE5FF;color:#004085}
.b-ENTREGADO{background:#D6D8D9;color:#383D41}
.b-CANCELADO{background:#F8D7DA;color:#842029}
select{border:1px solid #D4A04A;border-radius:6px;padding:4px 8px;font-size:12px;background:#fff}
.tab{padding:8px 16px;border-radius:8px 8px 0 0;cursor:pointer;font-size:13px;font-weight:600;color:#777}
.tab.active{background:#fff;color:#4A1A0A;box-shadow:0 -1px 3px rgba(0,0,0,.08)}
</style>
</head>
<body class="p-4 md:p-8">
<div class="max-w-6xl mx-auto">
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold" style="color:#4A1A0A">🌊 Raices Ancestrales del Pacifico</h1>
      <p class="text-sm text-gray-500">Panel de pedidos y reservas</p>
    </div>
    <button id="btnRefresh" class="px-4 py-2 rounded-lg text-sm font-semibold" style="background:#4A1A0A;color:#F5D78E">↻ Actualizar</button>
  </div>

  <div class="flex gap-2 mb-0">
    <div class="tab active" data-tab="todos">Todos</div>
    <div class="tab" data-tab="DOMICILIO">Domicilio</div>
    <div class="tab" data-tab="PARA_LLEVAR">Para llevar</div>
    <div class="tab" data-tab="RESERVA">Reservas</div>
  </div>

  <div class="card p-4 mb-4 overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-gray-500 border-b">
          <th class="py-2 pr-3">Fecha/Hora</th>
          <th class="py-2 pr-3">Tipo</th>
          <th class="py-2 pr-3">Cliente</th>
          <th class="py-2 pr-3">Telefono</th>
          <th class="py-2 pr-3">Detalle</th>
          <th class="py-2 pr-3">Personas</th>
          <th class="py-2 pr-3">Total/Deposito</th>
          <th class="py-2 pr-3">Pago</th>
          <th class="py-2 pr-3">Estado</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <p id="vacio" class="text-center text-gray-400 py-8 hidden">No hay pedidos o reservas registrados todavia.</p>
  </div>
</div>

<script>
var TODOS = [];
var filtroActivo = 'todos';

function badge(estado){
  return '<span class="badge b-'+estado+'">'+estado.replace('_',' ')+'</span>';
}

function selectorEstado(id, estadoActual){
  var estados = ['PENDIENTE','CONFIRMADO','EN_PREPARACION','ENTREGADO','CANCELADO'];
  var html = '<select onchange="cambiarEstado(\''+id+'\', this.value)">';
  estados.forEach(function(e){
    html += '<option value="'+e+'"'+(e===estadoActual?' selected':'')+'>'+e.replace('_',' ')+'</option>';
  });
  html += '</select>';
  return html;
}

function fila(p){
  var fecha = p.tipo === 'RESERVA' ? (p.fecha_reserva||'-') : (p.fecha_creacion||'-');
  var hora = p.tipo === 'RESERVA' ? (p.hora_reserva||'-') : (p.hora_creacion||'-');
  var detalle = p.tipo === 'RESERVA'
    ? ('Reserva' + (p.celebracion ? ' 🎉 '+p.celebracion : '') + (p.productos ? ' | '+p.productos : ''))
    : (p.direccion || p.productos || '-');
  var totalLabel = p.tipo === 'RESERVA' ? ('Deposito: $'+(p.deposito||'0')) : ('Total: $'+(p.total_platos||'0'));
  return '<tr class="border-b hover:bg-gray-50">'+
    '<td class="py-2 pr-3 whitespace-nowrap">'+fecha+'<br><span class="text-gray-400">'+hora+'</span></td>'+
    '<td class="py-2 pr-3">'+p.tipo+'</td>'+
    '<td class="py-2 pr-3">'+(p.nombre||'-')+'</td>'+
    '<td class="py-2 pr-3">'+(p.telefono||'-')+'</td>'+
    '<td class="py-2 pr-3 max-w-xs truncate" title="'+(detalle||'').replace(/"/g,'')+'">'+detalle+'</td>'+
    '<td class="py-2 pr-3">'+(p.personas||'-')+'</td>'+
    '<td class="py-2 pr-3 whitespace-nowrap">'+totalLabel+'</td>'+
    '<td class="py-2 pr-3">'+(p.pago||'-')+'</td>'+
    '<td class="py-2 pr-3">'+selectorEstado(p.id, p.estado||'PENDIENTE')+'</td>'+
  '</tr>';
}

function render(){
  var lista = filtroActivo === 'todos' ? TODOS : TODOS.filter(function(p){return p.tipo === filtroActivo;});
  var tbody = document.getElementById('tbody');
  var vacio = document.getElementById('vacio');
  if(lista.length === 0){
    tbody.innerHTML = '';
    vacio.classList.remove('hidden');
    return;
  }
  vacio.classList.add('hidden');
  tbody.innerHTML = lista.map(fila).join('');
}

function cargar(){
  fetch('/dashboard/api/pedidos')
    .then(function(r){return r.json();})
    .then(function(d){TODOS = d.pedidos || []; render();})
    .catch(function(e){console.error('Error cargando pedidos:', e);});
}

function cambiarEstado(id, nuevoEstado){
  fetch('/dashboard/api/pedidos/'+id+'/estado', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({estado: nuevoEstado})
  }).then(function(r){return r.json();})
    .then(function(d){ if(!d.ok){ alert('No se pudo actualizar el estado.'); cargar(); } });
}

document.querySelectorAll('.tab').forEach(function(t){
  t.addEventListener('click', function(){
    document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
    t.classList.add('active');
    filtroActivo = t.dataset.tab;
    render();
  });
});

document.getElementById('btnRefresh').addEventListener('click', cargar);

cargar();
setInterval(cargar, 15000); // refresco automatico cada 15 segundos (polling, simple y suficiente para este volumen)
</script>
</body>
</html>"""
