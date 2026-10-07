from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from common import decimal_number, require_unique, wagon_count


@dataclass
class Zayavka:
    nomer: str
    klient: str
    nachalo: date
    konec: date
    postupila: datetime
    available_wagons: int

    @classmethod
    def from_row(cls, row: dict) -> "Zayavka":
        nachalo = parse_period_date(row["nachalo"])
        konec = parse_period_date(row["konec"])
        if konec < nachalo:
            raise ValueError(f"Обратный период заявки {row['nomer']}")
        if not row["klient"]:
            raise ValueError(f"Нет клиента у заявки {row['nomer']}")
        return cls(
            row["nomer"], row["klient"], nachalo, konec,
            datetime.strptime(row["postupila"], "%d.%m.%Y %H:%M:%S"),
            wagon_count(row["vagonov"], allow_zero=True),
        )


def split_mass(massa_t: Decimal, wagons: list[int]) -> list[Decimal]:
    if massa_t < 0:
        raise ValueError("Масса не может быть отрицательной")
    units = int((massa_t * 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    total = sum(wagons)
    shares = [divmod(units * count, total) for count in wagons]
    allocated = [whole for whole, _ in shares]
    remainder = units - sum(allocated)
    priority = sorted(range(len(wagons)), key=lambda i: -shares[i][1])
    for index in priority[:remainder]:
        allocated[index] += 1
    return [Decimal(value) / 10 for value in allocated]


def allocate_nakladnye(zayavki: list[dict], nakladnye: list[dict]) -> dict:
    require_unique(zayavki, "nomer")
    require_unique(nakladnye, "nomer")
    queues = defaultdict(list)
    for row in zayavki:
        if not row["sostoyanie"].startswith("Отозвана"):
            zayavka = Zayavka.from_row(row)
            queues[zayavka.klient].append(zayavka)
    for queue in queues.values():
        queue.sort(key=lambda item: (item.nachalo, item.postupila))
    next_positions = defaultdict(int)

    po_zayavkam = {item.nomer: [] for queue in queues.values() for item in queue}
    bez_zayavki = defaultdict(list)
    bez_klienta = []
    dated_nakladnye = [
        (datetime.strptime(row["data_otpravki"], "%d.%m.%Y %H:%M:%S"), row)
        for row in nakladnye
    ]
    for data_otpravki, nakladnaya in sorted(dated_nakladnye, key=lambda item: item[0]):
        unallocated_wagons = wagon_count(nakladnaya["vagonov"])
        massa_t = decimal_number(nakladnaya["massa_t"])
        if massa_t < 0:
            raise ValueError(f"Отрицательная масса накладной {nakladnaya['nomer']}")
        klient = nakladnaya.get("klient")
        if not klient:
            bez_klienta.append(nakladnaya["nomer"])
            continue

        queue = queues.get(klient, [])
        parts = {}
        position = next_positions[klient]
        while unallocated_wagons and position < len(queue):
            zayavka = queue[position]
            if zayavka.available_wagons == 0:
                position += 1
                continue
            if zayavka.nachalo > data_otpravki.date():
                break
            count = min(unallocated_wagons, zayavka.available_wagons)
            if count:
                parts[zayavka.nomer] = (count, 0)
                zayavka.available_wagons -= count
                unallocated_wagons -= count
        next_positions[klient] = position
        if unallocated_wagons:
            overflow = next(
                (item for item in reversed(queue) if item.nachalo <= data_otpravki.date() <= item.konec),
                None,
            )
            nomer = overflow.nomer if overflow else None
            count, _ = parts.get(nomer, (0, 0))
            parts[nomer] = (count + unallocated_wagons, unallocated_wagons if overflow else 0)

        masses = split_mass(massa_t, [count for count, _ in parts.values()])
        for (nomer, (count, sverh_zayavki)), part_mass in zip(parts.items(), masses):
            entry = {
                "nakladnaya": nakladnaya["nomer"], "vagonov": count,
                "massa_t": float(part_mass),
            }
            if nomer is None:
                bez_zayavki[klient].append(entry)
            else:
                entry["sverh_zayavki"] = sverh_zayavki
                po_zayavkam[nomer].append(entry)

    return {
        "po_zayavkam": po_zayavkam,
        "bez_zayavki": dict(bez_zayavki),
        "bez_klienta": bez_klienta,
    }


def parse_period_date(value: str) -> date:
    for date_format in ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"Некорректная дата периода заявки: {value!r}")
