# kml_exporter.py
# Модуль для экспорта GeoDataFrame в KML-файл

import xml.etree.ElementTree as ET
from datetime import datetime
from logger_config import logger
from config import COLORS_KML, LINE_WIDTH, STYLE_IDS, ALL_FOLDERS, DESCRIPTION_TEMPLATE
from geometry_funcs import convert_multilinestring


def _get_style_id(ownership):
    """Возвращает ID стиля по принадлежности дороги."""
    # Защита от NaN (на всякий случай, хотя теперь их быть не должно)
    if ownership is None or (isinstance(ownership, float) and str(ownership) == 'nan'):
        return STYLE_IDS["не определена"]
    
    ownership_lower = str(ownership).lower()
    if "федерального" in ownership_lower:
        return STYLE_IDS["федеральная"]
    elif "регионального" in ownership_lower:
        return STYLE_IDS["региональная"]
    elif "местного" in ownership_lower:
        return STYLE_IDS["местная"]
    else:
        return STYLE_IDS["не определена"]


def _build_description(row):
    """Формирует текст description из строки GeoDataFrame."""
    lines = []
    for field_key, field_label in DESCRIPTION_TEMPLATE:
        value = row.get(field_key)
        if value and str(value) != 'nan':
            lines.append(f"{field_label} {value}")
    return '\n'.join(lines)


def _add_style(doc, style_id, color):
    """Добавляет стиль LineStyle в документ KML."""
    style = ET.SubElement(doc, "Style", id=style_id)
    line_style = ET.SubElement(style, "LineStyle")
    color_elem = ET.SubElement(line_style, "color")
    color_elem.text = color
    width = ET.SubElement(line_style, "width")
    width.text = str(LINE_WIDTH)


def _add_road_to_kml(parent, row):
    """Добавляет дорогу как Placemark в указанный элемент Folder."""
    placemark = ET.SubElement(parent, "Placemark")
    
    # Название
    name = ET.SubElement(placemark, "name")
    name.text = row.get('road_name', 'Без названия')
    
    # Описание
    description = ET.SubElement(placemark, "description")
    description.text = _build_description(row)
    
    # Стиль
    ownership = row.get('value_of_the_road', '')
    style_id = _get_style_id(ownership)
    style_url = ET.SubElement(placemark, "styleUrl")
    style_url.text = f"#{style_id}"
    
    # Геометрия (конвертируем из метров в градусы)
    geometry = row.get('geometry')
    if geometry:
        try:
            # Преобразуем Shapely-геометрию в GeoJSON-подобный словарь
            from shapely.geometry import mapping
            geom_dict = mapping(geometry)
            coords_deg = convert_multilinestring(geom_dict)
            
            line_string = ET.SubElement(placemark, "LineString")
            coordinates = ET.SubElement(line_string, "coordinates")
            
            coord_lines = []
            for line in coords_deg:
                for point in line:
                    lon, lat = point
                    coord_lines.append(f"{lon},{lat},0")
            
            coordinates.text = ' '.join(coord_lines)
        except Exception as e:
            logger.warning(f"Ошибка конвертации геометрии для дороги {row.get('road_name', 'неизвестной')}: {e}")


def save_to_kml(gdf, output_path):
    """
    Сохраняет GeoDataFrame в KML-файл.
    
    Параметры:
        gdf: GeoDataFrame с дорогами (CRS: EPSG:3857)
        output_path: полный путь к выходному файлу (.kml)
    
    Возвращает:
        bool: True при успехе, False при ошибке
    """
    try:
        kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
        document = ET.SubElement(kml, "Document")
        
        # Добавляем стили
        for style_id, color in COLORS_KML.items():
            _add_style(document, style_id, color)
        
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
        
        # Раскладываем дороги по папкам (используем колонку kml_folder, если есть)
        for idx, row in gdf.iterrows():
            folder_name = row.get('kml_folder')
            if folder_name and folder_name in folders:
                _add_road_to_kml(folders[folder_name], row)
            else:
                _add_road_to_kml(main_folder, row)
        
        # Создаём папку "Точки интереса" (пока пустую)
        poi_folder = ET.SubElement(document, "Folder")
        poi_name = ET.SubElement(poi_folder, "name")
        poi_name.text = "Точки интереса"
        
        tree = ET.ElementTree(kml)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        
        logger.info(f"KML сохранён: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка сохранения KML: {e}")
        return False
    
    
# ============= ТЕСТ kml_exporter.py =============
if __name__ == "__main__":
    import time
    import pandas as pd
    from coord_utils import parse_coordinate, build_bbox, convert_bbox_to_skdf
    from skdf_api import fetch_roads_raw, features_to_gdf, get_passport_id, get_road_characteristics, get_folder_name
    from shapely.geometry import box
    from kml_exporter import save_to_kml
    from datetime import datetime
    
    print("\n=== Тест kml_exporter.py ===\n")
    
    # Ручной ввод координат
    print("Введите северо-западную точку (широта, долгота):")
    lat1, lon1 = parse_coordinate(input())
    
    print("Введите юго-восточную точку (широта, долгота):")
    lat2, lon2 = parse_coordinate(input())
    
    # Строим bbox
    bbox_degrees = build_bbox((lat1, lon1), (lat2, lon2))
    bbox_meters = convert_bbox_to_skdf(bbox_degrees)
    print(f"Bbox (градусы): {bbox_degrees}")
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
    gdf = gdf[gdf['geometry'].apply(lambda geom: geom.intersects(search_bbox))].copy()
    print(f"После фильтрации: {len(gdf)} дорог за {time.time()-start:.1f} сек")
    
    # 3. Обогащение характеристиками
    start = time.time()
    gdf['passport_id'] = gdf['road_id'].apply(get_passport_id)
    gdf['characteristics'] = gdf['passport_id'].apply(get_road_characteristics)
    
    # Создаём DataFrame из характеристик
    chars_df = pd.DataFrame(gdf['characteristics'].to_list())
    
    # Добавляем road_id в chars_df
    chars_df['road_id'] = gdf['road_id'].values
    
    # Объединяем через merge
    gdf = pd.merge(
        gdf.drop(columns=['characteristics']), 
        chars_df, 
        on='road_id', 
        how='left'
    )
    print(f"Обогащение: {gdf['passport_id'].notna().sum()} / {len(gdf)} дорог за {time.time()-start:.1f} сек")
    
    # 4. Добавляем папки
    gdf['kml_folder'] = gdf['value_of_the_road'].apply(get_folder_name)
    
    # 5. Сохраняем в KML
    start = time.time()
    output_file = f"roads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
    success = save_to_kml(gdf, output_file)
    print(f"Сохранение KML: {time.time()-start:.1f} сек")
    
    total_time = time.time() - total_start
    print(f"\n✅ Общее время: {total_time:.1f} сек")
    
    if success:
        print(f"   KML файл: {output_file}")
        print(f"   Всего дорог: {len(gdf)}")
    else:
        print("   ❌ Ошибка сохранения KML")