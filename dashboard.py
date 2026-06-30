"""
================================================================
DASHBOARD.PY - Panel de administracion de pedidos y reservas
Raices Ancestrales del Pacifico Gastro Bar
Blueprint de Flask: vista de pedidos/reservas en tiempo real
(via polling) con cambio de estado, filtro por fecha, resumen de
hoy/manana, y limpieza automatica de registros ya completados.
Protegido con login compartido.
================================================================
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
from flask import Blueprint, request, jsonify, render_template_string, Response

import firestore_db

dashboard_bp = Blueprint("dashboard", __name__)

TZ_COLOMBIA = ZoneInfo("America/Bogota")

def _hoy_co():
    """Fecha/hora actual de Colombia, sin depender de la zona horaria del servidor."""
    return datetime.now(TZ_COLOMBIA)


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
    hoy = _hoy_co()
    manana = hoy + timedelta(days=1)
    return render_template_string(
        DASHBOARD_PAGE,
        hoy_iso=hoy.strftime("%Y-%m-%d"),
        manana_iso=manana.strftime("%Y-%m-%d"),
    )


@dashboard_bp.route("/dashboard/api/pedidos")
@requiere_login
def api_listar_pedidos():
    # listar_pedidos limpia automaticamente (al consultar) los registros ENTREGADO
    # cuya fecha relevante ya quedo en el pasado, para no saturar el panel.
    pedidos = firestore_db.listar_pedidos(limite=300)
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
        dbref = firestore_db.db()
        ocupacion = firestore_db._obtener_ocupacion(dbref, fecha, franja) if dbref else 0
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
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tailwindcss/2.2.19/tailwind.min.css">
<style>
:root{
  --cafe-oscuro: #342311;
  --rojo-vivo: #c81e1e;
  --rojo-coral: #dc4750;
  --naranja: #fa5302;
  --dorado: #ffa808;
  --crema: #FDF8F0;
  --crema-2: #F5ECDD;
}
*{box-sizing:border-box}
body{font-family:Arial,sans-serif;background:var(--crema)}
.card{background:#fff;border-radius:14px;box-shadow:0 1px 4px rgba(52,35,17,.10)}

/* ---- Header ---- */
.logo-img{height:56px;width:56px;object-fit:cover;border-radius:50%;box-shadow:0 0 0 2px var(--rojo-vivo),0 0 0 4px #fff,0 0 0 5px var(--rojo-coral)}
.titulo-marca{color:var(--cafe-oscuro)}
.subrayado-marca{height:3px;background:linear-gradient(90deg,var(--rojo-vivo),var(--naranja),var(--dorado));width:70px;border-radius:3px;margin-top:4px}
.btn-refrescar{background:var(--cafe-oscuro);color:var(--dorado);transition:background .15s}
.btn-refrescar:hover{background:#4a3320}

/* ---- Tarjetas resumen ---- */
.stat-card{background:linear-gradient(135deg,#fff,var(--crema-2));border-radius:14px;padding:16px 20px;box-shadow:0 1px 4px rgba(52,35,17,.10);flex:1;min-width:150px;border-left:4px solid var(--naranja)}
.stat-card.stat-manana{border-left-color:var(--dorado)}
.stat-card.stat-llevar{border-left-color:var(--rojo-coral)}
.stat-num{font-size:30px;font-weight:800;color:var(--cafe-oscuro);line-height:1}
.stat-label{font-size:11.5px;color:#9b8b7a;text-transform:uppercase;letter-spacing:.05em;font-weight:700;margin-top:4px}

/* ---- Filtro de fecha tipo calendario ---- */
.filtro-bar{background:#fff;border-radius:14px;box-shadow:0 1px 4px rgba(52,35,17,.10);padding:12px 16px;display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.filtro-label{font-size:12px;font-weight:700;color:#9b8b7a;text-transform:uppercase;letter-spacing:.04em}
.input-fecha{border:1px solid #e6dac6;border-radius:8px;padding:7px 10px;font-size:13px;color:var(--cafe-oscuro);background:#fffdf8}
.chip{padding:7px 14px;border-radius:20px;font-size:12.5px;font-weight:700;cursor:pointer;border:1px solid #e6dac6;background:#fffdf8;color:var(--cafe-oscuro);transition:all .12s;white-space:nowrap}
.chip:hover{border-color:var(--naranja)}
.chip.active{background:var(--cafe-oscuro);color:var(--dorado);border-color:var(--cafe-oscuro)}

/* ---- Tabs Para Llevar / Reservas ---- */
.tabs-wrap{display:flex;gap:8px;margin-top:18px}
.tab{padding:10px 22px;border-radius:10px 10px 0 0;cursor:pointer;font-size:14px;font-weight:700;color:#9b8b7a;background:#efe3cf;transition:all .12s}
.tab.active{background:#fff;color:var(--cafe-oscuro);box-shadow:0 -2px 4px rgba(52,35,17,.08);border-bottom:3px solid var(--naranja)}
.tab .tab-count{display:inline-block;background:rgba(0,0,0,.08);border-radius:10px;padding:1px 8px;font-size:11px;margin-left:6px}
.tab.active .tab-count{background:var(--naranja);color:#fff}

/* ---- Tabla ---- */
.tabla-wrap{border-radius:0 14px 14px 14px}
table{border-collapse:separate;border-spacing:0}
thead th{position:sticky;top:0;background:#fff;z-index:1}
tbody tr{transition:background .1s}
tbody tr:hover{background:#FBF4E7}

/* ---- Estado coloreado (select real, no decorativo) ---- */
select.estado-select{border:1.5px solid transparent;border-radius:20px;padding:5px 10px;font-size:11.5px;font-weight:700;cursor:pointer;outline:none;appearance:none;-webkit-appearance:none;background-repeat:no-repeat;background-position:right 8px center;background-size:10px;padding-right:26px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'%3E%3Cpath fill='%23342311' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E")}
select.b-PENDIENTE{background-color:#FFF3CD;color:#92750A;border-color:#F0DA8C}
select.b-CONFIRMADO{background-color:#D4EDDA;color:#1E7E34;border-color:#9FD8AE}
select.b-EN_PREPARACION{background-color:#FCE4D6;color:#9A3B12;border-color:#F4BC9C}
select.b-ENTREGADO{background-color:#D6D8D9;color:#383D41;border-color:#B7BBBE}
select.b-CANCELADO{background-color:#F8D7DA;color:#842029;border-color:#EFA8AE}

/* ---- Cupo / ocupacion de franjas (solo en pestana Reservas con fecha filtrada) ---- */
.cupo-bar-wrap{background:#fff;border-radius:14px;box-shadow:0 1px 4px rgba(52,35,17,.10);padding:14px 18px;display:flex;gap:24px;flex-wrap:wrap}
.cupo-item{flex:1;min-width:200px}
.cupo-titulo{font-size:12px;font-weight:700;color:var(--cafe-oscuro);margin-bottom:6px;display:flex;justify-content:space-between}
.cupo-track{background:#EFE3CF;border-radius:10px;height:8px;overflow:hidden}
.cupo-fill{height:100%;border-radius:10px}

.badge-tipo{font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:8px;background:#EFE3CF;color:var(--cafe-oscuro)}
</style>
</head>
<body class="p-4 md:p-8">
<div class="max-w-6xl mx-auto">

  <!-- HEADER -->
  <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
    <div class="flex items-center gap-4">
      <img class="logo-img" src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCACgAWADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD7LooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooqC+vLSxt2uL25htoV6yTSBFH4nigLXJ6K5Kf4mfDuCTy5fHXhpXHUf2nD/wDFVqaN4r8May4TSPEWkag5/htb2OQ/kpzS5l3NHSqJXcX9xs0UZFFMzCiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACsrxX4i0bwvo0ur65fRWdnGQpd8ksx6IqjlmPZQCTSeLvEOmeFvD13rmrTGO1tUyQq7ndicKiL/ABOzEKB3JFeE+LfEF1p2pDxR4qa1XxSITPZ2c7B7TwxbN0ZgeJLph1J78DCjnKrVVNXZ34DAVMZUUYr+v8l1f5tpPovE3jbxXqrxJ5s/gywuhm0tY7UXevXy/wB5IOUt193yR321wWqQ+FoLpp9bfS1vB96TV3k8Q6kT7rn7PCfYZxXCxa3418YPdHwxFLZ6Zd/NdazfAvNeDoWxw0i+gO2MdlPWnR/B+0voA9/r2oajORuZLpzFDn0CxkKPyNeTWxyjK0n/AF+H5o+8wGUYailbXz2X32ldesZJ7prY64+Lfh9CfJa68VXI6FYI7Kxj/BI1H86R7L4M64m7ULPxZYSHpcOIpAvvuAJ/KvLfEHgLQdEt2ku9K0aONVyWYqT/AI5rzDWda8O6dJeWth9utLmMg201lcN5R45DKWxnPtis8PjYYmTjTje3W2n33/zPWx2GwuX0VVqyUU/5ajv8l7Pl++yPtXwVouu2MYl+F3xVi1y2jGTo+sEyDA/hGTvT6jbXpHhfx4s9/FoXivTJPDeuvxHBcOGhuvUwS/df/d+8PevzDh8ceJYYkEeqTpNG4aKdGKSRkejDBH1r3z4SftIQ65Yp4G+NUY1XSJyFh1oLi5tH/hdyo+bH98fMO+4Zr1acKkV28r3X+aPgMwxmX16i5U3F9eWMZL/wF8svmk33R97Ag9KK8T8H+N9R8D+JbLwb4x1NNT0bUYxJoHiDcClxEcbVkYcEjIGc8ZB5UjHtgOa3hUU/U8jF4OWGa1vGWqa2a/zXVPVBRRRVnIQ3l3a2UPnXlzDbxZxvlkCLn6mucT4jfD95vJXxx4aMmcbf7Uhzn/vquW+MHwdtPifrNpNr3ijVrfSrSLEWm2ixqnmknMpLA5JGB04A46mvJ/EX7H9qYnbw94ylWT+CHULNWU/V0II/75NZylNbIuKi92fUtrc293bx3NrPHPDINySRsGVh6gjg1LX5/app3xk+BWqQy/atQ0+zDgRTW8xn0+fn7pU/KM/3WCn0r6R/Zq+OUvxMur3Qtc0+1sNatYRcRtbMfKuIshWIViSrKSMjJyGz2pRqpuz0Y5U2ldbHuFFFFamYVDZXdrfW63Nlcw3MDZ2yQyB1OOuCOK+d/wBtX4k3fh/Q7LwboOpNbahqYaW+eCXbLFbDgLkcr5hzz1wjDvWf+wj40W60TU/Ad0wEtgxvbIAYzC7YkX8HIP8AwP2rP2i5+UvkfLzH09RRXnv7RHiDxP4Y+FGq6x4RidtThMeJEiEpgjLjfJsIIOFz24zntVt2VyUrux6FketFfnxJ+0B8Y2iLHxbOEPG4WEAH5+X1q3oX7R3xds5ooRrkGq7cKIbixjdn9soA2e2ax+sRNfYyPvygkAZNUNO1Av4ft9U1JEsC1qs9ykkg2wZQMwLdMLzz7V8WftG/HjUPHN3P4Y8LSy2fhyOUo8sbESaiQcBjjkRnsnVuCewrSdRRVyIwcnZH1xe/EfwDZapJpd54z0C3vIl3PFJfxqVHvk4zx0610Om39jqdlFfadeW95ayjdHNBIHRx6hhwa+Tvg/8AsxadqPg8a78RLvUtMmuEMsdlA6Qm2j6h5WYHDEc7eNo689O4+Gfwm0Twz4rttR+GfxYnlto5c32mG5huorhMfdYRkYPvjPoRUxnN7objHoz3y7u7W0UNdXMMCnoZJAo/WqJ8R+Hw2065pgPp9rj/AMa+aP2lvgv8RvG3xIOtaSLG90yWEKgluhEtmFABDBupb72VHavDPhD8Jda+Jup6nY6Jd6RbHTQjTyXTNtYMzKCm1Tu+6fTtUyqyTtYcacWr3P0Im8TeHIYTNNr+lRxr1d7yMKPxLVLp2u6LqQJ0/V9PvABkmC5STA/Amvk+X9j3WRpe+HxhpTahkfumsHWH3+fcW/8AHayLb9kv4greBG1nwzDEeGmSSVuP93yxn6Zp88/5Q5IfzH2wCCMg5BozXBfEDxzpPwp+HVtqOvuk9xFDHa29tarsN1OE+6gOdq8EknO0evGflKXX/i9+0N4oOn6bI9jpcRHmQ28rw2Vqv96VxzI59DknsAKqdRR06kxg3r0Pt+XU9NinFvJf2iTHojTKGP4ZzVsEHpXzd4c/ZH8JQ2qv4k8Q6xqV4Rl2ttlvGD7ZDMfqTXp3w6+GL+A7+JdF8Y+ILnR8OJdM1KVbiPkDYY2IBjKnJOOGBxjjNNOXVCaj0Z6HRRRVkhRRRQAUUUUAFB4GaKqa3fw6Vo97qdzxBZ28lxJ/uopY/oKBpNuyPHfiX4lguPFl9q1yI5tH8GOkdpBI2I7vWZVym49NsEbBj6Fif4a8Z0fQ5PiFdv4h1rUBNowvDJbB4yTqswPzXUin/lnkYjQjGACewrO+Lep3cuheD/BbSOLrVreTXdbZSd267YyyZ99jLGPQOavWXiW7jEUcUfloiqihcIqKvAUDpgV8tm2aPDSsldv8P62+XmfqOQZDVrUL09lv59UvS3vPvzJfZPTpUt4rYLBvDAAE+QGz+fA/CjSZrCC8e6uUmkQx7WVohgH+9gcZ7VzX/CYX11b+S32YxgBfkRcD8QM0/TruUEurK2eCdx5+or5HG53zPSJ7Esvqxg1U0+f62PEv2qbmZLi1vIIzarfSsxCyF8gDHDYwPpXz+xJJJJJ96+rP2iJtP1bwNJFfyiO4ssTwuYx97pt49c4r5Sr7PhXE/WMAm42ab/zPgOL6daOMi6mzirLslp+gUoZg24Eg+tJR3r6Q+UPoL9nXxq/iTQ2+DviK5Rlncz+Fruc5+x34yVgJP/LKXlcerED73H2H+z74ul1fQI9F1Ey/a7WASW5lOZGhDGNkb1eKRWib6Ke9fmDaTzWt3Dc2szwzROskciHayODkEHsQQDX3P8JPGCaiYPGsRWMi4tNVulXoqXubW/QD+6LmES47bqwqrlkqi+Z7GXv6xSlhJddY+UttPXRfO/RH1VQelIDkUprc8c+e/D/xF1+7/bF1bwkLy6n0JbNrRLQHMUEkcSSGXHYltyk/7QFcB+0Z8bviT4c+K13o2jXo0Ky03CxRGCOT7UGAIlfcDkHsBjAz3qr+z7rFrL+154hunnKrqE+pxw/PkOxmBAyevCEj6V9M/Eq58A+F7KTx34t07TDLZRiOK7ktEkuGJOVjjJGSxPQDpyeBk1zq8ovXqbO0ZLQ574h6zHqn7MOp654q09LeS98OedPbOOEneMbAB2PmFSO4OO9fLX7G4m/4X5pHl8gWl35vH8PlH/2bbVf46/G/xB8TJDpsUJ0rw9HIGjskbc8xB+VpmH3jnoo4B9TzXvf7Hnwnv/CGnXPjDxHbG21XU4BFbWzjD29vkMS47O5CnHUADPJIE39pNW6FW5IO/U+h6y/FuuWPhrwzqWv6lJstNPtnuJTnkhRnA9z0Hua1K+Zf26fG8dp4d0/wLY3S/aL+UXOoIrfMkCcorem58H3CV0TlyxuYxjzOx5H8LvDuo/H34zarqPiSeeO3aGS7vHhOPKH3IIVPYA4HuEb1zVf9n2e/8D/tKabpWoMIpxfz6ReDGFYsGXp6FwhH4V9D/sg6JonhT4YQ3NzqenjV9cYXtzH9pTeiYxFGRnPC/Nj1c14D+1/pw0j46XepWE+z+0ba3v45In5SQDYSCOhBjB/GuVx5YqXU6FLmk49D71HSg81xPwP8ZxePPhnpGv8Amq920IhvgBjZcoAJBj68j2Irtq607q5ytW0PnH9u/Uo7L4caLosRWM32qiQooA3JFGxP4BmT9K7j9lSwto/gT4Xna0hW4aGVmk8sbyfOkwSevTFeMft/XpfxH4T07PEVpczkf7zov/spr3D9liTzfgD4TcnP+iup+omkH9Kxi/3rNWrU0cn+2r41k8OfDWLw9ZTeXeeIJGgfHUWyjMv0zlV+jGvI/wBjPwlpNxqet/ELxEsH9neH4sQtOmUSXaXaXnjKIOPdvUCqH7b3iFtT+Lsej5HkaLYJHgf89Jf3jn8tg/Ct/wCITH4c/sieG/C0JMWoeK5Bc3pHXYwE0g/Lyk+mahu8230LStBLucp4o1n4gftE/ESe18OW9ymlQKVgtWuGjtraHJ/eTHoXfr0J7AECvS/hF+zH4h8NeLtE8S6x4o0+NtNu0uvsllC778dUMhK4z0PB4r0P9kLwp/wjfwcsbqe18m+1iRr6YsuHKtxFn22AED/aPrXsVXCkn70tyJVGvdWxh/EC5ksvAfiC8ibbJb6XcyqfQrExH8q+WP8Agn7u/wCEm8UDB2/2fa5Pvvf/AOvX0l8brn7H8H/F9xnG3RroA/WJh/Wvkj9kv4l+GPhxqevDxPd3Fvb6hBb+U0Vs8o3oXyDtyRw/pRUdqkRwTcHY+6KK8z0r49/CPUXjjh8a2MLv0W6jkgx9S6gD861vinr0w+EGv614UvI7udtOl+xXFpIJAXPygow4JBPHuK15la6MuV3Pkz9szxxbeKfiVFo+nTrPYaBE1uzo2Va4Y5lx/u7VX6g19R/s1aHBoHwS8MW0Xks9xZrezPGB87zfvCSR1IDBc/7NfE/w/wDhxrPxB0DxHqWhTm71nSHjmewcfPdRSbyzI3/PQMp+U/ez1z17/wDZy+O8/wAPIpPC3i2O8uNCjY/ZwkW6axfd8y7SQSmcnb1BzjriuaE7T5pdTonG8eVdD7formPBHj/wd40tlm8NeILHUGK7mhSTEyf70Zwy/iK6eupNPY5mrBRRRTAKKKKACiiigArifjxM8HwZ8XyRnDf2PcLn6oQf5121c18VdNfWPhn4m0uJS0tzpVzHGB3cxtt/XFTL4Wa0GlVi33R8feLIptT+Oviy4ihWaPTUtdNgVnwFVIlyP0X8q1PsFrDB5tzHDAR1+bcAfw5rA0fWZLjxj4rv7d4h9tubW73N94iS1jYY/HNegeEoNPvLrdIryyyrhw8LSrnuemBX5RxJiJwxc5PZW29Eft2UVpUMrhNrRX230bX5Ii8Px288DJbDT7nI+4ApYAdyMg1v6Ro32qVo4DbNJ0/drhR6k/Ma63TNF0vyVKwxQbR1EAB/kKlfT9NMTi2VvNBwDs2D35Havg6+ZqUmopo8jE5yqkpcl1/XU+ZP2sNF1HTfC1lcyFGhkvliYowII2sVzj3zXzPXvX7XXi26ufFA8Hi0lgttOcSvLICPPYrxt55UA9e5z0xXgtfuPCVKrTyqn7Xd6/J7fgfn3EGLeKxjk3eyS+4KKKK+kPECvpv9kC6fV9E8YaFLlhD4bvjH7fPFIv5NuP418yV9SfsP2TWvh/4j+I5FxDb6FJDuPTcwY4/8h1lW+CzPQyxyWIUo7q35q34n3F4Uu2v/AAxpV+5y1zZQzH6sin+taMh2oWIJxzwMmsjwPA9r4L0S2kBV4dOt42B7ERqDS+NdVGheD9Z1pjgWFjNc/wDfCFh+oq4v3U2cuISVWSjtd/mfm5L4h1TRfiDe+I9EuZdNv4tQuZYJBgtEWdwR82QeGIOc1s2OnfE74u6/GFGteIrsjAnuGIghA6kucRoPpjPvTfgUkOofGvwmuqQLepcaqhnSRA4dm3HJB4I3cn6V+kMaIiBUUKoHAAwBXLTp863NKk+TofCPwB03TPBP7RsPhvx5ptpNeQyG0t5HbfFb3hCtHIMjDZHygkcFgRX3gOnFfHH7cvgeXTfFVj49slcW2pqtreMv/LO4jX922e25Bj6x+9e3/sy/E+L4ieBY476Zf7f0tVg1BDwZOMJMB6OBz6MGHpWtJ8rcGZ1FzJSPTNc1Kz0bRrzVtQlEVpZwPPM5ONqKCT+gr84hZ+Lfi58RdUu9J0+bU9W1CWS8eIOq7IwQACWIACrtXr6V7N+2j8VJdQ1d/hzotxtsbJlfVZY3/wBdNjIhOP4U4JHdsD+GuG8E/s+/E/xB4ds/Eelx2dhDeLvgW4vHgmMZ6OQFOFPUc5IIOKirLnlZdCqa5VdlvRv2XfilfqJLmw0bTM8/6Vegt+Uat/Os/wCLfwI8SfDXwfD4i1jVtMu0ku47Uw2gkJQsrEEswHGVx0716PpP7PXxut4V8v4kQ2G0YCR6teNt9uABVHx98HPjlD4I1SXX/H6axpNnA11NZtqNxN5qxjdwrJyRjIye1S4afCylPXc3/wBgLWpGtfFPh2SQmOOSC9hTsCwZH/8AQEr6pr4m/YRv1t/itqdkcn7Zo7bcdMpKjfyJr7ZPSt6DvAxqq0j4i/bgvEu/jTp9m7ER2ulQI2Oo3yyMf0xX0r+zPp50z4G+GrbzRKrQSTRsP7kkruoPuAwB96+Qv2rr1rr9oLxFIDn7O9vCvfGyGM/zJr7L+AMq3HwV8JSrCIg2lRHaBjt1/Hr+NZ09ajLqaQR8P/tHXBvfjr4weU8DUTCfZURE/kK9F/bnmEXiLwlpNuSLS00IvCoOQNz7f5RrXn37TNhc2Pxx8XJNH5ZmvfOj56q8aMp/WvTv2p9HuPGHw48EfE/S0e6s/wCyltr8oCTFuAYMfYN5ik9jis7aSNP5T6s+H1q1j4D8P2UkYje30y2iZM52lYlBFblfOPwX/aW8J3WgWOj+NZW0TUraJIDctGz20+1QA+4AlCcchuM98V7x4d8TeHvESytoOtWGpiEKZPss6ybA2ducHjODj6V1RnFrRnNKLT1OO/ablMPwG8XsDjOnsn/fTKP618V/BL4Yaj8UfEF9pmn6laaeLKBZ5ZLiNnBDNtAAUjn8RX1h+2pqRsfgbeWyyqjX97bW+0nlhv3kD8Erzn9gDTHM/i3WWUhMW1op7E/O7D8iv51jUXNUSNYNxptm/pH7JPhmKaB9W8TandonMsdvCkAk9s5YgZ/H3r3Twj4R0Lwt4RtfCulWmNLtlZUimbzCQzFjknrySa3qK3jCMdkZOblufnhZ6v41+BvxYvp47FrK4E0sb2tyrGC8tzISMN/EvQhgcg/iK6zxX4r+DfxYvEv/ABDaap4E8Sz/ACzX9tGtzZynoGlAwT2+bCn1JxX2j4h0DRPEVg1hrulWWp2rf8srqFZF+oyOD7ivJ/FP7Mvwu1a3lGnadd6HcsMpLZXTlUP+45Zce3H4Vg6UlotjVVIvV7nzF4y+D3jnwNBD4p0W8h1zTIh5sesaDMzeQB3bb8yDH8QyPU16n+zR+0LfPqkHhL4g6lJdrdyLHp+qTY3RsekczcZBOAHPIJweORnt4A+Jn7Pest4q0O6/4SPwpG2dTt7cFd8H8RlgJIBAyQ65weuBmvMP2kl8LQfFO9fwZDFbWDWkE5jhj2Ikzp5jYHb7y5HGDkY4rPWnqtC9J6M/ROis7ww88nhzTJLrPntaRGXIwdxQZ/XNaNdpyhRRRQAUUUUAFIwyCMZpaKAPz6+Julal8PvjTrGhQyzW9vOgazdDjfECXi+uEcr/ANszVzTfFevwj/j+unbGAGnbb+WcV9F/tZfC258ceFIde0CEN4k0TM1soHNxGOWi9z1I+rDvXxtp+qXt9GXSxEYyVOSco46qQe4NfJZzlkalTncVZ9/67fkft3A+c4TFYT6rXjea2Vr+v469tbdD3rwl4h8TXsUcYsrC43HaiTXO0+5wT+te2eDdG1ryWuNf+wIJF+SGGPLJ7788/lXxjpGs6xZBlMtyqOMGNRgV6F4V+KWq6REkZe9kjAAINxgjHoCDivhMyyBqbcYRkuydvx/yt6ndnPDuIx8G8HFRv0s0/vbsjhf25rHULX4qwSyC9OmyWafZWlQCEN/y0EZHXnBOecn0xXz9X0f8Xb+H4hJa/bjLG8GWV1zuVj1zkkNkY9K4GPwLo8drLHvnlmdCEkd8bG7HAr7zIcwp4XLqVCsrSirWX9fefE4nw5zmpVcoJNNXu3bXtbf06Hl4x3o78VJdQyW1xJBKpWSNirA9iDg1JpkyW+oQTyIsiRyKzKRkEA8jFfVt6XR+exp/vFCemtn5f8MO0+ylu7uK3jHzSHAycfWvuz4K+Dn8O/s+aVoRj8vUvHGpRBhtwwtsglsenkozf9tK8Q+BPgaT4keO4oltxFZy4mvpFXH2eyU8JkcB5D/P2NfZ/gqOPxJ4tl8UQRquiaVE2maGqjCvggTTr/skqI1Pop9a4lUdZ2t5f5n1FXBUsr96M+Zr3r2t/wBe1bvJ+81ukvJnfxqFQKoAA4AHYV5z+09cSWvwF8WyRSNGzWPl5GejuqkceoJH49q9Iqh4i0jT9f0K90XVYBPY30DwTxn+JGGD9D712yV1Y+UTs7nwd+yJZW178fND+0AkW8VzcRgDjesRAz/30T+Ar9AK8u+F/wAC/BPw88SyeINEbU57xrcwIby4EgiBxuK4UcnHOc+2K9RrOlBwjZl1JKTujmfih4RsvHXgTVPDF8Qi3kJEUpGTDKOY5B9GAP0yO9fEfwbTx38PfiXq97YaFPPcaHb3Vvq0e/ZDGqxs5Lk8MAE8xR1bAxX6BVVOm6cZ57g2FqZrgBZ5DCu6UAFQGOMnAJHPYkU50+ZpijPlTR8I/syeBh8Uvijcaj4jeS8sLIf2hqDFv+PiZ3yiMR2ZtzEdwpHevvdFVFCqAFAwAB0qnpek6VpfmjTNNsrHzW3SfZ4Fj3n1O0DJ+tXaKcORBOfMwqprVjHqmj3umzMyx3dvJA7L1AdSpI/OrdFaEHw9+zd4L8S+GP2kNN069tntGslvd7TqyLcQRhoWaM9HG8r0+teg/tSfGnx14E+Ilt4f8OTWFlaCwjuS8tuszzl2YHO77oG3GB9c19ONDC06TtEhlRSqOVBZQcZAPUA4H5CszXvDHhvX5Y5dc0DStTkiGI2u7RJSgznALA4FY+zajaLNPaXldo/M7xf4ivvFXiXUPEOrzQNfX8nmzmIBFztC8DPHAFfWnwX/AGjPBcHg3QvDep2l7bajaW0FiqWtuZUmcAINu0cE9SP517nH4G8FREGPwh4fTHI26bCMf+O1q2OlaXYKFsdOs7ZQxYCGBUGT34HWlClKLvcqdRSVrHz9+2b8NNR8T6Rp3inwzozXt/Yl0vlt1zNJAVG1tvV9hHQc4Y8GvCPgp8adZ+Hscuh6laLrnhe43rcabMRmPdw3llsgZ7oflPPQ81+gleX/ABL+BPw98dXLX17psmm6ixy95pzCF5P98YKv9SM+9E6bvzRFGorcsjwCPXv2U9Wvmurrwrr+js3JjVJRCDnPCxSMB9AAK9X+CPxB+CNr4ok8JfD+1u7K41E+aZ54ZBHMUU4QPKxYbRnC4A64rk9W/ZA0+S83aV43u7e2I+5c2KyuDj+8rKD+VdV8NP2YfCXhXXoNa1XVbzX7m1kElvHLEsMKOOQxUEliDyMnHsaUYzT2RUnBrdnJ/wDBQGa5GmeELdWxavcXTsATkuqxgfozV518B/j3D8MPCMnh9vCn9o+bfPdSXCXflswYKMYKnkBeO30r7F+IfgTwv4+0ZdK8T6at5DG/mQuGKSQt6o68rkcH1HWvNo/2XPhSsm82usOP7jak+P05olTnz80RRnHl5WYOk/tceC55QmpeG9fslP8AGgimA/AMD+leoeBvir4O+IKXln4P1kT6jDAZPJmt3jZMjAJDAZAOM4rnrD9m34RWsokbw5Nc4/hnv53X8twr0Xwr4V8N+FrMWnh3Q9P0uHGCLaBULf7xHLfiTVxVTqyJOHQ+Fbn4zfGfwz4qu4dS8R30Oo287Ld2V5Crxhs8jy2GFX024GMYr0nRf2vtTi04prHgq2ub0L8strfGKNj7qysR+BNfSXjn4e+DPG0ITxP4estQdRtSZk2zIP8AZkXDD868b1P9kjwTPcSyWPiHX7ONjlIi0UoT2yy5I+pzWbhUjszTng90eJ+O/wBpD4leJhJDZ30Hh6yYYMWnp85H+1K+W/LbVX9mz4e6t8QPiRY6pd2L3eh2N0LrUrq4BMUpU7hHuP32ZsZHpkn3+pfAn7O/wz8LxxST6P8A27epybjUyJQT7R8IPyr1extLWxtY7Wytoba3jGEiiQIij0AHApqlJu8mDqpK0UTDgUUUV0GAUUUUAFFFFABRRRQAEA9a+R/2uvgBfXs934/8ARSLcvmXVdOgJXzSOsyAfxf3h+PrX1xQRmplFSRvh68qMrrbr0/r+umh+S9j4o1uym8m7lL+WSrpMuGB9+M1sweLXDPJPJbsNp2qpP4ZzX2/8a/2cfCXj5pdT09Y9G1lskzRLiOQ+rAdD7jI9jXyP49/Zy+Ivhe4kZtK+3Wozi5gyVI9yoIH4gV5tXBUJP3429Nj7fL+Js0pQSw1dzXZv3l8n8Xyv5pbHLr4xYCQPbGQl/kC9h6E1LaeN7J3ZbqJ4NvTHOf8KyYvh54wd2jh0iR2PHy3MR/9mzWjb/B3xzcTKZrPT7KNxlpbzVbaFV+u58/kDUf2bhH/AMOdS4y4hoyT1ut04/8AAucT4jvI9S1u5vII9iStkD14xn8a6n4XfDfxD448RQ6TpGnPd3TAO8ZO2OBP+ek7/wDLNP8Ax49ACa9f+G/7PllNPHNqWqX2vSg/8enhq1dlPs97OqxoPUoCfQ19ReCfhW1roqaRcWtl4b8PZ3PomkyMz3R9bq6Pzyn1AwD6kV3RaUVCnql/W/8ATPk6tGcq08Ri7RlJtu61u3fSG78r2j3Zzvwq8EWlj4bbwJ4Qu3l0zzM+JfEca7PtsmMNbW2OigfLkZCLnksSa9306ztdPsYLGygSC2gjEcUSDCooGAAPTFGn2dpp9lDZ2VtFbW8KBI4okCoijsAOgqetYQ5dXucGLxbrWjHSK76tvu33/BLRBXKfFTVdZ0zwhdHw2R/bcqMLIGEyjeqlzlQCcEKVz2LCurrm/E41OLV7S903w5HqksUMkYmbUvs5iDldyhcEHO0c9sVbdjlp03Ulyr8Wl+L0MjWtc1rxF4D0TXvAt/BbXmoiK5tkuI1eKYGJpPJk4yobbsLLgqTntisef4kTN8NvFnjjTo55ZtLsyx0q5RQ1jdRofNhl2gNlW5bk5UZBwRV3SdP1bSdOstO034dWlraWMxntoY9ewsbndkgbf9puDxyauQv4gik1CSP4daarakwe9/4m0eLg7AmXHl4b5FC89gKn2i/pM6PqVTvH/wADj/mbui2mqQPZtca899FJanzhJHGrPKdhEibQML975eRyv48l8I9b8Qa/p1te6rqWoMY7q8jleW3gW3uVS5nhRV2qGDqI0J6Z54OeLmkrr+lRpHp/w/tIESPyowNdB8tP7iZQ7V6cDA4HpVTSNM1TSUto9P8Ah3bwRWszzwRjxExRJHLFn2lSMku5zjqxNHtF/SYfUqneP/gcf8yLSPFWtQfEH+xvEkl9ZJe6rPHpE8cEcun3tuqOVhEi5aOcBWZg+MlGAyOBbubjxKfihD4aTxNcJbz6Jc6gGFrCQsq3MSIvKZ2BHIIzk9c5p0NvrUWox6hH8ObAXMcsk0bf20pCSSZ3uq7MKzZOWAycnnk1Iw8QN4hj8QN8P7Q6nHbtbJcf26MiJiGKY2YwSAenUA9qPaL+kw+pVO8f/A4/5nPfEnxd4m0bxfr9npmpNFBaaTYXdsJYIzbRSy3EsbmZsbxEQi5wcjkiul+MXibVfDXhr7doiGW6tiL2eMQNJvtIWVp1GAdpZCVBPTNZ+qaVqOq3WoXOofDSxuZtStFs7xn1wHzYVJKoRswACSRjGCSR1q1JHr8nmb/AFs/m2f2J869ndDz8n3fc89fej2i/pMPqVTvH/wADj/mWfFuvXq+IfAg0fUiun61qLxz7ERhND9klmXBYEjJjXkY4J+ob8Vdb1TSl8Mto15NH9t16Kwukt0idpI2SQso3ggMCg54xzWYukaitno9onw4tUg0X/kGqniAr9l+Qp8hC5HykqPQEjpT7nTdVubOxtJ/h3bPDYXRu7UHxCcxzksTJu25LZduST1NHtF/SYfUqneP/AIHH/MveI73xXa/D77Xosst9q8s8EiwT+TFdCF3VpIVyBH5wj3hdwwTjOa0vhrr8PiLRrq7iur+VoL2S3lgv7UQXNo6hcwyKOCwzncMghgcnrWOINd+xyWr/AA9tpIpLgXTeZr29jKMYfcylgw2jBzxgYqxpU/ibSrd4NP8AAFlbxyStK+3WlJkkY5Z2JTLMe5JJo9ov6TD6lU7x/wDA4/5knjnUtWtvG/g3SrHUprO11W5uobsRxxsWEdtJKpBZTg7lH1Ga5PWPHPiNfhT4t1OC6EOq+Htak02O7ihQi5WOeNd+xgVBKybSBxuU4x0HQ6vFr+r31le3/gC3lurEu1rKuv7GhLqVYqVUYJUkZ9CRUF3p2p3Xhw+HZvhpp39klgzWqa0qIxD78nagJJb5iT1PJyaPaL+kw+pVO8f/AAOP+ZpahfavaeCfEeqLqF9FcwWlxNax3cUPm27RK4BIVdrKxQMMg8Hr6bPgW+uL/wAG6HeX9z517d6dDcSsQql2aNWYhQAAMt2HHFcw9trslvfwS+AIZY9QhEF35viEuZIwGGzJUkD5m4BHU0ujw69pEiSaf4At4mjt1to8+IN4SJfuooZSFA9vQelHtF/SYfUqneP/AIHH/M0Pi/q+p6H4Thv9JupLa4/tSwgYxxLIWjluY4nUBgedrnHfOKzotT8aweBtZ+3EW+sXF/cWugyy24aTym/1Ek0ceRuHzMQB91RkA5qXX/8AhIdeskstX+H9pdW6TJOqNrgUCRGDI3CDkMAR6EA9qnubrxTcXlpdzeBbZp7NmaBv7cA2Fl2k42YPBI5z1o9ov6TD6lU7x/8AA4/5mNd/EC/vvht4O1nTQLW78RajZ6bcSPGGNlI7FZvlPG5WR0GeNxGQeldD4sl1nQ/B/ii/g1lpZLTTJLqyZ40MsLpE7fNxhgWUdR6isW10vULbRrrRovhnp39n3c73M1u+tK6tK7b2flDhi/zZGDu5681Zmj1+fS7vTJ/h/ay2t7GY7lX17c0ykbSGYpuIxx16Ue0X9Jh9Sqd4/wDgcf8AMoeIvEPiC18JfD++t9Qujc6vfWkF/wCTDCXnWW2kkYKGXap3KMYxgZqz4s1bxBpeh+FZ4NVu45dU16zt5/Pt4vNW3nJLRMNuAy9NwAPFJcWGrXFppNrN8OrRodIlSWwT+3sCB0UqrDC9QpIGc8EirOuDxBrYtBqnw/tLkWdwl1b51wL5cqfdcYQcjtR7Rf0mH1Kp3j/4HH/MkstW1fXviL4m0CG+k0220S1tPJ8qNGaaSdHfzW3A5QbQoUYyQ+SeMJeazrE/j/Q/B/20W8cuiTald3cCLuuHR4owkZYEKuZC54JxtHAJzHfx69fagNQufh7ZNdiEwGZdbCO0Wc7GKoNy5ydpyOT607UP+EgvzatdfD6yZ7Qk20ia0qPDkbTsZUBUEcEA8ij2i/pMPqVTvH/wOP8AmXvhbr2o65perR6oyzXGlazd6Z9pVAguVhfCyYHAODtbHG5WxjoOurE8GxXFtpC2k2g22hxwsVitre4WVdvUtkKOSSc9yeT1rbqk76nNOLhJxf8An+QUUUUyQooooAKKKKACiiigAowKKKAM+/0PRdQbdfaRp903rNbI5/UVDa+GPDlrIJLXQNJgcdGjs41P5gVrUUuVb2NVXqpcqk7eogVQoUAADoKWiimZBRRRQAUUUUAFFFFABRRRQAUHpRRQB5vp8A8U6p4p1DXLvWHi0jUJLG20yxvJYPKWONHDkRMrSSyb9wLEgKUCgck6vg/xJo8HgzUrx9R1iS00OSeO8m1dNtxF5aiRlY4BbarABuSccknNaes+D9F1PVH1Ui9stQkjWKW5sL2W1kmRc7VcxsN4GTjOSMnBFSL4S8Op4bTw4mmRrpSSLIbcM2HYSCTLnOXJcbm3E7jndnJoA4b4OeL9W1HW7zTPEUt99p1SH+17KO6sZbf7IpO2SzUyKu/ygYTkZyZG7Cr2nR3uj/FR08Q3WrP/AGrcyto93FeObOVPK3fY5Yc7Y5ECO6MB84DHdncp7u/0uxvruxu7qAPPYTGa1kDENG5RkPQ8gqzAg8HPsKyrPwZoFpr41uG2m+0rNJPGjXUjQxSyAiSRIi2xHYM2WAB+Zv7xyAYujaeifGDWx9u1V4oNMs7qKCTUp3gSWaS6WQiMuU5CJxjA2jAFcV4f1PWNR8fy6XZvrlvqSeILq4N5daqfsU+nw3TJLDHAXYMVXCbQilSyPnGM+yRaZZRavcatHDi9uYI7eWTcfmjjLsi46cGR/wA/pVD/AIRTQd1u4sAr2+oSalC6yMGS4kLF3BznDb2BX7pDEYxQBzssMnin4h61pGp31/b6bo9ta+TZ2t09v57TB2M0jRlXZRt2KM7QVckE4xb8B3F3a+JvEnhiTULjUbPTGtpbWa5kMk0QmRmaB3PLldoYFsttlUEnANa+v+F9J1q7hvrhLm3voIzFHd2dzJbzqhIJTfGQSpIztORnnGateH9E0zQbFrPS7byY3kaWRmdnklkb7zu7Es7Hj5mJPA9BQB5V8Wb/AMRW/jDWp9I/tgppmkafd+fa6iUisV8+4M0rW+4C4zHHyuCSFxwSK6n4s+JzZeE7S00e/uIL7X5FtbO6tLd7iS3iZd0tysaAsdkeWHGNxQHrW3r/AIK8Pa7qMt9qdrcSyT26W1wiXk0cVxEjMypJGjBZFBd+GBzuIORWmdI0861DrBtwb2C2a1ik3HEcTMrMqrnAyUTJxn5QOgoA4iz8VXes/BDW9V86a11iw028gumCPDJFcwxN84VgGTdhZFyAcOtUvg9dajqWuXFzAms2GnWdp9k1Cy1bUzdTNe5R1kVS7mNfLLHO7DiRCBxmu+uPDuj3B1fzbMEazEIdQAdgJ1CGPkA8HYduRg4A54GH2eg6VZ6udVtrURXjWqWjyK7DfEhJRWGcMVycEjI3EZwTQBpUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFAH//2Q==" alt="Logo Raices">
      <div>
        <h1 class="text-2xl font-bold titulo-marca">Raices Ancestrales del Pacifico</h1>
        <div class="subrayado-marca"></div>
        <p class="text-sm mt-1" style="color:#9b8b7a">Panel de pedidos y reservas — Gastro Bar</p>
      </div>
    </div>
    <button id="btnRefresh" class="px-4 py-2 rounded-lg text-sm font-semibold btn-refrescar">↻ Actualizar</button>
  </div>

  <!-- RESUMEN HOY / MANANA -->
  <div class="flex gap-3 mb-4 flex-wrap">
    <div class="stat-card stat-llevar">
      <div class="stat-num" id="statLlevarHoy">—</div>
      <div class="stat-label">Para llevar hoy</div>
    </div>
    <div class="stat-card">
      <div class="stat-num" id="statReservasHoy">—</div>
      <div class="stat-label">Reservas hoy</div>
    </div>
    <div class="stat-card stat-manana">
      <div class="stat-num" id="statReservasManana">—</div>
      <div class="stat-label">Reservas manana</div>
    </div>
  </div>

  <!-- FILTRO DE FECHA -->
  <div class="filtro-bar mb-4">
    <span class="filtro-label">📅 Ver fecha:</span>
    <input type="date" id="inputFecha" class="input-fecha">
    <div class="chip active" id="chipHoy" data-fecha="{{ hoy_iso }}">Hoy</div>
    <div class="chip" id="chipManana" data-fecha="{{ manana_iso }}">Manana</div>
    <div class="chip" id="chipTodas" data-fecha="">Ver todas las fechas</div>
  </div>

  <!-- CUPO DE RESERVAS (solo visible en pestana Reservas con fecha activa) -->
  <div class="cupo-bar-wrap mb-4" id="cupoWrap" style="display:none">
    <div class="cupo-item">
      <div class="cupo-titulo"><span>🍽️ Almuerzo (12:00 PM - 3:00 PM)</span><span id="cupoAlmuerzoTxt">—</span></div>
      <div class="cupo-track"><div class="cupo-fill" id="cupoAlmuerzoFill"></div></div>
    </div>
    <div class="cupo-item">
      <div class="cupo-titulo"><span>🌙 Cena (6:00 PM - 10:00 PM)</span><span id="cupoCenaTxt">—</span></div>
      <div class="cupo-track"><div class="cupo-fill" id="cupoCenaFill"></div></div>
    </div>
  </div>

  <!-- TABS -->
  <div class="tabs-wrap">
    <div class="tab active" data-tab="PARA_LLEVAR">🥡 Para llevar <span class="tab-count" id="countLlevar">0</span></div>
    <div class="tab" data-tab="RESERVA">🍽️ Reservas <span class="tab-count" id="countReserva">0</span></div>
  </div>

  <div class="card p-4 mb-4 overflow-x-auto tabla-wrap">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-gray-500 border-b" id="theadRow"></tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <p id="vacio" class="text-center text-gray-400 py-10 hidden"></p>
  </div>
</div>

<script>
var TODOS = [];
var filtroActivo = 'PARA_LLEVAR';
var fechaActiva = '{{ hoy_iso }}'; // YYYY-MM-DD, '' = todas las fechas
var HOY_ISO = '{{ hoy_iso }}';
var MANANA_ISO = '{{ manana_iso }}';

function isoToDDMMYYYY(iso){
  if(!iso) return null;
  var p = iso.split('-');
  return p[2]+'/'+p[1]+'/'+p[0];
}

function selectorEstado(id, estadoActual){
  var estados = ['PENDIENTE','CONFIRMADO','EN_PREPARACION','ENTREGADO','CANCELADO'];
  var html = '<select class="estado-select b-'+estadoActual+'" onchange="cambiarEstado(\''+id+'\', this.value, this)">';
  estados.forEach(function(e){
    html += '<option value="'+e+'"'+(e===estadoActual?' selected':'')+'>'+e.replace('_',' ')+'</option>';
  });
  html += '</select>';
  return html;
}

function filaLlevar(p){
  var detalle = p.productos || '-';
  return '<tr class="border-b">'+
    '<td class="py-3 pr-3 whitespace-nowrap">'+(p.fecha_creacion||'-')+'<br><span class="text-gray-400">'+(p.hora_creacion||'-')+'</span></td>'+
    '<td class="py-3 pr-3 font-semibold">'+(p.nombre||'-')+'</td>'+
    '<td class="py-3 pr-3">'+(p.telefono||'-')+'</td>'+
    '<td class="py-3 pr-3 max-w-xs truncate" title="'+(detalle||'').replace(/"/g,'')+'">'+detalle+'</td>'+
    '<td class="py-3 pr-3 whitespace-nowrap font-semibold">$'+(p.total_platos||'0')+'</td>'+
    '<td class="py-3 pr-3">'+(p.pago||'-')+'</td>'+
    '<td class="py-3 pr-3">'+selectorEstado(p.id, p.estado||'PENDIENTE')+'</td>'+
  '</tr>';
}

function filaReserva(p){
  var detalle = (p.celebracion ? '🎉 '+p.celebracion+' · ' : '') + (p.productos ? p.productos : 'Sin pre-orden');
  return '<tr class="border-b">'+
    '<td class="py-3 pr-3 whitespace-nowrap">'+(p.fecha_reserva||'-')+'<br><span class="text-gray-400">'+(p.hora_reserva||'-')+'</span></td>'+
    '<td class="py-3 pr-3 font-semibold">'+(p.nombre||'-')+'</td>'+
    '<td class="py-3 pr-3">'+(p.telefono||'-')+'</td>'+
    '<td class="py-3 pr-3 text-center">'+(p.personas||'-')+'</td>'+
    '<td class="py-3 pr-3 max-w-xs truncate" title="'+(detalle||'').replace(/"/g,'')+'">'+detalle+'</td>'+
    '<td class="py-3 pr-3 whitespace-nowrap font-semibold">$'+(p.deposito||'0')+'</td>'+
    '<td class="py-3 pr-3">'+(p.pago||'-')+'</td>'+
    '<td class="py-3 pr-3">'+selectorEstado(p.id, p.estado||'PENDIENTE')+'</td>'+
  '</tr>';
}

var COLUMNAS = {
  PARA_LLEVAR: ['Fecha/Hora','Cliente','Telefono','Pedido','Total','Pago','Estado'],
  RESERVA: ['Fecha/Hora','Cliente','Telefono','Personas','Detalle','Deposito','Pago','Estado']
};

function renderHead(){
  var cols = COLUMNAS[filtroActivo];
  document.getElementById('theadRow').innerHTML = cols.map(function(c){return '<th class="py-2 pr-3">'+c+'</th>';}).join('');
}

function fechaDDMMYYYY(){
  return fechaActiva ? isoToDDMMYYYY(fechaActiva) : null;
}

function filtrarPorTipoYFecha(tipo){
  var ddmmyyyy = fechaDDMMYYYY();
  return TODOS.filter(function(p){
    if(p.tipo !== tipo) return false;
    if(!ddmmyyyy) return true;
    var campoFecha = tipo === 'RESERVA' ? p.fecha_reserva : p.fecha_creacion;
    return campoFecha === ddmmyyyy;
  });
}

function render(){
  renderHead();
  var lista = filtrarPorTipoYFecha(filtroActivo);
  var tbody = document.getElementById('tbody');
  var vacio = document.getElementById('vacio');

  document.getElementById('countLlevar').textContent = filtrarPorTipoYFecha('PARA_LLEVAR').length;
  document.getElementById('countReserva').textContent = filtrarPorTipoYFecha('RESERVA').length;

  if(lista.length === 0){
    tbody.innerHTML = '';
    vacio.textContent = filtroActivo === 'RESERVA'
      ? 'No hay reservas registradas para esta fecha.'
      : 'No hay pedidos para llevar registrados para esta fecha.';
    vacio.classList.remove('hidden');
  } else {
    vacio.classList.add('hidden');
    var fn = filtroActivo === 'RESERVA' ? filaReserva : filaLlevar;
    tbody.innerHTML = lista.map(fn).join('');
  }

  var mostrarCupo = (filtroActivo === 'RESERVA' && fechaActiva);
  document.getElementById('cupoWrap').style.display = mostrarCupo ? 'flex' : 'none';
  if(mostrarCupo){
    cargarCupo(fechaActiva);
  }

  actualizarStats();
}

function actualizarStats(){
  document.getElementById('statLlevarHoy').textContent = TODOS.filter(function(p){return p.tipo==='PARA_LLEVAR' && p.fecha_creacion===isoToDDMMYYYY(HOY_ISO);}).length;
  document.getElementById('statReservasHoy').textContent = TODOS.filter(function(p){return p.tipo==='RESERVA' && p.fecha_reserva===isoToDDMMYYYY(HOY_ISO);}).length;
  document.getElementById('statReservasManana').textContent = TODOS.filter(function(p){return p.tipo==='RESERVA' && p.fecha_reserva===isoToDDMMYYYY(MANANA_ISO);}).length;
}

function cupoColor(pct){
  if(pct >= 90) return '#c81e1e';
  if(pct >= 60) return '#fa5302';
  return '#1E7E34';
}

function cargarCupo(fechaIso){
  fetch('/dashboard/api/disponibilidad?fecha='+fechaIso)
    .then(function(r){return r.json();})
    .then(function(d){
      if(!d.ok) return;
      ['almuerzo','cena'].forEach(function(franja){
        var info = d.franjas[franja];
        var pct = Math.min(100, Math.round((info.ocupacion / info.capacidad) * 100));
        var txt = document.getElementById(franja === 'almuerzo' ? 'cupoAlmuerzoTxt' : 'cupoCenaTxt');
        var fill = document.getElementById(franja === 'almuerzo' ? 'cupoAlmuerzoFill' : 'cupoCenaFill');
        txt.textContent = info.ocupacion + ' / ' + info.capacidad + ' personas';
        fill.style.width = pct + '%';
        fill.style.background = cupoColor(pct);
      });
    })
    .catch(function(e){console.error('Error cargando cupo:', e);});
}

function cargar(){
  fetch('/dashboard/api/pedidos')
    .then(function(r){return r.json();})
    .then(function(d){TODOS = d.pedidos || []; render();})
    .catch(function(e){console.error('Error cargando pedidos:', e);});
}

function cambiarEstado(id, nuevoEstado, selectEl){
  selectEl.className = 'estado-select b-' + nuevoEstado;
  fetch('/dashboard/api/pedidos/'+id+'/estado', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({estado: nuevoEstado})
  }).then(function(r){return r.json();})
    .then(function(d){ if(!d.ok){ alert('No se pudo actualizar el estado.'); cargar(); } else { cargar(); } });
}

document.querySelectorAll('.tab').forEach(function(t){
  t.addEventListener('click', function(){
    document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
    t.classList.add('active');
    filtroActivo = t.dataset.tab;
    render();
  });
});

function setFiltroFecha(iso, chipEl){
  fechaActiva = iso;
  document.getElementById('inputFecha').value = iso || '';
  document.querySelectorAll('.chip').forEach(function(c){c.classList.remove('active');});
  if(chipEl) chipEl.classList.add('active');
  render();
}

document.getElementById('chipHoy').addEventListener('click', function(){ setFiltroFecha(HOY_ISO, this); });
document.getElementById('chipManana').addEventListener('click', function(){ setFiltroFecha(MANANA_ISO, this); });
document.getElementById('chipTodas').addEventListener('click', function(){ setFiltroFecha('', this); });
document.getElementById('inputFecha').addEventListener('change', function(){
  document.querySelectorAll('.chip').forEach(function(c){c.classList.remove('active');});
  if(this.value === HOY_ISO) document.getElementById('chipHoy').classList.add('active');
  else if(this.value === MANANA_ISO) document.getElementById('chipManana').classList.add('active');
  fechaActiva = this.value;
  render();
});

document.getElementById('inputFecha').value = HOY_ISO;
document.getElementById('btnRefresh').addEventListener('click', cargar);

cargar();
setInterval(cargar, 15000); // refresco automatico cada 15 segundos
</script>
</body>
</html>"""
