# category_filter.py
# Модуль для работы с фильтром категорий дорог

import geopandas as gpd


def get_user_filter():
    """
    Запрашивает у пользователя выбор категорий через консоль.

    Возвращает:
        dict: selected с полями federal, regional, local, km_posts
    """
    while True:
        print("\n" + "=" * 50)
        print("ВЫБОР КАТЕГОРИЙ ДОРОГ")
        print("=" * 50)
        print("  0 - всё (федеральные + региональные + местные + столбы)")
        print("  1 - федеральные дороги")
        print("  2 - региональные дороги")
        print("  3 - местные дороги")
        print("  4 - километровые столбы (только с федеральными)")
        print("-" * 50)

        user_input = input("Ваш выбор (цифры через пробел): ").strip()

        # Проверка: не пустой ли ввод
        if not user_input:
            print("\nОшибка: введите хотя бы одну цифру\n")
            continue

        # Разбиваем строку на отдельные цифры
        numbers = user_input.split()

        # Создаём словарь с выбранными опциями (все False по умолчанию)
        selected = {
            'federal': False,
            'regional': False,
            'local': False,
            'km_posts': False
        }

        # Обрабатываем каждую введённую цифру
        valid_input = True
        for num in numbers:
            if num == '0':
                selected['federal'] = True
                selected['regional'] = True
                selected['local'] = True
                selected['km_posts'] = True
                return selected  # 0 означает всё, дальше проверять не нужно
            elif num == '1':
                selected['federal'] = True
            elif num == '2':
                selected['regional'] = True
            elif num == '3':
                selected['local'] = True
            elif num == '4':
                selected['km_posts'] = True
            else:
                print(f"\nОшибка: неизвестная цифра '{num}'\n")
                valid_input = False
                break  # выходим из цикла, будет повторный запрос

        if not valid_input:
            continue

        # Проверка: столбы можно выбирать только вместе с федеральными
        if selected['km_posts'] and not selected['federal']:
            print(
                "\nОшибка: километровые столбы (4) можно выбирать только вместе с федеральными дорогами (1)")
            print("Попробуйте: 1 4   или   0\n")
            continue

        # Проверка: выбрано хоть что-то
        if not any([selected['federal'], selected['regional'], selected['local'], selected['km_posts']]):
            print("\nОшибка: выберите хотя бы одну категорию\n")
            continue

        # Выводим итоговый выбор
        print("\nВыбрано:")
        if selected['federal']:
            print("  - федеральные дороги")
        if selected['regional']:
            print("  - региональные дороги")
        if selected['local']:
            print("  - местные дороги")
        if selected['km_posts']:
            print("  - километровые столбы")
        print()

        return selected


def filter_gdf_by_categories(gdf, selected):
    """
    Фильтрует GeoDataFrame по выбранным категориям.

    Параметры:
        gdf: GeoDataFrame с колонкой 'категория'
        selected: словарь с выбором пользователя

    Возвращает:
        GeoDataFrame: отфильтрованный (только выбранные категории дорог)
    """
    # Собираем список категорий для фильтрации
    cats_to_keep = []

    if selected['federal']:
        cats_to_keep.append('федеральные')
    if selected['regional']:
        cats_to_keep.append('региональные')
    if selected['local']:
        cats_to_keep.append('местные')

    # Если нет ни одной категории дорог — возвращаем пустой GeoDataFrame
    if not cats_to_keep:
        return gpd.GeoDataFrame()

    # Фильтруем
    filtered_gdf = gdf[gdf['категория'].isin(cats_to_keep)].copy()

    # Информируем пользователя
    print(f"Фильтр применён: {len(filtered_gdf)} дорог из {len(gdf)}")

    return filtered_gdf


def need_km_posts(selected):
    """Возвращает True, если пользователь выбрал километровые столбы."""
    return selected.get('km_posts', False)


def need_federal_for_posts(selected):
    """
    Возвращает True, если для столбов нужно загружать федеральные дороги,
    но при этом пользователь не выбрал их для отображения.
    """
    return selected.get('km_posts', False) and not selected.get('federal', False)


def cat_to_key(category):
    """Преобразует название категории в ключ словаря selected."""
    mapping = {
        'федеральные': 'federal',
        'региональные': 'regional',
        'местные': 'local'
    }
    return mapping.get(category, '')
