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
    HEADERS_GEO, HEADERS_PASSPORT
)


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
                response = requests.post(
                    url, timeout=REQUEST_TIMEOUT, **kwargs)

            if response.status_code == 200:
                return response
            else:
                logger.warning(
                    f"Попытка {attempt + 1}: статус {response.status_code}")

        except requests.exceptions.Timeout:
            logger.warning(f"Попытка {attempt + 1}: таймаут")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Попытка {attempt + 1}: ошибка соединения")
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1}: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(1)

    logger.error(
        f"Не удалось выполнить запрос после {MAX_RETRIES + 1} попыток")
    return None


def fetch_roads_raw(bbox_3857, zoom=14):
    """
    Запрашивает у API СКДФ дороги в заданном прямоугольнике.

    Параметры:
        bbox_3857: [xmin, ymin, xmax, ymax] - границы в метрах (EPSG:3857)
        zoom: уровень детализации (6-18). По умолчанию 14.

    Возвращает:
        list: сырые features из GeoJSON
    """
    url = f"{BASE_URL}/api-pg/rpc/get_road_lr_geobox"
    payload = {
        "p_box": bbox_3857,
        "p_scale_factor": 1,
        "p_zoom": zoom
    }

    logger.info(f"Запрос дорог: zoom={zoom}")

    response = _make_request_with_retry(
        'POST', url, json=payload, headers=HEADERS_GEO)

    if response is None:
        logger.error("Не удалось получить дороги из СКДФ")
        raise Exception("Превышено количество попыток подключения к API СКДФ")

    data = response.json()
    features = data.get('features', [])

    if not features:
        logger.error(
            "API вернул пустой ответ (нет дорог в указанном квадрате).")
        raise ValueError(
            "API вернул пустой ответ. Проверьте область поиска или повторите запрос позже.")

    return features


def features_to_gdf(features):
    """
    Преобразует список features в GeoDataFrame.

    Параметры:
        features: список features из GeoJSON

    Возвращает:
        GeoDataFrame: дороги с геометрией и атрибутами (CRS: EPSG:3857)
    """
    if not features:
        return gpd.GeoDataFrame()

    gdf = gpd.GeoDataFrame.from_features(features)
    gdf = gdf.set_crs("EPSG:3857")

    logger.info(f"Создан GeoDataFrame: {len(gdf)} дорог")

    return gdf


def get_passport_id(road_id):
    """
    Получает passport_id по road_id.
    """

    url = f"{BASE_URL}/api-pg/rpc/f_get_approved_passport_id_by_object"
    payload = {
        "object_id": road_id,
        "object_type": 4      # 4 означает "дорога"
    }

    response = _make_request_with_retry(
        'POST', url, json=payload, headers=HEADERS_PASSPORT)

    if response is None:
        return None

    data = response.json()   # {'passport_id': 202411461}
    passport_id = data.get('passport_id')

    return passport_id


def get_road_characteristics(passport_id):
    """
    Получает характеристики дороги по passport_id из СКДФ.

    Параметры:
        passport_id: идентификатор паспорта дороги

    Возвращает:
        dict: словарь с характеристиками (категория, покрытие, полосы и т.д.)
              или {} при ошибке
    """
    url = f"https://скдф.рф/api/v3/portal/hwm/passports/roads/{passport_id}"
    response = _make_request_with_retry('GET', url)

    if response is None:
        return {}

    data = response.json()
    characteristics = {}

    if 'data' in data:
        d = data['data']

        # Категория дороги (I, II, III, IV, V) — может быть несколько
        if d.get('category'):
            categories = [c['name'] for c in d['category']]
            characteristics['категория'] = ' / '.join(categories)

        # Тип покрытия (асфальтобетон, щебень и т.д.)
        if d.get('pavement_type'):
            pavements = [p['name'] for p in d['pavement_type']]
            characteristics['покрытие'] = ' / '.join(pavements)

        # Количество полос движения (2, 3, 4)
        if d.get('lanes'):
            lanes_list = [str(l) for l in d['lanes']]
            characteristics['полосы'] = ' / '.join(lanes_list)

        # Протяжённость дороги в км (паспортная длина)
        if d.get('length'):
            characteristics['длина_паспорт'] = d['length']

        # Ограничение максимальной скорости (км/ч)
        if d.get('speed_limit'):
            speeds = [str(s) for s in d['speed_limit']]
            characteristics['скорость'] = ' / '.join(speeds)

        # Владелец/эксплуатант дороги
        if d.get('owner'):
            owners = [o['name'] for o in d['owner']]
            characteristics['владелец'] = ' / '.join(owners)

        # Пропускная способность (авто/сутки)
        if d.get('capacity'):
            characteristics['пропускная'] = d['capacity'][0]

        # Интенсивность движения (авто/сутки)
        if d.get('traffic'):
            characteristics['интенсивность'] = d['traffic'][0]

    return characteristics


# ============= ТЕСТ =============
if __name__ == "__main__":
    test_bbox = [5977746.526608107, 9236942.652847864,
                 5979323.042513346, 9238789.165837372]

    features = fetch_roads_raw(test_bbox, zoom=14)
    gdf = features_to_gdf(features)

    gdf['passport_id'] = gdf['road_id'].apply(get_passport_id)
    gdf['characteristics'] = gdf['passport_id'].apply(get_road_characteristics)

    chars_df = pd.DataFrame(gdf['characteristics'].to_list())
    gdf = pd.concat([gdf.drop(columns=['characteristics']), chars_df], axis=1)

    # Выводим нужные колонки, включая is_checked
    cols = ['road_name', 'value_of_the_road',
            'категория', 'покрытие', 'полосы']
    print(gdf[cols].to_string())
    print(gdf.columns)
