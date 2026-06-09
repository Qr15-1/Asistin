import json
import threading
from pathlib import Path
from datetime import datetime
from config import CALENDARIO_SEMANAL
from utils import obtener_rango_semana

STATE_PATH = Path(__file__).parent / "bot_state.json"
DATA_LOCK = threading.Lock()

def cargar_datos():
    base = {
        "reportes_hoy": {}, 
        "deudas": {"R": [], "F": [], "Roger": []}, 
        "entregados": {"R": [], "F": [], "Roger": []}, 
        "inactivas": {"R": [], "F": [], "Roger": []}, 
        "historial_mensual": [], 
        "archivo_historico": {},
        "ultimo_envio": "", 
        "semana_id": datetime.now().strftime("%W"), 
        "mes_id": datetime.now().strftime("%m"),
        "tipos_semanales": {}
    }
    with DATA_LOCK:
        if not STATE_PATH.exists(): 
            return base
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                datos = json.load(f)
                for k in base: 
                    datos.setdefault(k, base[k])
                return datos
        except Exception: 
            return base

def guardar_datos(datos):
    with DATA_LOCK:
        try:
            with open(STATE_PATH, "w", encoding="utf-8") as f: 
                json.dump(datos, f, indent=2, ensure_ascii=False)
        except Exception: 
            pass

def gestionar_tiempos(datos):
    hoy = datetime.now()
    sem_act = hoy.strftime("%W")
    mes_act = hoy.strftime("%m")
    anio_act = hoy.strftime("%Y")
    
    if mes_act != datos["mes_id"]:
        etiqueta = f"{datos['mes_id']}-{anio_act}"
        datos["archivo_historico"][etiqueta] = list(datos["historial_mensual"])
        datos["historial_mensual"] = []
        datos["mes_id"] = mes_act
        
    if sem_act != datos["semana_id"]:
        datos["historial_mensual"].append({
            "rango": obtener_rango_semana(), 
            "entregados": datos["entregados"], 
            "deudas": datos["deudas"]
        })
        datos.update({
            "entregados": {"R": [], "F": [], "Roger": []}, 
            "deudas": {"R": [], "F": [], "Roger": []}, 
            "inactivas": {"R": [], "F": [], "Roger": []}, 
            "reportes_hoy": {}, 
            "tipos_semanales": {}, 
            "semana_id": sem_act
        })
    guardar_datos(datos)

def obtener_responsable(marca):
    for dia, asignaciones in CALENDARIO_SEMANAL.items():
        for resp, lista_marcas in asignaciones.items():
            if marca in lista_marcas: 
                return resp
    return "F"
