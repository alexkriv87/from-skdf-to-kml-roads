# logger_config.py
# Модуль для настройки логирования

import logging
import sys
from pathlib import Path

def setup_logger(name="skdf_app", log_level=logging.INFO, log_to_file=True):
    """
    Настраивает логгер для приложения.
    
    Параметры:
        name: имя логгера
        log_level: уровень логирования (DEBUG, INFO, WARNING, ERROR)
        log_to_file: сохранять ли лог в файл
    
    Возвращает:
        logger: настроенный экземпляр логгера
    """
    # Создаём логгер
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Удаляем старые обработчики, если есть
    if logger.handlers:
        logger.handlers.clear()
    
    # Формат сообщений: время - уровень - сообщение
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                  datefmt='%H:%M:%S')
    
    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Обработчик для записи в файл (опционально)
    if log_to_file:
        # Создаём папку logs, если её нет
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # Имя файла: skdf_app_YYYYMMDD.log
        from datetime import datetime
        log_filename = log_dir / f"skdf_app_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"Лог-файл: {log_filename}")
    
    return logger


# Создаём глобальный логгер для всего приложения
logger = setup_logger()

# Уровни логирования для разных ситуаций:
# logger.debug()   - для отладки (детальная информация)
# logger.info()    - для обычных сообщений (что происходит)
# logger.warning() - для предупреждений (что-то пошло не так, но не критично)
# logger.error()   - для ошибок (что-то не работает)