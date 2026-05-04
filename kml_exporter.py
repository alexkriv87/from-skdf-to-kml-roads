# kml_exporter.py
# Модуль для экспорта GeoDataFrame в KML-файл (совместимый с SAS.Планет)

# kml_exporter.py
# Модуль для экспорта GeoDataFrame в KML-файл (совместимый с SAS.Планет)

from pathlib import Path
from collections import defaultdict
import pandas as pd
from logger_config import logger
from config import COLORS_KML, LINE_WIDTH, DESCRIPTION_TEMPLATE, CATEGORY_TO_PLACEHOLDER
from skdf_api import (
    fetch_roads_raw, features_to_gdf, get_passport_id,
    get_road_characteristics, get_category,
    get_roadway_width_segments, get_roadway_widths_json,
    format_widths_segments, format_road_widths,
    get_axle_load_segments, get_axle_loads_json,
    format_axle_load, format_axle_load_segments,
    get_km_posts_raw
)


# ============================================================================
# ЗАГРУЗКА ШАБЛОНОВ
# ============================================================================

def _load_template(template_name):
    """Загружает шаблон из файла."""
    template_path = Path(__file__).parent / template_name
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


PLACEMARK_LINE_TEMPLATE = _load_template("template_road_placemark.kml")
PLACEMARK_MULTILINE_TEMPLATE = _load_template(
    "template_road_placemark_multiline.kml")
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
        value = row.get(field_name)
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
    description_parts = [
        f"Километр: {row['number']}",
        f"Пикетаж: {row['location']}",
        f"Дорога: {row.get('road_name', 'Неизвестно')}",
        f"Расстояние до предыдущего: {row.get('distance_to_prev', '?')} м"
    ]
    description = '&#xa;'.join(description_parts)

    return f"""
    <Placemark>
      <name>km {row['number']}</name>
      <description>{description}</description>
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
    from datetime import datetime
    from coord_utils import build_bbox, convert_bbox_to_skdf
    from skdf_api import (
        fetch_roads_raw, features_to_gdf, get_category, get_passport_id,
        get_road_characteristics,
        get_roadway_width_segments, get_roadway_widths_json,
        format_widths_segments, format_road_widths,
        get_axle_load_segments, get_axle_loads_json,
        format_axle_load, format_axle_load_segments,
        get_km_posts_raw
    )
    from kml_exporter import update_kml, MAIN_TEMPLATE

    print("\n=== Тест kml_exporter.py (имитация main.py) ===\n")

    # ===== ЖЁСТКИЕ КООРДИНАТЫ для теста =====
    lat1, lon1 = 51.57265666666667, 128.18730294444444
    lat2, lon2 = 51.48442825, 128.40428294444445
    print(f"Тестовые координаты: NW({lat1}, {lon1}), SE({lat2}, {lon2})")

    # Строим bbox
    bbox_degrees = build_bbox((lat1, lon1), (lat2, lon2))
    bbox_meters = convert_bbox_to_skdf(bbox_degrees)
    print(f"Bbox: {bbox_degrees} -> {bbox_meters}")

    total_start = time.time()

    # 1. Загружаем дороги
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

    # 3. Добавляем колонку категории
    gdf['категория'] = gdf['value_of_the_road'].apply(get_category)
    print(f"Категории: {gdf['категория'].unique()}")

    # 4. Получаем passport_id для всех дорог
    start = time.time()
    gdf['passport_id'] = gdf['road_id'].apply(get_passport_id)
    print(
        f"passport_id получен для {gdf['passport_id'].notna().sum()} дорог за {time.time()-start:.1f} сек")

    # 5. Обогащение характеристиками
    start = time.time()
    gdf['characteristics'] = gdf['passport_id'].apply(get_road_characteristics)
    chars_df = pd.DataFrame(gdf['characteristics'].to_list())
    chars_df['road_id'] = gdf['road_id'].values
    gdf = pd.merge(
        gdf.drop(columns=['characteristics']),
        chars_df,
        on='road_id',
        how='left'
    )
    print(f"Обогащение характеристиками за {time.time()-start:.1f} сек")

    # 6. Получаем ширину
    start = time.time()
    gdf['segment_passport_ids'] = gdf['passport_id'].apply(
        get_roadway_width_segments)

    def get_all_widths_json(segment_ids):
        all_widths = []
        for seg_id in segment_ids:
            widths = get_roadway_widths_json(seg_id)
            all_widths.extend(widths)
        return all_widths

    gdf['widths_json'] = gdf['segment_passport_ids'].apply(get_all_widths_json)
    gdf['Ширина:'] = gdf['widths_json'].apply(format_widths_segments)
    gdf['Участки ширины:'] = gdf['widths_json'].apply(format_road_widths)
    print(
        f"Ширина добавлена для {gdf['Ширина:'].notna().sum()} дорог за {time.time()-start:.1f} сек")

    # 7. Получаем осевую нагрузку
    start = time.time()
    gdf['axle_segments'] = gdf['passport_id'].apply(get_axle_load_segments)

    def get_all_axle_loads(segment_ids):
        all_loads = []
        for seg_id in segment_ids:
            loads = get_axle_loads_json(seg_id)
            all_loads.extend(loads)
        return all_loads

    gdf['axle_loads_json'] = gdf['axle_segments'].apply(get_all_axle_loads)
    gdf['Осевая нагрузка:'] = gdf['axle_loads_json'].apply(format_axle_load)
    gdf['Участки нагрузки:'] = gdf['axle_loads_json'].apply(
        format_axle_load_segments)
    print(
        f"Осевая нагрузка добавлена для {gdf['Осевая нагрузка:'].notna().sum()} дорог за {time.time()-start:.1f} сек")

    # 8. Конвертация геометрии в градусы
    start = time.time()
    gdf = gdf.to_crs("EPSG:4326")
    gdf['geometry_deg'] = gdf.geometry
    print(f"Конвертация геометрии за {time.time()-start:.1f} сек")

    # 9. Получение километровых столбов для федеральных дорог
    print("\n9. Получение километровых столбов...")
    gdf_federal = gdf[gdf['категория'] == 'федеральные'].copy()
    all_dfs = []

    for idx, row in gdf_federal.iterrows():
        road_id = row['road_id']
        road_name = row['road_name']
        segment_ids = row['segment_passport_ids']

        for seg_id in segment_ids:
            posts_raw = get_km_posts_raw(seg_id)
            if posts_raw:
                df = pd.DataFrame(posts_raw)
                df['road_id'] = road_id
                df['road_name'] = road_name
                all_dfs.append(df)

    if all_dfs:
        df_km_posts = pd.concat(all_dfs, ignore_index=True)
        gdf_km_posts = gpd.GeoDataFrame(
            df_km_posts,
            geometry=gpd.points_from_xy(
                df_km_posts['longitude'], df_km_posts['latitude']),
            crs="EPSG:4326"
        )
        print(f"   Всего километровых столбов: {len(gdf_km_posts)}")
    else:
        gdf_km_posts = None
        print("   Федеральные дороги не найдены")

    # 10. Формируем KML
    print("\n10. Формирование KML...")
    kml_str = MAIN_TEMPLATE
    kml_str = update_kml(None, kml_str, mode="init",
                         top_folder_name="Тестовый участок")

    # Обычные категории
    for cat in ["федеральные", "региональные", "частные", "лесные", "ведомственные"]:
        gdf_cat = gdf[gdf['категория'] == cat]
        if not gdf_cat.empty:
            kml_str = update_kml(gdf_cat, kml_str, mode="roads", category=cat)

    # Местные (отдельно, с группировкой по владельцам)
    gdf_local = gdf[gdf['категория'] == 'местные']
    if not gdf_local.empty:
        kml_str = update_kml(gdf_local, kml_str,
                             mode="roads", category="местные")

    # Километровые столбы
    if gdf_km_posts is not None and not gdf_km_posts.empty:
        kml_str = update_kml(gdf_km_posts, kml_str, mode="points")

    # 11. Сохраняем в файл
    output_file = f"roads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(kml_str)
    print(f"   KML файл: {output_file}")
    print(f"   Всего дорог: {len(gdf)}")
    if gdf_km_posts is not None:
        print(f"   Всего столбов: {len(gdf_km_posts)}")

    total_time = time.time() - total_start
    print(f"\n✅ Общее время: {total_time:.1f} сек")
