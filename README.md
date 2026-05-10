# СКДФ → KML

Программа для выгрузки дорог из API СКДФ (Справочная карта дорог федерального значения) в KML-файл с характеристиками (категория, покрытие, полосы, скорость, ширина, осевая нагрузка, километровые столбы).

## Возможности

- Парсинг координат в форматах Яндекс.Карты (десятичные градусы) и SAS.Планет (DMS)
- Пакетный режим: несколько областей поиска с разными настройками
- Фильтрация по категориям: федеральные, региональные, местные
- Километровые столбы (только для федеральных дорог)
- Группировка местных дорог по владельцам
- Группировка километровых столбов по названиям дорог
- Цветовая кодировка дорог в KML
- Экспорт в KML (совместим с SAS.Планет, Google Earth)

Сборка исполняемого файла (PyInstaller)

```bash
pyinstaller --noconfirm --onedir --console --add-data "template_all_roads.kml;." --add-data "template_road_placemark.kml;." --add-data "template_road_placemark_multiline.kml;." --collect-all fiona --collect-all pyogrio --hidden-import "geopandas" --hidden-import "shapely" --hidden-import "pyproj" --hidden-import "openpyxl" --hidden-import "pandas" --hidden-import "requests" --hidden-import "tkinter" gui.py
``` 

После сборки исполняемый файл находится в папке dist/gui/

from-skdf-to-kml-roads/

├── gui.py                          # Графический интерфейс (главный файл)

├── main.py                         # Основная логика экспорта

├── category_filter.py              # Фильтрация категорий дорог

├── skdf_api.py                     # Работа с API СКДФ

├── kml_exporter.py                 # Экспорт в KML

├── coord_utils.py                  # Парсинг координат, построение bbox

├── geometry_funcs.py               # Конвертация проекций

├── logger_config.py                # Настройка логирования

├── config.py                       # Конфигурация (цвета, категории)

├── template_*.kml                  # Шаблоны KML

├── requirements.txt                # Зависимости Python

└── README.md

Форматы ввода координат

Формат	Пример

Яндекс.Карты	55.972483, 36.911828

SAS.Планет	N51°43'15.9790" E121°07'42.0984"

Зависимости

Python ≥ 3.9

geopandas

pandas

shapely

pyproj

requests

tkinter (встроен в Python)