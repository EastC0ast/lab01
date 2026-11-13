import pandas as pd

def get_stat(data, column_name):
    stats = {
        "Сумма": data.sum(),
        "Среднее": data.mean(),
        "Медиана": data.median(),
        "Минимум": data.min(),
        "Максимум": data.max(),
        "Стандартное отклонение": data.std(),
        "95-й перцентиль": data.quantile(0.95),
        "Дисперсия": data.var(),
        "Мода": data.mode().iloc[0],
    }
    return pd.DataFrame(stats.values(), index=stats.keys(), columns=[column_name])
