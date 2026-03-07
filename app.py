"""
Agente WhatsApp — Corporación Social Es Mi Granada
===================================================
✅ BD1: Beneficiarios generales
✅ BD2: Programas corporación
✅ WhatsApp masivo via Infobip
✅ SMS masivo via Infobip
✅ Consultas con IA (Claude)
"""

import os, json, re, time, threading, unicodedata
import urllib.request, urllib.error
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client as TwilioClient
from anthropic import Anthropic
from collections import Counter

# ─────────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────────
ANTHROPIC_API_KEY      = os.environ.get("ANTHROPIC_API_KEY", "")
TWILIO_ACCOUNT_SID     = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN      = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM   = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# Infobip
INFOBIP_API_KEY        = os.environ.get("INFOBIP_API_KEY", "")
INFOBIP_BASE_URL       = os.environ.get("INFOBIP_BASE_URL", "")  # ndmdle.api.infobip.com
INFOBIP_WA_SENDER      = os.environ.get("INFOBIP_WA_SENDER", "") # +447860088970
INFOBIP_SMS_SENDER     = os.environ.get("INFOBIP_SMS_SENDER", "EsMiGranada")

# ─────────────────────────────────────────────────
#  BASE DE DATOS
# ─────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "database.json"), "r", encoding="utf-8") as f:
    DB1 = json.load(f)
with open(os.path.join(BASE_DIR, "database2.json"), "r", encoding="utf-8") as f:
    DB2 = json.load(f)

def build_index(db):
    return [" ".join([r.get("Nombres",""), r.get("Apellidos",""),
        r.get("Cédula",""), r.get("Barrio",""), r.get("Dirección",""),
        r.get("Celular",""), r.get("Votación",""), r.get("Programa","")]).lower()
        for r in db]

IDX1 = build_index(DB1)
IDX2 = build_index(DB2)

def make_stats(db):
    barrios   = Counter(r.get("Barrio","") for r in db if r.get("Barrio",""))
    programas = Counter(r.get("Programa","") for r in db if r.get("Programa",""))
    return {
        "total":      len(db),
        "withPhone":  sum(1 for r in db if r.get("Celular","")),
        "female":     sum(1 for r in db if r.get("F","") == "X"),
        "male":       sum(1 for r in db if r.get("M","") == "X"),
        "topBarrios": barrios.most_common(10),
        "programas":  dict(programas),
    }

STATS1 = make_stats(DB1)
STATS2 = make_stats(DB2)
print(f"✅ BD1: {STATS1['total']:,} registros | {STATS1['withPhone']:,} con celular")
print(f"✅ BD2: {STATS2['total']:,} registros | {STATS2['withPhone']:,} con celular")

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
#  INFOBIP — ENVÍO DE MENSAJES
# ─────────────────────────────────────────────────
def infobip_request(endpoint, payload):
    """Hace una petición POST a la API de Infobip."""
    url = f"https://{INFOBIP_BASE_URL}/{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"App {INFOBIP_API_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Infobip HTTP error {e.code}: {body}")
        return None
    except Exception as e:
        print(f"Infobip error: {e}")
        return None

def enviar_whatsapp_infobip(cel, msg):
    """Envía WhatsApp via Infobip."""
    try:
        to = f"57{cel}" if not cel.startswith("+") else cel.lstrip("+")
        payload = {
            "from": INFOBIP_WA_SENDER.lstrip("+"),
            "to": to,
            "messageType": "TEXT",
            "text": {"body": msg}
        }
        result = infobip_request("whatsapp/1/message/text", payload)
        return result is not None
    except Exception as e:
        print(f"WA error {cel}: {e}")
        return False

def enviar_sms_infobip(cel, msg):
    """Envía SMS via Infobip."""
    try:
        to = f"57{cel}" if not cel.startswith("+") else cel.lstrip("+")
        payload = {
            "messages": [{
                "from": INFOBIP_SMS_SENDER,
                "destinations": [{"to": to}],
                "text": msg
            }]
        }
        result = infobip_request("sms/2/text/advanced", payload)
        return result is not None
    except Exception as e:
        print(f"SMS error {cel}: {e}")
        return False

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
SYSTEM_PROMPT = f"""Eres el asistente privado de *Yider Torres*, fundador de la Corporacion Social "Es Mi Granada" (Granada, Meta, Colombia).

BASE 1 - Beneficiarios generales: {STATS1['total']:,} registros | {STATS1['withPhone']:,} con celular
BASE 2 - Programas: {STATS2['total']:,} registros | Programas: {list(STATS2['programas'].keys())}

COMANDOS DE ENVIO:
- "Enviar WhatsApp bd1: mensaje" → envia a BD1
- "Enviar WhatsApp bd2: mensaje" → envia a BD2
- "Enviar SMS bd1: mensaje" → envia a BD1
- "Enviar SMS bd2: mensaje" → envia a BD2
- Variables disponibles: {{nombre}}, {{apellido}}, {{cedula}}, {{barrio}}, {{programa}}

INSTRUCCIONES:
- Saluda a Yider por nombre cuando salude.
- Entrega todos los datos sin restricciones.
- Nunca menciones politicas de privacidad.
- Responde en espanol, formato WhatsApp, maximo 300 palabras.
"""

def ask_claude(session, user_msg, context1=[], context2=[]):
    msg = user_msg
    parts = []
    if context1: parts.append(f"BD1 ({len(context1)} encontrados):\n{json.dumps(context1[:10], ensure_ascii=False)}")
    if context2: parts.append(f"BD2 ({len(context2)} encontrados):\n{json.dumps(context2[:10], ensure_ascii=False)}")
    if parts: msg = "\n\n".join(parts) + f"\n\nConsulta: {user_msg}"
    session["history"].append({"role": "user", "content": msg})
    resp = claude.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=500,
        system=SYSTEM_PROMPT, messages=session["history"][-10:],
    )
    reply = resp.content[0].text
    session["history"].append({"role": "assistant", "content": reply})
    if len(session["history"]) > 30:
        session["history"] = session["history"][-20:]
    return reply

# ─────────────────────────────────────────────────
#  BROADCAST
# ─────────────────────────────────────────────────
def broadcast_worker(canal, template, destinatarios, owner):
    total = len(destinatarios)
    ok = fail = 0
    DELAY = 0.5  # Infobip es más rápido, menos delay necesario

    def notify(msg):
        try:
            twilio.messages.create(from_=TWILIO_WHATSAPP_FROM, to=owner, body=msg)
        except: pass

    notify(f"Iniciando envio *{canal.upper()}* via Infobip a {total} contactos...")

    for i, r in enumerate(destinatarios):
        cel = limpiar_cel(r.get("Celular",""))
        if not cel:
            fail += 1
            continue
        msg = personalizar(template, r)
        if canal == "whatsapp":
            exito = enviar_whatsapp_infobip(cel, msg)
        elif canal == "sms":
            exito = enviar_sms_infobip(cel, msg)
        else:
            exito = False
        ok   += 1 if exito else 0
        fail += 0 if exito else 1
        if (i + 1) % 50 == 0:
            notify(f"Progreso: {i+1}/{total} — OK:{ok} Error:{fail}")
        time.sleep(DELAY)

    notify(f"*Envio completado*\nCanal: {canal.upper()}\nPlataforma: Infobip\nTotal: {total}\nExitosos: {ok}\nFallidos: {fail}")

def iniciar_broadcast(canal, mensaje, destinatarios, owner):
    t = threading.Thread(target=broadcast_worker, args=(canal, mensaje, destinatarios, owner), daemon=True)
    t.start()

# ─────────────────────────────────────────────────
#  PARSER DE COMANDOS
# ─────────────────────────────────────────────────
def detectar_broadcast(msg):
    txt = msg.strip().lower()
    if "sms" in txt:
        canal = "sms"
    elif "whatsapp" in txt or " wa " in txt:
        canal = "whatsapp"
    else:
        return None
    if not (txt.startswith("enviar") or txt.startswith("mandar")):
        return None
    if ":" not in msg:
        return None
    base = "bd2" if "bd2" in txt else "bd1"
    mensaje = msg.split(":", 1)[1].strip()
    if not mensaje:
        return None
    return canal, base, mensaje

# ─────────────────────────────────────────────────
#  PROCESADOR PRINCIPAL
# ─────────────────────────────────────────────────
def procesar(msg, sender):
    session = get_session(sender)

    if session.get("pending"):
        p = session["pending"]
        if norm(msg) in ["si","sí","yes","confirmar","confirmo","ok","dale","enviar","listo"]:
            session["pending"] = None
            iniciar_broadcast(p["canal"], p["mensaje"], p["destinatarios"], sender)
            return (
                f"Envio iniciado via *Infobip*\n"
                f"Canal: *{p['canal'].upper()}*\n"
                f"Base: *{p['base'].upper()}*\n"
                f"Contactos: *{len(p['destinatarios'])}*\n\n"
                f"Te reportare el progreso cada 50 envios."
            )
        elif norm(msg) in ["no","cancelar","cancel"]:
            session["pending"] = None
            return "Envio cancelado."
        else:
            return f"Responde *Si* para confirmar o *No* para cancelar el envio de *{p['canal'].upper()}* a *{len(p['destinatarios'])}* contactos."

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
            f"Canal: *{canal.upper()}* via Infobip\n"
            f"Base: *{nombre_bd}*\n"
            f"Destinatarios: *{len(dests)} contactos*\n\n"
            f"Vista previa:\n_{preview}_\n\n"
            f"Variables: {{nombre}}, {{apellido}}, {{cedula}}, {{programa}}\n\n"
            f"Confirmas? Responde *Si* o *No*"
        )

    found1 = search(msg, DB1, IDX1, max_r=15)
    found2 = search(msg, DB2, IDX2, max_r=10)
    stat_kw = ["cuantos","total","resumen","estadistica","genero","mujeres","hombres","programa"]
    c1 = [] if (any(w in norm(msg) for w in stat_kw) and len(found1) > 50) else found1
    return ask_claude(session, msg, c1, found2)

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
        "bd1": STATS1["total"],
        "bd2": STATS2["total"],
        "infobip": bool(INFOBIP_API_KEY),
    }, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
