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
    Поддерживает LineString и MultiLineString.
    """
    geometry_deg = row.get('geometry_deg')
    if geometry_deg is None:
        return ""

    geom_type = geometry_deg.geom_type

    if geom_type == 'LineString':
        # Формируем координаты для одной линии
        coord_lines = []
        for point in geometry_deg.coords:
            coord_lines.append(f"{point[0]},{point[1]},0")
        coordinates_str = ' '.join(coord_lines)

        return PLACEMARK_LINE_TEMPLATE.format(
            name=row.get('road_name', 'Без названия'),
            description=_build_description(row),
            color=_get_color(category),
            width=LINE_WIDTH,
            coordinates=coordinates_str
        )

    elif geom_type == 'MultiLineString':
        # Формируем отдельные LineString для каждой линии
        line_strings = []
        for line in geometry_deg.geoms:
            coord_lines = []
            for point in line.coords:
                coord_lines.append(f"{point[0]},{point[1]},0")
            coordinates_str = ' '.join(coord_lines)
            line_strings.append(f"""
    <LineString>
      <extrude>1</extrude>
      <coordinates>{coordinates_str}</coordinates>
    </LineString>""")

        return PLACEMARK_MULTILINE_TEMPLATE.format(
            name=row.get('road_name', 'Без названия'),
            description=_build_description(row),
            color=_get_color(category),
            width=LINE_WIDTH,
            line_strings=''.join(line_strings)
        )

    else:
        # Неподдерживаемый тип геометрии
        logger.warning(
            f"Неподдерживаемый тип геометрии: {geom_type}, дорога: {row.get('road_name', 'неизвестная')}")
        return ""


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
