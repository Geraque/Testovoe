from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from common import decimal_number, require_unique, wagon_count


@dataclass
class Application:
    number: str
    client: str
    start: date
    end: date
    received: datetime
    remaining: int

    @classmethod
    def from_row(cls, row: dict) -> "Application":
        start = datetime.strptime(row["nachalo"], "%d.%m.%Y").date()
        end = datetime.strptime(row["konec"], "%d.%m.%Y").date()
        if end < start:
            raise ValueError(f"Обратный период заявки {row['nomer']}")
        if not row["klient"]:
            raise ValueError(f"Нет клиента у заявки {row['nomer']}")
        return cls(
            row["nomer"], row["klient"], start, end,
            datetime.strptime(row["postupila"], "%d.%m.%Y %H:%M:%S"),
            wagon_count(row["vagonov"], allow_zero=True),
        )


def split_mass(mass: Decimal, wagons: list[int]) -> list[Decimal]:
    if mass < 0:
        raise ValueError("Масса не может быть отрицательной")
    units = int((mass * 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    total = sum(wagons)
    shares = [divmod(units * count, total) for count in wagons]
    allocated = [whole for whole, _ in shares]
    remainder = units - sum(allocated)
    priority = sorted(range(len(wagons)), key=lambda i: -shares[i][1])
    for index in priority[:remainder]:
        allocated[index] += 1
    return [Decimal(value) / 10 for value in allocated]


def allocate_invoices(applications: list[dict], invoices: list[dict]) -> dict:
    require_unique(applications, "nomer")
    require_unique(invoices, "nomer")
    queues = defaultdict(list)
    for row in applications:
        if not row["sostoyanie"].startswith("Отозвана"):
            application = Application.from_row(row)
            queues[application.client].append(application)
    for queue in queues.values():
        queue.sort(key=lambda item: (item.start, item.received))

    by_application = {item.number: [] for queue in queues.values() for item in queue}
    without_application = defaultdict(list)
    without_client = []
    dated_invoices = [
        (datetime.strptime(row["data_otpravki"], "%d.%m.%Y %H:%M:%S"), row)
        for row in invoices
    ]
    for sent, invoice in sorted(dated_invoices, key=lambda item: item[0]):
        remaining = wagon_count(invoice["vagonov"])
        mass = decimal_number(invoice["massa_t"])
        if mass < 0:
            raise ValueError(f"Отрицательная масса накладной {invoice['nomer']}")
        client = invoice.get("klient")
        if not client:
            without_client.append(invoice["nomer"])
            continue

        queue = queues.get(client, [])
        parts = []
        for application in queue:
            if remaining == 0 or application.start > sent.date():
                break
            count = min(remaining, application.remaining)
            if count:
                parts.append((application.number, count, False))
                application.remaining -= count
                remaining -= count
        if remaining:
            overflow = next(
                (item for item in reversed(queue) if item.start <= sent.date() <= item.end),
                None,
            )
            parts.append((overflow.number if overflow else None, remaining, True))

        masses = split_mass(mass, [count for _, count, _ in parts])
        for (number, count, is_overflow), part_mass in zip(parts, masses):
            entry = {
                "nakladnaya": invoice["nomer"], "vagonov": count,
                "massa_t": float(part_mass),
            }
            if number is None:
                without_application[client].append(entry)
            else:
                entry["sverh_zayavki"] = count if is_overflow else 0
                by_application[number].append(entry)

    return {
        "po_zayavkam": by_application,
        "bez_zayavki": dict(without_application),
        "bez_klienta": without_client,
    }
