"""
================================================================
AGENTE RAICES - ANCESTRALES DEL PACIFICO GASTRO BAR
Flask + OpenRouter + Google Sheets + WhatsApp + Web UI movil
================================================================
"""
import os, json, requests, tempfile
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
conversaciones = {}

PALABRAS_CARTA = ["menu","carta","que tienen","que hay","que ofrecen","que manejan","ver carta","ver menu","productos","platos","ejecutivo","almuerzo","almuerzo del dia","menu del dia","porciones","medias"]
PALABRAS_NEQUI = ["nequi","transferencia","transferir","consignar","pagar","datos de pago","numero de pago"]

DIAS_SEMANA = {0:"lunes",1:"martes",2:"miercoles",3:"jueves",4:"viernes",5:"sabado",6:"domingo"}

SYSTEM_PROMPT_BASE = """Eres la asistente virtual de Raices Ancestrales del Pacifico Gastro Bar. Eres profesional, formal, cordial y atenta. Representas a un restaurante de alta cocina del Pacifico colombiano. Habla SIEMPRE en espanol, sin usar palabras en ingles.

HOY ES: {fecha_hoy}

SALUDO INICIAL: Al primer mensaje responde SIEMPRE exactamente asi:
"Bienvenido a Raices Ancestrales del Pacifico Gastro Bar. Con quien tengo el gusto de hablar el dia de hoy?"

Una vez el cliente diga su nombre, identifica si es hombre o mujer y dirigete a el o ella por su nombre durante toda la conversacion. Ejemplo: si es hombre "con mucho gusto, senor Carlos" si es mujer "con mucho gusto, senora Maria" o "senorita" segun corresponda.

TONO: Formal y profesional en todo momento. No uses expresiones informales. Usa un lenguaje respetuoso y elegante que refleje la categoria del restaurante.

HORARIO DE ATENCION:
- Domicilios y Para Llevar: Todos los dias de 12:00 PM a 7:00 PM
- DIAS SIN SERVICIO (solo mencionar si el cliente pregunta o si es relevante): 25 de diciembre, 1 de enero, Viernes Santo y 1 de mayo
- Si el cliente escribe fuera de horario: "En este momento nuestro servicio no esta disponible. Le atendemos de lunes a domingo de 12:00 PM a 7:00 PM. Con gusto le esperamos."

MENU COMPLETO:
ENTRADAS:
- Brocheta de langostinos: $40.000
- Patacones con piangua, camarones o mixtura: $40.000

GRATINADOS:
- Filete de corvina gratinada: $65.000
- Apanados en salsa de mariscos gratinados: $75.000
- Chuleta a la calima gratinada: $75.000

CEVICHES:
- Ceviche de camarones: $35.000
- Ceviche de langostinos: $40.000
- Ceviche mixto o triple: $50.000
- Ceviche de corvina: $40.000

PASTA:
- Pasta ancestral: $55.000

PLATOS PACIFICO:
- Arroz marinero o de camaron: $50.000
- Arroz atollado mixto: $45.000
- Arroz atollado triple: $50.000
- Arroz de langostinos: $55.000
- Cazuela de langostino: $55.000
- Cazuela de mariscos: $70.000
- Chuleta a la calima de cerdo, pollo o pescado: $63.000
- Chuleta de pescado: $45.000
- Chuleta de pollo: $32.000
- Carapacho de jaiba: $45.000
- Filete de pargo o corvina a la plancha: $50.000
- Filete de pargo o corvina en salsa de mariscos o de camaron: $60.000
- Pargo frito o tapao: $55.000
- Pargo sudado: $60.000
- Pargo en salsa de mariscos: $70.000

ENCOCADOS:
- Encocado de jaiba: $55.000
- Encocado de muchilla: $85.000
- Encocado de pargo: $65.000
- Encocado de langostino: $60.000
- Encocado de corvina: $63.000

LANGOSTINOS:
- Langostinos al ajillo o sudados: $45.000
- Langostinos apanados: $50.000
- Langostinos apanados en salsa de mariscos: $60.000
- Langostinos en salsa de jaiba gratinada: $55.000
- Langostinos gratinados en salsa de mariscos: $60.000

PICADAS:
- Picada de mariscos para 2 personas: $100.000
- Picada de langostinos: $60.000
- Picada familiar: $200.000

SMOOTHIES:
- Smoothie de borojo: $10.000
- Smoothie de mango, lulo o mora: $10.000
- Smoothie de maracuya: $11.000

LIMONADAS:
- Limonada natural: $8.000
- Limonada de hierbabuena: $10.000
- Limonada de coco: $12.000
- Limonada de mango biche: $12.000
- Cocozetee: $20.000
- Cerezada: $12.000

OTRAS BEBIDAS:
- Gaseosa personal: $5.000
- Botella de agua: $5.000
- Cerveza nacional: $7.000

MENU EJECUTIVO (Almuerzo del dia):
IMPORTANTE: El menu ejecutivo SOLO se ofrece de LUNES A VIERNES. Sabado y domingo NO hay menu ejecutivo. Si el cliente pregunta por el menu ejecutivo, almuerzo del dia o ejecutivo en sabado o domingo, responder: "Lo sentimos, el menu ejecutivo solo lo ofrecemos de lunes a viernes. Hoy contamos unicamente con nuestra carta regular. Con gusto le comparto las opciones disponibles."

Cada menu ejecutivo incluye: sopa del dia + plato principal + arroz + ensalada + patacon.

SOPA DEL DIA segun dia de la semana (usa HOY para saber cual corresponde):
- Lunes: Sopa de res
- Martes: Sopa de raya
- Miercoles: Caldo de pescado
- Jueves: Sopa de camaron
- Viernes: Sopa de queso con huevo

OPCIONES DE PLATO PRINCIPAL DEL EJECUTIVO (todos los dias):
- Filete de pollo, cerdo o chuleta: $20.000
- Sudado de tollo o raya: $22.000
- Sudado de piangua o de huevo: $25.000
- Sudado de jaiba, camaron o mixto: $27.000
- Filete de marlin o triple: $30.000
- Cuadruple: $35.000
- Pelada frita o gualajo frito o sudado: $35.000 - $40.000
- Quintuple: $40.000
- Filete de marlin en salsa de tollo, jaiba, camaron, piangua o raya: $40.000
- Filete de marlin mixto: $45.000
- Filete de marlin en salsa de mariscos: $45.000

MEDIAS PORCIONES (platos de carta en porcion mitad):
- Media cazuela: $45.000
- Media chuleta a la calima (cerdo, pollo o pescado): $45.000
- Medio arroz marinero: $33.000

PORCIONES ADICIONALES:
- Porcion de arroz: $4.000
- Porcion de patacon: $5.000
- Porcion de papas a la francesa: $5.000
- Porcion de papachina: $8.000
- Porcion de toyo: $12.000
- Porcion de piangua: $15.000
- Porcion de jaiba: $18.000
- Porcion de langostino: $30.000

EMPAQUES:
- Empaque: $1.000 por cada plato (aplica para domicilio y para llevar)

SERVICIOS QUE OFRECEMOS:

1. DOMICILIO — ZONAS DE COBERTURA:

IMPORTANTE: Solo realizamos domicilios a los barrios listados a continuacion. Cualquier barrio que NO este en esta lista NO tiene cobertura. En ese caso, informar amablemente que no hay servicio de domicilio a esa zona y ofrecer la opcion de recoger en el restaurante (para llevar).

=== ZONA $6.000 — Cobertura total del barrio ===
- Centro (todo el barrio)
- Pueblo Nuevo (SOLO zona comercial — ver instrucciones especiales abajo)
- Zona portuaria (todo)

=== ZONA $8.000 — SOLO clientes ubicados SOBRE LA AUTOPISTA ===
Los siguientes barrios tienen cobertura UNICAMENTE para clientes que se encuentren sobre la autopista principal. Si el cliente esta en otra parte del barrio, NO hay cobertura.
- Nayita (solo autopista)
- El Firme (solo sobre la autopista)
- Santa Rosa (solo autopista)
- El Jorge (solo sobre la autopista)
- Juan XXII (solo sobre la autopista)
- 14 de Julio (solo autopista)
- Centenario (solo autopista)
- Capricho (solo autopista)

=== BARRIOS SIN COBERTURA ===
Cualquier barrio no listado arriba NO tiene domicilio. Ejemplos: Nayita interior, El Firme interior, La Independencia, comunas 9, 10, 11, 12, y cualquier otro barrio de Buenaventura no mencionado en las zonas anteriores.

INSTRUCCIONES ESPECIALES POR CASO:

CASO A — Cliente dice un barrio de ZONA $8.000 (autopista):
1. Preguntar: "Le confirmo que en [barrio] hacemos domicilio unicamente para clientes ubicados sobre la autopista. ?Se encuentra usted sobre la autopista?"
2. Si dice SI: proceder con domicilio a $8.000
3. Si dice NO: "Entendemos. Lamentablemente en [barrio] solo podemos entregar a quienes esten sobre la autopista. ?Le gustaria venir a recoger su pedido directamente en el restaurante? Lo tendriamos listo en 20 a 30 minutos."
   - Si acepta recoger: pasar a flujo PARA LLEVAR
   - Si no acepta: "Con mucho gusto le esperamos cuando pueda visitarnos. Quedamos a sus ordenes."

CASO B — Cliente dice "Pueblo Nuevo":
1. Preguntar: "En Pueblo Nuevo realizamos domicilios unicamente en la zona comercial. ?Se encuentra usted en la zona comercial?"
2. Si dice SI: proceder con domicilio a $6.000. Indicar que el domiciliario se comunicara con el para coordinar la entrega.
3. Si dice NO: "Entendemos. Lamentablemente en Pueblo Nuevo solo llegamos a la zona comercial. ?Le gustaria venir a recoger su pedido en el restaurante? Lo tendriamos listo en 20 a 30 minutos."
   - Si acepta recoger: pasar a flujo PARA LLEVAR
   - Si no acepta: "Con mucho gusto le esperamos cuando pueda visitarnos. Quedamos a sus ordenes."

CASO C — Cliente dice un barrio SIN COBERTURA (cualquier otro barrio no listado):
Responder directamente: "Lo sentimos mucho, [nombre]. Lamentablemente nuestro servicio de domicilio no cubre esa zona. ?Le gustaria venir a recoger su pedido directamente en el restaurante? Lo tendriamos listo en 20 a 30 minutos."
   - Si acepta recoger: pasar a flujo PARA LLEVAR
   - Si no acepta: "Con mucho gusto le esperamos cuando pueda visitarnos. Quedamos a sus ordenes."

NOTA PARA ZONAS CON COBERTURA: Siempre informar al cliente que el domiciliario se comunicara con el para coordinar la entrega una vez confirmado el pedido.

- Tiempo de entrega: 40 minutos a 1 hora
- Metodos de pago domicilio: Nequi, tarjeta de credito (al recibir), efectivo

2. PARA LLEVAR:
- Tiempo de preparacion: 20 a 30 minutos
- Pago: Por transferencia Nequi o al recoger en el local
- Instruccion al llegar: "Al llegar, acerquese a la barra, que es donde se encuentra la caja"

3. RESERVAS DE MESA:
- Anticipacion minima: 2 horas antes
- Maximo sin administrador: 30 personas (mas de 30 personas requiere hablar con administrador)
- Tolerancia: Guardamos la mesa hasta 30 minutos despues de la hora reservada
- Celebraciones especiales (cumpleanos, aniversarios): Se ofrece un postre especial de cortesia
- Deposito para reserva: $100.000 para confirmar y sostener la reserva
- Se PREFIERE que el cliente pida los platos al momento de reservar (pre-orden)
- El 50% del valor de los platos se paga por adelantado para garantizar la reserva
- El pedido estara listo 20 minutos despues de la hora de la reserva

DATOS DE PAGO NEQUI:
- Numero: 310 432 7103
- Titular: Didi Johana Vente
- Pedir siempre el comprobante antes de confirmar

METODOS DE PAGO EN LOCAL:
- Tarjeta de credito: Si aceptan
- Efectivo: Si aceptan

FLUJO DOMICILIO:
1. Saluda y pide nombre
2. Pregunta que desea ordenar (ofrece la carta si pide verla)
3. Confirma cada producto y cantidad
4. Calcula empaques: $1.000 por cada plato ordenado
5. Pregunta barrio y direccion completa
6. Verifica cobertura segun las zonas definidas arriba
7. Si hay cobertura: determina zona ($6.000 o $8.000) y aplica instrucciones especiales si aplica
8. Presenta resumen con total (productos + empaques + domicilio)
9. Tiempo estimado: 40 min a 1 hora
10. Pregunta metodo de pago
11. Si paga por Nequi: da datos y pide comprobante
12. Confirma el pedido e informa que el domiciliario se comunicara para coordinar

FLUJO PARA LLEVAR:
1. Saluda y pide nombre
2. Toma el pedido
3. Confirma productos
4. Calcula empaques: $1.000 por cada plato ordenado
5. Informa tiempo: 20 a 30 minutos
6. Presenta resumen con total (productos + empaques)
7. Pregunta metodo de pago (Nequi o al recoger)
8. Si paga por Nequi: da datos y pide comprobante
9. Confirma y da instruccion: "Al llegar, acerquese a la barra"

FLUJO RESERVA DE MESA:
1. Saluda y pide nombre
2. Pregunta fecha, hora y numero de personas
3. Si son mas de 30 personas: "Para grupos grandes es necesario hablar directamente con nuestra administradora."
4. Si son 30 o menos: confirma disponibilidad
5. Pregunta si es celebracion especial (cumpleanos, aniversario) - si es asi menciona el postre de cortesia
6. SIEMPRE invitar a hacer pre-orden: "Para garantizar una experiencia perfecta, le recomendamos hacer su pedido ahora. Asi la cocina tendra todo listo a su llegada."
7. Tomar pedido de platos (pre-orden)
8. Calcular el 50% del total de los platos
9. Informar deposito de $100.000 para la mesa + 50% del valor de platos por Nequi
10. Dar datos de Nequi y pedir comprobante
11. Confirmar reserva con todos los datos

Al confirmar cualquier pedido o reserva completamente pon al FINAL:
##PEDIDO_CONFIRMADO##{"tipo":"DOMICILIO/PARA_LLEVAR/RESERVA","nombre":"X","telefono":"X","direccion":"X","fecha_reserva":"X","hora_reserva":"X","personas":"X","productos":"X","total_platos":"X","total_empaques":"X","total_domicilio":"X","deposito":"X","celebracion":"X","pago":"X"}##

CELEBRACIONES ESPECIALES: Si el cliente menciona cumpleanos o aniversario, mencionar con entusiasmo que tienen un postre especial de cortesia para celebrar.

QUEJAS O PROBLEMAS: "Entiendo su situacion. Para ayudarle mejor le comunico con nuestra administradora directamente."

REGLAS:
- No inventes precios ni platos que no esten en el menu
- Calcula totales correctamente: productos + empaques ($1.000 por plato) + domicilio si aplica
- Para reservas siempre pedir pre-orden de platos
- Siempre pedir comprobante de Nequi antes de confirmar
- Habla SIEMPRE en espanol, sin palabras en ingles
- Tono formal y profesional en todo momento
- Si preguntan por la direccion del restaurante: indicar que esta en Buenaventura, Valle del Cauca
- MENU EJECUTIVO: Solo disponible de LUNES A VIERNES. Si hoy es sabado o domingo, NO ofrecer menu ejecutivo bajo ninguna circunstancia. Solo carta regular. De lunes a viernes, informar la sopa del dia correcta segun HOY ({fecha_hoy}).
- DOMICILIO: Solo a los barrios listados en las zonas de cobertura. Cualquier otro barrio: informar que no hay cobertura y ofrecer para llevar."""

PAGE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<title>Raices - Gastro Bar</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{height:100%;height:-webkit-fill-available}
body{font-family:Arial,sans-serif;background:#F5F0E8;display:flex;flex-direction:column;height:100vh;height:-webkit-fill-available;overflow:hidden;position:fixed;width:100%;top:0;left:0}
.hdr{background:#4A1A0A;color:#fff;padding:10px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0}
.av{width:40px;height:40px;background:#8B2500;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;border:2px solid #D4A04A}
.hi h2{font-size:14px;margin:0;color:#F5D78E}
.hi p{font-size:10px;color:#D4A04A;margin:0}
.badge{background:#8B2500;color:#F5D78E;font-size:9px;padding:1px 6px;border-radius:8px;margin-left:5px}
.rbtn{margin-left:auto;background:rgba(255,255,255,.15);color:#F5D78E;border:1px solid #D4A04A;border-radius:12px;padding:5px 12px;font-size:11px;cursor:pointer}
.msgs{flex:1;overflow-y:auto;overflow-x:hidden;padding:14px;display:flex;flex-direction:column;gap:7px;-webkit-overflow-scrolling:touch}
.msg{max-width:82%;padding:8px 11px;border-radius:10px;font-size:14px;line-height:1.5;word-wrap:break-word;white-space:pre-wrap}
.bot{background:#fff;align-self:flex-start;border-top-left-radius:0;box-shadow:0 1px 2px rgba(0,0,0,.1);border-left:3px solid #8B2500}
.usr{background:#D4EDDA;align-self:flex-end;border-top-right-radius:0}
.typ{background:#fff;align-self:flex-start;color:#999;font-style:italic;padding:9px 13px;border-radius:10px}
.iw{align-self:flex-start;max-width:85%}
.iw img{max-width:100%;border-radius:8px;display:block;box-shadow:0 1px 3px rgba(0,0,0,.2)}
.vm{background:#D4EDDA;align-self:flex-end;border-top-right-radius:0;display:flex;align-items:center;gap:7px;padding:8px 13px;border-radius:10px;font-size:13px;color:#555;max-width:82%}
.bar{background:#EDE8DF;padding:8px 10px;display:flex;gap:7px;align-items:center;flex-shrink:0;border-top:2px solid #D4A04A;padding-bottom:max(8px,env(safe-area-inset-bottom,8px))}
#inp{flex:1;padding:10px 14px;border-radius:22px;border:1px solid #D4A04A;outline:none;font-size:16px;background:#fff;min-width:0;-webkit-appearance:none}
.btn{background:#4A1A0A;color:#F5D78E;border:none;border-radius:50%;width:42px;height:42px;min-width:42px;cursor:pointer;font-size:17px;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.btn:active{background:#8B2500}
.btn:disabled{background:#aaa}
#mic.rec{background:#e53935;animation:pu 1s infinite}
@keyframes pu{0%,100%{transform:scale(1)}50%{transform:scale(1.1)}}
</style>
</head>
<body>
<div class="hdr">
  <div class="av">🌊</div>
  <div class="hi">
    <h2>Raices Gastro Bar <span class="badge">PRUEBAS</span></h2>
    <p>Ancestrales del Pacifico - Buenaventura</p>
  </div>
  <button class="rbtn" id="rst">&#128260; Nueva</button>
</div>
<div class="msgs" id="msgs"></div>
<div class="bar">
  <input type="text" id="inp" placeholder="Escribe tu pedido o reserva..." autocomplete="off" autocorrect="off" autocapitalize="sentences">
  <button class="btn" id="mic">&#127908;</button>
  <button class="btn" id="snd">&#10148;</button>
</div>
<script>
var sid='r_'+Math.random().toString(36).substr(2,8);
var mr=null,ac=[],rec=false;

function sb(){var m=document.getElementById('msgs');setTimeout(function(){m.scrollTop=m.scrollHeight;},50);}
function aM(t,x){var m=document.getElementById('msgs'),d=document.createElement('div');d.className='msg '+t;d.textContent=x;m.appendChild(d);sb();return d;}
function aI(u){var m=document.getElementById('msgs'),w=document.createElement('div');w.className='iw';var i=document.createElement('img');i.onload=sb;i.onerror=function(){w.remove();};i.src=u;w.appendChild(i);m.appendChild(w);sb();}

function proc(d){
  if(d.response)aM('bot',d.response);
  if(d.enviar_carta){setTimeout(function(){aI('CARTA_URL_1');},200);setTimeout(function(){aI('CARTA_URL_2');},500);}
  if(d.enviar_nequi){setTimeout(function(){aM('bot','Datos Nequi para pago:\nNumero: 310 432 7103\nTitular: Didi Johana Vente\n\nPor favor envia el comprobante para confirmar su pedido.');},200);}
}

function send(txt,voz){
  var btn=document.getElementById('snd');btn.disabled=true;
  if(voz){var v=document.createElement('div');v.className='vm';v.innerHTML='&#127908; '+txt;document.getElementById('msgs').appendChild(v);sb();}
  else{aM('usr',txt);}
  var t=aM('typ','Escribiendo...');
  fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:txt,session_id:sid})})
  .then(function(r){return r.json();})
  .then(function(d){t.remove();proc(d);btn.disabled=false;document.getElementById('inp').focus();})
  .catch(function(){t.remove();aM('bot','Error. Intenta de nuevo.');btn.disabled=false;});
}

function go(){var i=document.getElementById('inp'),v=i.value.trim();if(!v)return;i.value='';send(v,false);}

function startRec(){
  if(!navigator.mediaDevices){alert('Usa Chrome para notas de voz');return;}
  navigator.mediaDevices.getUserMedia({audio:true}).then(function(s){
    ac=[];mr=new MediaRecorder(s);
    mr.ondataavailable=function(e){ac.push(e.data);};
    mr.onstop=function(){var b=new Blob(ac,{type:'audio/webm'});s.getTracks().forEach(function(t){t.stop();});sendAudio(b);};
    mr.start();rec=true;document.getElementById('mic').classList.add('rec');
  }).catch(function(){alert('Permite el acceso al microfono');});
}
function stopRec(){if(mr&&rec){mr.stop();rec=false;document.getElementById('mic').classList.remove('rec');}}

function sendAudio(blob){
  var t=aM('typ','Escuchando...');
  var fd=new FormData();fd.append('audio',blob,'voz.webm');fd.append('session_id',sid);
  fetch('/audio',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){t.remove();if(d.transcripcion){var v=document.createElement('div');v.className='vm';v.innerHTML='&#127908; '+d.transcripcion;document.getElementById('msgs').appendChild(v);sb();}proc(d);})
  .catch(function(){t.remove();aM('bot','No pude procesar el audio.');});
}

document.getElementById('snd').onclick=go;
document.getElementById('mic').onclick=function(){if(!rec)startRec();else stopRec();};
document.getElementById('rst').onclick=function(){
  fetch('/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid})});
  document.getElementById('msgs').innerHTML='';
  aM('bot','Bienvenido a Raices Ancestrales del Pacifico Gastro Bar. Con quien tengo el gusto de hablar el dia de hoy?');
};
document.getElementById('inp').addEventListener('keypress',function(e){if(e.key==='Enter')go();});

if(window.visualViewport){
  window.visualViewport.addEventListener('resize',function(){
    var bar=document.querySelector('.bar');
    var offset=window.innerHeight-window.visualViewport.height;
    bar.style.marginBottom=offset>0?offset+'px':'0';sb();
  });
}

aM('bot','Bienvenido a Raices Ancestrales del Pacifico Gastro Bar. Con quien tengo el gusto de hablar el dia de hoy?');
</script>
</body>
</html>"""


def get_system_prompt():
    now = datetime.now()
    dia_num = now.weekday()
    dia_nombre = DIAS_SEMANA[dia_num]
    fecha_hoy = f"{dia_nombre} {now.strftime('%d/%m/%Y')}"
    return SYSTEM_PROMPT_BASE.replace("{fecha_hoy}", fecha_hoy)

def call_claude(session_id, mensaje):
    if session_id not in conversaciones:
        conversaciones[session_id] = []
    conversaciones[session_id].append({"role":"user","content":mensaje})
    h = conversaciones[session_id][-20:]
    hdrs = {
        "Authorization":"Bearer "+os.environ.get("OPENROUTER_API_KEY",""),
        "Content-Type":"application/json",
        "HTTP-Referer":"https://raices-bot.com",
        "X-Title":"Raices Gastro Bar Bot"
    }
    body = {
        "model":"anthropic/claude-sonnet-4-5",
        "max_tokens":1200,
        "messages":[{"role":"system","content":get_system_prompt()}]+h
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",headers=hdrs,json=body)
    txt = r.json()["choices"][0]["message"]["content"]
    clean = txt
    if "##PEDIDO_CONFIRMADO##" in clean:
        clean = clean[:clean.index("##PEDIDO_CONFIRMADO##")].strip()
    conversaciones[session_id].append({"role":"assistant","content":clean})
    pedido = extraer_pedido(txt)
    if pedido:
        pedido["telefono"] = session_id
        sheets(pedido)
    return txt

def build_resp(msg, txt):
    m = msg.lower()
    carta  = any(p in m for p in PALABRAS_CARTA)
    nequi  = any(p in m for p in PALABRAS_NEQUI) or "nequi" in txt.lower()
    clean  = txt
    if "##PEDIDO_CONFIRMADO##" in clean:
        clean = clean[:clean.index("##PEDIDO_CONFIRMADO##")].strip()
    return {"response":clean, "enviar_carta":carta, "enviar_nequi":nequi}

def extraer_pedido(txt):
    if "##PEDIDO_CONFIRMADO##" in txt:
        try:
            i = txt.index("##PEDIDO_CONFIRMADO##")+len("##PEDIDO_CONFIRMADO##")
            j = txt.index("##",i)
            return json.loads(txt[i:j])
        except: pass
    return None

def gclient():
    j = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not j: return None
    try:
        sc = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        c = Credentials.from_service_account_info(json.loads(j),scopes=sc)
        return gspread.authorize(c)
    except: return None

def sheets(d):
    try:
        gc = gclient()
        if not gc: return
        ws = gc.open_by_key(os.environ.get("GOOGLE_SHEET_ID_RAICES","")).sheet1
        if ws.row_count==0 or ws.cell(1,1).value!="Fecha":
            ws.append_row(["Fecha","Hora","Tipo","Nombre","Telefono","Direccion","Fecha Reserva","Hora Reserva","Personas","Productos","Total Platos","Empaques","Domicilio","Deposito","Celebracion","Pago","Estado"])
        n=datetime.now()
        ws.append_row([
            n.strftime("%d/%m/%Y"),n.strftime("%H:%M"),
            d.get("tipo",""),d.get("nombre",""),d.get("telefono",""),
            d.get("direccion",""),d.get("fecha_reserva",""),d.get("hora_reserva",""),
            d.get("personas",""),d.get("productos",""),d.get("total_platos",""),
            d.get("total_empaques",""),d.get("total_domicilio",""),d.get("deposito",""),
            d.get("celebracion",""),d.get("pago",""),"PENDIENTE"
        ])
        print("Raices pedido:", d.get("nombre"))
    except Exception as e: print("Sheets Raices:",e)

def wa_txt(num,msg):
    t=os.environ.get("WHATSAPP_TOKEN"); p=os.environ.get("PHONE_NUMBER_ID")
    requests.post(f"https://graph.facebook.com/v18.0/{p}/messages",
        headers={"Authorization":f"Bearer {t}","Content-Type":"application/json"},
        json={"messaging_product":"whatsapp","to":num,"type":"text","text":{"body":msg}})

def wa_img(num,url,cap=""):
    t=os.environ.get("WHATSAPP_TOKEN"); p=os.environ.get("PHONE_NUMBER_ID")
    requests.post(f"https://graph.facebook.com/v18.0/{p}/messages",
        headers={"Authorization":f"Bearer {t}","Content-Type":"application/json"},
        json={"messaging_product":"whatsapp","to":num,"type":"image","image":{"link":url,"caption":cap}})

def wa_send(num, msg_usuario, txt):
    m = msg_usuario.lower()
    nequi = any(p in m for p in PALABRAS_NEQUI) or "nequi" in txt.lower()
    clean = txt
    if "##PEDIDO_CONFIRMADO##" in clean:
        clean = clean[:clean.index("##PEDIDO_CONFIRMADO##")].strip()
    if clean: wa_txt(num, clean)
    if nequi:
        wa_txt(num, "Datos Nequi:\nNumero: 310 432 7103\nTitular: Didi Johana Vente\n\nEnvienos el comprobante para confirmar.")

def whisper(data, ext="webm"):
    try:
        from openai import OpenAI
        oc=OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        with tempfile.NamedTemporaryFile(suffix="."+ext,delete=False) as f:
            f.write(data); tp=f.name
        with open(tp,"rb") as af:
            tr=oc.audio.transcriptions.create(model="whisper-1",file=af,language="es")
        os.unlink(tp); return tr.text
    except Exception as e: print("Whisper:",e); return None

def whisper_wa(aid):
    try:
        t=os.environ.get("WHATSAPP_TOKEN")
        h={"Authorization":f"Bearer {t}"}
        u=requests.get(f"https://graph.facebook.com/v18.0/{aid}",headers=h).json().get("url")
        return whisper(requests.get(u,headers=h).content,"ogg")
    except: return None


@app.route("/")
def index(): return render_template_string(PAGE)

@app.route("/chat", methods=["POST"])
def chat():
    d=request.get_json(); msg=d.get("message",""); sid=d.get("session_id","web")
    return jsonify(build_resp(msg, call_claude(sid,msg)))

@app.route("/audio", methods=["POST"])
def audio():
    sid=request.form.get("session_id","web")
    af=request.files.get("audio")
    if not af: return jsonify({"error":"no audio"}),400
    tr=whisper(af.read(),"webm")
    if not tr: return jsonify({"response":"No pude entender. Escribe su mensaje.","enviar_carta":False,"enviar_nequi":False})
    r=build_resp(tr, call_claude(sid,tr)); r["transcripcion"]=tr; return jsonify(r)

@app.route("/reset", methods=["POST"])
def reset():
    d=request.get_json(); sid=d.get("session_id","web")
    conversaciones.pop(sid,None); return jsonify({"ok":True})

@app.route("/webhook", methods=["GET"])
def wh_verify():
    if request.args.get("hub.mode")=="subscribe" and request.args.get("hub.verify_token")==os.environ.get("VERIFY_TOKEN"):
        return request.args.get("hub.challenge"),200
    return "error",403

@app.route("/webhook", methods=["POST"])
def wh_recv():
    try:
        d=request.get_json()
        msgs=d.get("entry",[{}])[0].get("changes",[{}])[0].get("value",{}).get("messages",[])
        if not msgs: return jsonify({"ok":True}),200
        msg=msgs[0]; num=msg.get("from"); tipo=msg.get("type")
        if tipo=="text": txt=msg["text"]["body"]
        elif tipo=="audio":
            txt=whisper_wa(msg["audio"]["id"])
            if not txt: wa_txt(num,"No pude escuchar. Por favor escriba su mensaje."); return jsonify({"ok":True}),200
        elif tipo=="image": txt="[Cliente envio imagen, probablemente comprobante de pago]"
        else: wa_txt(num,"Solo entiendo texto, notas de voz e imagenes."); return jsonify({"ok":True}),200
        wa_send(num, txt, call_claude(num,txt))
        return jsonify({"ok":True}),200
    except Exception as e: print("WH error:",e); return jsonify({"error":str(e)}),500

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
