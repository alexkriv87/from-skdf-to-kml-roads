# config.py
# Настройки проекта

# ============= НАСТРОЙКИ API СКДФ =============
BASE_URL = "https://xn--d1aluo.xn--p1ai"

HEADERS_GEO = {
    "Content-Type": "application/json",
    "Content-Profile": "gis_api_public"
}

HEADERS_PASSPORT = {
    "Content-Type": "application/json",
    "Content-Profile": "query_api"
}

# ============= НАСТРОЙКИ ЗАПРОСОВ =============
DEFAULT_ZOOM = 14
REQUEST_TIMEOUT = 10
MAX_RETRIES = 1
REQUEST_DELAY = 0.5

# ============= НАСТРОЙКИ KML =============
LINE_WIDTH = 5

# Цвета в формате KML (AABBGGRR, FF = непрозрачный)
COLORS_KML = {
    "федеральные": "FF53A9FF",
    "региональные": "FFFFECCC",
    "местные": "FFCCCCFF",
    "частные": "FF00FF00",
    "лесные": "FF00FF00",
    "ведомственные": "FFFFFF00",
    "неизвестно": "FF888888",
}

# ============= КАТЕГОРИИ ДОРОГ =============
CATEGORY_MAPPING = {
    "федерального": "федеральные",
    "регионального": "региональные",
    "местного": "местные",
    "частные": "частные",
    "лесные": "лесные",
    "ведомственные": "ведомственные",
}

# ============= ФОРМИРОВАНИЕ DESCRIPTION =============
DESCRIPTION_TEMPLATE = [
    "Категория:",
    "Покрытие:",
    "Типы дорожной одежды:",
    "Полосы:",
    "Протяженность (паспорт):",
    "Максимальная скорость:",
    "Принадлежность:",
]

# ============= СХЕМА ДАННЫХ GeoDataFrame =============
GDF_SCHEMA = {
    'road_name': 'object',
    'road_id': 'int64',
    'gid': 'int64',
    'road_part_id': 'int64',
    'value_of_the_road': 'object',
    'skeleton': 'bool',
    'geom_length': 'float64',
    'road_length': 'float64',
    'passport_id': 'int64',
    'Категория:': 'object',
    'Покрытие:': 'object',
    'Типы дорожной одежды:': 'object',
    'Полосы:': 'object',
    'Протяженность (паспорт):': 'float64',
    'Максимальная скорость:': 'object',
    'Принадлежность:': 'object',
    'capacity': 'float64',
    'traffic': 'float64',
}

GDF_COLUMNS = list(GDF_SCHEMA.keys())
