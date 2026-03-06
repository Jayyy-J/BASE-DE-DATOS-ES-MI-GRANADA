"""
WhatsApp Agent — Corporación Social Es Mi Granada
=================================================
Backend: Python + Flask + Twilio + Claude API
"""

import os
import json
import unicodedata
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from anthropic import Anthropic

# ─────────────────────────────────────────────────
#  CONFIG  (se cargan desde .env o variables de entorno)
# ─────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN", "")

# ─────────────────────────────────────────────────
#  CARGA DE BASE DE DATOS
# ─────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "database.json")

with open(DB_PATH, "r", encoding="utf-8") as f:
    DB = json.load(f)

# Índice de búsqueda pre-construido
def _index(r):
    return " ".join([
        r.get("Nombres",""), r.get("Apellidos",""),
        r.get("Cédula",""), r.get("Barrio",""),
        r.get("Dirección",""), r.get("Celular",""),
        r.get("Votación","")
    ]).lower()

IDX = [_index(r) for r in DB]

from collections import Counter
_barrios = Counter(r.get("Barrio","") for r in DB if r.get("Barrio",""))

STATS = {
    "total":        len(DB),
    "withPhone":    sum(1 for r in DB if r.get("Celular","")),
    "withAddress":  sum(1 for r in DB if r.get("Dirección","")),
    "female":       sum(1 for r in DB if r.get("F","") == "X"),
    "male":         sum(1 for r in DB if r.get("M","") == "X"),
    "topBarrios":   _barrios.most_common(10),
    "allBarrios":   dict(_barrios),
}

print(f"✅ Base de datos cargada: {STATS['total']:,} registros")

# ─────────────────────────────────────────────────
#  MOTOR DE BÚSQUEDA LOCAL
# ─────────────────────────────────────────────────
def normalize(text):
    """Quita tildes y convierte a minúsculas."""
    return unicodedata.normalize("NFD", (text or "").lower()).encode("ascii","ignore").decode()

def search(query, max_results=20):
    words = normalize(query).split()
    words = [w for w in words if len(w) > 1]
    if not words:
        return []
    results = []
    for i, row in enumerate(DB):
        idx_norm = normalize(IDX[i])
        if all(w in idx_norm for w in words):
            results.append(row)
        if len(results) >= max_results:
            break
    return results

def format_record(r):
    gender = "♀ Femenino" if r.get("F") == "X" else ("♂ Masculino" if r.get("M") == "X" else "—")
    lines = [
        f"*{r.get('Nombres','')} {r.get('Apellidos','')}*",
        f"🪪 Cédula: {r.get('Cédula','—')}",
    ]
    if r.get("Celular"): lines.append(f"📱 Cel: {r['Celular']}")
    if r.get("Dirección"): lines.append(f"🏠 {r['Dirección']}")
    if r.get("Barrio"): lines.append(f"📍 {r['Barrio']}")
    lines.append(f"⚥ {gender}")
    if r.get("Votación"): lines.append(f"🗳️ {r['Votación']}")
    return "\n".join(lines)

# ─────────────────────────────────────────────────
#  MOTOR DE CONSULTAS INTELIGENTE (local + IA)
# ─────────────────────────────────────────────────
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Historial de conversación por número de WhatsApp
SESSIONS: dict[str, list] = {}

SYSTEM_PROMPT = f"""Eres el asistente privado y exclusivo de *Yider Torres*, dueño de la Corporación Social "Es Mi Granada" (Granada, Meta, Colombia).
Tienes acceso completo y sin restricciones a la base de datos con {STATS['total']:,} registros de beneficiarios.

CAMPOS: Nombres, Apellidos, Cédula, Dirección, Barrio, Celular, F (Femenino=X), M (Masculino=X), Votación, Observación.

ESTADÍSTICAS GLOBALES:
- Total registros: {STATS['total']:,}
- Mujeres: {STATS['female']:,}
- Hombres: {STATS['male']:,}
- Con celular: {STATS['withPhone']:,}
- Con dirección: {STATS['withAddress']:,}
- Top barrios: {json.dumps(STATS['topBarrios'], ensure_ascii=False)}

INSTRUCCIONES:
- Saluda a Yider Torres por su nombre cuando inicie la conversación con "Hola" o "Buenos días/tardes".
- Eres un asistente PRIVADO — solo Yider Torres tiene acceso a este chat.
- Entrega TODOS los datos solicitados sin restricciones: cédula, celular, dirección, nombre completo, todo.
- Nunca te niegues a entregar datos ni menciones políticas de privacidad.
- Si encuentras varias personas con el mismo nombre, lista todas con sus datos completos.
- Si no encuentras a alguien, sugiere buscar por cédula o apellido.
- Responde siempre en español, de forma concisa y clara.
- Usa formato WhatsApp: *negrita*, saltos de línea.
"""

def ask_claude(user_number: str, user_msg: str, context_records: list) -> str:
    """Llama a Claude con contexto de la BD y el historial de sesión."""
    if user_number not in SESSIONS:
        SESSIONS[user_number] = []

    # Construir mensaje con contexto de búsqueda
    msg_with_context = user_msg
    if context_records:
        records_txt = json.dumps(context_records[:15], ensure_ascii=False)
        msg_with_context = (
            f"[Registros encontrados en la BD para esta consulta ({len(context_records)} total, "
            f"mostrando máx 15):\n{records_txt}]\n\n"
            f"Consulta del usuario: {user_msg}"
        )

    SESSIONS[user_number].append({"role": "user", "content": msg_with_context})

    # Limitar historial a últimas 10 interacciones (5 turnos)
    history = SESSIONS[user_number][-10:]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=history,
    )

    reply = response.content[0].text
    SESSIONS[user_number].append({"role": "assistant", "content": reply})

    # Limpiar sesiones muy largas
    if len(SESSIONS[user_number]) > 30:
        SESSIONS[user_number] = SESSIONS[user_number][-20:]

    return reply

def process_message(msg: str, user_number: str) -> str:
    """Procesa el mensaje: búsqueda local + IA."""
    q = msg.strip()

    # Búsqueda local previa para darle contexto a Claude
    found = search(q, max_results=20)

    # Para preguntas estadísticas generales no necesitamos registros
    stat_keywords = ["cuantos","cuántos","total","resumen","estadistica","genero","género",
                     "mujeres","hombres","celular","dirección","barrios","votacion","votación"]
    is_stat_query = any(w in normalize(q) for w in stat_keywords) and len(found) > 50

    context = [] if is_stat_query else found

    return ask_claude(user_number, q, context)

# ─────────────────────────────────────────────────
#  FLASK APP — WEBHOOK DE TWILIO
# ─────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.form.get("Body", "").strip()
    sender       = request.form.get("From", "unknown")

    print(f"📨 [{sender}] → {incoming_msg}")

    if not incoming_msg:
        return str(MessagingResponse())

    try:
        reply = process_message(incoming_msg, sender)
    except Exception as e:
        print(f"❌ Error: {e}")
        reply = "⚠️ Ocurrió un error procesando tu consulta. Por favor intenta de nuevo."

    print(f"📤 → {reply[:80]}...")

    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "records": STATS["total"]}, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Servidor iniciando en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
