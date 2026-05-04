# main.py
# Основной скрипт для выгрузки дорог из СКДФ в KML

import time
import pandas as pd
import geopandas as gpd
from shapely.geometry import box
from datetime import datetime

from coord_utils import parse_coordinate, build_bbox, convert_bbox_to_skdf
from skdf_api import (
    fetch_roads_raw, features_to_gdf, get_passport_id,
    get_road_characteristics, get_category,
    get_roadway_width_segments, get_roadway_widths_json,
    format_widths_segments, format_road_widths,
    get_axle_load_segments, get_axle_loads_json,
    format_axle_load, format_axle_load_segments,
    get_km_posts_raw
)
from kml_exporter import update_kml, MAIN_TEMPLATE


# ============================================================================
# ПРИВЕТСТВИЕ
# ============================================================================
print("=" * 60)
print("СКДФ → KML")
print("=" * 60)
print("Программа загружает дороги из СКДФ по двум точкам")
print("и сохраняет в KML с характеристиками (ширина, нагрузка, столбы).")
print()
print("Форматы ввода координат:")
print("  - Яндекс.Карты: 55.972483, 36.911828")
print("  - SAS.Планет:   N51°43'15.9790\" E121°07'42.0984\"")
print("=" * 60)
print()


# ============================================================================
# 1. ВВОД КООРДИНАТ
# ============================================================================
print("Введите СЕВЕРО-ЗАПАДНУЮ точку (широта, долгота):")
lat1, lon1 = parse_coordinate(input())

print("Введите ЮГО-ВОСТОЧНУЮ точку (широта, долгота):")
lat2, lon2 = parse_coordinate(input())

# Строим bbox
bbox_degrees = build_bbox((lat1, lon1), (lat2, lon2))
bbox_meters = convert_bbox_to_skdf(bbox_degrees)

print(f"\nBbox (градусы): {bbox_degrees}")
print(f"Bbox (метры): {bbox_meters}\n")


# ============================================================================
# 2. ВВОД ZOOM
# ============================================================================
print("\nУровень детализации (zoom):")
print("  6-8   - область (сотни км)")
print("  9-11  - район (десятки км)")
print("  12-14 - город (единицы км)")
print("  15-18 - улицы (сотни метров)")
zoom_input = input("Zoom (по умолчанию 14): ").strip()
zoom = int(zoom_input) if zoom_input else 14
print(f"  Используется zoom = {zoom}\n")


# ============================================================================
# 3. ЗАГРУЗКА ДОРОГ
# ============================================================================
print("Загрузка дорог из СКДФ...")
start = time.time()
features = fetch_roads_raw(bbox_meters, zoom=zoom)
gdf = features_to_gdf(features)
print(f"  Загружено: {len(gdf)} дорог")

# Фильтрация по bbox
search_bbox = box(*bbox_meters)
gdf = gdf[gdf['geometry'].apply(
    lambda geom: geom.intersects(search_bbox))].copy()
print(f"  После фильтрации: {len(gdf)} дорог")


# ============================================================================
# 4. ОБОГАЩЕНИЕ ХАРАКТЕРИСТИКАМИ
# ============================================================================
print("\nПолучение характеристик...")
start = time.time()
gdf['passport_id'] = gdf['road_id'].apply(get_passport_id)
gdf['characteristics'] = gdf['passport_id'].apply(get_road_characteristics)

chars_df = pd.DataFrame(gdf['characteristics'].to_list())
chars_df['road_id'] = gdf['road_id'].values

# Удаляем дубликаты road_id
print(f"  chars_df до удаления дубликатов: {len(chars_df)} строк")
chars_df = chars_df.drop_duplicates(subset=['road_id'])
print(f"  chars_df после удаления дубликатов: {len(chars_df)} строк")

gdf = pd.merge(
    gdf.drop(columns=['characteristics']),
    chars_df,
    on='road_id',
    how='left'
)
print(
    f"  Характеристики получены для {gdf['passport_id'].notna().sum()} дорог")

# Категория
gdf['категория'] = gdf['value_of_the_road'].apply(get_category)
print(f"  Категории: {gdf['категория'].unique()}")


# ============================================================================
# 5. ШИРИНА И ОСЕВАЯ НАГРУЗКА
# ============================================================================
print("\nПолучение ширины и осевой нагрузки...")
start = time.time()

# Сегменты для ширины
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

# Осевая нагрузка
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

print(f"  Ширина добавлена для {gdf['Ширина:'].notna().sum()} дорог")
print(
    f"  Нагрузка добавлена для {gdf['Осевая нагрузка:'].notna().sum()} дорог")


# ============================================================================
# 6. КОНВЕРТАЦИЯ ГЕОМЕТРИИ
# ============================================================================
print("\nКонвертация геометрии в градусы...")
start = time.time()
gdf = gdf.to_crs("EPSG:4326")
gdf['geometry_deg'] = gdf.geometry
print(f"  Конвертация завершена")


# ============================================================================
# 7. КИЛОМЕТРОВЫЕ СТОЛБЫ (ТОЛЬКО ДЛЯ ФЕДЕРАЛЬНЫХ)
# ============================================================================
print("\nПолучение километровых столбов...")
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

    # Удаляем дубликаты столбов по координатам
    before = len(df_km_posts)
    df_km_posts = df_km_posts.drop_duplicates(subset=['latitude', 'longitude'])
    after = len(df_km_posts)
    print(f"  Удалено дубликатов столбов: {before - after}")

    gdf_km_posts = gpd.GeoDataFrame(
        df_km_posts,
        geometry=gpd.points_from_xy(
            df_km_posts['longitude'], df_km_posts['latitude']),
        crs="EPSG:4326"
    )
    print(f"  Всего километровых столбов: {len(gdf_km_posts)}")
else:
    gdf_km_posts = None
    print("  Федеральные дороги не найдены")


# ============================================================================
# 8. ФОРМИРОВАНИЕ KML
# ============================================================================
print("\nФормирование KML...")
kml_str = MAIN_TEMPLATE
kml_str = update_kml(None, kml_str, mode="init", top_folder_name="СКДФ Дороги")

# Обычные категории
for cat in ["федеральные", "региональные", "частные", "лесные", "ведомственные"]:
    gdf_cat = gdf[gdf['категория'] == cat]
    if not gdf_cat.empty:
        kml_str = update_kml(gdf_cat, kml_str, mode="roads", category=cat)

# Местные (с группировкой по владельцам)
gdf_local = gdf[gdf['категория'] == 'местные']
if not gdf_local.empty:
    kml_str = update_kml(gdf_local, kml_str, mode="roads", category="местные")

# Километровые столбы
if gdf_km_posts is not None and not gdf_km_posts.empty:
    kml_str = update_kml(gdf_km_posts, kml_str, mode="points")


# ============================================================================
# 9. СОХРАНЕНИЕ ФАЙЛА
# ============================================================================
output_file = f"roads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(kml_str)

print(f"\n✅ KML файл сохранён: {output_file}")
print(f"   Всего дорог: {len(gdf)}")
if gdf_km_posts is not None:
    print(f"   Всего километровых столбов: {len(gdf_km_posts)}")

print("\nГотово!")
