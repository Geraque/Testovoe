from decimal import Decimal, InvalidOperation
from typing import Iterable


def decimal_number(value: object) -> Decimal:
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"Некорректное число: {value!r}") from error
    if not number.is_finite():
        raise ValueError(f"Число должно быть конечным: {value!r}")
    return number


def wagon_count(value: object, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ValueError(f"Некорректное количество вагонов: {value!r}")
    return value


def require_unique(rows: Iterable[dict], field: str) -> None:
    seen = set()
    for row in rows:
        identifier = row[field]
        if identifier in seen:
            raise ValueError(f"Повторяющееся значение {field}: {identifier!r}")
        seen.add(identifier)
