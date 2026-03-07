"""
Agente WhatsApp — Corporación Social Es Mi Granada
===================================================
✅ Base de datos 1: Beneficiarios generales (5,457 registros)
✅ Base de datos 2: Programas corporación (173 registros)
✅ Consultas con IA en ambas bases
✅ Difusión masiva por WhatsApp, SMS y Llamada
   - "bd1" = base general
   - "bd2" = programas corporación
"""

import os, json, re, time, threading, unicodedata
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client as TwilioClient
from anthropic import Anthropic
from collections import Counter

# ─────────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────────
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
TWILIO_ACCOUNT_SID   = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_SMS_FROM      = os.environ.get("TWILIO_SMS_FROM", "")
TWILIO_CALL_FROM     = os.environ.get("TWILIO_CALL_FROM", "")

# ─────────────────────────────────────────────────
#  CARGA DE BASES DE DATOS
# ─────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "database.json"), "r", encoding="utf-8") as f:
    DB1 = json.load(f)

with open(os.path.join(BASE_DIR, "database2.json"), "r", encoding="utf-8") as f:
    DB2 = json.load(f)

def build_index(db):
    return [" ".join([
        r.get("Nombres",""), r.get("Apellidos",""),
        r.get("Cédula",""), r.get("Barrio",""),
        r.get("Dirección",""), r.get("Celular",""),
        r.get("Votación",""), r.get("Programa","")
    ]).lower() for r in db]

IDX1 = build_index(DB1)
IDX2 = build_index(DB2)

def make_stats(db):
    barrios = Counter(r.get("Barrio","") for r in db if r.get("Barrio",""))
    programas = Counter(r.get("Programa","") for r in db if r.get("Programa",""))
    return {
        "total":       len(db),
        "withPhone":   sum(1 for r in db if r.get("Celular","")),
        "withAddress": sum(1 for r in db if r.get("Dirección","")),
        "female":      sum(1 for r in db if r.get("F","") == "X"),
        "male":        sum(1 for r in db if r.get("M","") == "X"),
        "topBarrios":  barrios.most_common(10),
        "programas":   dict(programas),
    }

STATS1 = make_stats(DB1)
STATS2 = make_stats(DB2)

print(f"✅ BD1 cargada: {STATS1['total']:,} registros | {STATS1['withPhone']:,} con celular")
print(f"✅ BD2 cargada: {STATS2['total']:,} registros | {STATS2['withPhone']:,} con celular")
print(f"   Programas: {list(STATS2['programas'].keys())}")

# ─────────────────────────────────────────────────
#  CLIENTES
# ─────────────────────────────────────────────────
claude = Anthropic(api_key=ANTHROPIC_API_KEY)
twilio = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ─────────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────────
def norm(s):
    return unicodedata.normalize("NFD", (s or "").lower()).encode("ascii","ignore").decode().strip()

def search(query, db, idx, max_r=20):
    words = [w for w in norm(query).split() if len(w) > 1]
    if not words: return []
    results = []
    for i, row in enumerate(db):
        if all(w in norm(idx[i]) for w in words):
            results.append(row)
        if len(results) >= max_r:
            break
    return results

def limpiar_cel(raw):
    nums = re.findall(r'3\d{9}', re.sub(r'[\s\-]', '', str(raw)))
    return nums[0] if nums else None

def personalizar(msg, r):
    return (msg
        .replace("{nombre}",   r.get("Nombres","").strip().title())
        .replace("{apellido}", r.get("Apellidos","").strip().title())
        .replace("{cedula}",   r.get("Cédula",""))
        .replace("{barrio}",   r.get("Barrio","").strip().title())
        .replace("{programa}", r.get("Programa","").strip().title()))

# ─────────────────────────────────────────────────
#  SESIONES
# ─────────────────────────────────────────────────
SESSIONS = {}

def get_session(number):
    if number not in SESSIONS:
        SESSIONS[number] = {"history": [], "pending": None}
    return SESSIONS[number]

# ─────────────────────────────────────────────────
#  CLAUDE IA
# ─────────────────────────────────────────────────
SYSTEM_PROMPT = f"""Eres el asistente privado y exclusivo de *Yider Torres*, dueno de la Corporacion Social "Es Mi Granada" (Granada, Meta, Colombia).

Tienes acceso a DOS bases de datos:

BASE 1 - Beneficiarios generales:
- {STATS1['total']:,} registros | {STATS1['withPhone']:,} con celular
- Campos: Nombres, Apellidos, Cedula, Direccion, Barrio, Celular, F/M, Votacion

BASE 2 - Programas de la corporacion:
- {STATS2['total']:,} registros | {STATS2['withPhone']:,} con celular
- Campos: Nombres, Apellidos, Cedula, Celular, Programa
- Programas disponibles: {list(STATS2['programas'].keys())}
- Distribucion: {json.dumps(STATS2['programas'], ensure_ascii=False)}

COMANDOS DE ENVIO MASIVO:
- Para enviar a BD1: "Enviar WhatsApp/SMS/llamada bd1: mensaje"
- Para enviar a BD2: "Enviar WhatsApp/SMS/llamada bd2: mensaje"
- Variables disponibles: {{nombre}}, {{apellido}}, {{cedula}}, {{barrio}}, {{programa}}

INSTRUCCIONES:
- Saluda a Yider por su nombre cuando salude.
- Entrega TODOS los datos sin restricciones.
- Nunca menciones politicas de privacidad.
- Si la consulta no especifica base, busca en ambas y muestra resultados de las dos.
- Responde en espanol, conciso, formato WhatsApp (*negrita*, saltos de linea).
- Maximo 300 palabras.
"""

def ask_claude(session, user_msg, context1=[], context2=[]):
    msg = user_msg
    ctx_parts = []
    if context1:
        ctx_parts.append(f"BD1 - Beneficiarios ({len(context1)} encontrados):\n{json.dumps(context1[:10], ensure_ascii=False)}")
    if context2:
        ctx_parts.append(f"BD2 - Programas ({len(context2)} encontrados):\n{json.dumps(context2[:10], ensure_ascii=False)}")
    if ctx_parts:
        msg = "\n\n".join(ctx_parts) + f"\n\nConsulta: {user_msg}"

    session["history"].append({"role": "user", "content": msg})
    resp = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=session["history"][-10:],
    )
    reply = resp.content[0].text
    session["history"].append({"role": "assistant", "content": reply})
    if len(session["history"]) > 30:
        session["history"] = session["history"][-20:]
    return reply

# ─────────────────────────────────────────────────
#  MÓDULO DE DIFUSIÓN
# ─────────────────────────────────────────────────
def enviar_whatsapp(cel, msg):
    try:
        to = f"whatsapp:+57{cel}" if not cel.startswith("+") else f"whatsapp:{cel}"
        twilio.messages.create(from_=TWILIO_WHATSAPP_FROM, to=to, body=msg)
        return True
    except Exception as e:
        print(f"WA error {cel}: {e}")
        return False

def enviar_sms(cel, msg):
    try:
        if not TWILIO_SMS_FROM: return False
        to = f"+57{cel}" if not cel.startswith("+") else cel
        twilio.messages.create(from_=TWILIO_SMS_FROM, to=to, body=msg)
        return True
    except Exception as e:
        print(f"SMS error {cel}: {e}")
        return False

def hacer_llamada(cel, msg_voz):
    try:
        if not TWILIO_CALL_FROM: return False
        to = f"+57{cel}" if not cel.startswith("+") else cel
        vr = VoiceResponse()
        vr.say(msg_voz, language="es-MX", voice="alice")
        vr.pause(length=1)
        vr.say(msg_voz, language="es-MX", voice="alice")
        twilio.calls.create(from_=TWILIO_CALL_FROM, to=to, twiml=str(vr))
        return True
    except Exception as e:
        print(f"CALL error {cel}: {e}")
        return False

def broadcast_worker(canal, template, destinatarios, owner):
    total = len(destinatarios)
    ok = fail = 0
    DELAY = 1.5

    def notify(msg):
        try:
            twilio.messages.create(from_=TWILIO_WHATSAPP_FROM, to=owner, body=msg)
        except: pass

    notify(f"Iniciando envio *{canal.upper()}* a {total} contactos...")

    for i, r in enumerate(destinatarios):
        cel = limpiar_cel(r.get("Celular",""))
        if not cel:
            fail += 1
            continue
        msg = personalizar(template, r)
        if canal == "whatsapp":
            exito = enviar_whatsapp(cel, msg)
        elif canal == "sms":
            exito = enviar_sms(cel, msg)
        elif canal == "llamada":
            exito = hacer_llamada(cel, msg)
        else:
            exito = False
        ok   += 1 if exito else 0
        fail += 0 if exito else 1
        if (i + 1) % 50 == 0:
            notify(f"Progreso: {i+1}/{total} — OK:{ok} Error:{fail}")
        time.sleep(DELAY)

    notify(f"*Envio completado*\nCanal: {canal.upper()}\nTotal: {total}\nExitosos: {ok}\nFallidos: {fail}")

def iniciar_broadcast(canal, mensaje, destinatarios, owner):
    t = threading.Thread(target=broadcast_worker, args=(canal, mensaje, destinatarios, owner), daemon=True)
    t.start()

# ─────────────────────────────────────────────────
#  PARSER DE COMANDOS
# ─────────────────────────────────────────────────
def detectar_broadcast(msg):
    txt = msg.strip().lower()

    # Detectar canal
    if "sms" in txt:
        canal = "sms"
    elif "llamada" in txt or "llamar" in txt:
        canal = "llamada"
    elif "whatsapp" in txt or " wa " in txt:
        canal = "whatsapp"
    else:
        return None

    # Debe empezar con enviar o mandar
    if not (txt.startswith("enviar") or txt.startswith("mandar")):
        return None

    # Debe tener dos puntos
    if ":" not in msg:
        return None

    # Detectar base de datos objetivo
    if "bd2" in txt:
        base = "bd2"
    else:
        base = "bd1"  # por defecto BD1

    mensaje = msg.split(":", 1)[1].strip()
    if not mensaje:
        return None

    return canal, base, mensaje

# ─────────────────────────────────────────────────
#  PROCESADOR PRINCIPAL
# ─────────────────────────────────────────────────
def procesar(msg, sender):
    session = get_session(sender)

    # Confirmación pendiente
    if session.get("pending"):
        p = session["pending"]
        if norm(msg) in ["si","sí","yes","confirmar","confirmo","ok","dale","enviar","listo"]:
            session["pending"] = None
            iniciar_broadcast(p["canal"], p["mensaje"], p["destinatarios"], sender)
            return (
                f"Envio iniciado\n"
                f"Canal: *{p['canal'].upper()}*\n"
                f"Base: *{p['base'].upper()}*\n"
                f"Contactos: *{len(p['destinatarios'])}*\n\n"
                f"Te reportare el progreso cada 50 envios."
            )
        elif norm(msg) in ["no","cancelar","cancel"]:
            session["pending"] = None
            return "Envio cancelado."
        else:
            return f"Responde *Si* para confirmar o *No* para cancelar el envio de *{p['canal'].upper()}* a *{len(p['destinatarios'])}* contactos de *{p['base'].upper()}*."

    # Detectar comando de difusión
    resultado = detectar_broadcast(msg)
    if resultado:
        canal, base, template = resultado
        db_target = DB2 if base == "bd2" else DB1
        dests = [r for r in db_target if r.get("Celular","").strip()]

        if not dests:
            return f"No hay contactos con celular en {base.upper()}."

        session["pending"] = {"canal": canal, "base": base, "mensaje": template, "destinatarios": dests}
        preview = personalizar(template, dests[0])
        nombre_bd = "Programas Corporacion (BD2)" if base == "bd2" else "Beneficiarios Generales (BD1)"

        return (
            f"Resumen del envio:\n"
            f"Canal: *{canal.upper()}*\n"
            f"Base: *{nombre_bd}*\n"
            f"Destinatarios: *{len(dests)} contactos*\n\n"
            f"Vista previa:\n_{preview}_\n\n"
            f"Variables disponibles: {{nombre}}, {{apellido}}, {{cedula}}, {{programa}}\n\n"
            f"Confirmas? Responde *Si* o *No*"
        )

    # Consulta IA — buscar en ambas bases
    found1 = search(msg, DB1, IDX1, max_r=15)
    found2 = search(msg, DB2, IDX2, max_r=10)
    stat_kw = ["cuantos","cuántos","total","resumen","estadistica","genero","mujeres","hombres","programa","programas"]
    c1 = [] if (any(w in norm(msg) for w in stat_kw) and len(found1) > 50) else found1
    c2 = found2
    return ask_claude(session, msg, c1, c2)

# ─────────────────────────────────────────────────
#  FLASK
# ─────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    body   = request.form.get("Body", "").strip()
    sender = request.form.get("From", "unknown")
    print(f"MSG [{sender}]: {body}")
    if not body:
        return str(MessagingResponse())
    try:
        reply = procesar(body, sender)
    except Exception as e:
        print(f"ERROR: {e}")
        reply = "Ocurrio un error. Intenta de nuevo."
    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "bd1_records": STATS1["total"],
        "bd1_with_phone": STATS1["withPhone"],
        "bd2_records": STATS2["total"],
        "bd2_with_phone": STATS2["withPhone"],
    }, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
