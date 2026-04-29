# main.py
# Тестовый скрипт для проверки полного цикла: 
# координаты → загрузка дорог → обогащение → сохранение в KML

import time
from logger_config import logger
from coord_utils import parse_coordinate, build_bbox, convert_bbox_to_skdf
from skdf_api import get_roads_in_bbox, get_passport_id, get_road_characteristics
from kml_exporter import save_to_kml


def main():
    print("\n" + "=" * 50)
    print("Тестовый запуск экспорта дорог из СКДФ в KML")
    print("=" * 50 + "\n")
    
    # ============= 1. Ввод координат =============
    print("Введите координаты двух углов прямоугольника")
    print("Форматы: 55.972483, 36.911828 (Яндекс) или N51°43'15.98\" E121°07'42.10\" (SAS)")
    print()
    
    # Северо-западная точка
    print("Северо-западная точка:")
    input1 = input("> ")
    lat1, lon1 = parse_coordinate(input1)
    
    # Юго-восточная точка
    print("\nЮго-восточная точка:")
    input2 = input("> ")
    lat2, lon2 = parse_coordinate(input2)
    
    # ============= 2. Построение bbox =============
    bbox_4326 = build_bbox((lat1, lon1), (lat2, lon2))
    logger.info(f"Bbox (градусы): {bbox_4326}")
    
    bbox_3857 = convert_bbox_to_skdf(bbox_4326)
    logger.info(f"Bbox (метры): {bbox_3857}")
    
    # ============= 3. Запрос дорог из СКДФ =============
    print("\nЗагрузка дорог из СКДФ...")
    start_time = time.time()
    roads = get_roads_in_bbox(bbox_3857, zoom=14)
    elapsed = time.time() - start_time
    
    print(f"Найдено дорог: {len(roads)} за {elapsed:.2f} сек")
    
    if not roads:
        print("Нет дорог для экспорта")
        return
    
    # ============= 4. Обогащение характеристиками =============
    print("\nОбогащение характеристиками...")
    enriched = 0
    
    for i, road in enumerate(roads):
        road_id = road['properties'].get('road_id')
        if road_id:
            passport_id = get_passport_id(road_id)
            if passport_id:
                chars = get_road_characteristics(passport_id)
                road.update(chars)
                enriched += 1
        
        # Прогресс каждые 10 дорог
        if (i + 1) % 10 == 0 or (i + 1) == len(roads):
            print(f"  Обработано {i + 1} из {len(roads)} дорог")
    
    print(f"Обогащено: {enriched} из {len(roads)}")
    
    # ============= 5. Сохранение в KML =============
    output_file = f"roads_{time.strftime('%Y%m%d_%H%M%S')}.kml"
    success = save_to_kml(roads, output_file)
    
    if success:
        print(f"\n✅ KML файл сохранён: {output_file}")
        print(f"   Всего дорог: {len(roads)}")
    else:
        print("\n❌ Ошибка сохранения KML")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        print(f"\n❌ Ошибка: {e}")
    
    input("\nНажмите Enter для выхода...")