# gui.py
# Графический интерфейс для выгрузки дорог из СКДФ в KML

import tkinter as tk
from tkinter import ttk, filedialog
import threading
import pandas as pd
from datetime import datetime

from main import run_export_batch


def log_message(message):
    """Выводит сообщение в лог-поле"""
    log_text.insert(tk.END, message + "\n")
    log_text.see(tk.END)
    root.update_idletasks()


def display_queries():
    """Отображает текущий список запросов в виде таблицы в логе"""
    if queries_df.empty:
        return

    # Очищаем лог для отображения таблицы (но сохраняем историю?)
    # Решение: вставляем таблицу в начало лога с разделителями
    log_text.insert(tk.END, "\n" + "=" * 100 + "\n")
    log_text.insert(tk.END, "ТЕКУЩИЕ ЗАПРОСЫ\n")
    log_text.insert(tk.END, "=" * 100 + "\n")

    # Заголовки
    log_text.insert(
        tk.END, f"{'№':<3} {'Северо-запад':<35} {'Юго-восток':<35} {'Zoom':<5} {'Категории':<20}\n")
    log_text.insert(tk.END, "-" * 100 + "\n")

    for idx, row in queries_df.iterrows():
        categories = []
        if row['federal']:
            categories.append("фед")
        if row['regional']:
            categories.append("рег")
        if row['local']:
            categories.append("мест")
        if row['km_posts']:
            categories.append("столбы")
        cat_str = ", ".join(categories) if categories else "нет"

        # Обрезаем длинные строки
        nw_short = row['nw_input'][:35] + \
            "..." if len(row['nw_input']) > 35 else row['nw_input']
        se_short = row['se_input'][:35] + \
            "..." if len(row['se_input']) > 35 else row['se_input']

        log_text.insert(
            tk.END, f"{idx + 1:<3} {nw_short:<35} {se_short:<35} {row['zoom']:<5} {cat_str:<20}\n")

    log_text.insert(tk.END, "=" * 100 + "\n\n")
    log_text.see(tk.END)


def add_query():
    """Добавляет текущие параметры в список запросов"""
    nw_input = entry_nw.get().strip()
    se_input = entry_se.get().strip()
    zoom_input = entry_zoom.get().strip()

    # Проверка заполнения полей
    if not nw_input:
        log_message("Ошибка: введите северо-западную точку")
        return
    if not se_input:
        log_message("Ошибка: введите юго-восточную точку")
        return

    # Парсим zoom
    zoom = 14
    if zoom_input:
        try:
            zoom = int(zoom_input)
            if zoom < 6 or zoom > 18:
                log_message("Ошибка: zoom должен быть от 6 до 18")
                return
        except ValueError:
            log_message("Ошибка: zoom должен быть числом")
            return

    # Формируем словарь selected на основе чекбоксов
    selected = {
        'federal': federal_var.get(),
        'regional': regional_var.get(),
        'local': local_var.get(),
        'km_posts': pillars_var.get()
    }

    # Проверка: столбы только с федеральными
    if selected['km_posts'] and not selected['federal']:
        log_message(
            "Ошибка: километровые столбы можно выбирать только вместе с федеральными дорогами")
        return

    # Проверка: выбрана хотя бы одна категория
    if not any([selected['federal'], selected['regional'], selected['local']]):
        log_message(
            "Ошибка: выберите хотя бы одну категорию дорог (федеральные, региональные или местные)")
        return

    # Добавляем запрос в DataFrame
    global queries_df
    new_row = pd.DataFrame([{
        'nw_input': nw_input,
        'se_input': se_input,
        'zoom': zoom,
        'federal': selected['federal'],
        'regional': selected['regional'],
        'local': selected['local'],
        'km_posts': selected['km_posts']
    }])
    queries_df = pd.concat([queries_df, new_row], ignore_index=True)

    log_message(f"Запрос {len(queries_df)} добавлен")
    display_queries()

    # Очистка полей ввода
    entry_nw.delete(0, tk.END)
    entry_se.delete(0, tk.END)
    entry_zoom.delete(0, tk.END)
    entry_zoom.insert(0, "14")

    # Сброс чекбоксов к значениям по умолчанию
    federal_var.set(True)
    regional_var.set(True)
    local_var.set(False)
    pillars_var.set(False)

    # Обновляем состояние чекбокса столбов
    on_federal_change()


def clear_all_queries():
    """Очищает список запросов"""
    global queries_df
    queries_df = pd.DataFrame(
        columns=['nw_input', 'se_input', 'zoom', 'federal', 'regional', 'local', 'km_posts'])
    log_message("Список запросов очищен")
    display_queries()


def run_export_thread():
    """Запускает пакетный экспорт в отдельном потоке"""
    if queries_df.empty:
        log_message(
            "Ошибка: нет добавленных запросов. Сначала добавьте хотя бы один запрос")
        return

    # Получаем путь к файлу
    output_file = file_path_var.get().strip()
    if not output_file:
        log_message("Ошибка: выберите файл для сохранения")
        return

    # Блокируем кнопки на время работы
    btn_add.config(state="disabled")
    btn_clear.config(state="disabled")
    btn_run.config(state="disabled")
    btn_choose.config(state="disabled")

    log_message("=" * 60)
    log_message(f"Запуск пакетной обработки: {len(queries_df)} запросов")
    log_message("=" * 60)

    # Запускаем экспорт в отдельном потоке
    def target():
        try:
            run_export_batch(queries_df, output_file, log_callback=log_message)
        except Exception as e:
            log_message(f"Ошибка: {e}")
            import traceback
            log_message(traceback.format_exc())
        finally:
            # Разблокируем кнопки после завершения
            btn_add.config(state="normal")
            btn_clear.config(state="normal")
            btn_run.config(state="normal")
            btn_choose.config(state="normal")
            log_message("\nПрограмма завершила работу")

    thread = threading.Thread(target=target, daemon=True)
    thread.start()


def paste_on_physical_v(event):
    """Обработчик Ctrl+V для любой раскладки клавиатуры"""
    if event.keycode == 86 and (event.state & 0x0004 or event.state & 0x0008):
        try:
            text = root.clipboard_get()
            event.widget.insert(tk.INSERT, text)
        except:
            pass
        return 'break'


def on_federal_change():
    """При изменении чекбокса федеральных - включаем/отключаем столбы"""
    if federal_var.get():
        pillars_check.config(state="normal")
    else:
        pillars_check.config(state="disabled")
        pillars_var.set(False)


def choose_output_file():
    """Открывает диалог выбора файла для сохранения"""
    initial_file = file_path_var.get()
    if not initial_file:
        initial_file = f"roads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"

    selected_file = filedialog.asksaveasfilename(
        defaultextension=".kml",
        filetypes=[("KML files", "*.kml"), ("All files", "*.*")],
        initialfile=initial_file
    )
    if selected_file:
        file_path_var.set(selected_file)


# ============================================================================
# СОЗДАНИЕ ОКНА
# ============================================================================
root = tk.Tk()
root.title("СКДФ → KML")
root.geometry("850x1000")

# Инициализация DataFrame для запросов
queries_df = pd.DataFrame(
    columns=['nw_input', 'se_input', 'zoom', 'federal', 'regional', 'local', 'km_posts'])

# === ПЕРВОЕ ПОЛЕ ===
label_nw = ttk.Label(root, text="Северо-запад (lat, lon):")
label_nw.pack(pady=(10, 0))

entry_nw = ttk.Entry(root, width=60)
entry_nw.pack(pady=5)
entry_nw.bind('<Key>', paste_on_physical_v)

# === ВТОРОЕ ПОЛЕ ===
label_se = ttk.Label(root, text="Юго-восток (lat, lon):")
label_se.pack(pady=(10, 0))

entry_se = ttk.Entry(root, width=60)
entry_se.pack(pady=5)
entry_se.bind('<Key>', paste_on_physical_v)

# === Zoom ===
label_zoom = ttk.Label(root, text="Zoom (6-18, по умолчанию 14):")
label_zoom.pack(pady=(10, 0))

entry_zoom = ttk.Entry(root, width=10)
entry_zoom.pack(pady=5)
entry_zoom.bind('<Key>', paste_on_physical_v)

# === Чекбоксы ===
federal_var = tk.BooleanVar(value=True)
regional_var = tk.BooleanVar(value=True)
local_var = tk.BooleanVar(value=False)
pillars_var = tk.BooleanVar(value=False)

check_federal = ttk.Checkbutton(
    root, text="Федеральные", variable=federal_var, command=on_federal_change)
check_federal.pack(pady=2)

check_regional = ttk.Checkbutton(
    root, text="Региональные", variable=regional_var)
check_regional.pack(pady=2)

check_local = ttk.Checkbutton(root, text="Местные", variable=local_var)
check_local.pack(pady=2)

pillars_check = ttk.Checkbutton(
    root, text="Километровые столбы", variable=pillars_var, state="normal")
pillars_check.pack(pady=2)

# === КНОПКИ УПРАВЛЕНИЯ ЗАПРОСАМИ ===
button_frame = ttk.Frame(root)
button_frame.pack(pady=10)

btn_add = ttk.Button(button_frame, text="Добавить запрос",
                     command=add_query, width=15)
btn_add.pack(side="left", padx=5)

btn_clear = ttk.Button(button_frame, text="Очистить всё",
                       command=clear_all_queries, width=15)
btn_clear.pack(side="left", padx=5)

# === ВЫБОР ФАЙЛА ===
file_label = ttk.Label(root, text="Файл для сохранения:")
file_label.pack(pady=(15, 0))

file_frame = ttk.Frame(root)
file_frame.pack(pady=5)

file_path_var = tk.StringVar()
file_entry = ttk.Entry(file_frame, textvariable=file_path_var, width=45)
file_entry.pack(side="left", padx=(0, 5))

btn_choose = ttk.Button(file_frame, text="Обзор...",
                        command=choose_output_file)
btn_choose.pack(side="left")

# === КНОПКА ЗАПУСКА ===
btn_run = ttk.Button(root, text="ВЫПОЛНИТЬ ВСЕ ЗАПРОСЫ",
                     command=run_export_thread, width=30)
btn_run.pack(pady=15)

# === ОКНО ВЫВОДА (ЛОГ) ===
log_label = ttk.Label(root, text="Статус выполнения:")
log_label.pack(pady=(15, 5))

log_text = tk.Text(root, height=25, width=100, wrap="word")
log_text.pack(pady=5)

# Полоса прокрутки
scrollbar = ttk.Scrollbar(root, orient="vertical", command=log_text.yview)
scrollbar.pack(side="right", fill="y")
log_text.configure(yscrollcommand=scrollbar.set)

# ============================================================================
# ЗАПУСК ОКНА
# ============================================================================
if __name__ == "__main__":
    log_message("Программа запущена")
    log_message("Добавьте запросы и нажмите 'ВЫПОЛНИТЬ ВСЕ ЗАПРОСЫ'")
    root.mainloop()
