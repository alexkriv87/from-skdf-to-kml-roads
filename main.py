# main.py
# Основная логика выгрузки дорог из СКДФ в KML

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
from category_filter import filter_gdf_by_categories, need_km_posts, need_federal_for_posts
from skdf_api import get_counter


def run_export(nw_input, se_input, zoom, selected, output_file, log_callback=print):
    """
    Одиночный экспорт (для совместимости)
    """
    queries_df = pd.DataFrame([{
        'nw_input': nw_input,
        'se_input': se_input,
        'zoom': zoom,
        'federal': selected.get('federal', False),
        'regional': selected.get('regional', False),
        'local': selected.get('local', False),
        'km_posts': selected.get('km_posts', False)
    }])
    return run_export_batch(queries_df, output_file, log_callback)


def run_export_batch(queries_df, output_file, log_callback=print):
    """
    Пакетный экспорт по нескольким запросам.

    Параметры:
        queries_df: DataFrame с колонками nw_input, se_input, zoom, 
                   federal, regional, local, km_posts
        output_file: путь к выходному KML-файлу
        log_callback: функция для вывода сообщений

    Возвращает:
        tuple: (количество дорог в экспорте, количество столбов в экспорте)
    """
    if queries_df.empty:
        log_callback("Ошибка: нет добавленных запросов")
        return 0, 0

    log_callback(f"Пакетная обработка: {len(queries_df)} запросов")
    log_callback("")

    # Собираем все дороги из всех запросов
    gdf_all_merged = gpd.GeoDataFrame()
    need_km_posts_global = False

    for idx, row in queries_df.iterrows():
        log_callback(f"Обработка запроса {idx + 1} из {len(queries_df)}")

        # Собираем selected для текущего запроса
        selected = {
            'federal': row['federal'],
            'regional': row['regional'],
            'local': row['local'],
            'km_posts': row['km_posts']
        }

        if selected['km_posts']:
            need_km_posts_global = True

        # Парсинг координат
        log_callback(
            f"  Парсинг координат: {row['nw_input']} / {row['se_input']}")
        lat1, lon1 = parse_coordinate(row['nw_input'])
        lat2, lon2 = parse_coordinate(row['se_input'])

        # Строим bbox
        bbox_degrees = build_bbox((lat1, lon1), (lat2, lon2))
        bbox_meters = convert_bbox_to_skdf(bbox_degrees)

        # Загрузка дорог
        log_callback(f"  Загрузка дорог, zoom={row['zoom']}")
        features = fetch_roads_raw(bbox_meters, zoom=row['zoom'])
        gdf = features_to_gdf(features)

        # Фильтрация по bbox
        search_bbox = box(*bbox_meters)
        gdf = gdf[gdf['geometry'].apply(
            lambda geom: geom.intersects(search_bbox))].copy()
        log_callback(f"  Загружено дорог: {len(gdf)}")

        # Определяем категории
        gdf['категория'] = gdf['value_of_the_road'].apply(get_category)

        # Фильтруем по выбранным категориям
        gdf = filter_gdf_by_categories(gdf, selected)
        log_callback(f"  После фильтрации: {len(gdf)} дорог")

        # Добавляем в общий GDF
        if not gdf.empty:
            gdf_all_merged = pd.concat(
                [gdf_all_merged, gdf], ignore_index=True)

        log_callback("")

    # Удаляем дубликаты по road_id
    if not gdf_all_merged.empty:
        before = len(gdf_all_merged)
        gdf_all_merged = gdf_all_merged.drop_duplicates(subset=['road_id'])
        after = len(gdf_all_merged)
        if before > after:
            log_callback(f"Удалено дубликатов дорог: {before - after}")
    else:
        log_callback("Внимание: не найдено ни одной дороги во всех запросах")

    log_callback("")

    # Обогащение характеристиками
    gdf = gdf_all_merged

    if not gdf.empty:
        log_callback("Получение характеристик...")
        gdf['passport_id'] = gdf['road_id'].apply(get_passport_id)
        gdf['characteristics'] = gdf['passport_id'].apply(
            get_road_characteristics)

        chars_df = pd.DataFrame(gdf['characteristics'].to_list())
        chars_df['road_id'] = gdf['road_id'].values

        chars_df = chars_df.drop_duplicates(subset=['road_id'])

        gdf = pd.merge(
            gdf.drop(columns=['characteristics']),
            chars_df,
            on='road_id',
            how='left'
        )
        log_callback(
            f"  Характеристики получены для {gdf['passport_id'].notna().sum()} дорог")

        # Ширина и осевая нагрузка
        log_callback("Получение ширины и осевой нагрузки...")

        gdf['segment_passport_ids'] = gdf['passport_id'].apply(
            get_roadway_width_segments)

        def get_all_widths_json(segment_ids):
            all_widths = []
            for seg_id in segment_ids:
                widths = get_roadway_widths_json(seg_id)
                all_widths.extend(widths)
            return all_widths

        gdf['widths_json'] = gdf['segment_passport_ids'].apply(
            get_all_widths_json)
        gdf['Ширина:'] = gdf['widths_json'].apply(format_widths_segments)
        gdf['Участки ширины:'] = gdf['widths_json'].apply(format_road_widths)

        gdf['axle_segments'] = gdf['passport_id'].apply(get_axle_load_segments)

        def get_all_axle_loads(segment_ids):
            all_loads = []
            for seg_id in segment_ids:
                loads = get_axle_loads_json(seg_id)
                all_loads.extend(loads)
            return all_loads

        gdf['axle_loads_json'] = gdf['axle_segments'].apply(get_all_axle_loads)
        gdf['Осевая нагрузка:'] = gdf['axle_loads_json'].apply(
            format_axle_load)
        gdf['Участки нагрузки:'] = gdf['axle_loads_json'].apply(
            format_axle_load_segments)

        log_callback(
            f"  Ширина добавлена для {gdf['Ширина:'].notna().sum()} дорог")
        log_callback(
            f"  Нагрузка добавлена для {gdf['Осевая нагрузка:'].notna().sum()} дорог")

        # Конвертация геометрии
        log_callback("Конвертация геометрии в градусы...")
        gdf = gdf.to_crs("EPSG:4326")
        gdf['geometry_deg'] = gdf.geometry
        log_callback("  Конвертация завершена")
    else:
        gdf = gpd.GeoDataFrame()

    # Километровые столбы (если хотя бы в одном запросе нужны)
    gdf_km_posts = None

    if need_km_posts_global:
        log_callback("Получение километровых столбов...")

        # Собираем федеральные дороги из всех запросов заново
        all_federal = gpd.GeoDataFrame()

        for idx, row in queries_df.iterrows():
            lat1, lon1 = parse_coordinate(row['nw_input'])
            lat2, lon2 = parse_coordinate(row['se_input'])

            bbox_degrees = build_bbox((lat1, lon1), (lat2, lon2))
            bbox_meters = convert_bbox_to_skdf(bbox_degrees)

            features = fetch_roads_raw(bbox_meters, zoom=row['zoom'])
            gdf_temp = features_to_gdf(features)

            search_bbox = box(*bbox_meters)
            gdf_temp = gdf_temp[gdf_temp['geometry'].apply(
                lambda geom: geom.intersects(search_bbox))].copy()

            gdf_temp['категория'] = gdf_temp['value_of_the_road'].apply(
                get_category)
            gdf_fed = gdf_temp[gdf_temp['категория'] == 'федеральные'].copy()

            if not gdf_fed.empty:
                all_federal = pd.concat(
                    [all_federal, gdf_fed], ignore_index=True)

        if not all_federal.empty:
            all_federal = all_federal.drop_duplicates(subset=['road_id'])
            log_callback(f"  Уникальных федеральных дорог: {len(all_federal)}")

            all_federal['passport_id'] = all_federal['road_id'].apply(
                get_passport_id)
            all_federal['segment_passport_ids'] = all_federal['passport_id'].apply(
                get_roadway_width_segments)

            all_dfs = []
            for idx, row in all_federal.iterrows():
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

                before = len(df_km_posts)
                df_km_posts = df_km_posts.drop_duplicates(
                    subset=['latitude', 'longitude'])
                after = len(df_km_posts)
                log_callback(f"  Удалено дубликатов столбов: {before - after}")

                gdf_km_posts = gpd.GeoDataFrame(
                    df_km_posts,
                    geometry=gpd.points_from_xy(
                        df_km_posts['longitude'], df_km_posts['latitude']),
                    crs="EPSG:4326"
                )
                log_callback(
                    f"  Всего километровых столбов: {len(gdf_km_posts)}")
            else:
                log_callback("  Километровые столбы не найдены")
        else:
            log_callback("  Федеральные дороги не найдены, столбы недоступны")
    else:
        log_callback("Километровые столбы не выбраны ни в одном запросе")

    # Формирование KML
    log_callback("Формирование KML...")
    kml_str = MAIN_TEMPLATE
    kml_str = update_kml(None, kml_str, mode="init",
                         top_folder_name="СКДФ Дороги")

    selected_for_export = {
        'federal': queries_df['federal'].any(),
        'regional': queries_df['regional'].any(),
        'local': queries_df['local'].any()
    }

    if not gdf.empty:
        if selected_for_export['federal']:
            gdf_cat = gdf[gdf['категория'] == 'федеральные']
            if not gdf_cat.empty:
                kml_str = update_kml(
                    gdf_cat, kml_str, mode="roads", category="федеральные")

        if selected_for_export['regional']:
            gdf_cat = gdf[gdf['категория'] == 'региональные']
            if not gdf_cat.empty:
                kml_str = update_kml(
                    gdf_cat, kml_str, mode="roads", category="региональные")

        for cat in ["частные", "лесные", "ведомственные"]:
            gdf_cat = gdf[gdf['категория'] == cat]
            if not gdf_cat.empty:
                kml_str = update_kml(
                    gdf_cat, kml_str, mode="roads", category=cat)

        if selected_for_export['local']:
            gdf_local = gdf[gdf['категория'] == 'местные']
            if not gdf_local.empty:
                kml_str = update_kml(gdf_local, kml_str,
                                     mode="roads", category="местные")

    if gdf_km_posts is not None and not gdf_km_posts.empty:
        kml_str = update_kml(gdf_km_posts, kml_str, mode="points")

    # Сохранение файла
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(kml_str)

    log_callback(f"\nKML файл сохранён: {output_file}")
    log_callback(f"   Всего дорог в экспорте: {len(gdf)}")
    if gdf_km_posts is not None:
        log_callback(f"   Всего километровых столбов: {len(gdf_km_posts)}")

    log_callback(f"\nВсего выполнено API-запросов: {get_counter()}")

    return len(gdf), len(gdf_km_posts) if gdf_km_posts is not None else 0


# ============================================================================
# КОНСОЛЬНАЯ ТОЧКА ВХОДА (для совместимости)
# ============================================================================
if __name__ == "__main__":
    from category_filter import get_user_filter

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

    # Ввод координат
    print("Введите СЕВЕРО-ЗАПАДНУЮ точку (широта, долгота):")
    nw_input = input()

    print("Введите ЮГО-ВОСТОЧНУЮ точку (широта, долгота):")
    se_input = input()

    # Ввод zoom
    print("\nУровень детализации (zoom):")
    print("  6-8   - область (сотни км)")
    print("  9-11  - район (десятки км)")
    print("  12-14 - город (единицы км)")
    print("  15-18 - улицы (сотни метров)")
    zoom_input = input("Zoom (по умолчанию 14): ").strip()
    zoom = int(zoom_input) if zoom_input else 14

    # Выбор категорий
    selected = get_user_filter()

    # Имя выходного файла
    output_file = f"roads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"

    # Запуск экспорта
    run_export(nw_input, se_input, zoom, selected,
               output_file, log_callback=print)
