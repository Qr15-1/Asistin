import os
import threading
from flask import Flask, render_template, jsonify, request
from config import CALENDARIO_SEMANAL, DIAS_MENSUALES, USUARIOS
from state_manager import cargar_datos, guardar_datos, obtener_responsable

app = Flask(__name__, template_folder="templates")

# Referencia a la función de test para no tener importación circular
test_diario_callback = None

def registrar_test_callback(fn):
    global test_diario_callback
    test_diario_callback = fn

DIAS_ES = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}

def obtener_todas_las_marcas():
    """Compila lista completa de marcas con sus frecuencias y días asignados."""
    datos = cargar_datos()
    marcas_desactivadas = set(datos.get("marcas_desactivadas", []))
    marcas_eliminadas = set(datos.get("marcas_eliminadas", []))
    asignaciones_custom = datos.get("asignaciones_personalizadas", {})
    resultado = []
    marcas_vistas = set()

    # 1. Marcas semanales: agrupa todos los días de la misma marca
    marca_sem_info = {}
    for dia_en, asignaciones in CALENDARIO_SEMANAL.items():
        for resp_orig, lista_m in asignaciones.items():
            for m in lista_m:
                if m in marcas_eliminadas:
                    continue
                if m not in marca_sem_info:
                    marca_sem_info[m] = {"resp": resp_orig, "dias": []}
                if dia_en not in marca_sem_info[m]["dias"]:
                    marca_sem_info[m]["dias"].append(dia_en)

    for m, info in marca_sem_info.items():
        resp_actual = asignaciones_custom.get(m, info["resp"])
        dias_m = [d for d, m_list in DIAS_MENSUALES.items() if m in m_list]
        dias_es = [DIAS_ES.get(d, d) for d in info["dias"]]
        freq = "Semanal"
        if dias_m:
            freq += f" + Mensual (Día {', '.join(dias_m)})"
        resultado.append({
            "nombre": m,
            "resp": resp_actual,
            "respNombre": USUARIOS.get(resp_actual, {}).get("nombre", resp_actual),
            "freq": freq,
            "dia": ", ".join(dias_es),
            "dias_semanales": info["dias"],
            "dias_mensuales": dias_m,
            "activa": m not in marcas_desactivadas
        })
        marcas_vistas.add(m)

    # 2. Marcas únicamente mensuales
    for dia_m, lista_m in DIAS_MENSUALES.items():
        for m in lista_m:
            if m not in marcas_vistas and m not in marcas_eliminadas:
                resp_actual = asignaciones_custom.get(m, obtener_responsable(m))
                resultado.append({
                    "nombre": m,
                    "resp": resp_actual,
                    "respNombre": USUARIOS.get(resp_actual, {}).get("nombre", resp_actual),
                    "freq": f"Mensual (Día {dia_m})",
                    "dia": f"Día {dia_m} del mes",
                    "dias_semanales": [],
                    "dias_mensuales": [dia_m],
                    "activa": m not in marcas_desactivadas
                })
                marcas_vistas.add(m)

    # 3. Marcas dinámicas agregadas desde la Web
    for m_custom in datos.get("marcas_personalizadas", []):
        m_nombre = m_custom.get("nombre")
        if m_nombre and m_nombre not in marcas_vistas and m_nombre not in marcas_eliminadas:
            resp_actual = asignaciones_custom.get(m_nombre, m_custom.get("resp", "F"))
            dias_sem = m_custom.get("dias_semanales", [])
            dias_mes = m_custom.get("dias_mensuales", [])
            resultado.append({
                "nombre": m_nombre,
                "resp": resp_actual,
                "respNombre": USUARIOS.get(resp_actual, {}).get("nombre", resp_actual),
                "freq": m_custom.get("freq", "Personalizado"),
                "dia": m_custom.get("dia", "Asignado"),
                "dias_semanales": dias_sem,
                "dias_mensuales": dias_mes,
                "activa": m_nombre not in marcas_desactivadas
            })
            marcas_vistas.add(m_nombre)

    return resultado

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    return jsonify({"status": "online", "app": "Asistin Bot & Web Panel"})

@app.route("/api/marcas")
def get_marcas():
    return jsonify(obtener_todas_las_marcas())

@app.route("/api/marcas/toggle", methods=["POST"])
def toggle_marca():
    body = request.get_json() or {}
    nombre = body.get("nombre")
    if not nombre:
        return jsonify({"error": "Nombre de marca requerido"}), 400

    datos = cargar_datos()
    marcas_desactivadas = datos.get("marcas_desactivadas", [])
    
    if nombre in marcas_desactivadas:
        marcas_desactivadas.remove(nombre)
        estado_nuevo = True
    else:
        marcas_desactivadas.append(nombre)
        estado_nuevo = False
        
    datos["marcas_desactivadas"] = marcas_desactivadas
    guardar_datos(datos)
    
    return jsonify({"success": True, "nombre": nombre, "activa": estado_nuevo})

@app.route("/api/marcas/reasignar", methods=["POST"])
def reasignar_marca():
    body = request.get_json() or {}
    nombre = body.get("nombre")
    nuevo_resp = body.get("resp")
    if not nombre or not nuevo_resp:
        return jsonify({"error": "Nombre y responsable requeridos"}), 400

    if nuevo_resp not in USUARIOS:
        return jsonify({"error": "Responsable inválido"}), 400

    datos = cargar_datos()
    datos.setdefault("asignaciones_personalizadas", {})[nombre] = nuevo_resp
    guardar_datos(datos)

    return jsonify({"success": True, "nombre": nombre, "resp": nuevo_resp, "respNombre": USUARIOS[nuevo_resp]["nombre"]})

@app.route("/api/marcas/crear", methods=["POST"])
def crear_marca():
    body = request.get_json() or {}
    nombre = body.get("nombre")
    resp = body.get("resp", "F")
    dias_semanales = body.get("dias_semanales", [])   # ["Monday", "Tuesday", ...]
    dias_mensuales = body.get("dias_mensuales", [])   # ["05", "18", ...]

    if not nombre:
        return jsonify({"error": "Nombre de marca requerido"}), 400

    datos = cargar_datos()
    marcas_custom = datos.get("marcas_personalizadas", [])

    # Evitar duplicados
    for m in marcas_custom:
        if m.get("nombre") == nombre:
            return jsonify({"error": "La marca ya existe"}), 400

    # Construir freq y dia legibles
    partes_freq = []
    if dias_semanales:
        partes_freq.append("Semanal")
    if dias_mensuales:
        dias_num = [str(int(d)) for d in sorted(dias_mensuales)]
        partes_freq.append(f"Mensual (Día {', '.join(dias_num)})")
    freq = " + ".join(partes_freq) if partes_freq else "Personalizado"

    dias_es = [DIAS_ES.get(d, d) for d in dias_semanales]
    dia_str = ", ".join(dias_es) if dias_es else ("Días " + ", ".join(dias_mensuales) if dias_mensuales else "Asignado")

    marcas_custom.append({
        "nombre": nombre,
        "resp": resp,
        "freq": freq,
        "dia": dia_str,
        "dias_semanales": dias_semanales,
        "dias_mensuales": dias_mensuales
    })
    datos["marcas_personalizadas"] = marcas_custom
    datos.setdefault("asignaciones_personalizadas", {})[nombre] = resp
    guardar_datos(datos)

    return jsonify({"success": True, "nombre": nombre})

@app.route("/api/marcas/editar", methods=["POST"])
def editar_marca():
    body = request.get_json() or {}
    nombre = body.get("nombre")
    resp = body.get("resp")
    dias_semanales = body.get("dias_semanales", [])
    dias_mensuales = body.get("dias_mensuales", [])

    if not nombre:
        return jsonify({"error": "Nombre de marca requerido"}), 400

    datos = cargar_datos()
    if resp and resp in USUARIOS:
        datos.setdefault("asignaciones_personalizadas", {})[nombre] = resp

    # Construir freq y dia legibles
    partes_freq = []
    if dias_semanales:
        partes_freq.append("Semanal")
    if dias_mensuales:
        dias_num = [str(int(d)) for d in sorted(dias_mensuales)]
        partes_freq.append(f"Mensual (Día {', '.join(dias_num)})")
    freq = " + ".join(partes_freq) if partes_freq else "Personalizado"

    dias_es = [DIAS_ES.get(d, d) for d in dias_semanales]
    dia_str = ", ".join(dias_es) if dias_es else ("Días " + ", ".join(dias_mensuales) if dias_mensuales else "Asignado")

    marcas_custom = datos.get("marcas_personalizadas", [])
    encontrada = False
    for m in marcas_custom:
        if m.get("nombre") == nombre:
            m["resp"] = resp or m.get("resp", "F")
            m["dias_semanales"] = dias_semanales
            m["dias_mensuales"] = dias_mensuales
            m["freq"] = freq
            m["dia"] = dia_str
            encontrada = True
            break

    if not encontrada:
        # Si era estática original, se registra en marcas_personalizadas para sobreescribir sus días
        marcas_custom.append({
            "nombre": nombre,
            "resp": resp or obtener_responsable(nombre),
            "freq": freq,
            "dia": dia_str,
            "dias_semanales": dias_semanales,
            "dias_mensuales": dias_mensuales
        })

    datos["marcas_personalizadas"] = marcas_custom
    guardar_datos(datos)
    return jsonify({"success": True, "nombre": nombre})



@app.route("/api/marcas/eliminar", methods=["POST"])
def eliminar_marca():
    body = request.get_json() or {}
    nombre = body.get("nombre")
    if not nombre:
        return jsonify({"error": "Nombre de marca requerido"}), 400

    datos = cargar_datos()
    marcas_eliminadas = datos.get("marcas_eliminadas", [])
    if nombre not in marcas_eliminadas:
        marcas_eliminadas.append(nombre)
        datos["marcas_eliminadas"] = marcas_eliminadas
        guardar_datos(datos)

    return jsonify({"success": True, "nombre": nombre})

@app.route("/api/kpis")
def get_kpis():
    datos = cargar_datos()
    marcas = obtener_todas_las_marcas()
    total_activas = len([m for m in marcas if m["activa"]])
    total_pausadas = len([m for m in marcas if not m["activa"]])

    # Función auxiliar para clasificar item
    def clasificar(item):
        if isinstance(item, dict):
            return item.get("marca", ""), item.get("tipo", "SEMANAL")
        if isinstance(item, str):
            if "|" in item:
                partes = item.split("|", 1)
                return partes[0], partes[1]
            tipo = datos.get("tipos_semanales", {}).get(item, "SEMANAL")
            return item, tipo
        return str(item), "SEMANAL"

    # Rendimiento por responsable
    rendimiento = {}
    for r in ["R", "F", "Roger"]:
        entregados_items = datos.get("entregados", {}).get(r, [])
        deudas_items = datos.get("deudas", {}).get(r, [])

        ent_sem = []
        ent_men = []
        for item in entregados_items:
            m, t = clasificar(item)
            if t == "MENSUAL":
                ent_men.append(m)
            else:
                ent_sem.append(m)

        pen_sem = []
        pen_men = []
        for item in deudas_items:
            m, t = clasificar(item)
            if t == "MENSUAL":
                pen_men.append(m)
            else:
                pen_sem.append(m)

        rendimiento[r] = {
            "nombre": USUARIOS.get(r, {}).get("nombre", r),
            "entregados": len(entregados_items),
            "entregados_semanal": ent_sem,
            "entregados_mensual": ent_men,
            "deudas": len(deudas_items),
            "deudas_semanal": pen_sem,
            "deudas_mensual": pen_men
        }

    return jsonify({
        "activas": total_activas,
        "pausadas": total_pausadas,
        "rendimiento": rendimiento,
        "historial_semanas": len(datos.get("historial_mensual", []))
    })

@app.route("/api/historial")
def get_historial():
    datos = cargar_datos()
    historial_mensual = datos.get("historial_mensual", [])
    archivo_historico = datos.get("archivo_historico", {})

    def procesar_semana(sem, index):
        ent = sem.get("entregados", {})
        deu = sem.get("deudas", {})

        detalles_resp = {}
        total_ent = 0
        total_deu = 0

        for r in ["R", "F", "Roger"]:
            lista_ent = ent.get(r, [])
            lista_deu = deu.get(r, [])

            # Normalizar nombres de marcas si vienen como dict o string
            norm_ent = [x.get("marca", str(x)) if isinstance(x, dict) else str(x) for x in lista_ent]
            norm_deu = [x.get("marca", str(x)) if isinstance(x, dict) else str(x) for x in lista_deu]

            total_ent += len(norm_ent)
            total_deu += len(norm_deu)

            detalles_resp[r] = {
                "nombre": USUARIOS.get(r, {}).get("nombre", r),
                "entregados": norm_ent,
                "deudas": norm_deu
            }

        total = total_ent + total_deu
        pct = round((total_ent / total) * 100) if total > 0 else 100

        return {
            "num": index,
            "rango": sem.get("rango", f"Semana {index}"),
            "total_entregados": total_ent,
            "total_deudas": total_deu,
            "cumplimiento_pct": pct,
            "responsables": detalles_resp
        }

    semanas_actuales = [procesar_semana(s, i + 1) for i, s in enumerate(historial_mensual)]

    meses_archivados = {}
    for mes_tag, lista_sem in archivo_historico.items():
        meses_archivados[mes_tag] = [procesar_semana(s, i + 1) for i, s in enumerate(lista_sem)]

    return jsonify({
        "mes_actual_id": datos.get("mes_id", ""),
        "semanas": semanas_actuales,
        "archivo_historico": meses_archivados
    })


@app.route("/api/test", methods=["POST"])
def trigger_test():
    if test_diario_callback:
        threading.Thread(target=test_diario_callback, kwargs={"forzar": True}).start()
        return jsonify({"success": True, "message": "Test diario disparado en segundo plano"})
    return jsonify({"error": "Callback de test no disponible"}), 500

def iniciar_servidor_web(host="0.0.0.0", port=5000):
    try:
        from waitress import serve
        print(f"Servidor Web Asistin (Waitress) corriendo en http://{host}:{port}")
        serve(app, host=host, port=port)
    except Exception:
        print(f"Servidor Web Asistin (Flask dev) corriendo en http://{host}:{port}")
        app.run(host=host, port=port, debug=False, use_reloader=False)
