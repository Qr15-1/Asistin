import telebot
import schedule
import time
import threading
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# Importaciones modulares
from bot import bot
from config import TOKEN, ID_GRUPO_OFICIAL, USUARIOS, ADMIN_IDS, CALENDARIO_SEMANAL, DIAS_MENSUALES
from state_manager import cargar_datos, guardar_datos, gestionar_tiempos, obtener_responsable
from utils import obtener_hora_actual, obtener_rango_semana, es_fin_de_semana, proximo_lunes
from web_server import iniciar_servidor_web, registrar_test_callback

# HELPER DE ESTRUCTURA
def obtener_item_info(item, datos=None):
    """Normaliza cualquier elemento de deudas o entregados a tupla (marca, tipo)."""
    if isinstance(item, dict):
        return item.get("marca", ""), item.get("tipo", "SEMANAL")
    if isinstance(item, str):
        if "|" in item:
            partes = item.split("|", 1)
            return partes[0], partes[1]
        tipo = datos.get("tipos_semanales", {}).get(item, "SEMANAL") if datos else "SEMANAL"
        return item, tipo
    return str(item), "SEMANAL"

# MENUS
def menu_inicial(inicial, marca, tipo="SEMANAL"):
    m = InlineKeyboardMarkup(row_width=1)
    m.add(InlineKeyboardButton("Ya lo envie", callback_data=f"si_{inicial}_{marca}_{tipo}"),
          InlineKeyboardButton("Tengo retraso", callback_data=f"re_menu_{inicial}_{marca}_{tipo}"),
          InlineKeyboardButton("Marca no disponible", callback_data=f"off_{inicial}_{marca}_{tipo}"))
    return m

def menu_trabajando(inicial, marca, tipo="SEMANAL"):
    m = InlineKeyboardMarkup(row_width=1)
    m.add(InlineKeyboardButton("Hecho: Ya lo envie", callback_data=f"si_{inicial}_{marca}_{tipo}"),
          InlineKeyboardButton("Cambio: No podre hoy", callback_data=f"noh_{inicial}_{marca}_{tipo}"))
    return m

# REPORTES (TEXTOS)
def resumen_semanal_texto(datos):
    res = f"BALANCE SEMANAL DE RENDIMIENTO\n"
    res += f"PERIODO: {obtener_rango_semana()}\n"
    res += "----------------------------------\n"
    for i in ["R", "F", "Roger"]:
        res += f"\nRESPONSABLE: {USUARIOS[i]['nombre']}\n"
        ent_sem = []; ent_men = []
        pen_sem = []; pen_men = []
        for item in datos['entregados'].get(i, []):
            m, tipo = obtener_item_info(item, datos)
            if tipo == "MENSUAL": ent_men.append(m)
            else: ent_sem.append(m)
        for item in datos['deudas'].get(i, []):
            m, tipo = obtener_item_info(item, datos)
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

    # BLOQUEO FIN DE SEMANA: no enviar nada sábado ni domingo
    if es_fin_de_semana(ahora) and not forzar:
        return

    # Marcar como enviado antes de empezar para evitar bucles si hay error en el envío
    datos["ultimo_envio"] = hoy_str
    guardar_datos(datos)

    bot.send_message(ID_GRUPO_OFICIAL, f"--- INICIO DE JORNADA: {ahora.strftime('%d/%m')} ---")
    datos["reportes_hoy"] = {}
    marcas_desactivadas = datos.get("marcas_desactivadas", [])
    marcas_eliminadas = datos.get("marcas_eliminadas", [])
    marcas_custom_nombres = {m.get("nombre") for m in datos.get("marcas_personalizadas", []) if m.get("nombre")}

    # Marcas semanales estáticas (solo si no fueron personalizadas/editadas)
    if dia_en in CALENDARIO_SEMANAL:
        for resp, marcas in CALENDARIO_SEMANAL[dia_en].items():
            for m in marcas:
                if m not in marcas_desactivadas and m not in marcas_eliminadas and m not in marcas_custom_nombres:
                    resp_actual = obtener_responsable(m)
                    datos["reportes_hoy"][m] = {"status": "POR ENTREGA", "user": resp_actual, "tipo": "SEMANAL"}

    # Marcas dinámicas agregadas o editadas desde la web (semanales y mensuales)
    for m_custom in datos.get("marcas_personalizadas", []):
        m_nombre = m_custom.get("nombre")
        if not m_nombre or m_nombre in marcas_desactivadas or m_nombre in marcas_eliminadas:
            continue
        resp_actual = obtener_responsable(m_nombre)
        dias_sem = m_custom.get("dias_semanales", [])
        dias_mes = m_custom.get("dias_mensuales", [])

        if dia_en in dias_sem:
            datos["reportes_hoy"][m_nombre] = {"status": "POR ENTREGA", "user": resp_actual, "tipo": "SEMANAL"}
        if dia_numero in dias_mes or str(int(dia_numero)) in [str(int(x)) for x in dias_mes if x.isdigit()]:
            datos["reportes_hoy"][m_nombre] = {"status": "POR ENTREGA", "user": resp_actual, "tipo": "MENSUAL"}

    # Verificar si hoy es lunes: agregar entregas mensuales que cayeron en finde
    if dia_en == "Monday":
        sabado = ahora - timedelta(days=2)
        domingo = ahora - timedelta(days=1)
        for fecha_finde in [sabado, domingo]:
            dia_finde = fecha_finde.strftime("%d")
            if dia_finde in DIAS_MENSUALES:
                for m_mensual in DIAS_MENSUALES[dia_finde]:
                    if m_mensual not in marcas_desactivadas and m_mensual not in marcas_eliminadas and m_mensual not in marcas_custom_nombres:
                        resp = obtener_responsable(m_mensual)
                        datos["reportes_hoy"][m_mensual] = {"status": "POR ENTREGA", "user": resp, "tipo": "MENSUAL"}
            # Marcas dinámicas mensuales en finde
            for m_custom in datos.get("marcas_personalizadas", []):
                m_nombre = m_custom.get("nombre")
                if not m_nombre or m_nombre in marcas_desactivadas or m_nombre in marcas_eliminadas:
                    continue
                dias_mes = m_custom.get("dias_mensuales", [])
                if dia_finde in dias_mes or str(int(dia_finde)) in [str(int(x)) for x in dias_mes if x.isdigit()]:
                    resp = obtener_responsable(m_nombre)
                    datos["reportes_hoy"][m_nombre] = {"status": "POR ENTREGA", "user": resp, "tipo": "MENSUAL"}

    if dia_numero in DIAS_MENSUALES:
        for m_mensual in DIAS_MENSUALES[dia_numero]:
            if m_mensual not in marcas_desactivadas and m_mensual not in marcas_eliminadas and m_mensual not in marcas_custom_nombres:
                resp = obtener_responsable(m_mensual)
                datos["reportes_hoy"][m_mensual] = {"status": "POR ENTREGA", "user": resp, "tipo": "MENSUAL"}
    
    for m, info in datos["reportes_hoy"].items():
        resp = info["user"]; tipo = info["tipo"]
        datos.setdefault("tipos_semanales", {})[m] = tipo
        deuda_item = {"marca": m, "tipo": tipo}
        datos.setdefault("deudas", {}).setdefault(resp, [])
        if not any(obtener_item_info(x, datos) == (m, tipo) for x in datos["deudas"][resp]):
            datos["deudas"][resp].append(deuda_item)
        try:
            bot.send_message(
                ID_GRUPO_OFICIAL, 
                f"Responsable: {USUARIOS[resp]['alias']}\nMarca: {m} (Informe {tipo})\nEstatus: POR ENTREGA", 
                reply_markup=menu_inicial(resp, m, tipo)
            )
        except Exception as e:
            print(f"Error al enviar menu {m}: {e}")

    marcas_de_hoy = list(datos["reportes_hoy"].keys())
    for i in ["R", "F", "Roger"]:
        deudas_viejas = [x for x in datos["deudas"][i] if obtener_item_info(x, datos)[0] not in marcas_de_hoy]
        if deudas_viejas:
            try: bot.send_message(ID_GRUPO_OFICIAL, f"----------------------------------\nMARCAS PENDIENTES DE DIAS ANTERIORES\nRESPONSABLE: {USUARIOS[i]['alias']}\n----------------------------------")
            except: pass
            for item_deuda in deudas_viejas:
                m_deuda, tipo_d = obtener_item_info(item_deuda, datos)
                try: bot.send_message(ID_GRUPO_OFICIAL, f"Marca: {m_deuda} (Informe {tipo_d})\nEstatus: POR ENTREGA", reply_markup=menu_inicial(i, m_deuda, tipo_d))
                except: pass
    guardar_datos(datos)

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
        for i in ["R", "F", "Roger"]:
            if datos["deudas"][i]:
                hay_deuda = True
                bot.send_message(message.chat.id, f"PENDIENTES DE {USUARIOS[i]['nombre']}:")
                for item_deuda in datos["deudas"][i]:
                    m_deuda, tipo_d = obtener_item_info(item_deuda, datos)
                    bot.send_message(message.chat.id, f"Marca: {m_deuda} ({tipo_d})", reply_markup=menu_inicial(i, m_deuda, tipo_d))
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
                res += f"Semana {s['rango']}: {len(s['entregados']['R'])+len(s['entregados']['F'])+len(s['entregados'].get('Roger', []))} OK\n"
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
    datos = cargar_datos()
    data = call.data.split("_")
    
    # Parseo flexible para compatibilidad con botones nuevos (4+ partes) y legacy (3 partes)
    if data[0] == "re" and len(data) >= 2 and data[1] == "menu":
        accion = "re"
        inicial = data[2] if len(data) >= 4 else data[-2]
        tipo_inf = data[-1] if len(data) >= 5 else "SEMANAL"
        marca = "_".join(data[3:-1]) if len(data) >= 5 else data[-1]
    elif len(data) >= 4:
        accion = data[0]
        inicial = data[1]
        tipo_inf = data[-1]
        marca = "_".join(data[2:-1])
    else:
        accion = data[0]
        inicial = data[-2]
        marca = data[-1]
        tipo_inf = datos.get("reportes_hoy", {}).get(marca, {}).get("tipo") or datos.get("tipos_semanales", {}).get(marca, "SEMANAL")

    if call.from_user.id != USUARIOS[inicial]["id"]:
        bot.answer_callback_query(call.id, "Acceso Denegado", show_alert=True); return
    
    h = obtener_hora_actual(); j = USUARIOS['Jefe']['alias']; n = USUARIOS[inicial]['nombre']
    item_target = {"marca": marca, "tipo": tipo_inf}

    if accion == "si":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        if marca in datos["reportes_hoy"]: datos["reportes_hoy"][marca]["status"] = f"ENTREGADO ({h})"
        datos["deudas"][inicial] = [x for x in datos["deudas"][inicial] if obtener_item_info(x, datos) != (marca, tipo_inf)]
        if not any(obtener_item_info(x, datos) == (marca, tipo_inf) for x in datos["entregados"][inicial]):
            datos["entregados"][inicial].append(item_target)
        bot.send_message(call.message.chat.id, f"ENTREGADO: {marca} (Informe {tipo_inf}) por {n}. CC: {j}")
    elif accion == "tra":
        if marca in datos["reportes_hoy"]: datos["reportes_hoy"][marca]["status"] = f"TRABAJANDO ({h})"
        bot.edit_message_text(f"ESTATUS: Trabajando en {marca}. Responsable: {n}", call.message.chat.id, call.message.message_id, reply_markup=menu_trabajando(inicial, marca, tipo_inf))
    elif accion == "off":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        if marca in datos["reportes_hoy"]: datos["reportes_hoy"][marca]["status"] = f"INACTIVA ({h})"
        datos["deudas"][inicial] = [x for x in datos["deudas"][inicial] if obtener_item_info(x, datos) != (marca, tipo_inf)]
        bot.send_message(call.message.chat.id, f"MARCA NO DISPONIBLE: {marca}. Reportado por {n}. CC: {j}")
    elif accion == "noh":
        msg = bot.send_message(call.message.chat.id, f"Escribe motivo de retraso para {marca}:", reply_markup=ForceReply(selective=True))
        bot.register_next_step_handler(msg, procesar_justificacion, inicial, marca, call.message.message_id, tipo_inf)
    elif accion == "re":
        m_re = InlineKeyboardMarkup(); m_re.add(InlineKeyboardButton("Trabajando en eso", callback_data=f"tra_{inicial}_{marca}_{tipo_inf}"), InlineKeyboardButton("No podre hoy", callback_data=f"noh_{inicial}_{marca}_{tipo_inf}"))
        bot.edit_message_text(f"Opciones para {marca}:", call.message.chat.id, call.message.message_id, reply_markup=m_re)
    guardar_datos(datos)

def procesar_justificacion(message, inicial, marca, original_msg_id, tipo_inf="SEMANAL"):
    datos = cargar_datos(); h = obtener_hora_actual()
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
    # No enviar alertas en fin de semana
    if es_fin_de_semana():
        return
    try:
        for m, info in cargar_datos()["reportes_hoy"].items():
            if info["status"] == "POR ENTREGA":
                try: bot.send_message(ID_GRUPO_OFICIAL, f"RECORDATORIO {USUARIOS[info['user']]['alias']}: Pendiente informe para {m}.")
                except Exception as e: print(e)
    except Exception as e: print(e)

def tarea_viernes():
    if es_fin_de_semana():
        return
    try: bot.send_message(ID_GRUPO_OFICIAL, resumen_semanal_texto(cargar_datos()))
    except Exception as e: print(e)

def reloj():
    # Horarios en UTC (Venezuela = UTC-4, se suma +4h)
    schedule.every().day.at("15:00").do(enviar_recordatorio_diario)       # 11:00 AM Venezuela
    tiempos_alerta = ["16:00", "20:00", "22:00"]                          # 12:00 / 16:00 / 18:00 Venezuela
    for t in tiempos_alerta:
        schedule.every().day.at(t).do(tarea_alertas)
    schedule.every().friday.at("21:00").do(tarea_viernes)  # 17:00 Venezuela
    while True:
        try: schedule.run_pending()
        except Exception as e: print(f"Error schedule: {e}")
        time.sleep(1)

print("BOT REPORTIN ACTIVO")
registrar_test_callback(enviar_recordatorio_diario)
threading.Thread(target=iniciar_servidor_web, kwargs={"host": "0.0.0.0", "port": 5000}, daemon=True).start()
threading.Thread(target=reloj, daemon=True).start()
bot.infinity_polling(timeout=10, long_polling_timeout=5)