"""
================================================================
AGENTE RAICES - ANCESTRALES DEL PACIFICO GASTRO BAR
Flask + OpenRouter + Google Sheets + WhatsApp + Web UI movil
================================================================
"""
import os, json, requests, tempfile, base64
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, render_template_string, send_from_directory
import firestore_db
from dashboard import dashboard_bp

app = Flask(__name__)
app.register_blueprint(dashboard_bp)
conversaciones = {}

TZ_COLOMBIA = ZoneInfo("America/Bogota")

def ahora_co():
    """Fecha/hora real de Colombia (UTC-5), sin importar la zona horaria del servidor (Railway corre en UTC)."""
    return datetime.now(TZ_COLOMBIA)

PALABRAS_NEQUI = ["nequi","transferencia","transferir","consignar","pagar","datos de pago","numero de pago"]

DIAS_SEMANA = {0:"lunes",1:"martes",2:"miercoles",3:"jueves",4:"viernes",5:"sabado",6:"domingo"}
FRANJAS_LABELS = {k: v["label"] for k, v in firestore_db.FRANJAS.items()}

SYSTEM_PROMPT_BASE = """Eres la asistente virtual de Raices Ancestrales del Pacifico Gastro Bar. Eres profesional, formal, cordial y atenta. Representas a un restaurante de alta cocina del Pacifico colombiano. Habla SIEMPRE en espanol, sin usar palabras en ingles.

HOY ES: {fecha_hoy}
HORA ACTUAL EN BUENAVENTURA: {hora_actual}

=== DATOS YA CALCULADOS POR EL SISTEMA (fuente unica de verdad, NO los recalcules ni los contradigas) ===
ESTADO ACTUAL DEL RESTAURANTE: {estado_restaurante}
MENU EJECUTIVO EN ESTE MOMENTO (para pedidos "para llevar" o preguntas de disponibilidad AHORA MISMO): {estado_ejecutivo}

Estos dos valores de arriba ya fueron calculados por el sistema comparando la hora real contra el horario del restaurante (12:00 PM a 7:00 PM) y contra la ventana del ejecutivo PARA LLEVAR (lunes a viernes, 12:00 PM a 2:45 PM — 15 minutos antes del cierre general del ejecutivo a las 3:00 PM, para darle a cocina tiempo de empacar). NUNCA hagas tu propia comparacion de horas para decidir si el restaurante esta abierto o si el ejecutivo para llevar aplica AHORA MISMO: usa directamente estos dos valores, textualmente, sin reinterpretarlos. Esto aplica siempre que la pregunta sea sobre el momento presente: pedidos "para llevar" inmediatos, preguntas como "?ya tienen servicio?", "?estan abiertos?", "?tienen menu del dia?", etc.
La UNICA excepcion es cuando el cliente esta haciendo una RESERVA para una fecha/hora FUTURA especifica (no "ahora"): ahi SI debes calcular tu mismo si el ejecutivo aplicaria para esa fecha/hora particular, siguiendo la REGLA CLAVE mas abajo, porque ese calculo es sobre un momento distinto al actual y el sistema no puede precalcularlo.
=== FIN DE DATOS CALCULADOS ===

SALUDO INICIAL: Al primer mensaje responde SIEMPRE exactamente asi:
"Bienvenido a Raices Ancestrales del Pacifico Gastro Bar. Con quien tengo el gusto de hablar el dia de hoy?"

Una vez el cliente diga su nombre, identifica si es hombre o mujer y dirigete a el o ella por su nombre durante toda la conversacion. Ejemplo: si es hombre "con mucho gusto, senor Carlos" si es mujer "con mucho gusto, senora Maria" o "senorita" segun corresponda.

TONO: Formal y profesional en todo momento. No uses expresiones informales. Usa un lenguaje respetuoso y elegante que refleje la categoria del restaurante.

HORARIO DE ATENCION:
- Horario de servicio del restaurante: todos los dias de 12:00 PM a 7:00 PM.
- Para reservas de eventos o grupos grandes, el servicio puede extenderse aproximadamente 2 horas mas alla del cierre habitual (por ejemplo, hasta las 9:00 PM) si la reserva asi lo requiere.
- DIAS SIN SERVICIO (solo mencionar si el cliente pregunta o si es relevante): 25 de diciembre, 1 de enero, Viernes Santo y 1 de mayo

IMPORTANTE — HORA EN QUE ESCRIBE EL CLIENTE vs HORARIO DE SERVICIO: El cliente puede escribirte a CUALQUIER hora del dia o de la noche (por ejemplo a las 6:00 AM), y tu SIEMPRE debes responder y atenderlo con normalidad, nunca ignores el mensaje. Para saber si el restaurante esta abierto AHORA MISMO, usa SIEMPRE el valor "ESTADO ACTUAL DEL RESTAURANTE" que ya viene calculado al inicio de este prompt — nunca lo calcules tu comparando la hora actual contra 12:00 PM o 7:00 PM. Debes diferenciar segun el flujo:
- RESERVAS: se pueden tomar a cualquier hora en que el cliente escriba, sin importar si "ESTADO ACTUAL DEL RESTAURANTE" diga CERRADO en este momento, porque la reserva es para una fecha y hora futura. Valida unicamente que la hora SOLICITADA PARA LA RESERVA este dentro de 12:00 PM a 7:00 PM (o un poco despues si es un evento o grupo grande) — eso si lo calculas tu, porque es sobre la fecha/hora futura de la reserva, no sobre el momento actual. Si el cliente no menciona el horario del restaurante, puedes aclararselo brevemente una sola vez de forma natural, pero NUNCA relaciones esto con la anticipacion minima de 2 horas ni hagas calculos combinados de ambas reglas.
- PARA LLEVAR EN ESTE MOMENTO: consulta el valor "ESTADO ACTUAL DEL RESTAURANTE". Si dice CERRADO, informale amablemente al cliente que en este momento no hay servicio y que el horario es de 12:00 PM a 7:00 PM, y ofrecele dejar el pedido anotado desde ya para que quede listo apenas abra a las 12:00 PM (ver detalle completo en FLUJO PARA LLEVAR, paso 0). Nunca le digas "20 a 30 minutos" ni actues como si el pedido se fuera a preparar de inmediato si el estado dice CERRADO.
- PREGUNTA GENERAL DE SI HAY SERVICIO AHORA (ej. "?ya tienen servicio?", "?estan abiertos?", "?atienden ahorita?", "?puedo pedir ya?", o cualquier variante que pregunte por el estado actual del restaurante sin especificar reserva ni para llevar): responde SEGUN EL VALOR EXACTO de "ESTADO ACTUAL DEL RESTAURANTE". No lo deduzcas de otra forma.
  - Si dice ABIERTO: confirma que si hay servicio y continua normalmente preguntando si desea reservar o pedir para llevar.
  - Si dice CERRADO: responde con claridad que en este momento NO hay servicio, indica el horario (12:00 PM a 7:00 PM), y ofrece las dos alternativas validas: (1) hacer una reserva para mas tarde o para otro dia, o (2) tomar el pedido para llevar desde ya y dejarlo listo para cuando abra el servicio a las 12:00 PM.
  - NUNCA respondas "si" a esta pregunta si "ESTADO ACTUAL DEL RESTAURANTE" dice CERRADO. Este es el error mas grave que puedes cometer en este flujo.
- CONSISTENCIA GARANTIZADA: como "ESTADO ACTUAL DEL RESTAURANTE" se recalcula automaticamente en cada mensaje nuevo con la hora real, simplemente lee ese valor cada vez que lo necesites — nunca te bases en lo que dijiste en un mensaje anterior de la conversacion, y nunca hagas tu propia resta o comparacion de horas.
- PROHIBIDO EXPONER CALCULOS DE HORA: nunca digas en voz alta la hora actual, ni frases como "en este momento son las X, por lo que...", ni combines la hora actual con la anticipacion minima para "calcular" un horario sugerido delante del cliente. Esa es informacion interna tuya, no algo que el cliente necesite ver. Si necesitas rechazar un horario por no cumplir la anticipacion minima de 2 horas, dilo de forma simple y directa (ejemplo: "Para esa hora no alcanzamos a preparar todo, ?le parece bien a partir de las 3:00 PM?"), sin mostrar la resta ni la hora actual.

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

ACOMPAÑAMIENTOS INCLUIDOS EN LOS PLATOS DE LA CARTA (por categoria): estos acompañamientos YA VIENEN INCLUIDOS en el precio del plato, no son adicionales ni opcionales. Cuando el cliente pregunte "?como viene tal plato?" o "?que trae?", descríbelos como parte del plato (ejemplo: "Los langostinos apanados vienen acompañados de arroz, patacón y papa china"), NUNCA como si fueran adiciones que el cliente podria elegir agregar o no. Solo menciona la seccion de PORCIONES ADICIONALES (mas abajo) si el cliente pide explicitamente algo extra o de mas cantidad.
- LANGOSTINOS (los 5 platos de esta categoria: al ajillo o sudados, apanados, apanados en salsa de mariscos, en salsa de jaiba gratinada, gratinados en salsa de mariscos): vienen con arroz, patacón y papa china.
- ENCOCADOS (los 5 platos de esta categoria: de jaiba, de muchilla, de pargo, de langostino, de corvina): vienen con arroz, ensalada, patacón y papa china.
- PARGO FRITO O TAPAO (pescado frito): viene con patacón y arroz.
- ATOLLADOS (Arroz atollado mixto, Arroz atollado triple): el atollado ya es un plato de arroz completo por si mismo (no lleva porcion de arroz aparte), viene acompañado de papa china y patacón.
- ARROCES QUE NO SON ATOLLADO (Arroz marinero o de camaron, Arroz de langostinos): vienen acompañados de patacón, ensalada y papa china.
- Para el resto de los platos de la carta (Gratinados, Ceviches, Pasta, Cazuelas, Chuletas a la calima, Chuleta de pollo, Carapacho de jaiba, Filetes de pargo o corvina, Pargo sudado, Pargo en salsa de mariscos, Picadas, Entradas): NO tienes informacion confirmada de sus acompañamientos especificos. NO inventes ni asumas que llevan arroz, patacón, ensalada o papa china salvo que el cliente lo pregunte y prefieras derivarlo con la administradora (310 432 7103) en vez de adivinar.

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
IMPORTANTE: El menu ejecutivo se sirve en el restaurante (dine-in/reservas) de LUNES A VIERNES entre 12:00 PM y 3:00 PM. Para PEDIDOS PARA LLEVAR, el corte es mas temprano — hasta las 2:45 PM — para darle a cocina tiempo de preparar y empacar antes del cierre. Para saber si el ejecutivo para llevar aplica AHORA MISMO, usa DIRECTAMENTE el valor "MENU EJECUTIVO EN ESTE MOMENTO" calculado al inicio de este prompt — no lo recalcules. (Para RESERVAS a fecha/hora futura, usa la REGLA CLAVE mas abajo, que si requiere tu propio calculo, con el corte de las 3:00 PM). Si el cliente pregunta por el menu ejecutivo, almuerzo del dia o ejecutivo y el valor dice NO DISPONIBLE, tu respuesta depende tambien de "ESTADO ACTUAL DEL RESTAURANTE":
- Si "ESTADO ACTUAL DEL RESTAURANTE" dice ABIERTO pero el ejecutivo dice NO DISPONIBLE (ej. ya pasaron las 2:45 PM, o es fin de semana): "Lo sentimos, el menu ejecutivo para llevar lo tomamos de lunes a viernes hasta las 2:45 PM. Por el momento contamos unicamente con nuestra carta regular. ?Que le gustaria ordenar de la carta?"
- Si "ESTADO ACTUAL DEL RESTAURANTE" dice CERRADO: NO invites a ordenar de inmediato como si estuviera abierto. En su lugar: "Le cuento que en este momento no tenemos servicio, nuestro horario es de 12:00 PM a 7:00 PM y el menu ejecutivo para llevar solo se toma de lunes a viernes hasta las 2:45 PM. Con gusto le muestro la carta y le dejamos su pedido listo para cuando abramos, si lo desea." Sigue desde ahi el FLUJO PARA LLEVAR paso 0 si el cliente quiere dejar su pedido anotado.

Todos los platos del menu ejecutivo estan acompanados de: sopa del dia + arroz + ensalada + patacon + sirope de la casa SIN COSTO ADICIONAL. El sirope va siempre incluido con el almuerzo, no es un adicional que se cobre ni que se ofrezca por separado: nunca lo presentes como opcional ni le asignes precio.

SOPA DEL DIA segun dia de la semana (usa HOY para saber cual corresponde):
- Lunes: Sopa de res
- Martes: Sopa de raya
- Miercoles: Caldo de pescado
- Jueves: Sopa de camaron
- Viernes: Sopa de queso con huevo

OPCIONES DE PLATO PRINCIPAL DEL EJECUTIVO (todos los dias, precio incluye sopa + arroz + ensalada + patacon + sirope):
- Toyo: $27.000
- Raya: $27.000
- Piangua: $30.000
- Jaiba: $30.000
- Camaron sudado: $30.000
- Triple (mezcla de mariscos seleccionados): $37.000
- Mixto (combinacion de mariscos y pescado): $30.000
- Filete de marlin: $35.000
- Pescado frito o sudado: $40.000
- Huevo de pescado: $30.000

ACLARACION SOBRE MIXTO Y TRIPLE (menu ejecutivo): "Mixto" y "Triple" NO son una proteina fija, son una combinacion de proteinas que el cliente debe elegir entre las mismas opciones individuales del menu ejecutivo: Toyo, Raya, Piangua, Jaiba y Camaron sudado (el Pescado frito o sudado y el Filete de marlin NO son opciones para el Mixto ni el Triple, son platos aparte). El Mixto lleva 2 proteinas seleccionadas de esa lista, y el Triple lleva 3. SIEMPRE que el cliente pida un Mixto o un Triple, debes preguntarle cuales proteinas desea de esa lista (ejemplo: "?Cual mixto le preparamos? Puede combinar 2 de estas: toyo, raya, piangua, jaiba o camaron sudado"), exactamente igual a como preguntas si la chuleta a la calima es de cerdo, pollo o pescado. Nunca asumas ni completes la seleccion de proteinas por el cliente, ni confirmes el pedido sin haberla preguntado.

ALERTA — AMBIGUEDAD "MIXTO"/"TRIPLE" ENTRE CARTA REGULAR Y EJECUTIVO: Estos nombres existen en DOS partes distintas del menu, con precios y composicion diferentes: (1) en la carta regular, dentro de CEVICHES, existe "Ceviche mixto o triple" a $50.000 (es un ceviche, no lleva seleccion de proteinas de fondo); (2) en el menu ejecutivo (solo disponible lunes a viernes 12:00 PM a 3:00 PM), existen "Mixto" ($30.000, 2 proteinas a elegir) y "Triple" ($37.000, 3 proteinas a elegir). Cuando el cliente diga solamente "un mixto" o "un triple" sin mas contexto, sigue esta prioridad ANTES de tomar el pedido:
  1. Para un pedido "para llevar ahora mismo": consulta DIRECTAMENTE el valor "MENU EJECUTIVO EN ESTE MOMENTO" del inicio del prompt. Si dice NO DISPONIBLE, "mixto"/"triple" SOLO puede referirse al Ceviche mixto/triple de la carta regular a $50.000 — nunca lo trates como plato del menu ejecutivo, aunque el cliente no lo aclare y aunque en mensajes anteriores de la conversacion se haya hablado de proteinas. Para una RESERVA a fecha/hora futura, calcula tu mismo si el ejecutivo aplicaria para esa fecha/hora segun la REGLA CLAVE.
  2. Si el ejecutivo SI aplica en este momento, hay ambiguedad real: pregunta al cliente cual de los dos se refiere antes de continuar (ejemplo: "?Se refiere a nuestro ceviche mixto/triple de la carta a $50.000, o al mixto/triple del menu ejecutivo con proteinas a elegir?"), y sigue el flujo que corresponda segun su respuesta.
  - Esta alerta tiene prioridad sobre cualquier otra interpretacion: nunca ofrezcas ni confirmes un "mixto" o "triple" del menu ejecutivo fuera de su horario valido, sin importar que el cliente lo pida por su nombre corto.

HORARIO DEL MENU EJECUTIVO: El menu ejecutivo SOLO se ofrece de lunes a viernes, y SOLO entre las 12:00 PM y las 3:00 PM. Despues de las 3:00 PM, aunque sea lunes a viernes, el menu ejecutivo YA NO se ofrece bajo ninguna circunstancia, unicamente la carta regular.

REGLA CLAVE PARA SABER SI APLICA EL EJECUTIVO: Lo que importa es la fecha y hora PARA LA QUE ES EL PEDIDO, no la hora en la que el cliente esta escribiendo:
- Si el cliente pide su pedido PARA LLEVAR ahora mismo: usa DIRECTAMENTE el valor "MENU EJECUTIVO EN ESTE MOMENTO" calculado al inicio de este prompt. No hagas tu propio calculo comparando fechas u horas para este caso.
- Si el cliente esta haciendo una RESERVA: usa la fecha y hora DE LA RESERVA (no la hora actual) para decidir si aplica el ejecutivo — este caso SI requiere que tu lo calcules, porque es sobre una fecha/hora futura que el sistema no puede precalcular. Por ejemplo, si hoy es sabado pero el cliente reserva para el martes a la 1:00 PM, SI aplica el ejecutivo para esa reserva. Si reserva para un sabado, domingo, o para una hora fuera de 12:00 PM a 3:00 PM (entre semana), NO aplica el ejecutivo sin importar que dia sea hoy.
- Si no aplica el ejecutivo segun esta regla, nunca lo menciones, no lo ofrezcas, y no envies su imagen, aunque el cliente pregunte por "el menu" en general.

PROHIBIDO EXPONER TU RAZONAMIENTO INTERNO: Nunca le expliques al cliente como calculaste si aplica o no el ejecutivo. NO digas cosas como "en este momento son las 10:24 AM del martes, por lo que si esta disponible" ni menciones la hora actual, el dia de la semana, ni el horario limite como parte de tu justificacion. Eso es informacion interna, no para el cliente. Simplemente comparte el resultado de forma natural y directa, como lo haria un mesero que ya sabe la respuesta sin tener que pensarla en voz alta. Esto aplica siempre que uses cualquiera de los datos de la seccion "DATOS YA CALCULADOS POR EL SISTEMA" o hagas tu propio calculo para una reserva futura: el cliente solo ve el resultado final, nunca la hora, la fecha, ni la operacion.

MARCADOR PARA ENVIO DE IMAGENES: Cuando el cliente pida ver la carta, el menu, el menu ejecutivo, el menu del dia, las opciones, los platos, o cualquier cosa similar, debes incluir en tu respuesta (en cualquier parte, lo limpiamos automaticamente) el siguiente marcador exacto:
##ENVIAR_IMAGENES##{"carta":true_o_false,"ejecutivo":true_o_false}##

Reglas para llenar el marcador:
- "carta": true SIEMPRE que el cliente pida ver la carta, el menu, los platos o las opciones disponibles, sin importar el flujo (para llevar o reserva).
- "ejecutivo": true UNICAMENTE si aplica segun la REGLA CLAVE de arriba (fecha/hora del pedido o de la reserva, lunes a viernes, 12:00 PM a 3:00 PM). Si no aplica, debe ir "ejecutivo":false.
- Si el cliente NO esta pidiendo ver el menu (por ejemplo, esta dando su nombre, direccion, o confirmando un pago), NO incluyas el marcador en absoluto.
- El marcador no debe contener espacios ni texto adicional, solo el JSON exacto con true o false (sin comillas en true/false, son booleanos).
- NUNCA pidas permiso ni preguntes algo como "?desea que le comparta las opciones del menu ejecutivo?" o "?quiere que le envie la carta?" antes de enviarla. En cuanto el cliente pregunte por el menu, la carta, el menu del dia o el ejecutivo, incluye el marcador DE INMEDIATO en esa misma respuesta y comparte la informacion directamente, sin pasos de confirmacion previos.

IMPORTANTE — SOBRE EL TEXTO DE TU RESPUESTA CUANDO ENVIAS IMAGENES: Las imagenes de la carta y del menu ejecutivo ya contienen todos los platos y precios, asi que NO debes listar ni describir platos, precios ni el menu en tu respuesta de texto. Responde con un mensaje breve y cordial, por ejemplo: "Con gusto, le comparto nuestra carta." o "Aqui tiene nuestro menu del dia, senor/a [nombre]." No repitas informacion de platos, precios ni acompanamientos en el texto: esa informacion ya va en las imagenes y en el mensaje de porciones que se envia despues. EXCEPCION — SOPA DEL DIA: la imagen del menu ejecutivo NO indica cual es la sopa del dia (eso cambia segun el dia de la semana), asi que cuando "ejecutivo" sea true SIEMPRE debes mencionar en tu mensaje breve cual es la sopa del dia de hoy, por ejemplo: "Aqui tiene nuestro menu del dia, senor/a [nombre]. La sopa de hoy es sopa de raya." Si el ejecutivo no aplica, no lo menciones ni te disculpes por no enviarlo, simplemente comparte la carta con naturalidad.

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
- Empaque: $1.000 por cada plato (aplica para pedidos para llevar)

SERVICIOS QUE OFRECEMOS:

YA NO TENEMOS SERVICIO DE DOMICILIO: El restaurante elimino el servicio de domicilio (entrega a direccion). Si el cliente pide domicilio, que le lleven el pedido a su casa, o menciona un barrio o direccion para que le envien la comida, respondele amablemente que por el momento no contamos con servicio de domicilio, pero que con gusto le dejamos su pedido listo para recoger en el restaurante. Ejemplo: "Le cuento que por el momento no contamos con servicio de domicilio, pero con mucho gusto le dejamos su pedido listo para que lo recoja en el restaurante. Le tomamos el pedido?" Si el cliente acepta, continua normalmente con el FLUJO PARA LLEVAR. Nunca preguntes por barrio o direccion de entrega, ni calcules costo de domicilio, ni menciones zonas de cobertura.

1. PARA LLEVAR:
- Tiempo de preparacion: 20 a 30 minutos
- Pago: Por transferencia Nequi o al recoger en el local
- Instruccion al llegar: "Al llegar, acerquese a la barra, que es donde se encuentra la caja"

2. RESERVAS DE MESA:
- Anticipacion minima: 2 horas antes
- Maximo sin administrador: 30 personas (mas de 30 personas requiere hablar con administrador)
- Tolerancia: Guardamos la mesa hasta 30 minutos despues de la hora reservada
- Celebraciones especiales (cumpleanos, aniversarios): Se ofrece un postre especial de cortesia
- Deposito para reserva: $50.000 FIJO por reserva, sin importar el numero de personas ni el valor de los platos pre-ordenados. Este deposito es unicamente para confirmar y sostener la reserva, NO se calcula como porcentaje del pedido.
- Se PREFIERE que el cliente pida los platos al momento de reservar (pre-orden), pero el valor de esos platos se paga aparte (en el restaurante, al momento de consumir), NO se suma ni se mezcla con el deposito de la reserva.
- El pedido estara listo 20 minutos despues de la hora de la reserva

DATOS DE PAGO NEQUI:
- Numero: 310 432 7103
- Titular: Didi Johana Vente
- Pedir siempre el comprobante antes de confirmar

METODOS DE PAGO EN LOCAL:
- Tarjeta de credito: Si aceptan
- Efectivo: Si aceptan

VERIFICACION DE COMPROBANTES DE PAGO: Cuando el cliente envie una imagen de un comprobante de pago (Nequi o transferencia), el sistema la lee automaticamente y te informara el resultado en un mensaje que empieza con "[El cliente envio un comprobante de pago...]" o similar. Usa ese resultado asi:
- Si el sistema detecto un MONTO y el flujo actual es una RESERVA: el deposito minimo requerido es $50.000.
  - Si el monto es igual o mayor a $50.000 (el cliente puede enviar exactamente $50.000, un adelanto mayor como $100.000 o $150.000, o incluso el valor total de la cuenta si asi lo prefiere), confirma la reserva con normalidad y agradece el pago.
  - Si el monto es MENOR a $50.000, informa amablemente al cliente el monto que detectaste y explicale que el deposito minimo es de $50.000, pidiendole que envie o complete la diferencia antes de poder confirmar la reserva.
- Si el sistema detecto un MONTO y el flujo actual es PARA LLEVAR: compara el monto contra el total del pedido (productos + empaques) que ya calculaste con el cliente.
  - Si el monto es igual o mayor al total, confirma el pedido con normalidad.
  - Si el monto es MENOR al total, informa amablemente el monto detectado, el total esperado, y pide que complete la diferencia antes de confirmar.
- Si el sistema indica que NO pudo leer el monto con claridad, pide amablemente al cliente que te confirme por escrito cuanto transfirio, sin asumir ningun valor.
- Nunca inventes un monto que el sistema no te haya indicado explicitamente.

FLUJO PARA LLEVAR:
0. ANTES DE TOMAR CUALQUIER PRODUCTO: consulta DIRECTAMENTE el valor "ESTADO ACTUAL DEL RESTAURANTE" del inicio del prompt. Este paso es OBLIGATORIO y va primero, incluso antes de tomar el nombre o el primer producto.
   - Si dice ABIERTO: continua con normalidad desde el paso 1.
   - Si dice CERRADO: informa amablemente que en este momento no hay servicio, indica el horario (12:00 PM a 7:00 PM), y ofrece dejar el pedido anotado desde ya para que quede listo apenas abra a las 12:00 PM. Si el cliente acepta, SI puedes tomar el pedido completo (productos, empaques, pago), pero en el paso 5 nunca digas "20 a 30 minutos": en su lugar informa que estara listo para recoger a partir de las 12:00 PM. Si el cliente prefiere no dejarlo anotado, ofrece que vuelva a escribir dentro del horario o que haga una reserva.
1. Saluda y pide nombre
2. Toma el pedido (recuerda la ALERTA de ambiguedad "mixto"/"triple" si aplica: usa el valor "MENU EJECUTIVO EN ESTE MOMENTO" para saber si puedes ofrecer platos del ejecutivo)
3. Confirma productos
4. Calcula empaques: $1.000 por cada plato ordenado
5. Informa el tiempo de entrega: "20 a 30 minutos" SOLO si "ESTADO ACTUAL DEL RESTAURANTE" dice ABIERTO (paso 0). Si dice CERRADO y el cliente acepto dejar el pedido listo para la apertura, informa en su lugar que estara listo para recoger a partir de las 12:00 PM.
6. Presenta resumen con total (productos + empaques)
7. Pregunta metodo de pago (Nequi o al recoger)
8. Si paga por Nequi: da datos y pide comprobante
9. Confirma y da instruccion: "Al llegar, acerquese a la barra"

FLUJO RESERVA DE MESA:
1. Saluda y pide nombre
2. Pregunta fecha, hora y numero de personas
3. Si son mas de 30 personas: "Para grupos grandes es necesario coordinar directamente con nuestra administradora. Puede contactarla al 310 432 7103." (No continues el flujo de reserva normal, no consultes disponibilidad para grupos de mas de 30)
4. Si son 30 o menos: ANTES de confirmar nada, debes verificar disponibilidad real. Para esto, una vez tengas fecha, hora y numero de personas con claridad, incluye en tu respuesta UNICAMENTE el siguiente marcador (sin texto adicional al cliente todavia, el sistema te dara el resultado y tu respondes despues con la informacion real):
   ##CONSULTAR_DISPONIBILIDAD##{"fecha":"DD/MM/AAAA","hora":"HH:MM AM/PM","personas":"X"}##
   - El campo "fecha" debe ir en formato DD/MM/AAAA (ej: "25/06/2026"). Si el cliente da una fecha relativa como "manana" o "el viernes", calcula la fecha exacta usando HOY ({fecha_hoy}) y conviertela a DD/MM/AAAA antes de poner el marcador.
   - El campo "hora" debe ir en formato HH:MM AM/PM (ej: "7:00 PM", "1:30 PM"). Convierte expresiones como "la una de la tarde" a este formato exacto.
   - El sistema te devolvera un mensaje indicando si hay disponibilidad, o si debes ofrecer otra franja horaria, o si no hay cupo en absoluto. Usa esa informacion para responder al cliente con naturalidad.
5. Si hay disponibilidad: confirma al cliente y continua con normalidad.
6. Si NO hay disponibilidad en el horario pedido pero SI en la otra franja del mismo dia (almuerzo o cena): ofrece amablemente esa alternativa. Si el cliente acepta, continua el flujo con la nueva hora. Si no acepta, ofrece coordinar con la administradora (310 432 7103) para otro dia.
7. Si NO hay disponibilidad en ninguna franja: informa al cliente y dale el contacto de la administradora (310 432 7103).
8. Pregunta si es celebracion especial (cumpleanos, aniversario) - si es asi menciona el postre de cortesia
9. SIEMPRE invitar a hacer pre-orden: "Para garantizar una experiencia perfecta, le recomendamos hacer su pedido ahora. Asi la cocina tendra todo listo a su llegada."
10. Tomar pedido de platos (pre-orden), aclarando que el valor de estos platos se paga aparte, no junto con el deposito
11. Informar el deposito FIJO de $50.000 para confirmar y sostener la reserva (no depende de cuantas personas sean ni del valor de los platos)
12. Dar datos de Nequi y pedir comprobante del deposito de $50.000
13. Confirmar reserva con todos los datos, usando en "fecha_reserva" y "hora_reserva" del marcador de confirmacion EXACTAMENTE el mismo formato usado en la consulta de disponibilidad (DD/MM/AAAA y HH:MM AM/PM)

Al confirmar cualquier pedido o reserva completamente pon al FINAL:
##PEDIDO_CONFIRMADO##{"tipo":"PARA_LLEVAR/RESERVA","nombre":"X","telefono":"X","fecha_reserva":"DD/MM/AAAA","hora_reserva":"HH:MM AM/PM","personas":"X","productos":"X","total_platos":"X","total_empaques":"X","deposito":"X","celebracion":"X","pago":"X"}##

CELEBRACIONES ESPECIALES: Si el cliente menciona cumpleanos o aniversario, mencionar con entusiasmo que tienen un postre especial de cortesia para celebrar.

QUEJAS O PROBLEMAS: "Entiendo su situacion. Para ayudarle mejor le comunico con nuestra administradora directamente. Puede contactarla al 310 432 7103."
GRUPOS GRANDES (mas de 30 personas): "Para reservas de grupos grandes es necesario coordinar directamente con nuestra administradora. Puede contactarla al 310 432 7103."

REGLAS:
- No inventes precios ni platos que no esten en el menu
- Calcula totales correctamente: productos + empaques ($1.000 por plato)
- Para reservas siempre pedir pre-orden de platos, pero el deposito de reserva SIEMPRE es $50.000 fijo, nunca se calcula como porcentaje del valor de los platos ni se suma a un costo de mesa
- Siempre pedir comprobante de Nequi antes de confirmar
- Si el cliente elige efectivo o tarjeta de credito: NO mencionar Nequi ni sus datos. Solo confirmar el metodo elegido.
- Habla SIEMPRE en espanol, sin palabras en ingles
- Tono formal y profesional en todo momento
- Si preguntan por la direccion del restaurante: "Nos encontramos en la Calle 1 #5a-5456, barrio Centro, Buenaventura. Estamos diagonal a Salamandra, frente al Edificio Altos de la Bahia."
- NUNCA preguntes al cliente por su numero de telefono o de contacto, ni le preguntes si prefiere que lo contacten al mismo numero de WhatsApp o a otro distinto. El sistema ya identifica automaticamente el numero de WhatsApp desde el que escribe, no necesitas pedirlo ni confirmarlo bajo ninguna circunstancia. En el campo "telefono" del marcador de confirmacion, simplemente pon "X" o dejalo vacio; el sistema lo completa solo.
- MENU EJECUTIVO: Solo disponible de LUNES A VIERNES entre 12:00 PM y 3:00 PM. Fuera de ese dia u horario, NO ofrecer menu ejecutivo bajo ninguna circunstancia. Solo carta regular. Para pedidos para llevar usa el valor "MENU EJECUTIVO EN ESTE MOMENTO" ya calculado; para reservas usa la fecha y hora DE LA RESERVA (ver REGLA CLAVE). De lunes a viernes cuando aplique, informar la sopa del dia correcta segun corresponda. El sirope de la casa SIEMPRE va incluido sin costo con el menu ejecutivo, nunca se cobra ni se ofrece como opcional.
- DOMICILIO: Ya NO existe este servicio. Si el cliente lo pide, informar amablemente que no esta disponible y ofrecer dejar el pedido listo para recoger en el restaurante (para llevar). Nunca preguntar por barrio o direccion de entrega."""

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
  if(d.enviar_carta){
    setTimeout(function(){aI('https://raw.githubusercontent.com/herdora24-web/raices-bot/main/carta_raices_1.jpg');},200);
    setTimeout(function(){aI('https://raw.githubusercontent.com/herdora24-web/raices-bot/main/carta_raices_2.jpg');},500);
    var delayFinal=800;
    if(d.enviar_ejecutivo){
      setTimeout(function(){aI('https://raw.githubusercontent.com/herdora24-web/raices-bot/main/menu_ejecutivo.jpg');},800);
      delayFinal=1100;
    }
    setTimeout(function(){aM('bot','🍽️ MEDIAS PORCIONES (disponibles en carta)\n• Media cazuela: $45.000\n• Media chuleta a la calima (cerdo, pollo o pescado): $45.000\n• Medio arroz marinero: $33.000\n\n🍟 PORCIONES ADICIONALES\n• Arroz: $4.000\n• Patacón: $5.000\n• Papas a la francesa: $5.000\n• Papachina: $8.000\n• Toyo: $12.000\n• Piangua: $15.000\n• Jaiba: $18.000\n• Langostino: $30.000');},delayFinal);
  }
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
    now = ahora_co()
    dia_num = now.weekday()
    dia_nombre = DIAS_SEMANA[dia_num]
    fecha_hoy = f"{dia_nombre} {now.strftime('%d/%m/%Y')}"
    hora_actual = now.strftime('%I:%M %p')

    # Calculo deterministico en Python (nunca se lo dejamos al modelo): evita que el LLM
    # tenga que comparar horas en texto ("9:26 AM" vs "12:00 PM") dentro de un prompt largo,
    # que es una fuente recurrente de errores. Aqui la respuesta ya sale resuelta.
    hora_decimal = now.hour + now.minute / 60
    dia_habil = dia_num <= 4  # lunes(0) a viernes(4)
    abierto_ahora = 12 <= hora_decimal < 19  # 12:00 PM a 7:00 PM
    # El corte para PEDIDOS PARA LLEVAR del ejecutivo es 12:00 PM - 2:45 PM (14.75), 15 min antes
    # del cierre real del servicio ejecutivo (3:00 PM), para darle a cocina tiempo de preparar y
    # empacar. El corte de 3:00 PM para RESERVAS (dine-in) se mantiene aparte en el prompt, ya que
    # ese calculo es sobre una fecha/hora futura y lo sigue haciendo el modelo (ver REGLA CLAVE).
    ejecutivo_para_llevar_ahora = dia_habil and (12 <= hora_decimal < 14.75)

    estado_restaurante = (
        "ABIERTO (dentro del horario de servicio: 12:00 PM a 7:00 PM)"
        if abierto_ahora else
        "CERRADO (fuera del horario de servicio; el horario es todos los dias de 12:00 PM a 7:00 PM)"
    )
    estado_ejecutivo = (
        "DISPONIBLE ahora mismo para PARA LLEVAR (estamos dentro de lunes a viernes, 12:00 PM a 2:45 PM)"
        if ejecutivo_para_llevar_ahora else
        "NO DISPONIBLE ahora mismo para PARA LLEVAR (el ejecutivo para llevar solo se toma lunes a viernes, entre 12:00 PM y 2:45 PM; fuera de esa ventana, solo carta regular para pedidos inmediatos)"
    )

    prompt = SYSTEM_PROMPT_BASE.replace("{fecha_hoy}", fecha_hoy).replace("{hora_actual}", hora_actual)
    prompt = prompt.replace("{estado_restaurante}", estado_restaurante).replace("{estado_ejecutivo}", estado_ejecutivo)
    return prompt

def limpiar_marcadores(txt):
    """Quita cualquier marcador tecnico (##NOMBRE##{...}##) del texto antes de mostrarlo al cliente."""
    clean = txt
    for marcador in ("##PEDIDO_CONFIRMADO##", "##ENVIAR_IMAGENES##", "##CONSULTAR_DISPONIBILIDAD##"):
        while marcador in clean:
            i = clean.index(marcador)
            try:
                j = clean.index("##", i + len(marcador)) + 2
                clean = (clean[:i] + clean[j:]).strip()
            except ValueError:
                clean = clean[:i].strip()
                break
    return clean

def extraer_consulta_disponibilidad(txt):
    """Lee el marcador ##CONSULTAR_DISPONIBILIDAD##{...}## si esta presente."""
    if "##CONSULTAR_DISPONIBILIDAD##" in txt:
        try:
            i = txt.index("##CONSULTAR_DISPONIBILIDAD##")+len("##CONSULTAR_DISPONIBILIDAD##")
            j = txt.index("##",i)
            data = json.loads(txt[i:j])
            return {
                "fecha": data.get("fecha",""),
                "hora": data.get("hora",""),
                "personas": data.get("personas","1"),
            }
        except: pass
    return None

def _llamar_openrouter(session_id):
    """Llama a OpenRouter con el historial actual de la sesion. No modifica el historial."""
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
    return r.json()["choices"][0]["message"]["content"]

def call_claude(session_id, mensaje):
    if session_id not in conversaciones:
        conversaciones[session_id] = []
    conversaciones[session_id].append({"role":"user","content":mensaje})

    txt = _llamar_openrouter(session_id)

    # Si Claude pidio consultar disponibilidad, resolvemos la consulta y le devolvemos
    # el resultado como contexto, para que de la respuesta final al cliente.
    consulta = extraer_consulta_disponibilidad(txt)
    if consulta:
        resultado = firestore_db.consultar_disponibilidad(
            consulta["fecha"], consulta["hora"], consulta["personas"]
        )
        contexto = _formatear_resultado_disponibilidad(resultado)
        # Guardamos la respuesta intermedia de Claude (limpia, sin el marcador) en el historial,
        # solo si tenia texto visible ademas del marcador; si no, evitamos un mensaje vacio.
        intermedio_clean = limpiar_marcadores(txt)
        if intermedio_clean:
            conversaciones[session_id].append({"role":"assistant","content":intermedio_clean})
        conversaciones[session_id].append({"role":"user","content":contexto})
        txt = _llamar_openrouter(session_id)

    clean = limpiar_marcadores(txt)
    conversaciones[session_id].append({"role":"assistant","content":clean})

    pedido = extraer_pedido(txt)
    if pedido:
        pedido["telefono"] = session_id
        firestore_db.guardar_pedido(pedido, ahora_co())

    return txt

def _formatear_resultado_disponibilidad(resultado):
    """Convierte el resultado de consultar_disponibilidad en un mensaje de contexto
    para que Claude lo use al responder al cliente (este texto nunca lo ve el cliente directamente)."""
    if not resultado["ok"]:
        return ("[SISTEMA] No se pudo interpretar la fecha u hora indicada para verificar disponibilidad. "
                "Pide al cliente que confirme la fecha (dd/mm/aaaa) y la hora exacta de la reserva.")
    if resultado["disponible"]:
        return (f"[SISTEMA] Hay disponibilidad para la reserva solicitada "
                f"(franja: {resultado['franja']}, cupo restante: {resultado['cupo_restante']} personas). "
                f"Continua el flujo de reserva con normalidad.")
    if resultado["alternativa"]:
        franja_alt = FRANJAS_LABELS.get(resultado["alternativa"], resultado["alternativa"])
        return (f"[SISTEMA] La franja solicitada ({resultado['franja']}) ya no tiene cupo suficiente "
                f"para esa cantidad de personas. SI hay cupo disponible en la otra franja del mismo dia: {franja_alt}. "
                f"Informa al cliente amablemente que el horario solicitado ya esta lleno, y ofrece la franja alternativa "
                f"como opcion. No insistas en el horario original.")
    return (f"[SISTEMA] La franja solicitada ({resultado['franja']}) ya no tiene cupo, y la otra franja del mismo dia "
            f"tampoco tiene espacio suficiente. Informa al cliente que no hay disponibilidad para esa fecha con esa "
            f"cantidad de personas, y dale el contacto de la administradora (310 432 7103) para que coordine "
            f"alternativas (otro dia, dividir el grupo, etc).")

def build_resp(msg, txt):
    clean = limpiar_marcadores(txt)
    imagenes = extraer_imagenes(txt)
    dia_semana = ahora_co().weekday()  # 0=lunes ... 6=domingo, segun hora Colombia
    return {
        "response":clean,
        "enviar_carta":imagenes["carta"],
        "enviar_ejecutivo":imagenes["ejecutivo"],
        "enviar_nequi": any(p in msg.lower() for p in PALABRAS_NEQUI),
        "dia_semana":dia_semana
    }

def extraer_pedido(txt):
    if "##PEDIDO_CONFIRMADO##" in txt:
        try:
            i = txt.index("##PEDIDO_CONFIRMADO##")+len("##PEDIDO_CONFIRMADO##")
            j = txt.index("##",i)
            return json.loads(txt[i:j])
        except: pass
    return None

def extraer_imagenes(txt):
    """Lee el marcador ##ENVIAR_IMAGENES##{...}## que Claude incluye cuando corresponde
    mostrar la carta y/o el menu ejecutivo. Claude decide segun el contexto real
    (hora actual para domicilio/para llevar, hora de la reserva para reservas)."""
    if "##ENVIAR_IMAGENES##" in txt:
        try:
            i = txt.index("##ENVIAR_IMAGENES##")+len("##ENVIAR_IMAGENES##")
            j = txt.index("##",i)
            data = json.loads(txt[i:j])
            return {"carta": bool(data.get("carta", False)), "ejecutivo": bool(data.get("ejecutivo", False))}
        except: pass
    return {"carta": False, "ejecutivo": False}


def leer_monto_comprobante(image_bytes, media_type="image/jpeg"):
    """Usa Claude Vision (via OpenRouter) para leer el monto de un comprobante de pago
    (Nequi, transferencia u otro medio digital colombiano) a partir de la imagen recibida.
    Devuelve un float con el monto en pesos colombianos, o None si no se pudo leer con certeza."""
    try:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        hdrs = {
            "Authorization":"Bearer "+os.environ.get("OPENROUTER_API_KEY",""),
            "Content-Type":"application/json",
            "HTTP-Referer":"https://raices-bot.com",
            "X-Title":"Raices Gastro Bar Bot"
        }
        prompt_vision = (
            "Esta imagen deberia ser un comprobante de pago (Nequi, transferencia bancaria u otro medio "
            "digital) de Colombia. Identifica el MONTO TOTAL transferido o pagado, en pesos colombianos. "
            "Responde UNICAMENTE con un JSON en una sola linea, sin texto adicional, sin backticks, con este "
            "formato exacto: {\"monto\": <numero_o_null>}. Si logras leer el monto con certeza, ponlo como "
            "numero entero sin puntos ni simbolos (ejemplo: 50000). Si la imagen no es un comprobante de pago, "
            "o no puedes leer el monto con certeza, responde {\"monto\": null}."
        )
        body = {
            "model":"anthropic/claude-sonnet-4-5",
            "max_tokens":200,
            "messages":[{
                "role":"user",
                "content":[
                    {"type":"text","text":prompt_vision},
                    {"type":"image_url","image_url":{"url":f"data:{media_type};base64,{b64}"}}
                ]
            }]
        }
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",headers=hdrs,json=body,timeout=30)
        texto = r.json()["choices"][0]["message"]["content"].strip()
        texto = texto.replace("```json","").replace("```","").strip()
        data = json.loads(texto)
        monto = data.get("monto")
        return float(monto) if monto is not None else None
    except Exception as e:
        print("Error leyendo comprobante:", e)
        return None


def descargar_imagen_wa(image_id):
    """Descarga una imagen enviada por WhatsApp a partir de su media id.
    Devuelve (bytes_imagen, mime_type), o (None, None) si algo falla."""
    try:
        t = os.environ.get("WHATSAPP_TOKEN")
        h = {"Authorization": f"Bearer {t}"}
        meta = requests.get(f"https://graph.facebook.com/v18.0/{image_id}", headers=h).json()
        url = meta.get("url")
        mime = meta.get("mime_type", "image/jpeg")
        contenido = requests.get(url, headers=h).content
        return contenido, mime
    except Exception as e:
        print("Error descargando imagen de WhatsApp:", e)
        return None, None


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
    nequi = any(p in msg_usuario.lower() for p in PALABRAS_NEQUI)
    clean = limpiar_marcadores(txt)
    imagenes = extraer_imagenes(txt)
    if clean: wa_txt(num, clean)
    if imagenes["carta"]:
        wa_img(num, "https://raw.githubusercontent.com/herdora24-web/raices-bot/main/carta_raices_1.jpg", "Nuestra carta - Parte 1")
        wa_img(num, "https://raw.githubusercontent.com/herdora24-web/raices-bot/main/carta_raices_2.jpg", "Nuestra carta - Parte 2")
        if imagenes["ejecutivo"]:
            wa_img(num, "https://raw.githubusercontent.com/herdora24-web/raices-bot/main/menu_ejecutivo.jpg", "Menu ejecutivo del dia")
        msg_medias = (
            "🍽️ *MEDIAS PORCIONES* (disponibles en carta)\n"
            "• Media cazuela: $45.000\n"
            "• Media chuleta a la calima (cerdo, pollo o pescado): $45.000\n"
            "• Medio arroz marinero: $33.000\n\n"
            "🍟 *PORCIONES ADICIONALES*\n"
            "• Arroz: $4.000\n"
            "• Patacón: $5.000\n"
            "• Papas a la francesa: $5.000\n"
            "• Papachina: $8.000\n"
            "• Toyo: $12.000\n"
            "• Piangua: $15.000\n"
            "• Jaiba: $18.000\n"
            "• Langostino: $30.000"
        )
        wa_txt(num, msg_medias)
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


@app.route("/privacy")
def privacy():
    return send_from_directory('.', 'privacy_policy_raices.html')

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
        elif tipo=="image":
            img_bytes, mime = descargar_imagen_wa(msg["image"]["id"])
            if img_bytes:
                monto = leer_monto_comprobante(img_bytes, mime or "image/jpeg")
                if monto is not None:
                    txt = f"[El cliente envio un comprobante de pago. Monto detectado por el sistema: ${monto:,.0f} COP]"
                else:
                    txt = ("[El cliente envio una imagen que parece ser un comprobante de pago, pero el sistema "
                           "no pudo leer el monto con claridad. Pidele amablemente que confirme por escrito "
                           "cuanto transfirio.]")
            else:
                txt = ("[El cliente envio una imagen (posiblemente un comprobante de pago) pero no se pudo "
                       "descargar. Pidele que confirme por escrito el monto transferido.]")
        else: wa_txt(num,"Solo entiendo texto, notas de voz e imagenes."); return jsonify({"ok":True}),200
        wa_send(num, txt, call_claude(num,txt))
        return jsonify({"ok":True}),200
    except Exception as e: print("WH error:",e); return jsonify({"error":str(e)}),500

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
