# kml_exporter.py
# Модуль для экспорта дорог в KML-файл

import os
import xml.etree.ElementTree as ET
from datetime import datetime
from logger_config import logger
from config import COLORS_KML, LINE_WIDTH, STYLE_IDS, ALL_FOLDERS, DESCRIPTION_TEMPLATE
from geometry_funcs import convert_multilinestring


def get_folder_name(ownership):
    """
    Определяет имя папки для дороги по её принадлежности.
    
    Параметры:
        ownership: строка принадлежности (например, "Автомобильные дороги федерального значения")
    
    Возвращает:
        str: имя папки (например, "1. Федеральные дороги") или None
    """
    ownership_lower = ownership.lower()
    
    if "федерального" in ownership_lower:
        return "1. Федеральные дороги"
    elif "регионального" in ownership_lower:
        return "2. Региональные дороги"
    elif "местного" in ownership_lower:
        return "3. Местные дороги"
    elif "частные" in ownership_lower:
        return "4. Частные дороги"
    elif "ведомственные" in ownership_lower:
        return "5. Ведомственные"
    elif "лесные" in ownership_lower:
        return "6. Лесные дороги"
    else:
        return None


def get_style_id(ownership):
    """
    Возвращает ID стиля по принадлежности дороги.
    
    Параметры:
        ownership: строка принадлежности
    
    Возвращает:
        str: ID стиля (например, "style_federal")
    """
    ownership_lower = ownership.lower()
    
    if "федерального" in ownership_lower:
        return STYLE_IDS["федеральная"]
    elif "регионального" in ownership_lower:
        return STYLE_IDS["региональная"]
    elif "местного" in ownership_lower:
        return STYLE_IDS["местная"]
    else:
        return STYLE_IDS["не определена"]


def build_description(road):
    """
    Формирует текст description для дороги.
    
    Параметры:
        road: словарь с данными дороги (properties + характеристики)
    
    Возвращает:
        str: текст description
    """
    lines = []
    
    # Название дороги
    name = road.get('road_name', 'Без названия')
    lines.append(f"Название: {name}")
    lines.append("")  # пустая строка для разделения
    
    # Характеристики из шаблона
    for field_key, field_label in DESCRIPTION_TEMPLATE:
        value = road.get(field_key)
        if value:
            lines.append(f"{field_label} {value}")
    
    return '\n'.join(lines)


def add_style(doc, style_id, color):
    """
    Добавляет стиль LineStyle в документ KML.
    
    Параметры:
        doc: элемент Document
        style_id: ID стиля
        color: цвет в формате KML (AABBGGRR)
    """
    style = ET.SubElement(doc, "Style", id=style_id)
    line_style = ET.SubElement(style, "LineStyle")
    color_elem = ET.SubElement(line_style, "color")
    color_elem.text = color
    width = ET.SubElement(line_style, "width")
    width.text = str(LINE_WIDTH)


def add_folder(doc, folder_name):
    """
    Добавляет пустую папку в документ KML.
    
    Параметры:
        doc: элемент Document
        folder_name: имя папки
    """
    folder = ET.SubElement(doc, "Folder")
    name = ET.SubElement(folder, "name")
    name.text = folder_name


def add_road_to_kml(parent, road):
    """
    Добавляет дорогу как Placemark в указанный элемент (Folder).
    
    Параметры:
        parent: элемент Folder, куда добавлять
        road: словарь с данными дороги
    """
    placemark = ET.SubElement(parent, "Placemark")
    
    # Название
    name = ET.SubElement(placemark, "name")
    name.text = road.get('road_name', 'Без названия')
    
    # Описание
    description = ET.SubElement(placemark, "description")
    description.text = build_description(road)
    
    # Стиль
    ownership = road.get('value_of_the_road', '')
    style_id = get_style_id(ownership)
    style_url = ET.SubElement(placemark, "styleUrl")
    style_url.text = f"#{style_id}"
    
    # Геометрия (конвертируем из метров в градусы)
    geometry = road.get('geometry')
    if geometry and geometry.get('type') == 'MultiLineString':
        try:
            coords_deg = convert_multilinestring(geometry)
            
            line_string = ET.SubElement(placemark, "LineString")
            coordinates = ET.SubElement(line_string, "coordinates")
            
            # Формируем строку координат: lon,lat,altitude
            coord_lines = []
            for line in coords_deg:
                for point in line:
                    lon, lat = point
                    coord_lines.append(f"{lon},{lat},0")
            
            coordinates.text = ' '.join(coord_lines)
        except Exception as e:
            logger.warning(f"Ошибка конвертации геометрии для дороги {road.get('road_name')}: {e}")


def save_to_kml(roads, output_path):
    """
    Основная функция: сохраняет список дорог в KML-файл.
    
    Параметры:
        roads: список дорог (каждая дорога — словарь)
        output_path: полный путь к выходному файлу (.kml)
    
    Возвращает:
        bool: True при успехе, False при ошибке
    """
    try:
        # Создаём корневой элемент KML
        kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
        document = ET.SubElement(kml, "Document")
        
        # Добавляем стили
        for style_id, color in COLORS_KML.items():
            add_style(document, style_id, color)
        
        # Создаём основную папку "Дороги"
        main_folder = ET.SubElement(document, "Folder")
        main_name = ET.SubElement(main_folder, "name")
        main_name.text = "Дороги"
        
        # Создаём подпапки (все из списка)
        folders = {}
        for folder_name in ALL_FOLDERS:
            folder = ET.SubElement(main_folder, "Folder")
            folder_name_elem = ET.SubElement(folder, "name")
            folder_name_elem.text = folder_name
            folders[folder_name] = folder
        
        # Раскладываем дороги по папкам
        for road in roads:
            ownership = road.get('value_of_the_road', '')
            folder_name = get_folder_name(ownership)
            
            if folder_name and folder_name in folders:
                add_road_to_kml(folders[folder_name], road)
            else:
                # Если папка не определена, кладём в основную папку
                add_road_to_kml(main_folder, road)
        
        # Создаём папку "Точки интереса" (пока пустую)
        poi_folder = ET.SubElement(document, "Folder")
        poi_name = ET.SubElement(poi_folder, "name")
        poi_name.text = "Точки интереса"
        
        # Записываем в файл
        tree = ET.ElementTree(kml)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        
        logger.info(f"KML сохранён: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка сохранения KML: {e}")
        return False


# ============= ТЕСТ =============
if __name__ == "__main__":
    import time
    from skdf_api import get_roads_in_bbox, get_passport_id, get_road_characteristics
    
    print("\n=== Тест kml_exporter.py ===\n")
    
    # Координаты из coord_utils.py (Свободный, bbox в метрах)
    test_bbox = [14215755.537897442, 6660090.979195764, 14296014.416992927, 6720328.170348525]
    
    # Загружаем все дороги
    print("Загрузка дорог из СКДФ...")
    start_time = time.time()
    roads = get_roads_in_bbox(test_bbox, zoom=14)
    elapsed_time = time.time() - start_time
    
    print(f"\nВремя выполнения: {elapsed_time:.2f} сек")
    print(f"Получено дорог: {len(roads)}")
    
    if not roads:
        print("Нет дорог для экспорта")
        exit()
    
    # Обогащаем все дороги характеристиками
    print("\nОбогащение характеристиками...")
    enriched_count = 0
    no_passport_count = 0
    
    for i, road in enumerate(roads):
        road_id = road['properties'].get('road_id')
        if road_id:
            passport_id = get_passport_id(road_id)
            if passport_id:
                chars = get_road_characteristics(passport_id)
                road.update(chars)
                enriched_count += 1
            else:
                no_passport_count += 1
        
        # Прогресс каждые 50 дорог
        if (i + 1) % 50 == 0:
            print(f"  Обработано {i + 1} из {len(roads)} дорог")
    
    print(f"\nОбогащено характеристиками: {enriched_count}")
    print(f"Нет паспорта: {no_passport_count}")
    
    # Сохраняем в KML
    from kml_exporter import save_to_kml
    
    output_file = f"roads_{time.strftime('%Y%m%d_%H%M%S')}.kml"
    success = save_to_kml(roads, output_file)
    
    if success:
        print(f"\n✅ KML файл сохранён: {output_file}")
        print(f"   Всего дорог: {len(roads)}")
        print(f"   Открой файл в Google Earth или SAS.Планет")
    else:
        print("\n❌ Ошибка сохранения KML")