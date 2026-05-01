# kml_exporter.py
# Модуль для экспорта GeoDataFrame в KML-файл (совместимый с SAS.Планет)
#
# ВНИМАНИЕ: Функция save_to_kml() ожидает, что в gdf уже есть колонка 'geometry_deg'
#          с геометрией в градусах (EPSG:4326) в формате списка линий.
#          Подготовку данных (конвертацию) нужно выполнить ДО вызова save_to_kml().

import xml.etree.ElementTree as ET
from logger_config import logger
from config import COLORS_KML, LINE_WIDTH, DESCRIPTION_TEMPLATE


# ============================================================================
# ОСНОВНАЯ ФУНКЦИЯ ЭКСПОРТА (API)
# ============================================================================

def save_to_kml(gdf, output_path, top_folder_name="СКДФ Дороги"):
    """
    Сохраняет GeoDataFrame в KML-файл (структура как у SAS.Планет).

    Параметры:
        gdf: GeoDataFrame с дорогами.
             ДОЛЖЕН содержать колонку 'geometry_deg' с геометрией в градусах
             в формате: список линий, каждая линия - список [lon, lat]
        output_path: полный путь к выходному файлу (.kml)
        top_folder_name: имя верхней папки-обёртки

    Возвращает:
        bool: True при успехе, False при ошибке
    """
    try:
        kml = _build_kml_tree(gdf, top_folder_name)
        _write_kml_file(kml, output_path)
        logger.info(f"KML сохранён: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Ошибка сохранения KML: {e}")
        return False


# ============================================================================
# ПОСТРОЕНИЕ KML-СТРУКТУРЫ
# ============================================================================

def _build_kml_tree(gdf, top_folder_name):
    """
    Строит ElementTree всей KML-структуры (без записи на диск).

    Параметры:
        gdf: GeoDataFrame с дорогами (должен содержать колонку 'geometry_deg')
        top_folder_name: имя верхней папки-обёртки

    Возвращает:
        Element: корневой элемент kml
    """
    # 1. Создаём корневой элемент с namespace Google Earth
    kml = ET.Element("kml", xmlns="http://earth.google.com/kml/2.2")
    document = ET.SubElement(kml, "Document")

    # 2. Создаём верхнюю папку-обёртку
    top_folder = _add_folder(document, top_folder_name, "1")

    # 3. Создаём папку "Дороги"
    roads_folder = _add_folder(top_folder, "1. Дороги", "1")

    # 4. Определяем соответствие value_of_the_road -> имя папки
    folder_mapping = {
        "федерального": "1. Федеральные",
        "регионального": "2. Региональные",
        "местного": "3. Местные",
        "частные": "4. Частные",
        "лесные": "5. Лесные",
        "ведомственные": "6. Ведомственные"
    }

    # 5. Словарь для хранения созданных папок
    folders = {}

    # 6. Проходим по всем дорогам и раскладываем по папкам
    for idx, row in gdf.iterrows():
        ownership = row.get('value_of_the_road', '')
        ownership_lower = str(ownership).lower()

        # Определяем имя папки
        folder_name = None
        for key, name in folder_mapping.items():
            if key in ownership_lower:
                folder_name = name
                break

        # Если не определили - в "3. Местные" по умолчанию
        if not folder_name:
            folder_name = "3. Местные"

        # Создаём папку, если ещё не создана
        if folder_name not in folders:
            folders[folder_name] = _add_folder(roads_folder, folder_name, "1")

        # Добавляем дорогу (geometry_deg уже есть в gdf)
        _add_road_placemark(folders[folder_name], row)

    # 7. Создаём недостающие пустые папки (для красоты)
    all_needed_folders = ["1. Федеральные", "2. Региональные", "3. Местные",
                          "4. Частные", "5. Лесные", "6. Ведомственные"]
    for folder_name in all_needed_folders:
        if folder_name not in folders:
            _add_empty_folder(roads_folder, folder_name)

    # 8. Создаём папку "4. Точки интереса" (пока пустую, как заготовку)
    poi_folder = _add_folder(top_folder, "4. Точки интереса", "1")
    _add_empty_folder(poi_folder, "Точки интереса")

    return kml


# ============================================================================
# ЗАПИСЬ KML-ФАЙЛА НА ДИСК
# ============================================================================

def _write_kml_file(kml, output_path):
    """
    Записывает KML-дерево в файл.

    Параметры:
        kml: корневой элемент kml
        output_path: полный путь к выходному файлу (.kml)
    """
    tree = ET.ElementTree(kml)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (в порядке вызова из основной)
# ============================================================================

def _add_folder(parent, name, open_state="1"):
    """
    Создаёт папку с именем, open и ListStyle.

    Параметры:
        parent: родительский элемент
        name: имя папки
        open_state: состояние открытия ("1" - открыта, "0" - закрыта)

    Возвращает:
        Element: созданная папка
    """
    folder = ET.SubElement(parent, "Folder")
    ET.SubElement(folder, "name").text = name
    ET.SubElement(folder, "open").text = open_state
    _add_list_style(folder)
    return folder


def _add_list_style(parent):
    """Добавляет ListStyle в папку (check-список, как в SAS.Планет)."""
    style = ET.SubElement(parent, "Style")
    list_style = ET.SubElement(style, "ListStyle")
    ET.SubElement(list_style, "listItemType").text = "check"
    ET.SubElement(list_style, "bgColor").text = "00ffffff"


def _add_road_placemark(parent, row):
    """
    Добавляет дорогу как Placemark с вложенным стилем (как в SAS.Планет).
    """
    placemark = ET.SubElement(parent, "Placemark")

    # Название
    ET.SubElement(placemark, "name").text = row.get(
        'road_name', 'Без названия')

    # Описание
    description_text = _build_description(row)
    if description_text:
        ET.SubElement(placemark, "description").text = description_text

    # Стиль (вложенный, как в SAS.Планет)
    style = ET.SubElement(placemark, "Style")
    line_style = ET.SubElement(style, "LineStyle")

    ownership = row.get('value_of_the_road', '')
    color = _get_color_from_ownership(ownership)
    ET.SubElement(line_style, "color").text = color
    ET.SubElement(line_style, "width").text = str(LINE_WIDTH)

    # Геометрия (берём из подготовленной колонки geometry_deg)
    geometry_deg = row.get('geometry_deg')
    _add_geometry(placemark, geometry_deg, row.get('road_name', 'неизвестной'))


def _build_description(row):
    """Формирует текст description из строки GeoDataFrame."""
    lines = []
    for field_key, field_label in DESCRIPTION_TEMPLATE:
        value = row.get(field_key)
        if value and str(value) != 'nan':
            lines.append(f"{field_label} {value}")
    return '\n'.join(lines)


def _get_color_from_ownership(ownership):
    """
    Возвращает цвет в формате KML (AABBGGRR) по принадлежности дороги.
    """
    ownership_lower = str(ownership).lower()

    if "федерального" in ownership_lower:
        return COLORS_KML.get("style_federal", "FF53A9FF")
    elif "регионального" in ownership_lower:
        return COLORS_KML.get("style_regional", "FFFFECCC")
    elif "местного" in ownership_lower:
        return COLORS_KML.get("style_local", "FFCCCCFF")
    else:
        return COLORS_KML.get("style_unknown", "FF888888")


def _add_geometry(placemark, geometry_deg, road_name="неизвестной"):
    """
    Добавляет геометрию (уже в градусах) в Placemark.

    Параметры:
        placemark: элемент Placemark
        geometry_deg: геометрия в градусах (список линий, каждая линия - список [lon, lat])
        road_name: название дороги (для логов)
    """
    if not geometry_deg:
        return

    try:
        line_string = ET.SubElement(placemark, "LineString")
        ET.SubElement(line_string, "extrude").text = "1"
        coordinates = ET.SubElement(line_string, "coordinates")

        coord_lines = []
        for line in geometry_deg:
            for point in line:
                lon, lat = point
                coord_lines.append(f"{lon},{lat},0")

        coordinates.text = ' '.join(coord_lines)

    except Exception as e:
        logger.warning(
            f"Ошибка добавления геометрии для дороги {road_name}: {e}")


def _add_empty_folder(parent, name):
    """Создаёт пустую папку (для частных, лесных, ведомственных и т.д.)."""
    return _add_folder(parent, name)


# ============================================================================
# ТЕСТОВЫЙ БЛОК (имитация main.py)
# ============================================================================
if __name__ == "__main__":
    import time
    import pandas as pd
    from shapely.geometry import box
    from datetime import datetime

    print("\n=== Тест kml_exporter.py ===\n")

    from skdf_api import fetch_roads_raw, features_to_gdf, get_passport_id, get_road_characteristics
    from geometry_funcs import geometry_meters_to_degrees

    # ===== ЖЁСТКИЕ КООРДИНАТЫ для теста =====
    bbox_meters = [5970482.543307837, 9237349.770030644,
                   5979941.6263704365, 9244439.304687222]
    print(f"Bbox (метры): {bbox_meters}")

    total_start = time.time()

    # 1. Загрузка дорог
    start = time.time()
    features = fetch_roads_raw(bbox_meters, zoom=14)
    gdf = features_to_gdf(features)
    print(f"Загружено: {len(gdf)} дорог за {time.time()-start:.1f} сек")

    # 2. Фильтрация по bbox
    start = time.time()
    search_bbox = box(*bbox_meters)
    gdf = gdf[gdf['geometry'].apply(
        lambda geom: geom.intersects(search_bbox))].copy()
    print(f"После фильтрации: {len(gdf)} дорог за {time.time()-start:.1f} сек")

    # 3. Обогащение характеристиками
    start = time.time()
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
    print(
        f"Обогащение: {gdf['passport_id'].notna().sum()} / {len(gdf)} дорог за {time.time()-start:.1f} сек")

    # 4. ПОДГОТОВКА ГЕОМЕТРИИ (конвертация метров → градусы)
    start = time.time()
    gdf['geometry_deg'] = gdf['geometry'].apply(geometry_meters_to_degrees)
    print(f"Конвертация геометрии: {time.time()-start:.1f} сек")

    # 5. Сохраняем в KML
    start = time.time()
    output_file = f"roads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
    if save_to_kml(gdf, output_file, top_folder_name="Тестовый участок"):
        print(f"   KML файл: {output_file}")
        print(f"   Всего дорог: {len(gdf)}")
    else:
        print("   ❌ Ошибка сохранения KML")
    print(f"Сохранение KML: {time.time()-start:.1f} сек")

    total_time = time.time() - total_start
    print(f"\n✅ Общее время: {total_time:.1f} сек")
