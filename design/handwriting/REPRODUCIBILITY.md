# Повторный расчёт

[Отчёт](README.md) · [Расчётный ноутбук](handwriting_calculations.ipynb) · [HTML](handwriting_reading.html)

Нужны Python 3.12 и зависимости из `requirements-verified.txt`. Из корня репозитория:

```sh
python -m pip install -r requirements-verified.txt
python design/handwriting/prepare_data.py
python design/handwriting/build_study.py
```

Исходный архив находится в `data/`; повторная загрузка не требуется. Для перестановочной проверки и bootstrap задано начальное состояние `20261111` с отдельными потоками случайных чисел. Используются 19 999 перестановок и 10 000 bootstrap-выборок. Правила отбора записаны в `data/selection_plan.json`, сведения об источнике — в `data/provenance.json`.

Проверка данных и результатов:

```sh
python -m unittest discover -s design/handwriting -p test_handwriting.py -v
python design/handwriting/verify_study.py
```
