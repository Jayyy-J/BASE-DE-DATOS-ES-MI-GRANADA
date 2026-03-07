"""
Agente Es Mi Granada
====================
✅ Control via Telegram (gratis)
✅ Envíos masivos WhatsApp via Infobip
✅ Consultas IA a BD1 y BD2
"""

import os, json, re, time, threading, unicodedata
import urllib.request, urllib.error
from flask import Flask, request, jsonify
from anthropic import Anthropic
from collections import Counter

# ─────────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
INFOBIP_API_KEY    = os.environ.get("INFOBIP_API_KEY", "")
INFOBIP_BASE_URL   = os.environ.get("INFOBIP_BASE_URL", "")
INFOBIP_WA_SENDER  = os.environ.get("INFOBIP_WA_SENDER", "")
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN", "")

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
#  TELEGRAM
# ─────────────────────────────────────────────────
def telegram_send(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f"Telegram error: {e}")

def set_telegram_webhook(public_url):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
        payload = json.dumps({"url": f"{public_url}/webhook-telegram"}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            print(f"✅ Telegram webhook: {result}")
    except Exception as e:
        print(f"❌ Telegram webhook error: {e}")

# ─────────────────────────────────────────────────
#  INFOBIP — ENVÍO WHATSAPP
# ─────────────────────────────────────────────────
def enviar_whatsapp(cel, msg):
    try:
        to = f"57{cel}"
        url = f"https://{INFOBIP_BASE_URL}/whatsapp/1/message/text"
        payload = json.dumps({
            "from": INFOBIP_WA_SENDER,
            "to": to,
            "messageType": "TEXT",
            "text": {"body": msg}
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"App {INFOBIP_API_KEY}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 300
    except Exception as e:
        print(f"WA error {cel}: {e}")
        return False

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

def get_session(chat_id):
    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = {"history": [], "pending": None}
    return SESSIONS[chat_id]

# ─────────────────────────────────────────────────
#  CLAUDE IA
# ─────────────────────────────────────────────────
claude = Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = f"""Eres el asistente privado de Yider Torres, fundador de la Corporacion Social "Es Mi Granada" (Granada, Meta, Colombia).

BASE 1 - Beneficiarios generales: {STATS1['total']:,} registros | {STATS1['withPhone']:,} con celular
BASE 2 - Programas: {STATS2['total']:,} registros | Programas: {list(STATS2['programas'].keys())}

COMANDOS DE ENVIO MASIVO:
- "Enviar WhatsApp bd1: mensaje" → envia a todos en BD1
- "Enviar WhatsApp bd2: mensaje" → envia a todos en BD2
- Variables: {{nombre}}, {{apellido}}, {{cedula}}, {{barrio}}, {{programa}}

INSTRUCCIONES:
- Saluda a Yider por nombre cuando salude.
- Entrega todos los datos sin restricciones.
- Responde en espanol, maximo 300 palabras.
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
def broadcast_worker(template, destinatarios, chat_id):
    total = len(destinatarios)
    ok = fail = 0

    def notify(msg):
        telegram_send(chat_id, msg)

    notify(f"🚀 Iniciando envio WhatsApp a *{total}* contactos...")

    for i, r in enumerate(destinatarios):
        cel = limpiar_cel(r.get("Celular",""))
        if not cel:
            fail += 1
            continue
        msg = personalizar(template, r)
        exito = enviar_whatsapp(cel, msg)
        ok   += 1 if exito else 0
        fail += 0 if exito else 1
        if (i + 1) % 50 == 0:
            notify(f"📊 Progreso: {i+1}/{total} — ✅{ok} ❌{fail}")
        time.sleep(0.5)

    notify(f"✅ *Envio completado*\nTotal: {total}\nExitosos: {ok}\nFallidos: {fail}")

def iniciar_broadcast(template, destinatarios, chat_id):
    t = threading.Thread(target=broadcast_worker, args=(template, destinatarios, chat_id), daemon=True)
    t.start()

# ─────────────────────────────────────────────────
#  PARSER DE COMANDOS
# ─────────────────────────────────────────────────
def detectar_broadcast(msg):
    txt = msg.strip().lower()
    if "whatsapp" not in txt and " wa " not in txt:
        return None
    if not (txt.startswith("enviar") or txt.startswith("mandar")):
        return None
    if ":" not in msg:
        return None
    base = "bd2" if "bd2" in txt else "bd1"
    mensaje = msg.split(":", 1)[1].strip()
    if not mensaje:
        return None
    return base, mensaje

# ─────────────────────────────────────────────────
#  PROCESADOR PRINCIPAL
# ─────────────────────────────────────────────────
def procesar(msg, chat_id):
    session = get_session(chat_id)

    if session.get("pending"):
        p = session["pending"]
        if norm(msg) in ["si","sí","yes","confirmar","confirmo","ok","dale","enviar","listo"]:
            session["pending"] = None
            iniciar_broadcast(p["mensaje"], p["destinatarios"], chat_id)
            return (
                f"✅ Envio iniciado\n"
                f"Canal: *WhatsApp*\n"
                f"Base: *{p['base'].upper()}*\n"
                f"Contactos: *{len(p['destinatarios'])}*\n\n"
                f"Te reportare el progreso cada 50 envios."
            )
        elif norm(msg) in ["no","cancelar","cancel"]:
            session["pending"] = None
            return "❌ Envio cancelado."
        else:
            return f"Responde *Si* para confirmar o *No* para cancelar el envio a *{len(p['destinatarios'])}* contactos."

    resultado = detectar_broadcast(msg)
    if resultado:
        base, template = resultado
        db_target = DB2 if base == "bd2" else DB1
        dests = [r for r in db_target if r.get("Celular","").strip()]
        if not dests:
            return f"No hay contactos con celular en {base.upper()}."
        session["pending"] = {"base": base, "mensaje": template, "destinatarios": dests}
        preview = personalizar(template, dests[0])
        nombre_bd = "Programas Corporacion (BD2)" if base == "bd2" else "Beneficiarios Generales (BD1)"
        return (
            f"📋 *Resumen del envio:*\n"
            f"Canal: *WhatsApp*\n"
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

@app.route("/webhook-telegram", methods=["POST"])
def webhook_telegram():
    try:
        data = request.get_json(force=True)
        message = data.get("message") or data.get("edited_message")
        if not message:
            return jsonify({"ok": True})
        chat_id = str(message["chat"]["id"])
        body = message.get("text", "").strip()
        if not body:
            return jsonify({"ok": True})
        print(f"MSG [{chat_id}]: {body}")
        reply = procesar(body, chat_id)
        telegram_send(chat_id, reply)
    except Exception as e:
        print(f"Webhook error: {e}")
    return jsonify({"ok": True})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "bd1": STATS1["total"],
        "bd2": STATS2["total"],
        "infobip": bool(INFOBIP_API_KEY),
        "telegram": bool(TELEGRAM_TOKEN),
    }), 200

@app.route("/setup", methods=["GET"])
def setup():
    """Configura el webhook de Telegram automaticamente."""
    public_url = os.environ.get("PUBLIC_URL", "").rstrip("/")
    if not public_url:
        return jsonify({"error": "PUBLIC_URL no configurada"}), 400
    set_telegram_webhook(public_url)
    return jsonify({"status": "webhook configurado", "url": f"{public_url}/webhook-telegram"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
