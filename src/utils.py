# src/utils.py
from starlette.datastructures import FormData

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