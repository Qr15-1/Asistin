import telebot
import schedule
import time
import threading
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# CONFIGURACION
def cargar_token():
    # EasyPanel / Docker: leer desde variable de entorno
    token_env = os.environ.get('BOT_TOKEN')
    if token_env:
        return token_env
    # Fallback: archivo .env local
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if line.startswith('BOT_TOKEN='):
                    return line.strip().split('=')[1]
    return 'TU_TOKEN_AQUI'

TOKEN = cargar_token()
bot = telebot.TeleBot(TOKEN)
ID_GRUPO_OFICIAL = '-1005138078545'

USUARIOS = {
    "R": { "nombre": "Rebeca", "alias": "@Rebecaarh", "id": 5937374472 },
    "F": { "nombre": "Franklin", "alias": "@Franklinjlopezr", "id": 975494788 },
    "Jefe": { "nombre": "Jonathan", "alias": "@JonathanSchemel", "id": 515198765 },
    "Roger": { "nombre": "Roger", "id": 5499547223 }
}

ADMIN_IDS = [515198765, 5499547223]

# CALENDARIOS
# Calendario Semanal (Dia -> Responsable -> Marcas)
CALENDARIO_SEMANAL = {
    "Monday": { "R": ["Emiliarte",], "F": ["Agro PDK"] },
    "Tuesday": { "R": ["Luva"], "F": ["+58 Shop", "La Zapeteria"] },
    "Wednesday": { "R": ["Altamar"], "F": [] },
    "Thursday": { "R": ["Dra. K Beauty"], "F": ["Bungerz"] },
    "Friday": { "R": ["La Cava", "Chocology"], "F": ["La Cascada"] }
}

# Calendario Mensual (Dia del mes DD -> Marcas)
DIAS_MENSUALES = {
    "03": ["Dra. K Beauty", "Agro PDK"],
    "06": ["La Zapeteria"],
    "09": ["Bungerz"],
    "10": ["Emiliarte"],
    "12": ["La Cava", "Emiliarte", "La Cascada"],
    "13": ["Luva", "Altamar"],
    "15": ["Chaofan"],

    "18": ["+58 Shop"]
}

# MEMORIA (bot_state.json)
STATE_PATH = Path(__file__).with_name("bot_state.json")
DATA_LOCK = threading.Lock()

def cargar_datos():
    base = {
        "reportes_hoy": {}, "deudas": {"R": [], "F": []}, "entregados": {"R": [], "F": []}, 
        "inactivas": {"R": [], "F": []}, "historial_mensual": [], "archivo_historico": {},
        "ultimo_envio": "", "semana_id": datetime.now().strftime("%W"), "mes_id": datetime.now().strftime("%m"),
        "tipos_semanales": {}
    }
    with DATA_LOCK:
        if not STATE_PATH.exists(): return base
        try:
            with open(STATE_PATH, "r") as f:
                datos = json.load(f)
                for k in base: datos.setdefault(k, base[k])
                return datos
        except: return base

def guardar_datos(datos):
    with DATA_LOCK:
        try:
            with open(STATE_PATH, "w") as f: 
                json.dump(datos, f, indent=2)
        except: pass

# UTILIDADES
def obtener_hora_actual(): return datetime.now().strftime("%I:%M %p")

def obtener_rango_semana():
    hoy = datetime.now()
    l = hoy - timedelta(days=hoy.weekday()); v = l + timedelta(days=4)
    return f"DEL {l.strftime('%d/%m')} AL {v.strftime('%d/%m')}"

def gestionar_tiempos(datos):
    hoy = datetime.now(); sem_act = hoy.strftime("%W"); mes_act = hoy.strftime("%m"); anio_act = hoy.strftime("%Y")
    if mes_act != datos["mes_id"]:
        etiqueta = f"{datos['mes_id']}-{anio_act}"
        datos["archivo_historico"][etiqueta] = list(datos["historial_mensual"])
        datos["historial_mensual"] = []; datos["mes_id"] = mes_act
    if sem_act != datos["semana_id"]:
        datos["historial_mensual"].append({"rango": obtener_rango_semana(), "entregados": datos["entregados"], "deudas": datos["deudas"]})
        datos.update({"entregados": {"R": [], "F": []}, "deudas": {"R": [], "F": []}, "inactivas": {"R": [], "F": []}, "reportes_hoy": {}, "tipos_semanales": {}, "semana_id": sem_act})
    guardar_datos(datos)

def obtener_responsable(marca):
    for dia, asignaciones in CALENDARIO_SEMANAL.items():
        for resp, lista_marcas in asignaciones.items():
            if marca in lista_marcas: return resp
    return "F"

# MENUS
def menu_inicial(inicial, marca):
    m = InlineKeyboardMarkup(row_width=1)
    m.add(InlineKeyboardButton("Ya lo envie", callback_data=f"si_{inicial}_{marca}"),
          InlineKeyboardButton("Tengo retraso", callback_data=f"re_menu_{inicial}_{marca}"),
          InlineKeyboardButton("Marca no disponible", callback_data=f"off_{inicial}_{marca}"))
    return m

def menu_trabajando(inicial, marca):
    m = InlineKeyboardMarkup(row_width=1)
    m.add(InlineKeyboardButton("Hecho: Ya lo envie", callback_data=f"si_{inicial}_{marca}"),
          InlineKeyboardButton("Cambio: No podre hoy", callback_data=f"noh_{inicial}_{marca}"))
    return m

# REPORTES (TEXTOS)
def resumen_semanal_texto(datos):
    res = f"BALANCE SEMANAL DE RENDIMIENTO\n"
    res += f"PERIODO: {obtener_rango_semana()}\n"
    res += "----------------------------------\n"
    for i in ["R", "F"]:
        res += f"\nRESPONSABLE: {USUARIOS[i]['nombre']}\n"
        ent_sem = []; ent_men = []
        pen_sem = []; pen_men = []
        for m in datos['entregados'][i]:
            tipo = datos.get("tipos_semanales", {}).get(m, "SEMANAL")
            if tipo == "MENSUAL": ent_men.append(m)
            else: ent_sem.append(m)
        for m in datos['deudas'][i]:
            tipo = datos.get("tipos_semanales", {}).get(m, "SEMANAL")
            if tipo == "MENSUAL": pen_men.append(m)
            else: pen_sem.append(m)
        res += f"ENTREGADOS SEMANALES: {', '.join(ent_sem) if ent_sem else 'Ninguno'}\n"
        res += f"ENTREGADOS MENSUALES: {', '.join(ent_men) if ent_men else 'Ninguno'}\n"
        res += f"PENDIENTES SEMANALES: {', '.join(pen_sem) if pen_sem else 'Ninguno'}\n"
        res += f"PENDIENTES MENSUALES: {', '.join(pen_men) if pen_men else 'Ninguno'}\n"
    res += "\n----------------------------------\n"
    res += f"OBSERVADOR: {USUARIOS['Jefe']['alias']}"
    return res

# LOGICA DE ENVIO SEGUN CALENDARIO
def enviar_recordatorio_diario(forzar=False):
    datos = cargar_datos(); gestionar_tiempos(datos)
    ahora = datetime.now(); hoy_str = ahora.strftime("%Y-%m-%d"); dia_numero = ahora.strftime("%d")
    if not forzar and datos.get("ultimo_envio") == hoy_str: return
    dia_en = ahora.strftime("%A")
    bot.send_message(ID_GRUPO_OFICIAL, f"--- INICIO DE JORNADA: {ahora.strftime('%d/%m')} ---")
    datos["reportes_hoy"] = {}
    if dia_en in CALENDARIO_SEMANAL:
        for resp, marcas in CALENDARIO_SEMANAL[dia_en].items():
            for m in marcas:
                datos["reportes_hoy"][m] = {"status": "POR ENTREGA", "user": resp, "tipo": "SEMANAL"}
    if dia_numero in DIAS_MENSUALES:
        for m_mensual in DIAS_MENSUALES[dia_numero]:
            resp = obtener_responsable(m_mensual)
            datos["reportes_hoy"][m_mensual] = {"status": "POR ENTREGA", "user": resp, "tipo": "MENSUAL"}
    for m, info in datos["reportes_hoy"].items():
        resp = info["user"]; tipo = info["tipo"]
        datos.setdefault("tipos_semanales", {})[m] = tipo
        if m not in datos["deudas"][resp]: datos["deudas"][resp].append(m)
        try:
            bot.send_message(
                ID_GRUPO_OFICIAL, 
                f"Responsable: {USUARIOS[resp]['alias']}\nMarca: {m} (Informe {tipo})\nEstatus: POR ENTREGA", 
                reply_markup=menu_inicial(resp, m)
            )
        except Exception as e:
            print(f"Error al enviar menu {m}: {e}")
    for i in ["R", "F"]:
        marcas_de_hoy = [m for m, info in datos["reportes_hoy"].items() if info["user"] == i]
        deudas_viejas = [m for m in datos["deudas"][i] if m not in marcas_de_hoy]
        if deudas_viejas:
            try: bot.send_message(ID_GRUPO_OFICIAL, f"----------------------------------\nMARCAS PENDIENTES DE DIAS ANTERIORES\nRESPONSABLE: {USUARIOS[i]['alias']}\n----------------------------------")
            except: pass
            for m_deuda in deudas_viejas:
                tipo_d = datos.get("tipos_semanales", {}).get(m_deuda, "SEMANAL")
                try: bot.send_message(ID_GRUPO_OFICIAL, f"Marca: {m_deuda} (Informe {tipo_d})\nEstatus: POR ENTREGA", reply_markup=menu_inicial(i, m_deuda))
                except: pass
    datos["ultimo_envio"] = hoy_str; guardar_datos(datos)

# COMANDOS
@bot.message_handler(commands=['chatid'])
def enviar_chat_id(message):
    bot.reply_to(message, f"El ID de este chat es: {message.chat.id}")

@bot.message_handler(func=lambda message: True)
def manejar_comandos(message):
    if message.from_user.id not in ADMIN_IDS: return
    datos = cargar_datos(); gestionar_tiempos(datos); text = message.text.lower()
    if "/fechas_semanal" in text:
        DIAS_ES = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles", "Thursday": "Jueves", "Friday": "Viernes"}
        res = "CALENDARIO SEMANAL DE ENTREGAS\n"
        res += "----------------------------------\n"
        for dia_en, asignaciones in CALENDARIO_SEMANAL.items():
            res += f"\n {DIAS_ES.get(dia_en, dia_en)}:\n"
            for resp, marcas in asignaciones.items():
                if marcas:
                    nombre = USUARIOS[resp]['nombre']
                    res += f"  · {nombre}: {', '.join(marcas)}\n"
        bot.send_message(message.chat.id, res)
    elif "/fechas_mensual" in text:
        res = "CALENDARIO MENSUAL DE ENTREGAS\n"
        res += "----------------------------------\n"
        for dia, marcas in sorted(DIAS_MENSUALES.items()):
            marcas_con_resp = []
            for m in marcas:
                resp = obtener_responsable(m)
                nombre = USUARIOS[resp]['nombre']
                marcas_con_resp.append(f"{m} ({nombre})")
            res += f"\n Dia {dia}: {', '.join(marcas_con_resp)}\n"
        bot.send_message(message.chat.id, res)
    elif "/status" in text and "semanal" not in text and "mensual" not in text and "deuda" not in text:
        res = "ESTATUS ACTUAL DE HOY:\n"
        res += "----------------------------------\n"
        for m, info in datos["reportes_hoy"].items():
            tipo = info.get('tipo', 'SEMANAL')
            res += f"- {m} ({tipo}): {info['status']}\n"
        bot.send_message(message.chat.id, res if datos["reportes_hoy"] else "Sin actividad hoy.")
    elif "/deuda" in text:
        hay_deuda = False
        for i in ["R", "F"]:
            if datos["deudas"][i]:
                hay_deuda = True
                bot.send_message(message.chat.id, f"PENDIENTES DE {USUARIOS[i]['nombre']}:")
                for m_deuda in datos["deudas"][i]:
                    tipo_d = datos.get("tipos_semanales", {}).get(m_deuda, "SEMANAL")
                    bot.send_message(message.chat.id, f"Marca: {m_deuda} ({tipo_d})", reply_markup=menu_inicial(i, m_deuda))
        if not hay_deuda:
            bot.send_message(message.chat.id, "No existen deudas pendientes.")
    elif "semanal" in text:
        bot.send_message(message.chat.id, resumen_semanal_texto(datos))
    elif "mensual" in text:
        if not datos["historial_mensual"]:
            bot.send_message(message.chat.id, "RESUMEN MENSUAL: Aun no hay semanas cerradas en el historial.")
        else:
            res = "RESUMEN MENSUAL (SEMANAS CERRADAS):\n\n"
            for s in datos["historial_mensual"]: 
                res += f"Semana {s['rango']}: {len(s['entregados']['R'])+len(s['entregados']['F'])} OK\n"
            bot.send_message(message.chat.id, res)
    elif "/ver_mes" in text:
        partes = text.split()
        if len(partes) < 2: return
        archivo = datos["archivo_historico"].get(partes[1])
        if not archivo: bot.send_message(message.chat.id, "No hay datos para ese mes."); return
        res = f"ARCHIVO MES: {partes[1]}\n"
        for i, sem in enumerate(archivo): res += f"Semana {i+1}: R({len(sem['entregados']['R'])}) F({len(sem['entregados']['F'])}) OK\n"
        bot.send_message(message.chat.id, res)
    elif "/test_diario" in text: enviar_recordatorio_diario(forzar=True)

# CALLBACKS (BOTONES)
@bot.callback_query_handler(func=lambda call: True)
def manejar_botones(call):
    datos = cargar_datos(); data = call.data.split("_")
    accion, inicial, marca = data[0], data[-2], data[-1]
    if call.from_user.id != USUARIOS[inicial]["id"]:
        bot.answer_callback_query(call.id, "Acceso Denegado", show_alert=True); return
    h = obtener_hora_actual(); j = USUARIOS['Jefe']['alias']; n = USUARIOS[inicial]['nombre']
    tipo_inf = datos.get("tipos_semanales", {}).get(marca, "SEMANAL")
    if accion == "si":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        if marca in datos["reportes_hoy"]: datos["reportes_hoy"][marca]["status"] = f"ENTREGADO ({h})"
        if marca in datos["deudas"][inicial]: datos["deudas"][inicial].remove(marca)
        if marca not in datos["entregados"][inicial]: datos["entregados"][inicial].append(marca)
        bot.send_message(call.message.chat.id, f"ENTREGADO: {marca} (Informe {tipo_inf}) por {n}. CC: {j}")
    elif accion == "tra":
        if marca in datos["reportes_hoy"]: datos["reportes_hoy"][marca]["status"] = f"TRABAJANDO ({h})"
        bot.edit_message_text(f"ESTATUS: Trabajando en {marca}. Responsable: {n}", call.message.chat.id, call.message.message_id, reply_markup=menu_trabajando(inicial, marca))
    elif accion == "off":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        if marca in datos["reportes_hoy"]: datos["reportes_hoy"][marca]["status"] = f"INACTIVA ({h})"
        if marca in datos["deudas"][inicial]: datos["deudas"][inicial].remove(marca)
        bot.send_message(call.message.chat.id, f"MARCA NO DISPONIBLE: {marca}. Reportado por {n}. CC: {j}")
    elif accion == "noh":
        msg = bot.send_message(call.message.chat.id, f"Escribe motivo de retraso para {marca}:", reply_markup=ForceReply(selective=True))
        bot.register_next_step_handler(msg, procesar_justificacion, inicial, marca, call.message.message_id)
    elif accion == "re" and data[1] == "menu":
        m_re = InlineKeyboardMarkup(); m_re.add(InlineKeyboardButton("Trabajando en eso", callback_data=f"tra_{inicial}_{marca}"), InlineKeyboardButton("No podre hoy", callback_data=f"noh_{inicial}_{marca}"))
        bot.edit_message_text(f"Opciones para {marca}:", call.message.chat.id, call.message.message_id, reply_markup=m_re)
    guardar_datos(datos)

def procesar_justificacion(message, inicial, marca, original_msg_id):
    datos = cargar_datos(); h = obtener_hora_actual()
    tipo_inf = datos.get("tipos_semanales", {}).get(marca, "SEMANAL")
    bot.edit_message_reply_markup(message.chat.id, original_msg_id, reply_markup=None)
    if marca in datos["reportes_hoy"]: datos["reportes_hoy"][marca]["status"] = f"RETRASO: {message.text} ({h})"
    bot.send_message(message.chat.id, f"RETRASO: {marca} (Informe {tipo_inf}). Motivo: {message.text}. Resp: {USUARIOS[inicial]['nombre']}. CC: {USUARIOS['Jefe']['alias']}")
    guardar_datos(datos)

# MENU Y RELOJ DE ALERTAS
bot.set_my_commands([
    telebot.types.BotCommand("status", "Estatus de las entregas de hoy"),
    telebot.types.BotCommand("deuda", "Ver deudas y reportes pendientes"),
    telebot.types.BotCommand("status_semanal", "Balance de rendimiento semanal"),
    telebot.types.BotCommand("status_mensual", "Resumen de semanas cerradas"),
    telebot.types.BotCommand("fechas_semanal", "Marcas por día de la semana"),
    telebot.types.BotCommand("fechas_mensual", "Marcas por día del mes"),
    telebot.types.BotCommand("ver_mes", "Consultar historial (Ej: 03-2026)"),
    telebot.types.BotCommand("test_diario", "Ejecutar prueba de envío (Admin)")
])

def tarea_alertas():
    try:
        for m, info in cargar_datos()["reportes_hoy"].items():
            if info["status"] == "POR ENTREGA":
                try: bot.send_message(ID_GRUPO_OFICIAL, f"RECORDATORIO {USUARIOS[info['user']]['alias']}: Pendiente informe para {m}.")
                except Exception as e: print(e)
    except Exception as e: print(e)

def tarea_viernes():
    try: bot.send_message(ID_GRUPO_OFICIAL, resumen_semanal_texto(cargar_datos()))
    except Exception as e: print(e)

def reloj():
    # Horarios en UTC (Venezuela = UTC-4, se suma +4h)
    schedule.every().day.at("14:00").do(lambda: [(enviar_recordatorio_diario() if True else None)])       # 10:00 AM Venezuela
    tiempos_alerta = ["16:00", "20:00", "22:00"]                          # 12:00 / 16:00 / 18:00 Venezuela
    for t in tiempos_alerta:
        schedule.every().day.at(t).do(tarea_alertas)
    schedule.every().friday.at("21:00").do(tarea_viernes)  # 17:00 Venezuela
    while True:
        try: schedule.run_pending()
        except Exception as e: print(f"Error schedule: {e}")
        time.sleep(1)

print("BOT REPORTIN ACTIVO")
threading.Thread(target=reloj, daemon=True).start()
bot.infinity_polling(timeout=10, long_polling_timeout=5)