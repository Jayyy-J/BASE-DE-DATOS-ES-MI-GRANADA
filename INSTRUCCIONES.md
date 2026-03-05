# 🤖 Agente WhatsApp — Corporación Social Es Mi Granada

Bot de WhatsApp con IA para consultar la base de datos de beneficiarios.
Funciona con **Twilio + Claude (Anthropic) + Railway (servidor gratis)**.

---

## 📋 Lo que necesitas (todo gratuito para empezar)

| Servicio | Para qué | Costo |
|---|---|---|
| **Twilio** | Conectar WhatsApp | Gratis (sandbox) |
| **Anthropic** | Inteligencia artificial | ~$0.01 por consulta |
| **Railway** | Servidor en la nube | Gratis 5$/mes crédito |
| **GitHub** | Subir el código | Gratis |

---

## 🚀 PASO 1 — Crear cuenta en Twilio

1. Ve a **https://www.twilio.com** → clic en **"Sign up"**
2. Confirma tu correo y número de teléfono
3. En el dashboard busca **"WhatsApp Sandbox"**:
   - Menú izquierdo → **Messaging** → **Try it out** → **Send a WhatsApp message**
4. Verás un número de Twilio (ej: `+1 415 523 8886`) y una palabra clave (ej: `join bright-forest`)
5. **Desde tu WhatsApp** envía ese mensaje al número de Twilio para activar el sandbox
6. Guarda tu **Account SID** y **Auth Token** del dashboard principal

---

## 🔑 PASO 2 — Obtener clave de Anthropic (Claude)

1. Ve a **https://console.anthropic.com**
2. Crea una cuenta (puedes entrar con Google)
3. Ve a **Settings → API Keys** → **"Create Key"**
4. Copia la clave (empieza con `sk-ant-...`)
5. Recarga tu cuenta con $5 USD mínimo (en **Billing**) → alcanza para miles de consultas

---

## 📁 PASO 3 — Subir el código a GitHub

1. Crea cuenta en **https://github.com** si no tienes
2. Crea un **nuevo repositorio** privado (ej: `agente-granada`)
3. Sube todos estos archivos al repositorio:
   - `app.py`
   - `database.json`
   - `requirements.txt`
   - `Procfile`
   - `.gitignore`
   - (NO subas `.env` — contiene claves secretas)

**Opción fácil sin terminal** — usa la interfaz web de GitHub:
- En tu repo → **"Add file"** → **"Upload files"** → arrastra todos los archivos

---

## ☁️ PASO 4 — Desplegar en Railway (servidor gratis)

1. Ve a **https://railway.app** → entra con tu cuenta de GitHub
2. **"New Project"** → **"Deploy from GitHub repo"**
3. Selecciona tu repositorio `agente-granada`
4. Railway detecta automáticamente el `Procfile` y despliega

### Configurar variables de entorno en Railway:
- En tu proyecto Railway → pestaña **"Variables"**
- Agrega estas tres variables:

```
ANTHROPIC_API_KEY = sk-ant-TU_CLAVE_AQUI
TWILIO_AUTH_TOKEN = TU_AUTH_TOKEN_AQUI
PORT              = 5000
```

5. Railway te dará una URL pública, algo como:
   `https://agente-granada-production.up.railway.app`

---

## 📱 PASO 5 — Conectar Twilio con tu servidor

1. En el dashboard de Twilio → **Messaging** → **WhatsApp Sandbox Settings**
2. En el campo **"When a message comes in"** pega tu URL + `/webhook`:
   ```
   https://agente-granada-production.up.railway.app/webhook
   ```
3. Método: **HTTP POST**
4. Guarda los cambios

---

## ✅ PASO 6 — ¡Probar!

Desde el WhatsApp que activaste en el sandbox, envía mensajes como:

- `¿Cuántas personas hay registradas?`
- `Busca a María García`
- `¿Cuántos hay en el barrio Belén?`
- `Dame los datos de la cédula 40413339`
- `¿Cuántas mujeres hay?`
- `Resumen de la base de datos`

---

## 💬 Ejemplos de consultas que responde el bot

```
Tú:  Busca a Juan Pérez
Bot: ✅ Se encontraron 2 registros:
     1. JUAN PÉREZ RODRÍGUEZ
        🪪 Cédula: 12345678
        📱 Cel: 3101234567
        📍 Barrio: VILLAS DE GRANADA

Tú:  ¿Cuántas mujeres hay registradas?
Bot: ♀️ Hay 2,456 mujeres registradas (24.4% del total de 10,078 registros)

Tú:  ¿Cuántos hay en Villas de Granada?
Bot: 📍 Barrio VILLAS DE GRANADA: 174 registros
     ♀ Mujeres: 98 | ♂ Hombres: 22
     Primeros 5: ...
```

---

## 🔧 Solución de problemas

| Problema | Solución |
|---|---|
| El bot no responde | Verifica que la URL en Twilio termina en `/webhook` |
| Error de API | Revisa que `ANTHROPIC_API_KEY` está bien en Railway Variables |
| "Join" no funciona | Envía exactamente el mensaje que indica Twilio (ej: `join bright-forest`) |
| Railway no despliega | Asegúrate de que `database.json` está subido al repo de GitHub |

---

## 📞 Para producción (número propio de WhatsApp)

Cuando quieras usar tu propio número de WhatsApp (sin sandbox):
1. Aplica a **WhatsApp Business API** en Twilio → **Senders** → **WhatsApp**
2. El proceso tarda ~2 días y requiere verificación de negocio en Meta
3. El costo es ~$0.005 por mensaje

---

## 📊 Costos estimados de operación mensual

| Volumen | Anthropic | Twilio | Railway | **Total** |
|---|---|---|---|---|
| 100 consultas/mes | ~$0.10 | $0 | $0 | **~$0.10** |
| 1,000 consultas/mes | ~$1.00 | $0 | $0 | **~$1.00** |
| 5,000 consultas/mes | ~$5.00 | ~$2 | $5 | **~$12** |

---

*Desarrollado para Corporación Social "Es Mi Granada" — Granada, Meta, Colombia*
