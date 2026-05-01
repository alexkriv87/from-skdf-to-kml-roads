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
from shapely.geometry import shape, box
from logger_config import logger
from config import (
    MAX_RETRIES, REQUEST_TIMEOUT, BASE_URL,
    HEADERS_GEO, HEADERS_PASSPORT, CATEGORY_MAPPING
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


def fetch_roads_raw(bbox_meters, zoom=14):
    """
    Запрашивает у API СКДФ дороги в заданном прямоугольнике.

    Параметры:
        bbox_meters: [xmin, ymin, xmax, ymax] - границы в метрах (EPSG:3857)
        zoom: уровень детализации (6-18). По умолчанию 14.

    Возвращает:
        list: сырые features из GeoJSON
    """
    url = f"{BASE_URL}/api-pg/rpc/get_road_lr_geobox"
    payload = {
        "p_box": bbox_meters,
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


def check_road_intersects_bbox(geometry, search_bbox):
    """
    Проверяет, пересекается ли геометрия дороги с поисковым bbox.

    Параметры:
        geometry: Shapely-объект в EPSG:3857
        search_bbox: полигон bbox (shapely.geometry.Polygon) в EPSG:3857

    Возвращает:
        bool: True, если пересекается
    """
    return geometry.intersects(search_bbox)


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
            characteristics['Категория:'] = ' / '.join(categories)

        # Вид покрытия (асфальтобетон, щебень и т.д.)
        if d.get('pavement_kind'):
            pavement_kinds = [p['name'] for p in d['pavement_kind']]
            characteristics['Покрытие:'] = ' / '.join(pavement_kinds)

        # Типы дорожной одежды (капитальные, облегченные, переходные)
        if d.get('pavement_type'):
            pavement_types = [p['name'] for p in d['pavement_type']]
            characteristics['Типы дорожной одежды:'] = ' / '.join(
                pavement_types)

        # Количество полос движения (2, 3, 4)
        if d.get('lanes'):
            lanes_list = [str(l) for l in d['lanes']]
            characteristics['Полосы:'] = ' / '.join(lanes_list)

        # Протяжённость дороги в км (паспортная длина)
        if d.get('length'):
            characteristics['Протяженность (паспорт):'] = d['length']

        # Ограничение максимальной скорости (км/ч)
        if d.get('speed_limit'):
            speeds = [str(s) for s in d['speed_limit']]
            characteristics['Максимальная скорость:'] = ' / '.join(speeds)

        # Владелец/эксплуатант дороги
        if d.get('owner'):
            owners = [o['name'] for o in d['owner']]
            characteristics['Принадлежность:'] = ' / '.join(owners)

        # Пропускная способность (авто/сутки) — пока не используется в DESCRIPTION_TEMPLATE
        if d.get('capacity'):
            characteristics['capacity'] = d['capacity'][0]

        # Интенсивность движения (авто/сутки) — пока не используется в DESCRIPTION_TEMPLATE
        if d.get('traffic'):
            characteristics['traffic'] = d['traffic'][0]

    return characteristics


def get_category(value_of_the_road):
    """
    Определяет Значение автомобильной дороги по value_of_the_road (поиск по подстроке).

    Пример входа: "Автомобильные дороги местного значения"
    Пример выхода: "местные"
    """
    value_lower = value_of_the_road.lower()

    for key, category in CATEGORY_MAPPING.items():
        if key in value_lower:
            return category

    raise ValueError(f"Неизвестная категория дороги: {value_of_the_road}")


# ============================================================================
# ТЕСТОВЫЙ БЛОК
# ============================================================================
if __name__ == "__main__":
    import time
    import pandas as pd
    from shapely.geometry import box
    from coord_utils import build_bbox, convert_bbox_to_skdf

    print("\n=== Тест skdf_api.py ===\n")

    # ===== ЖЁСТКИЕ КООРДИНАТЫ для теста =====
    lat1, lon1 = 51.43000002777777, 128.07111802777777
    lat2, lon2 = 51.40874844444444, 128.12141480555556
    print(f"Тестовые координаты: NW({lat1}, {lon1}), SE({lat2}, {lon2})")

    # Строим bbox
    bbox_degrees = build_bbox((lat1, lon1), (lat2, lon2))
    bbox_meters = convert_bbox_to_skdf(bbox_degrees)
    print(f"Bbox: {bbox_degrees} -> {bbox_meters}")

    # 1. Загружаем дороги
    print("\n1. Загрузка дорог из СКДФ...")
    features = fetch_roads_raw(bbox_meters, zoom=14)
    gdf = features_to_gdf(features)
    print(f"   Загружено: {len(gdf)} дорог")

    # 2. Фильтрация по bbox
    print("\n2. Фильтрация по bbox...")
    search_bbox = box(*bbox_meters)
    gdf = gdf[gdf['geometry'].apply(
        lambda geom: geom.intersects(search_bbox))].copy()
    print(f"   После фильтрации: {len(gdf)} дорог")

    # 3. Обогащение характеристиками
    print("\n3. Обогащение характеристиками...")
    gdf['passport_id'] = gdf['road_id'].apply(get_passport_id)
    gdf['characteristics'] = gdf['passport_id'].apply(get_road_characteristics)

    chars_df = pd.DataFrame(gdf['characteristics'].to_list())
    chars_df['road_id'] = gdf['road_id'].values

    gdf = pd.merge(
        gdf.drop(columns=['characteristics']),
        chars_df,
        on='road_id',
        how='left'
    )

    # 4. Добавляем категорию
    gdf['Значение автомобильной дороги'] = gdf['value_of_the_road'].apply(
        get_category)

    # 5. Выводим результат
    print("\n4. Результат:")
    cols = ['road_name', 'Значение автомобильной дороги',
            'Категория:']
    existing_cols = [c for c in cols if c in gdf.columns]
    print(gdf[existing_cols].head().to_string())
    print(
        f"\n✅ Итоговый GeoDataFrame: {len(gdf)} дорог, колонки: {list(gdf.columns)}")
