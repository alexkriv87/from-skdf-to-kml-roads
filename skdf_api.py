# skdf_api.py
# Модуль для работы с API СКДФ (Справочная карта дорог федерального значения)
# Содержит функции для:
# 1. Получения дорог по bounding box (заполняет переданный GeoDataFrame)
# 2. Получения passport_id по road_id
# 3. Получения характеристик дороги по passport_id
# 4. Создания пустого GeoDataFrame с правильной структурой

import requests
import time
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape
from logger_config import logger
from config import (
    MAX_RETRIES, REQUEST_TIMEOUT, BASE_URL,
    HEADERS_GEO, HEADERS_PASSPORT, GDF_SCHEMA
)


def create_empty_gdf():
    """
    Создаёт пустой GeoDataFrame с правильной структурой (колонки + типы).
    Колонка geometry добавляется отдельно.
    
    Возвращает:
        GeoDataFrame: пустой gdf с заданной схемой
    """
    df = pd.DataFrame({
        col: pd.Series(dtype=dtype) 
        for col, dtype in GDF_SCHEMA.items()
    })
    
    df['geometry'] = None
    
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:3857")
    
    return gdf


def _make_request_with_retry(method, url, **kwargs):
    """
    Внутренняя функция для выполнения запроса с повторами.
    Вызывается только внутри этого модуля.
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


def get_roads_in_bbox(bbox_3857, gdf, zoom=14):
    """
    Заполняет переданный GeoDataFrame дорогами из СКДФ.
    
    Параметры:
        bbox_3857: [xmin, ymin, xmax, ymax] - границы в метрах (EPSG:3857)
        gdf: GeoDataFrame (должен быть создан через create_empty_gdf)
        zoom: уровень детализации (6-18). По умолчанию 14.
    
    Возвращает:
        GeoDataFrame: заполненный gdf
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
        return gdf
    
    data = response.json()
    features = data.get('features', [])
    
    if not features:
        logger.error("API вернул пустой ответ (нет дорог в указанном квадрате).")
        raise ValueError("API вернул пустой ответ. Проверьте область поиска или повторите запрос позже.")
    
    # Собираем все строки для добавления
    rows_to_add = []
    
    for feature in features:
        props = feature['properties']
        geom = shape(feature['geometry'])
        
        # Создаём новую строку согласно схеме
        new_row = {}
        for col in GDF_SCHEMA.keys():
            new_row[col] = props.get(col, None)
        new_row['geometry'] = geom
        
        rows_to_add.append(new_row)
    
    # Добавляем все строки одной операцией
    if rows_to_add:
        new_rows_df = pd.DataFrame(rows_to_add)
        gdf = pd.concat([gdf, new_rows_df], ignore_index=True)
    
    logger.info(f"Найдено дорог: {len(gdf)}")
    
    return gdf


def get_passport_id(road_id):
    """
    Получает passport_id по road_id.
    
    Параметры:
        road_id: идентификатор дороги (из get_roads_in_bbox)
    
    Возвращает:
        int: passport_id или None, если не найден
    """
    # Преобразуем numpy.int64 в обычный int
    road_id = int(road_id)
    
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
        
        if d.get('category'):
            categories = [c['name'] for c in d['category']]
            characteristics['категория'] = ', '.join(categories)
        
        if d.get('pavement_type'):
            pavements = [p['name'] for p in d['pavement_type']]
            characteristics['покрытие'] = ', '.join(pavements)
        
        if d.get('lanes'):
            lanes_list = [str(l) for l in d['lanes']]
            characteristics['полосы'] = ', '.join(lanes_list)
        
        if d.get('length'):
            characteristics['длина_паспорт'] = d['length']
        
        if d.get('speed_limit'):
            speeds = [str(s) for s in d['speed_limit']]
            characteristics['скорость'] = ', '.join(speeds)
        
        if d.get('owner'):
            owners = [o['name'] for o in d['owner']]
            characteristics['владелец'] = ', '.join(owners)
        
        if d.get('capacity'):
            characteristics['пропускная'] = d['capacity'][0]
        
        if d.get('traffic'):
            characteristics['интенсивность'] = d['traffic'][0]
    
    logger.debug(f"Получены характеристики: {list(characteristics.keys())}")
    
    return characteristics

# ============= ТЕСТ =============
if __name__ == "__main__":
    import time
    
    print("\n=== Тест skdf_api.py ===\n")
    
    # Координаты из coord_utils.py (Ухта, bbox в метрах)
    test_bbox = [5977746.526608107, 9236942.652847864, 5979323.042513346, 9238789.165837372]
    
    # Создаём пустой gdf
    gdf = create_empty_gdf()
    
    # Заполняем дорогами
    start_time = time.time()
    gdf = get_roads_in_bbox(test_bbox, gdf, zoom=14)
    elapsed_time = time.time() - start_time
    
    print(f"Время выполнения: {elapsed_time:.2f} сек")
    print(f"Получено дорог: {len(gdf)}")
    
    if len(gdf) > 0:
        print("\n=== Содержимое GeoDataFrame ===")
        
        # Выводим только нужные колонки для читаемости
        display_cols = ['road_name', 'road_id', 'value_of_the_road', 'geom_length', 'road_length']
        existing_cols = [col for col in display_cols if col in gdf.columns]
        
        for idx, row in gdf.iterrows():
            print(f"\n--- Дорога {idx + 1} ---")
            for col in existing_cols:
                value = row.get(col)
                if value is not None:
                    print(f"  {col}: {value}")
    else:
        print("Нет дорог для теста")