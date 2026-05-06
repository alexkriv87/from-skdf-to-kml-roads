# geometry_funcs.py
# Функции для работы с геометрией (конвертация проекций)

from pyproj import Transformer
from logger_config import logger

# Создаём трансформер один раз (переиспользуем)
# Из EPSG:3857 (метры, СКДФ) в EPSG:4326 (градусы, KML)
TRANSFORMER = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

# gui.py
import tkinter as tk

# Создаём главное окно
root = tk.Tk()

# Заголовок окна
root.title("СКДФ → KML")

# Размер окна (ширина x высота)
root.geometry("500x400")

# Бесконечный цикл, который показывает окно
root.mainloop()
def convert_coordinate(x_m, y_m):
    """
    Переводит одну координату из метров (EPSG:3857) в градусы (EPSG:4326).
    
    Параметры:
        x_m: долгота в метрах
        y_m: широта в метрах
    
    Возвращает:
        tuple: (lon, lat) в градусах
    """
    lon, lat = TRANSFORMER.transform(x_m, y_m)
    return lon, lat


def convert_linestring(coords_m):
    """
    Переводит линию (список координат) из метров в градусы.
    
    Параметры:
        coords_m: список [[x1, y1, z?], [x2, y2, z?], ...]
    
    Возвращает:
        list: список [lon, lat] в градусах (без высоты)
    """
    coords_deg = []
    for point in coords_m:
        x = point[0]
        y = point[1]
        lon, lat = convert_coordinate(x, y)
        coords_deg.append([lon, lat])
    
    return coords_deg


def convert_multilinestring(geometry):
    """
    Переводит MultiLineString из метров в градусы.
    
    Параметры:
        geometry: GeoJSON геометрия (type: MultiLineString)
    
    Возвращает:
        list: список линий, каждая линия — список [lon, lat]
    """
    result = []
    for line in geometry['coordinates']:
        converted_line = convert_linestring(line)
        result.append(converted_line)
    
    return result
