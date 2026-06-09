from datetime import datetime, timedelta

def obtener_hora_actual():
    return datetime.now().strftime("%I:%M %p")

def obtener_rango_semana():
    hoy = datetime.now()
    l = hoy - timedelta(days=hoy.weekday())
    v = l + timedelta(days=4)
    return f"DEL {l.strftime('%d/%m')} AL {v.strftime('%d/%m')}"

def es_fin_de_semana(fecha=None):
    """Devuelve True si la fecha es sábado o domingo."""
    if fecha is None:
        fecha = datetime.now()
    return fecha.weekday() >= 5  # 5=Sábado, 6=Domingo

def proximo_lunes(fecha):
    """Dado un sábado o domingo, devuelve el lunes siguiente."""
    dias_hasta_lunes = (7 - fecha.weekday()) % 7
    if dias_hasta_lunes == 0:
        dias_hasta_lunes = 7
    return fecha + timedelta(days=dias_hasta_lunes)
