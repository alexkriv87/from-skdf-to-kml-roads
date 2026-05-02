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


def get_roadway_segments(passport_id):
    """
    Получает список passport_id сегментов roadway для дороги.

    Принимает: passport_id (int) - например, 201384581

    Возвращает: list of int - список passport_id сегментов
    """
    url = f"{BASE_URL}/api/v3/portal/hwm/passports/roads/{passport_id}/roadway"
    response = _make_request_with_retry('GET', url, headers=HEADERS_PASSPORT)

    if not response or response.status_code != 200:
        return []

    data = response.json()
    segments = data.get('data', [])

    result = []
    for seg in segments:
        result.append(seg.get('passport_id'))

    return result


def get_roadway_widths_json(segment_passport_id):
    """
    Получает сырые данные по ширине для сегмента дороги.

    Принимает: segment_passport_id (int) - из get_roadway_segments

    Возвращает: list of dict - список участков (как есть из API)
        Пример: [
            {"id": 433435008, "start": "0+000", "finish": "7+740", 
             "length": 7.74, "square": 46440.0, "roadway_width": 6.0}
        ]
    """
    url = f"{BASE_URL}/api/v3/portal/hwm/passports/parts/{segment_passport_id}/roadway"
    response = _make_request_with_retry('GET', url, headers=HEADERS_PASSPORT)

    if not response or response.status_code != 200:
        return []

    data = response.json()
    return data.get('data', [])


def format_widths(widths_list):
    """
    Форматирует список участков с шириной в краткий диапазон.

    Принимает: widths_list - список участков из API
        Пример: [
            {"start": "0+000", "finish": "7+740", "roadway_width": 6.0},
            {"start": "10+000", "finish": "56+700", "roadway_width": 7.0}
        ]

    Возвращает: str - диапазон ширин
        Примеры:
            - Если все ширины одинаковые: "6,0"
            - Если разные: "6,0-7,0"
            - Если нет данных: ""
    """
    if not widths_list:
        return ""

    # Собираем все значения ширины
    widths = []
    for w in widths_list:
        width = w.get('roadway_width')
        if width is not None:
            widths.append(width)

    if not widths:
        return ""

    min_w = min(widths)
    max_w = max(widths)

    # Форматируем с запятой вместо точки
    if min_w == max_w:
        return f"{min_w:.1f}".replace('.', ',')
    else:
        return f"{min_w:.1f}-{max_w:.1f}".replace('.', ',')


def format_road_segments(widths_list):
    """
    Форматирует список участков дороги в детальную многострочную строку.

    Принимает: widths_list - список участков из API
        Пример: [
            {"start": "0+000", "finish": "7+740", "roadway_width": 6.0},
            {"start": "10+000", "finish": "56+700", "roadway_width": 7.0}
        ]

    Возвращает: str - многострочная строка с перечислением участков
        Пример: "Участки:\n1. 0+000 - 7+740 (6,0 м)\n2. 10+000 - 56+700 (7,0 м)"
    """
    if not widths_list:
        return ""

    lines = ["Участки:"]

    for i, w in enumerate(widths_list, 1):
        start = w.get('start', '?')
        finish = w.get('finish', '?')
        width = w.get('roadway_width')

        if width is None:
            width_str = "?"
        else:
            width_str = f"{width:.1f}".replace('.', ',')

        lines.append(f"{i}. {start} - {finish} ({width_str} м)")

    return '\n'.join(lines)


def get_km_posts_raw(part_id):
    """
    Получает сырые данные километровых столбов для part_id.

    Принимает: part_id (int) - из road_part_id в GDF

    Возвращает: list of dict - каждый dict с полями:
        id, number, latitude, longitude, location, distance_to_prev

    Пример возвращаемого значения:
        [
            {
                "id": 440452305,
                "number": 0,
                "latitude": 50.85415,
                "longitude": 128.660539,
                "location": "0+000",
                "distance_to_prev": 1000
            },
            {
                "id": 440452306,
                "number": 1,
                "latitude": 50.85408,
                "longitude": 128.646338,
                "location": "1+000",
                "distance_to_prev": 1000
            }
        ]
    """
    all_posts = []
    offset = 0
    limit = 100

    while True:
        url = f"{BASE_URL}/api/v3/portal/hwm/passports/parts/{part_id}/km-posts?limit={limit}&offset={offset}"
        response = _make_request_with_retry(
            'GET', url, headers=HEADERS_PASSPORT)

        if not response or response.status_code != 200:
            break

        data = response.json()
        posts = data.get('data', [])

        if not posts:
            break

        all_posts.extend(posts)

        total = data.get('total', 0)
        offset += limit
        if offset >= total:
            break

    return all_posts


# ============================================================================
# ТЕСТОВЫЙ БЛОК (имитация main.py)
# ============================================================================
if __name__ == "__main__":
    import time
    import pandas as pd
    import geopandas as gpd
    from shapely.geometry import box
    from coord_utils import build_bbox, convert_bbox_to_skdf

    print("\n=== Тест skdf_api.py (имитация main.py) ===\n")

    # ===== ЖЁСТКИЕ КООРДИНАТЫ для теста =====
    lat1, lon1 = 51.57265666666667, 128.18730294444444   # северо-запад
    lat2, lon2 = 51.48442825, 128.40428294444445        # юго-восток
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

    # 3. Добавляем категорию
    gdf['категория'] = gdf['value_of_the_road'].apply(get_category)
    print(f"   Категории: {gdf['категория'].unique()}")

    # 4. Получаем passport_id для всех дорог
    print("\n4. Получение passport_id...")
    gdf['passport_id'] = gdf['road_id'].apply(get_passport_id)
    print(
        f"   passport_id получен для {gdf['passport_id'].notna().sum()} дорог")

    # 5. Получаем сегменты для всех дорог (нужно для ширины и столбов)
    print("\n5. Получение сегментов roadway...")
    gdf['segment_passport_ids'] = gdf['passport_id'].apply(
        get_roadway_segments)
    print(f"   Сегменты получены")

    # 6. Получаем километровые столбы для федеральных дорог
    print("\n6. Получение километровых столбов...")

    # Фильтруем федеральные дороги
    gdf_federal = gdf[gdf['категория'] == 'федеральные'].copy()
    print(f"   Федеральных дорог: {len(gdf_federal)}")

    gdf_km_posts = None

    if len(gdf_federal) > 0:
        def get_km_posts_for_segments(seg_ids):
            all_posts = []
            for seg_id in seg_ids:
                posts = get_km_posts_raw(seg_id)
                all_posts.extend(posts)
            return all_posts

        gdf_federal['km_posts_raw'] = gdf_federal['segment_passport_ids'].apply(
            get_km_posts_for_segments)

        # Собираем все столбы в отдельный список
        km_posts_list = []
        for idx, row in gdf_federal.iterrows():
            for post in row['km_posts_raw']:
                km_posts_list.append({
                    'road_id': row['road_id'],
                    'road_name': row['road_name'],
                    'number': post.get('number'),
                    'location': post.get('location'),
                    'latitude': post.get('latitude'),
                    'longitude': post.get('longitude'),
                })

        # Создаём GeoDataFrame с точками
        if km_posts_list:
            gdf_km_posts = gpd.GeoDataFrame(
                km_posts_list,
                geometry=gpd.points_from_xy(
                    [p['longitude'] for p in km_posts_list],
                    [p['latitude'] for p in km_posts_list]
                ),
                crs="EPSG:4326"
            )
            print(f"   Всего километровых столбов: {len(gdf_km_posts)}")
            if len(gdf_km_posts) > 0:
                print(
                    f"   Пример столба: {gdf_km_posts[['road_name', 'number', 'location']].iloc[0].to_dict()}")
        else:
            print("   Столбы не найдены")
    else:
        print("   Нет федеральных дорог, столбы не получены")

    # 7. Выводим итоговую информацию
    print("\n7. ИТОГИ:")
    print(f"   Дорог всего: {len(gdf)}")
    print(f"   Колонки в gdf: {list(gdf.columns)}")

    if gdf_km_posts is not None and len(gdf_km_posts) > 0:
        print(f"   Километровых столбов: {len(gdf_km_posts)}")
        print(f"   Колонки в gdf_km_posts: {list(gdf_km_posts.columns)}")
    else:
        print("   Километровые столбы: не получены")

    print(f"\n✅ Тест завершён")
