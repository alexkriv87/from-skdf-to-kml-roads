# skdf_api.py
# Модуль для работы с API СКДФ (Справочная карта дорог федерального значения)
# Содержит функции для:
# 1. Получения дорог по bounding box
# 2. Получения passport_id по road_id
# 3. Получения характеристик дороги по passport_id

import requests
import time
from logger_config import logger
from config import REQUEST_TIMEOUT, MAX_RETRIES

# Константы API
BASE_URL = "https://xn--d1aluo.xn--p1ai"  # Адрес API (punycode для скдф.рф)

# Заголовки для разных типов запросов
HEADERS_GEO = {
    "Content-Type": "application/json",
    "Content-Profile": "gis_api_public"      # Для запросов геометрии
}

HEADERS_PASSPORT = {
    "Content-Type": "application/json",
    "Content-Profile": "query_api"           # Для запросов паспортов
}


def _make_request_with_retry(method, url, **kwargs):
    """
    Внутренняя функция для выполнения запроса с повторами.
    Вызывается только внутри этого модуля.
    
    Параметры:
        method: 'GET' или 'POST'
        url: адрес запроса
        **kwargs: дополнительные параметры (json, headers и т.д.)
    
    Возвращает:
        Response объект или None при ошибке
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            if method.upper() == 'GET':
                response = requests.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
            else:
                response = requests.post(url, timeout=REQUEST_TIMEOUT, **kwargs)
            
            if response.status_code == 200:
                return response
            else:
                logger.warning(f"Попытка {attempt + 1}: статус {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"Попытка {attempt + 1}: таймаут")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Попытка {attempt + 1}: ошибка соединения")
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1}: {e}")
        
        if attempt < MAX_RETRIES:
            time.sleep(1)
    
    logger.error(f"Не удалось выполнить запрос после {MAX_RETRIES + 1} попыток")
    return None


def get_roads_in_bbox(bbox_3857, zoom=14):
    """
    Запрашивает у API СКДФ все дороги в заданном прямоугольнике.
    
    Параметры:
        bbox_3857: [xmin, ymin, xmax, ymax] - границы в метрах (EPSG:3857)
        zoom: уровень детализации (6-18). По умолчанию 14.
    
    Возвращает:
        list: список дорог (каждая дорога - Feature из GeoJSON)
              или пустой список при ошибке
    """
    url = f"{BASE_URL}/api-pg/rpc/get_road_lr_geobox"
    payload = {
        "p_box": bbox_3857,
        "p_scale_factor": 1,
        "p_zoom": zoom
    }
    
    logger.info(f"Запрос дорог: zoom={zoom}")
    
    response = _make_request_with_retry('POST', url, json=payload, headers=HEADERS_GEO)
    
    if response is None:
        logger.error("Не удалось получить дороги из СКДФ")
        return []
    
    data = response.json()
    features = data.get('features', [])
    
    logger.info(f"Найдено дорог: {len(features)}")
    
    return features


def get_passport_id(road_id):
    """
    Получает passport_id по road_id.
    
    Параметры:
        road_id: идентификатор дороги (из get_roads_in_bbox)
    
    Возвращает:
        int: passport_id или None, если не найден
    """
    url = f"{BASE_URL}/api-pg/rpc/f_get_approved_passport_id_by_object"
    payload = {
        "object_id": road_id,
        "object_type": 4      # 4 означает "дорога"
    }
    
    logger.debug(f"Запрос passport_id для road_id={road_id}")
    
    response = _make_request_with_retry('POST', url, json=payload, headers=HEADERS_PASSPORT)
    
    if response is None:
        logger.warning(f"Не удалось получить passport_id для road_id={road_id}")
        return None
    
    data = response.json()
    passport_id = data.get('passport_id')
    
    if passport_id:
        logger.debug(f"Найден passport_id={passport_id} для road_id={road_id}")
    else:
        logger.warning(f"passport_id не найден для road_id={road_id}")
    
    return passport_id


def get_road_characteristics(passport_id):
    """
    Получает детальные характеристики дороги по passport_id.
    Извлекает ВСЕ значения (не только первые).
    
    Параметры:
        passport_id: идентификатор паспорта дороги
    
    Возвращает:
        dict: словарь с характеристиками или {} при ошибке
    """
    url = f"https://скдф.рф/api/v3/portal/hwm/passports/roads/{passport_id}"
    
    logger.debug(f"Запрос характеристик для passport_id={passport_id}")
    
    response = _make_request_with_retry('GET', url)
    
    if response is None:
        logger.warning(f"Не удалось получить характеристики для passport_id={passport_id}")
        return {}
    
    data = response.json()
    
    characteristics = {}
    
    if 'data' in data:
        d = data['data']
        
        # Категория дороги (все значения)
        if d.get('category'):
            categories = [c['name'] for c in d['category']]
            characteristics['категория'] = ', '.join(categories)
        
        # Тип покрытия (все значения)
        if d.get('pavement_type'):
            pavements = [p['name'] for p in d['pavement_type']]
            characteristics['покрытие'] = ', '.join(pavements)
        
        # Количество полос (все значения)
        if d.get('lanes'):
            lanes_list = [str(l) for l in d['lanes']]
            characteristics['полосы'] = ', '.join(lanes_list)
        
        # Протяжённость дороги в км
        if d.get('length'):
            characteristics['длина_паспорт'] = d['length']
        
        # Ограничение скорости (все значения)
        if d.get('speed_limit'):
            speeds = [str(s) for s in d['speed_limit']]
            characteristics['скорость'] = ', '.join(speeds)
        
        # Владельцы дороги (все)
        if d.get('owner'):
            owners = [o['name'] for o in d['owner']]
            characteristics['владелец'] = ', '.join(owners)
        
        # Пропускная способность (если есть)
        if d.get('capacity'):
            characteristics['пропускная'] = d['capacity'][0]
        
        # Интенсивность движения (если есть)
        if d.get('traffic'):
            characteristics['интенсивность'] = d['traffic'][0]
    
    logger.debug(f"Получены характеристики: {list(characteristics.keys())}")
    
    return characteristics


# ============= ТЕСТ =============
if __name__ == "__main__":
    import time
    
    print("\n=== Тест skdf_api.py ===\n")
    
    # Координаты из coord_utils.py (Свободный, bbox в метрах)
    test_bbox = [14215755.537897442, 6660090.979195764, 14296014.416992927, 6720328.170348525]
    
    # Тест 1: get_roads_in_bbox
    start_time = time.time()
    roads = get_roads_in_bbox(test_bbox, zoom=14)
    elapsed_time = time.time() - start_time
    
    print(f"\nВремя выполнения: {elapsed_time:.2f} сек")
    print(f"Получено дорог: {len(roads)}")
    
    if roads:
        # Находим самую длинную дорогу по геометрической длине
        longest_road = max(roads, key=lambda r: r['properties'].get('geom_length', 0))
        
        print(f"\n=== Самая длинная дорога ===")
        print(f"  Название: {longest_road['properties'].get('road_name')}")
        print(f"  Геометрическая длина: {longest_road['properties'].get('geom_length')} км")
        print(f"  Паспортная длина (из API): {longest_road['properties'].get('road_length')} км")
        print(f"  road_id: {longest_road['properties'].get('road_id')}")
        print(f"  road_part_id: {longest_road['properties'].get('road_part_id')}")
        print(f"  Принадлежность: {longest_road['properties'].get('value_of_the_road')}")
        
        # Тест 2: get_passport_id для самой длинной дороги
        print("\n=== Тест get_passport_id ===")
        test_road_id = longest_road['properties']['road_id']
        print(f"road_id: {test_road_id}")
        
        passport_id = get_passport_id(test_road_id)
        print(f"passport_id: {passport_id}")
        
        # Тест 3: get_road_characteristics
        if passport_id:
            print("\n=== Тест get_road_characteristics ===")
            chars = get_road_characteristics(passport_id)
            print(f"Характеристики: {chars}")
        else:
            print("\nНет passport_id, пропускаем тест характеристик")