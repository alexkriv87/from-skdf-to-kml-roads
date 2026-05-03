# kml_exporter.py
# Модуль для экспорта GeoDataFrame в KML-файл (совместимый с SAS.Планет)

from pathlib import Path
from collections import defaultdict
import pandas as pd
from logger_config import logger
from config import COLORS_KML, LINE_WIDTH, DESCRIPTION_TEMPLATE, CATEGORY_TO_PLACEHOLDER


# ============================================================================
# ЗАГРУЗКА ШАБЛОНОВ
# ============================================================================

def _load_template(template_name):
    """Загружает шаблон из файла."""
    template_path = Path(__file__).parent / template_name
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


PLACEMARK_TEMPLATE = _load_template("template_road_placemark.kml")
MAIN_TEMPLATE = _load_template("template_all_roads.kml")


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _build_description(row):
    """
    Формирует текст description из строки GeoDataFrame.

    Пример входа: {"Категория:": "IV", "Покрытие:": "Асфальтобетон"}
    Пример выхода: "Категория: IV\nПокрытие: Асфальтобетон"
    """
    lines = []
    for field_name in DESCRIPTION_TEMPLATE:
        # Удалить print
        print(f'field_name = {field_name}')

        value = row.get(field_name)
        # Удалить print
        print(f'value = {value}')

        if value and str(value) != 'nan':
            lines.append(f"{field_name} {value}")
    return '\n'.join(lines)


def _get_color(category):
    """
    Возвращает цвет для категории.

    Пример входа: "федеральные"
    Пример выхода: "FF53A9FF"
    """
    return COLORS_KML.get(category, COLORS_KML.get("неизвестно", "FF888888"))


def _make_placemark(row, category):
    """
    Создаёт XML-строку Placemark для одной дороги.
    """
    geometry_deg = row.get('geometry_deg')
    coord_lines = []

    if geometry_deg is not None:
        geom_type = geometry_deg.geom_type

        if geom_type == 'LineString':
            for point in geometry_deg.coords:
                coord_lines.append(f"{point[0]},{point[1]},0")
        elif geom_type == 'MultiLineString':
            for line in geometry_deg.geoms:
                for point in line.coords:
                    coord_lines.append(f"{point[0]},{point[1]},0")

    coordinates_str = ' '.join(coord_lines)

    return PLACEMARK_TEMPLATE.format(
        name=row.get('road_name', 'Без названия'),
        description=_build_description(row),
        color=_get_color(category),
        width=LINE_WIDTH,
        coordinates=coordinates_str
    )


def _group_local_roads_by_owner(gdf_local):
    """
    Группирует местные дороги по владельцам.

    Принимает: GeoDataFrame с местными дорогами (категория = "местные")
    Возвращает: XML-строку с подпапками владельцев
    """
    if gdf_local.empty:
        return ""

    # Группируем по колонке "Принадлежность:"
    owners = gdf_local.groupby('Принадлежность:')

    # Сортируем владельцев по алфавиту
    sorted_owners = sorted(owners.groups.keys())

    folders = []
    for owner in sorted_owners:
        if not owner or pd.isna(owner):
            owner_name = "_Владелец не известен"
        else:
            owner_name = owner

        group = owners.get_group(owner)

        placemarks = []
        for idx, row in group.iterrows():
            placemark = _make_placemark(row, "местные")
            placemarks.append(placemark)

        folder_xml = f"""
        <Folder>
          <name>{owner_name}</name>
          <open>1</open>
          <Style>
            <ListStyle>
              <listItemType>check</listItemType>
              <bgColor>00ffffff</bgColor>
            </ListStyle>
          </Style>
          {''.join(placemarks)}
        </Folder>
        """
        folders.append(folder_xml)

    return '\n'.join(folders)


def _group_km_posts_by_road(gdf_km_posts):
    """
    Группирует километровые столбы по названиям дорог.

    Принимает: GeoDataFrame с точками (столбами), содержащий колонку 'road_name'
    Возвращает: XML-строку с подпапками дорог, внутри которых Placemark'и столбов
    """
    if gdf_km_posts.empty:
        return ""

    # Группируем по названию дороги
    grouped = gdf_km_posts.groupby('road_name')

    # Сортируем дороги по алфавиту
    sorted_roads = sorted(grouped.groups.keys())

    folders = []
    for road_name in sorted_roads:
        group = grouped.get_group(road_name)

        point_placemarks = []
        for idx, row in group.iterrows():
            point_placemarks.append(_make_point_placemark(row))

        folder_xml = f"""
        <Folder>
          <name>{road_name}</name>
          <open>1</open>
          <Style>
            <ListStyle>
              <listItemType>check</listItemType>
              <bgColor>00ffffff</bgColor>
            </ListStyle>
          </Style>
          {''.join(point_placemarks)}
        </Folder>
        """
        folders.append(folder_xml)

    return '\n'.join(folders)


# ============================================================================
# ОСНОВНАЯ ФУНКЦИЯ ЭКСПОРТА
# ============================================================================
def update_kml(gdf, kml_str, mode, category=None, top_folder_name=None):
    """
    Обновляет KML-строку: заменяет плейсхолдеры на данные из gdf.

    Параметры:
        gdf: GeoDataFrame (дороги или столбы)
        kml_str: текущая KML-строка
        mode: "init" | "roads" | "points"
        category: для mode="roads" - категория дорог
        top_folder_name: для mode="init" - имя верхней папки

    Возвращает:
        kml_str: обновлённая KML-строка
    """
    if mode == "init":
        if top_folder_name is None:
            raise ValueError(
                "Для mode='init' необходимо указать top_folder_name")
        return kml_str.replace("{top_folder_name}", top_folder_name)

    elif mode == "roads":
        if category is None:
            raise ValueError("Для mode='roads' необходимо указать category")

        placeholder = CATEGORY_TO_PLACEHOLDER.get(category)
        if placeholder is None:
            raise ValueError(f"Неизвестная категория: {category}")

        if category == "местные":
            placemarks_xml = _group_local_roads_by_owner(gdf)
        else:
            # Обычные категории
            placemarks_list = []
            for idx, row in gdf.iterrows():
                placemark = _make_placemark(row, category)
                placemarks_list.append(placemark)
            placemarks_xml = '\n'.join(placemarks_list)

        return kml_str.replace(f"{{{placeholder}}}", placemarks_xml)

    elif mode == "points":
        km_posts_xml = _group_km_posts_by_road(gdf)
        return kml_str.replace("{km_posts}", km_posts_xml)

    else:
        raise ValueError(f"Неизвестный mode: {mode}")


def _make_point_placemark(row):
    """
    Создаёт Placemark для точки (километрового столба).

    Принимает: строку из gdf_km_posts с колонками: number, location, longitude, latitude
    Возвращает: XML-строку Placemark
    """
    return f"""
    <Placemark>
      <name>km {row['number']}</name>
      <description>Пикетаж: {row['location']}</description>
      <Point>
        <coordinates>{row['longitude']},{row['latitude']},0</coordinates>
      </Point>
    </Placemark>
    """


# ============================================================================
# ТЕСТОВЫЙ БЛОК (имитация main.py)
# ============================================================================
if __name__ == "__main__":
    import time
    import pandas as pd
    import geopandas as gpd
    from shapely.geometry import box
    from coord_utils import build_bbox, convert_bbox_to_skdf
    from skdf_api import (
        fetch_roads_raw, features_to_gdf, get_category, get_passport_id,
        get_road_characteristics, get_roadway_segments, get_roadway_widths_json,
        format_widths, format_road_segments
    )

    print("\n=== Тест skdf_api.py (имитация main.py) ===\n")

    # ===== ЖЁСТКИЕ КООРДИНАТЫ для теста =====
    lat1, lon1 = 51.57265666666667, 128.18730294444444
    lat2, lon2 = 51.48442825, 128.40428294444445
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

    # 5. Обогащение характеристиками
    print("\n5. Обогащение характеристиками...")
    gdf['characteristics'] = gdf['passport_id'].apply(get_road_characteristics)
    chars_df = pd.DataFrame(gdf['characteristics'].to_list())
    chars_df['road_id'] = gdf['road_id'].values
    gdf = pd.merge(
        gdf.drop(columns=['characteristics']),
        chars_df,
        on='road_id',
        how='left'
    )

    # 6. Получаем ширину
    print("\n6. Получение ширины...")
    gdf['segment_passport_ids'] = gdf['passport_id'].apply(
        get_roadway_segments)

    def get_all_widths_json(segment_ids):
        all_widths = []
        for seg_id in segment_ids:
            widths = get_roadway_widths_json(seg_id)
            all_widths.extend(widths)
        return all_widths

    gdf['widths_json'] = gdf['segment_passport_ids'].apply(get_all_widths_json)
    gdf['Ширина:'] = gdf['widths_json'].apply(format_widths)
    gdf['Участки:'] = gdf['widths_json'].apply(format_road_segments)

    # ========== ПЕЧАТАЕМ ВСЕ СТРОКИ УЧАСТКОВ ==========
    print("\n=== ВСЕ ЗНАЧЕНИЯ 'Участки:' В GDF ===")
    for idx, value in gdf['Участки:'].items():
        print(f"Строка {idx}:")
        print(repr(value))
        print("-" * 50)

    print(f"   Ширина добавлена для {gdf['Ширина:'].notna().sum()} дорог")

    # ========== ПРОВЕРКА _build_description ДЛЯ ВСЕХ ДОРОГ ==========
    print("\n=== ПРОВЕРКА _build_description ДЛЯ ВСЕХ ДОРОГ ===")
    for idx, row in gdf.iterrows():
        desc = _build_description(row)
        print(
            f"Строка {idx}, road_name: {row.get('road_name', 'N/A')[:50]}...")
        print(f"  РЕЗУЛЬТАТ _build_description (полностью):")
        print(desc)
        print("-" * 50)
