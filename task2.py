from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from common import decimal_number, require_unique


DOCUMENT_KINDS = {
    "vydacha_podryadchiku": "peredacha_podryadchiku",
    "vydacha_svoim": "trebovanie",
}


def quantities(stroki: list[dict]) -> dict[str, Decimal]:
    result = defaultdict(Decimal)
    for stroka in stroki:
        kol = decimal_number(stroka["kol"])
        if kol <= 0:
            raise ValueError(f"Количество позиции {stroka['kod']} должно быть положительным")
        result[stroka["kod"]] += kol
    if not result:
        raise ValueError("Пустой набор позиций")
    return dict(result)


def match_key(vid: str, row: dict, kol_by_kod: dict[str, Decimal]) -> tuple:
    kontragent_id = row.get("kontragent_id", "") if vid == "peredacha_podryadchiku" else ""
    if vid == "peredacha_podryadchiku" and not kontragent_id:
        raise ValueError(f"Не указан контрагент: {row['id']}")
    return vid, row["mol"], kontragent_id, tuple(sorted(kol_by_kod.items()))


def reconcile_stock(zhurnal: list[dict], dokumenty: list[dict], ostatki_1c: list[dict]) -> dict:
    require_unique(zhurnal, "id")
    require_unique(dokumenty, "id")
    dokument_index = defaultdict(list)
    for dokument in dokumenty:
        vid = dokument["vid"]
        if vid in DOCUMENT_KINDS.values():
            key = match_key(vid, dokument, quantities(dokument["stroki"]))
            dokument_index[key].append((date.fromisoformat(dokument["data"]), dokument["id"]))

    operativnyj_ostatok = defaultdict(Decimal)
    u_podryadchikov = defaultdict(Decimal)
    for row in ostatki_1c:
        kol = decimal_number(row["kol"])
        if row["schet"] == "10.07":
            if not row["kontragent_id"]:
                raise ValueError("Остаток на 10.07 без контрагента")
            u_podryadchikov[row["kontragent_id"], row["kod"]] += kol
        else:
            operativnyj_ostatok[row["mol"], row["kod"]] += kol

    svyazi = {}
    ne_najdeno = []
    neodnoznachno = {}
    used_dokumenty = set()
    active = [row for row in zhurnal if row["status"] == "vydano"]
    active.sort(key=lambda row: (date.fromisoformat(row["data"]), row["id"]))
    for row in active:
        tip = row["tip"]
        if tip not in DOCUMENT_KINDS and tip != "vozvrat":
            raise ValueError(f"Неизвестный тип записи: {tip}")
        kol_by_kod = quantities(row["stroki"])
        recorded = date.fromisoformat(row["data"])
        candidates = []
        if tip in DOCUMENT_KINDS:
            key = match_key(DOCUMENT_KINDS[tip], row, kol_by_kod)
            candidates = sorted(
                identifier for documented, identifier in dokument_index.get(key, [])
                if recorded - timedelta(days=2) <= documented <= recorded + timedelta(days=14)
                and identifier not in used_dokumenty
            )
        if len(candidates) == 1:
            svyazi[str(row["id"])] = candidates[0]
            used_dokumenty.add(candidates[0])
            continue
        if candidates:
            neodnoznachno[str(row["id"])] = candidates
        else:
            ne_najdeno.append(row["id"])

        sign = 1 if tip == "vozvrat" else -1
        kontragent_id = row.get("kontragent_id")
        for kod, kol in kol_by_kod.items():
            operativnyj_ostatok[row["mol"], kod] += sign * kol
            if tip == "vydacha_podryadchiku" or (tip == "vozvrat" and kontragent_id):
                u_podryadchikov[kontragent_id, kod] -= sign * kol

    return {
        "svyazi": svyazi,
        "ne_najdeno": sorted(ne_najdeno),
        "neodnoznachno": neodnoznachno,
        "operativnyj_ostatok": [
            {"mol": mol, "kod": kod, "operativnyj": float(kol)}
            for (mol, kod), kol in sorted(operativnyj_ostatok.items())
        ],
        "u_podryadchikov": [
            {"kontragent_id": kontragent_id, "kod": kod, "kol": float(kol)}
            for (kontragent_id, kod), kol in sorted(u_podryadchikov.items()) if kol != 0
        ],
    }
