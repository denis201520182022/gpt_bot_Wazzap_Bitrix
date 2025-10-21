# src/utils.py
from starlette.datastructures import FormData
import re

def parse_form_data(data: FormData) -> dict:
    """
    Преобразует "плоскую" FormData от Битрикс24 во вложенный словарь.
    Пример: ключ 'data[FIELDS][ID]' превратится в {'data': {'FIELDS': {'ID': ...}}}
    """
    parsed_dict = {}
    for key, value in data.items():
        # Разбираем ключ на части, например, 'data[FIELDS][ID]' -> ['data', 'FIELDS', 'ID']
        parts = key.replace("]", "").split("[")
        
        # Двигаемся по словарю, создавая вложенные словари по необходимости
        d = parsed_dict
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        
        # В конце присваиваем значение
        d[parts[-1]] = value
        
    return parsed_dict

def normalize_phone(phone_number: str) -> str:

    if not phone_number:
        return ""
# re.sub(r'\D', '', ...) находит все не-цифры (\D) и заменяет их на пустую строку
    return re.sub(r'\D', '', phone_number)