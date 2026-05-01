# kml_exporter.py
# Модуль для экспорта GeoDataFrame в KML-файл (совместимый с SAS.Планет)

from pathlib import Path
from collections import defaultdict
from logger_config import logger
from config import COLORS_KML, LINE_WIDTH, DESCRIPTION_TEMPLATE


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


# ============================================================================
# ОСНОВНАЯ ФУНКЦИЯ ЭКСПОРТА
# ============================================================================

def save_to_kml(gdf, output_path, top_folder_name="СКДФ Дороги"):
    """
    Сохраняет GeoDataFrame в KML-файл (структура как у SAS.Планет).

    Ожидает, что в gdf есть колонка 'категория' с русскими значениями:
    федеральные, региональные, местные, частные, лесные, ведомственные.
    И колонка 'geometry_deg' с Shapely-геометрией в градусах (EPSG:4326).
    """
    # Проверка наличия обязательных колонок
    if 'категория' not in gdf.columns:
        logger.error("Отсутствует колонка 'категория' в GeoDataFrame")
        return False

    try:
        # 1. Группируем дороги по категории
        roads_by_category = defaultdict(list)

        for idx, row in gdf.iterrows():
            category = row.get('категория')
            if category:
                placemark = _make_placemark(row, category)
                roads_by_category[category].append(placemark)

        # 2. Маппинг русских категорий на английские плейсхолдеры
        category_to_placeholder = {
            "федеральные": "federal",
            "региональные": "regional",
            "местные": "local",
            "частные": "private",
            "лесные": "forest",
            "ведомственные": "departmental",
        }

        # 3. Формируем kwargs для format()
        format_kwargs = {"top_folder_name": top_folder_name}
        for russian_key, english_key in category_to_placeholder.items():
            format_kwargs[english_key] = '\n'.join(
                roads_by_category.get(russian_key, []))

        # 4. Заполняем шаблон
        kml_str = MAIN_TEMPLATE.format(**format_kwargs)

        # 5. Сохраняем в файл
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(kml_str)

        logger.info(f"KML сохранён: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Ошибка сохранения KML: {e}")
        return False


# ============================================================================
# ТЕСТОВЫЙ БЛОК
# ============================================================================
if __name__ == "__main__":
    import time
    import pandas as pd
    import geopandas as gpd
    from shapely.geometry import box
    from datetime import datetime

    print("\n=== Тест kml_exporter.py ===\n")

    from skdf_api import fetch_roads_raw, features_to_gdf, get_passport_id, get_road_characteristics, get_category

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

    # 4. Добавляем колонку категории
    gdf['категория'] = gdf['value_of_the_road'].apply(get_category)
    print(f"Категории: {gdf['категория'].unique()}")

    # 5. Конвертация геометрии в градусы
    start = time.time()
    gdf = gdf.to_crs("EPSG:4326")
    gdf['geometry_deg'] = gdf.geometry
    print(f"Конвертация геометрии: {time.time()-start:.1f} сек")

    # 6. Сохраняем в KML
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
