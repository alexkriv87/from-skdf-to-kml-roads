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
from category_filter import get_user_filter, filter_gdf_by_categories, need_km_posts, need_federal_for_posts, cat_to_key


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
gdf_all = features_to_gdf(features)
print(f"  Загружено: {len(gdf_all)} дорог")

# Фильтрация по bbox
search_bbox = box(*bbox_meters)
gdf_all = gdf_all[gdf_all['geometry'].apply(
    lambda geom: geom.intersects(search_bbox))].copy()
print(f"  После фильтрации: {len(gdf_all)} дорог")

# Определяем категории для всех дорог
gdf_all['категория'] = gdf_all['value_of_the_road'].apply(get_category)

# ============================================================================
# 3.5. ФИЛЬТР КАТЕГОРИЙ (ВВОД ОТ ПОЛЬЗОВАТЕЛЯ)
# ============================================================================
selected = get_user_filter()

# Фильтруем gdf для обогащения (только выбранные категории дорог)
gdf = filter_gdf_by_categories(gdf_all, selected)

# Если после фильтрации не осталось дорог, предупреждаем
if gdf.empty and not need_federal_for_posts(selected):
    print("\nВнимание: после применения фильтра не осталось дорог для обработки")
    print("Проверьте выбранные категории и область поиска\n")

# ============================================================================
# 4. ОБОГАЩЕНИЕ ХАРАКТЕРИСТИКАМИ (только для отфильтрованных дорог)
# ============================================================================
if not gdf.empty:
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

    # ============================================================================
    # 5. ШИРИНА И ОСЕВАЯ НАГРУЗКА (только для отфильтрованных дорог)
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

else:
    # Если дорог нет, создаём пустой GeoDataFrame с правильной структурой
    gdf = gpd.GeoDataFrame()


# ============================================================================
# 7. КИЛОМЕТРОВЫЕ СТОЛБЫ
# ============================================================================
gdf_km_posts = None

if need_km_posts(selected):
    print("\nПолучение километровых столбов...")
    
    # Если федеральные дороги не выбраны для отображения, берём их только для столбов
    if need_federal_for_posts(selected):
        # Берём федеральные дороги из полного набора (gdf_all)
        gdf_federal_for_posts = gdf_all[gdf_all['категория'] == 'федеральные'].copy()
        # Получаем только segment_passport_ids без обогащения
        gdf_federal_for_posts['passport_id'] = gdf_federal_for_posts['road_id'].apply(get_passport_id)
        gdf_federal_for_posts['segment_passport_ids'] = gdf_federal_for_posts['passport_id'].apply(
            get_roadway_width_segments)
        gdf_federal_source = gdf_federal_for_posts
    else:
        # Федеральные дороги уже есть в отфильтрованном gdf
        gdf_federal_source = gdf[gdf['категория'] == 'федеральные'].copy() if not gdf.empty else None
    
    if gdf_federal_source is not None and not gdf_federal_source.empty:
        all_dfs = []
        for idx, row in gdf_federal_source.iterrows():
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
            print("  Километровые столбы не найдены")
    else:
        print("  Федеральные дороги не найдены, столбы недоступны")
else:
    print("\nКилометровые столбы не выбраны")


# ============================================================================
# 8. ФОРМИРОВАНИЕ KML
# ============================================================================
print("\nФормирование KML...")
kml_str = MAIN_TEMPLATE
kml_str = update_kml(None, kml_str, mode="init", top_folder_name="СКДФ Дороги")

# Обычные категории (только те, которые выбраны и есть в gdf)
if not gdf.empty:
    # Федеральные
    if selected['federal']:
        gdf_cat = gdf[gdf['категория'] == 'федеральные']
        if not gdf_cat.empty:
            kml_str = update_kml(gdf_cat, kml_str, mode="roads", category="федеральные")
    
    # Региональные
    if selected['regional']:
        gdf_cat = gdf[gdf['категория'] == 'региональные']
        if not gdf_cat.empty:
            kml_str = update_kml(gdf_cat, kml_str, mode="roads", category="региональные")
    
    # Частные, лесные, ведомственные (всегда, если есть в gdf)
    for cat in ["частные", "лесные", "ведомственные"]:
        gdf_cat = gdf[gdf['категория'] == cat]
        if not gdf_cat.empty:
            kml_str = update_kml(gdf_cat, kml_str, mode="roads", category=cat)
    
    # Местные (с группировкой по владельцам)
    if selected['local']:
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

print(f"\nKML файл сохранён: {output_file}")
print(f"   Всего дорог в экспорте: {len(gdf)}")
if gdf_km_posts is not None:
    print(f"   Всего километровых столбов: {len(gdf_km_posts)}")

print("\nГотово!")