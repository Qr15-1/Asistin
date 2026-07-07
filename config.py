import os

# CONFIGURACION DEL BOT
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
ID_GRUPO_OFICIAL = '-1003860093839'

USUARIOS = {
    "R": { "nombre": "Rebeca", "alias": "@Rebecaarh", "id": 5937374472 },
    "F": { "nombre": "Franklin", "alias": "@Franklinjlopezr", "id": 975494788 },
    "Jefe": { "nombre": "Jonathan", "alias": "@JonathanSchemel", "id": 515198765 },
    "Roger": { "nombre": "Roger", "alias": "@RogerAQA", "id": 5499547223 }
}

ADMIN_IDS = [515198765, 5499547223]

# CALENDARIOS
# Calendario Semanal (Dia -> Responsable -> Marcas)
CALENDARIO_SEMANAL = {
    "Monday": { "R": ["Emiliarte",], "F": [], "Roger": ["El Toque"] },
    "Tuesday": { "R": ["Luva"], "F": ["+58 Shop", "La Zapeteria"], "Roger": ["Osersa"] },
    "Wednesday": { "R": ["Altamar"], "F": [] },
    "Thursday": { "R": ["Dra. K Beauty"], "F": ["Bungerz"] },
    "Friday": { "R": ["La Cava"], "F": [] }
}

# Calendario Mensual (Dia del mes DD -> Marcas)
DIAS_MENSUALES = {
    "03": ["Dra. K Beauty"],
    "05": ["El Toque"],
    "06": ["La Zapeteria"],
    "09": ["Bungerz"],
    "10": ["Emiliarte"],
    "12": ["La Cava", "Emiliarte"],
    "13": ["Luva", "Altamar"],
    "15": ["Chaofan"],

    "18": ["+58 Shop", "Osersa"]
}
