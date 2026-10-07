import argparse
import csv
import json
from decimal import Decimal
from pathlib import Path

from task1 import allocate_nakladnye
from task2 import reconcile_stock


BASE_DIR = Path(__file__).resolve().parent


def read_json(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as source:
        return json.load(source, parse_float=Decimal)


def main() -> None:
    parser = argparse.ArgumentParser(description="Распределение накладных и сверка склада")
    parser.add_argument("--data-dir", type=Path, default=BASE_DIR / "data")
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR)
    args = parser.parse_args()
    try:
        result1 = allocate_nakladnye(
            read_json(args.data_dir / "z1_zayavki.json"),
            read_json(args.data_dir / "z1_nakladnye.json"),
        )
        with (args.data_dir / "z2_ostatki_1c.csv").open(encoding="utf-8-sig", newline="") as source:
            ostatki_1c = list(csv.DictReader(source, delimiter=";"))
        result2 = reconcile_stock(
            read_json(args.data_dir / "z2_zhurnal.json"),
            read_json(args.data_dir / "z2_dokumenty_1c.json"),
            ostatki_1c,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for filename, result in (("result_z1.json", result1), ("result_z2.json", result2)):
            with (args.output_dir / filename).open("w", encoding="utf-8", newline="\n") as target:
                json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
                target.write("\n")
            print(args.output_dir / filename)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Ошибка обработки данных: {error}\n")


if __name__ == "__main__":
    main()
