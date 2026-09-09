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

def obtener_todas_las_marcas():
    """Compila lista completa de marcas con sus frecuencias y días asignados."""
    datos = cargar_datos()
    marcas_desactivadas = set(datos.get("marcas_desactivadas", []))
    marcas_eliminadas = set(datos.get("marcas_eliminadas", []))
    asignaciones_custom = datos.get("asignaciones_personalizadas", {})
    resultado = []
    marcas_vistas = set()

    # 1. Marcas semanales estáticas
    DIAS_ES = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}
    for dia_en, asignaciones in CALENDARIO_SEMANAL.items():
        dia_es = DIAS_ES.get(dia_en, dia_en)
        for resp_orig, lista_m in asignaciones.items():
            for m in lista_m:
                if m in marcas_eliminadas:
                    continue
                resp_actual = asignaciones_custom.get(m, resp_orig)
                freq = "Semanal"
                dias_m = [d for d, m_list in DIAS_MENSUALES.items() if m in m_list]
                if dias_m:
                    freq += f" + Mensual (Día {', '.join(dias_m)})"
                
                resultado.append({
                    "nombre": m,
                    "resp": resp_actual,
                    "respNombre": USUARIOS.get(resp_actual, {}).get("nombre", resp_actual),
                    "freq": freq,
                    "dia": dia_es,
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
                    "activa": m not in marcas_desactivadas
                })
                marcas_vistas.add(m)

    # 3. Marcas dinámicas agregadas desde la Web
    for m_custom in datos.get("marcas_personalizadas", []):
        m_nombre = m_custom.get("nombre")
        if m_nombre and m_nombre not in marcas_vistas and m_nombre not in marcas_eliminadas:
            resp_actual = asignaciones_custom.get(m_nombre, m_custom.get("resp", "F"))
            resultado.append({
                "nombre": m_nombre,
                "resp": resp_actual,
                "respNombre": USUARIOS.get(resp_actual, {}).get("nombre", resp_actual),
                "freq": m_custom.get("freq", "Personalizado"),
                "dia": m_custom.get("dia", "Asignado"),
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
    freq = body.get("freq", "Semanal")
    dia = body.get("dia", "Lunes")

    if not nombre:
        return jsonify({"error": "Nombre de marca requerido"}), 400

    datos = cargar_datos()
    marcas_custom = datos.get("marcas_personalizadas", [])
    
    # Evitar duplicados
    for m in marcas_custom:
        if m.get("nombre") == nombre:
            return jsonify({"error": "La marca ya existe"}), 400

    marcas_custom.append({
        "nombre": nombre,
        "resp": resp,
        "freq": freq,
        "dia": dia
    })
    datos["marcas_personalizadas"] = marcas_custom
    datos.setdefault("asignaciones_personalizadas", {})[nombre] = resp
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

    # Rendimiento por responsable
    rendimiento = {}
    for r in ["R", "F", "Roger"]:
        entregados = len(datos.get("entregados", {}).get(r, []))
        deudas = len(datos.get("deudas", {}).get(r, []))
        rendimiento[r] = {
            "nombre": USUARIOS.get(r, {}).get("nombre", r),
            "entregados": entregados,
            "deudas": deudas
        }

    return jsonify({
        "activas": total_activas,
        "pausadas": total_pausadas,
        "rendimiento": rendimiento,
        "historial_semanas": len(datos.get("historial_mensual", []))
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
