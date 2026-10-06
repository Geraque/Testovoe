from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from common import decimal_number, require_unique


DOCUMENT_KINDS = {
    "vydacha_podryadchiku": "peredacha_podryadchiku",
    "vydacha_svoim": "trebovanie",
}


def quantities(lines: list[dict]) -> dict[str, Decimal]:
    result = defaultdict(Decimal)
    for line in lines:
        quantity = decimal_number(line["kol"])
        if quantity <= 0:
            raise ValueError(f"Количество позиции {line['kod']} должно быть положительным")
        result[line["kod"]] += quantity
    if not result:
        raise ValueError("Пустой набор позиций")
    return dict(result)


def match_key(kind: str, row: dict, items: dict[str, Decimal]) -> tuple:
    contractor = row.get("kontragent_id", "") if kind == "peredacha_podryadchiku" else ""
    if kind == "peredacha_podryadchiku" and not contractor:
        raise ValueError(f"Не указан контрагент: {row['id']}")
    return kind, row["mol"], contractor, tuple(sorted(items.items()))


def reconcile_stock(journal: list[dict], documents: list[dict], balances: list[dict]) -> dict:
    require_unique(journal, "id")
    require_unique(documents, "id")
    document_index = defaultdict(list)
    for document in documents:
        kind = document["vid"]
        if kind in DOCUMENT_KINDS.values():
            key = match_key(kind, document, quantities(document["stroki"]))
            document_index[key].append((date.fromisoformat(document["data"]), document["id"]))

    stock = defaultdict(Decimal)
    contractors = defaultdict(Decimal)
    for row in balances:
        quantity = decimal_number(row["kol"])
        if row["schet"] == "10.07":
            if not row["kontragent_id"]:
                raise ValueError("Остаток на 10.07 без контрагента")
            contractors[row["kontragent_id"], row["kod"]] += quantity
        else:
            stock[row["mol"], row["kod"]] += quantity

    links = {}
    not_found = []
    ambiguous = {}
    used_documents = set()
    active = [row for row in journal if row["status"] == "vydano"]
    active.sort(key=lambda row: (date.fromisoformat(row["data"]), row["id"]))
    for row in active:
        kind = row["tip"]
        if kind not in DOCUMENT_KINDS and kind != "vozvrat":
            raise ValueError(f"Неизвестный тип записи: {kind}")
        items = quantities(row["stroki"])
        recorded = date.fromisoformat(row["data"])
        candidates = []
        if kind in DOCUMENT_KINDS:
            key = match_key(DOCUMENT_KINDS[kind], row, items)
            candidates = sorted(
                identifier for documented, identifier in document_index.get(key, [])
                if recorded - timedelta(days=2) <= documented <= recorded + timedelta(days=14)
                and identifier not in used_documents
            )
        if len(candidates) == 1:
            links[str(row["id"])] = candidates[0]
            used_documents.add(candidates[0])
            continue
        if candidates:
            ambiguous[str(row["id"])] = candidates
        else:
            not_found.append(row["id"])

        sign = 1 if kind == "vozvrat" else -1
        contractor = row.get("kontragent_id")
        for code, quantity in items.items():
            stock[row["mol"], code] += sign * quantity
            if kind == "vydacha_podryadchiku" or (kind == "vozvrat" and contractor):
                contractors[contractor, code] -= sign * quantity

    return {
        "svyazi": links,
        "ne_najdeno": sorted(not_found),
        "neodnoznachno": ambiguous,
        "operativnyj_ostatok": [
            {"mol": mol, "kod": code, "operativnyj": float(quantity)}
            for (mol, code), quantity in sorted(stock.items())
        ],
        "u_podryadchikov": [
            {"kontragent_id": contractor, "kod": code, "kol": float(quantity)}
            for (contractor, code), quantity in sorted(contractors.items()) if quantity != 0
        ],
    }
