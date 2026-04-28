# coord_utils.py
# Модуль для работы с географическими координатами
# Поддерживает два формата:
# 1. Десятичные градусы: 55.972483, 36.911828 (Яндекс.Карты)
# 2. Градусы/минуты/секунды: N51°43'15.9790" E121°07'42.0984" (SAS.Планет)

import re
from logger_config import logger
from pyproj import Transformer


def parse_coordinate(coord_str):
    """
    Первая функция, которую вызывает пользователь.
    Определяет формат координат и преобразует их в десятичные градусы.
    
    Параметры:
        coord_str: строка с координатами от пользователя
    
    Возвращает:
        tuple: (latitude, longitude) - широта и долгота в десятичных градусах
    
    Примеры:
        parse_coordinate("55.972483, 36.911828") -> (55.972483, 36.911828)
        parse_coordinate('N51°43\'15.9790" E121°07\'42.0984"') -> (51.7211, 121.1284)
    """
    # Удаляем лишние пробелы в начале и конце строки
    coord_str = coord_str.strip()
    
    # ==================== DMS ФОРМАТ (SAS.Планет) ====================
    # Проверяем, есть ли признаки DMS формата:
    # символы градуса (°), минуты ('), секунды ("), направления (N, S, E, W)
    if any(c in coord_str for c in ['°', "'", '"', 'N', 'S', 'E', 'W']):
        # Сообщаем в лог, какой формат определён
        logger.info("Определён формат: SAS.Планет")
        
        # Паттерн для поиска широты: буква (N/S) + число°число'число"
        # Пример: N51°43'15.9790"
        lat_pattern = r'([NS])(\d+°\d+\'[\d.]+")'
        
        # Паттерн для поиска долготы: буква (E/W) + число°число'число"
        # Пример: E121°07'42.0984"
        lon_pattern = r'([EW])(\d+°\d+\'[\d.]+")'
        
        # Ищем широту и долготу в строке
        lat_match = re.search(lat_pattern, coord_str)
        lon_match = re.search(lon_pattern, coord_str)
        
        # Если не нашли оба значения - ошибка (пользователь ввёл что-то не так)
        if not lat_match or not lon_match:
            logger.error(f"Неверный формат DMS: {coord_str}")
            raise ValueError(f"Неверный формат DMS: {coord_str}")
        
        # Извлекаем направление (N/S/E/W) из первой группы (1)
        lat_dir = lat_match.group(1)   # N или S
        lon_dir = lon_match.group(1)   # E или W
        
        # Извлекаем числовую часть из второй группы (2)
        # Например: "51°43'15.9790""
        lat_dms = lat_match.group(2)
        lon_dms = lon_match.group(2)
        
        # Вызываем вспомогательную функцию для преобразования DMS в десятичные градусы
        latitude = dms_to_decimal(lat_dms)
        longitude = dms_to_decimal(lon_dms)
        
        # Корректируем знак для южной широты (S) и западной долготы (W)
        # В северном полушарии широта положительная, в южном - отрицательная
        # В восточном полушарии долгота положительная, в западном - отрицательная
        if lat_dir == 'S':
            latitude = -latitude
        if lon_dir == 'W':
            longitude = -longitude
        
        return latitude, longitude
    
    # ==================== ДЕСЯТИЧНЫЙ ФОРМАТ (Яндекс.Карты) ====================
    else:
        # Сообщаем в лог, какой формат определён
        logger.info("Определён формат: Яндекс.Карты")
        
        # Пробуем разные разделители для удобства пользователя:
        # запятая (стандарт Яндекс.Карт), точка с запятой, пробел
        parts = None
        for sep in [',', ';', ' ']:
            if sep in coord_str:
                parts = coord_str.split(sep)
                break  # как нашли разделитель - выходим из цикла
        
        # Если не нашли ни одного разделителя - ошибка
        if not parts or len(parts) < 2:
            logger.error(f"Неверный формат десятичных координат: {coord_str}")
            raise ValueError(f"Неверный формат десятичных координат: {coord_str}")
        
        try:
            # Преобразуем строки в числа с плавающей точкой
            # strip() удаляет лишние пробелы вокруг числа
            latitude = float(parts[0].strip())
            longitude = float(parts[1].strip())
            return latitude, longitude
        except ValueError:
            # Если не удалось преобразовать в числа - ошибка
            logger.error(f"Не удалось преобразовать числа: {coord_str}")
            raise ValueError(f"Не удалось преобразовать числа: {coord_str}")


def dms_to_decimal(coord_str):
    """
    Вспомогательная функция (вызывается только из parse_coordinate для DMS формата).
    Преобразует строку вида "51°43'15.9790" в десятичные градусы.
    
    Параметры:
        coord_str: строка вида "51°43'15.9790" (без букв N/S/E/W)
    
    Возвращает:
        float: координата в десятичных градусах
    
    Пример:
        dms_to_decimal("51°43'15.9790\"") -> 51.72110527777778
    """
    # Регулярное выражение для поиска градусов, минут и секунд
    # (\d+)  - одна или несколько цифр (градусы)
    # °      - символ градуса
    # (\d+)  - одна или несколько цифр (минуты)
    # \'     - символ минуты (экранирован, так как ' спецсимвол)
    # ([\d.]+) - цифры и точка (секунды)
    # "      - символ секунды
    pattern = r'(\d+)°(\d+)\'([\d.]+)"'
    match = re.search(pattern, coord_str)
    
    # Если шаблон не найден - ошибка
    if not match:
        raise ValueError(f"Неверный формат DMS: {coord_str}")
    
    # Извлекаем группы: градусы, минуты, секунды
    degrees = int(match.group(1))   # градусы (целое число)
    minutes = int(match.group(2))   # минуты (целое число)
    seconds = float(match.group(3)) # секунды (дробное число)
    
    # Перевод в десятичные градусы
    # 1 градус = 60 минут, 1 минута = 60 секунд
    # Поэтому минуты делим на 60, секунды на 3600
    decimal = degrees + minutes / 60 + seconds / 3600
    
    return decimal


def build_bbox(point1, point2):
    """
    Функция, вызываемая после получения двух точек от пользователя.
    Строит bounding box (прямоугольник) по двум точкам.
    
    Bounding box нужен для запроса к API СКДФ - он возвращает все дороги внутри этого прямоугольника.
    
    Параметры:
        point1: (lat1, lon1) - первая точка (широта, долгота)
        point2: (lat2, lon2) - вторая точка (широта, долгота)
    
    Возвращает:
        tuple: (west, south, east, north) в порядке, который ожидает API СКДФ

    Пример:
        point1 = (55.91, 37.73)  # северо-запад
        point2 = (55.86, 37.71)  # юго-восток
        build_bbox(...) -> (37.71, 55.86, 37.73, 55.91)
    """
    # Распаковываем координаты из кортежей
    lat1, lon1 = point1
    lat2, lon2 = point2
    
    # Вычисляем границы (берём минимальные и максимальные значения)
    # Примечание: чем больше число широты, тем севернее
    north = max(lat1, lat2)   # север = самая большая широта
    south = min(lat1, lat2)   # юг = самая маленькая широта
    
    # Чем больше число долготы, тем восточнее
    east = max(lon1, lon2)    # восток = самая большая долгота
    west = min(lon1, lon2)    # запад = самая маленькая долгота
    
    # Для отладки (пишем в лог, но только если включён режим DEBUG)
    logger.debug(f"Bbox: west={west}, south={south}, east={east}, north={north}")
    
    return west, south, east, north

def convert_bbox_to_skdf(bbox_4326):
    """
    Переводит bbox из градусов (EPSG:4326) в метры (EPSG:3857) для API СКДФ.
    Возвращает [xmin, ymin, xmax, ymax] в метрах.
    """
    
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    west, south, east, north = bbox_4326
    
    xmin, ymin = transformer.transform(west, south)
    xmax, ymax = transformer.transform(east, north)
    
    logger.debug(f"Bbox в метрах: xmin={xmin}, ymin={ymin}, xmax={xmax}, ymax={ymax}")
    
    return [xmin, ymin, xmax, ymax]



# ============= ТЕСТЫ =============
if __name__ == "__main__":
    print("\n=== Тест координат ===\n")
    
    # Ввод двух точек
    print("Введите первую точку (северо-запад):")
    lat1, lon1 = parse_coordinate(input())
    
    print("Введите вторую точку (юго-восток):")
    lat2, lon2 = parse_coordinate(input())
    
    # Строим bbox
    bbox = build_bbox((lat1, lon1), (lat2, lon2))
    print(f"Bbox (west, south, east, north): {bbox}")
    
    # Конвертируем в метры для СКДФ
    bbox_skdf = convert_bbox_to_skdf(bbox)
    print(f"Bbox в метрах: {bbox_skdf}")