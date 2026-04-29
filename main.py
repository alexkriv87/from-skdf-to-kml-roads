# main.py
# Скрипт для экспорта дорог из СКДФ в KML

import time
import os
import pandas as pd
from logger_config import logger
from coord_utils import parse_coordinate, build_bbox, convert_bbox_to_skdf
from skdf_api import fetch_roads_raw, features_to_gdf, get_passport_id, get_road_characteristics
from kml_exporter import save_to_kml


def main():
    print("\n" + "=" * 50)
    print("Экспорт дорог из СКДФ в KML")
    print("=" * 50 + "\n")

    # ============= 1. Ввод координат =============
    print("Введите координаты двух углов прямоугольника")
    print("Форматы: 55.972483, 36.911828 (Яндекс) или N51°43'15.98\" E121°07'42.10\" (SAS)")
    print()

    print("Северо-западная точка:")
    lat1, lon1 = parse_coordinate(input("> "))

    print("\nЮго-восточная точка:")
    lat2, lon2 = parse_coordinate(input("> "))

    # ============= 2. Построение bbox =============
    bbox_4326 = build_bbox((lat1, lon1), (lat2, lon2))
    bbox_3857 = convert_bbox_to_skdf(bbox_4326)

    # ============= 3. Запрос zoom =============
    zoom_input = input("\nZoom (6-18, Enter=14): ").strip()
    zoom = int(zoom_input) if zoom_input else 14

    # ============= 4. Путь для сохранения =============
    while True:
        output_folder = input(
            "Путь для сохранения (Enter=output): ").strip() or "output"
        if os.path.exists(output_folder):
            break
        print(f"Папка '{output_folder}' не найдена. Попробуйте снова.")

    # ============= 5. Загрузка дорог =============
    print("\nЗагрузка дорог из СКДФ...")
    start_time = time.time()
    features = fetch_roads_raw(bbox_3857, zoom)
    gdf = features_to_gdf(features)
    logger.info(
        f"Загружено дорог: {len(gdf)} за {time.time()-start_time:.1f} сек")

    if len(gdf) == 0:
        print("Нет дорог для экспорта")
        return

    # ============= 6. Обогащение характеристиками =============
    print("Обогащение характеристиками...")
    gdf['passport_id'] = gdf['road_id'].apply(get_passport_id)
    gdf['characteristics'] = gdf['passport_id'].apply(get_road_characteristics)

    chars_df = pd.DataFrame(gdf['characteristics'].to_list())
    gdf = pd.concat([gdf.drop(columns=['characteristics']), chars_df], axis=1)

    enriched = gdf['passport_id'].notna().sum()
    logger.info(f"Обогащено дорог: {enriched} / {len(gdf)}")

    # ============= 7. Сохранение в KML =============
    output_file = os.path.join(
        output_folder, f"roads_{time.strftime('%Y%m%d_%H%M%S')}.kml")

    # Сохраняем GeoDataFrame напрямую в KML
    gdf.to_file(output_file, driver='KML')

    print(f"\n✅ KML файл сохранён: {output_file}")
    print(f"   Всего дорог: {len(gdf)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        print(f"\n❌ Ошибка: {e}")

    input("\nНажмите Enter для выхода...")
