import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


EXPECTED_Z1 = {
    "po_zayavkam": {
        "0000700188": [
            {"nakladnaya": "A1003", "vagonov": 12, "massa_t": 708.0, "sverh_zayavki": 0},
            {"nakladnaya": "A1001", "vagonov": 18, "massa_t": 1062.0, "sverh_zayavki": 0},
        ],
        "0000700120": [
            {"nakladnaya": "A1002", "vagonov": 17, "massa_t": 1003.0, "sverh_zayavki": 0},
            {"nakladnaya": "A1004", "vagonov": 16, "massa_t": 944.0, "sverh_zayavki": 0},
            {"nakladnaya": "A1005", "vagonov": 7, "massa_t": 413.0, "sverh_zayavki": 0},
        ],
        "0000700310": [
            {"nakladnaya": "A1005", "vagonov": 7, "massa_t": 413.0, "sverh_zayavki": 0},
        ],
        "0000700050": [
            {"nakladnaya": "B2001", "vagonov": 12, "massa_t": 684.0, "sverh_zayavki": 0},
            {"nakladnaya": "B2002", "vagonov": 10, "massa_t": 570.0, "sverh_zayavki": 2},
        ],
        "0000700333": [
            {"nakladnaya": "B2003", "vagonov": 9, "massa_t": 513.0, "sverh_zayavki": 0},
        ],
        "0000700400": [
            {"nakladnaya": "G3002", "vagonov": 5, "massa_t": 295.0, "sverh_zayavki": 0},
        ],
    },
    "bez_zayavki": {"Гамма-Нефть": [
        {"nakladnaya": "G3001", "vagonov": 6, "massa_t": 354.0},
    ]},
    "bez_klienta": ["X9001"],
}

EXPECTED_Z2 = {
    "svyazi": {"1": "d-101", "3": "d-103", "6": "d-105"},
    "ne_najdeno": [2, 5, 8],
    "neodnoznachno": {"4": ["d-106", "d-107"]},
    "operativnyj_ostatok": [
        {"mol": "Кузнецов И.П.", "kod": "Н-003", "operativnyj": 11.41},
        {"mol": "Кузнецов И.П.", "kod": "Н-006", "operativnyj": 640.0},
        {"mol": "Кузнецов И.П.", "kod": "Н-007", "operativnyj": 9.0},
        {"mol": "Петров А.А.", "kod": "Н-001", "operativnyj": 30.0},
        {"mol": "Петров А.А.", "kod": "Н-002", "operativnyj": 9.0},
        {"mol": "Петров А.А.", "kod": "Н-004", "operativnyj": 48.0},
        {"mol": "Сидорова Е.В.", "kod": "Н-002", "operativnyj": 20.0},
        {"mol": "Сидорова Е.В.", "kod": "Н-005", "operativnyj": 112.5},
        {"mol": "Сидорова Е.В.", "kod": "Н-008", "operativnyj": 24.0},
    ],
    "u_podryadchikov": [
        {"kontragent_id": "k-1", "kod": "Н-001", "kol": 5.0},
        {"kontragent_id": "k-1", "kod": "Н-004", "kol": 10.0},
        {"kontragent_id": "k-1", "kod": "Н-006", "kol": 150.0},
        {"kontragent_id": "k-1", "kod": "Н-007", "kol": 6.0},
        {"kontragent_id": "k-2", "kod": "Н-007", "kol": 6.0},
        {"kontragent_id": "k-3", "kod": "Н-002", "kol": 11.0},
        {"kontragent_id": "k-4", "kod": "Н-003", "kol": 20.1},
        {"kontragent_id": "k-4", "kod": "Н-007", "kol": 1.0},
    ],
}


class IntegrationTests(unittest.TestCase):
    def test_cli_null_application_state_reports_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for path in (ROOT / "data").iterdir():
                if path.is_file():
                    (data / path.name).write_bytes(path.read_bytes())
            path = data / "z1_zayavki.json"
            zayavki = json.loads(path.read_text(encoding="utf-8"))
            zayavki[0]["sostoyanie"] = None
            path.write_text(json.dumps(zayavki, ensure_ascii=False), encoding="utf-8")
            output = data / "output"
            completed = subprocess.run([
                sys.executable, "-X", "utf8", str(ROOT / "main.py"),
                "--data-dir", str(data), "--output-dir", str(output),
            ], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("Ошибка обработки данных:", completed.stderr)
            self.assertIn(f"Состояние заявки {zayavki[0]['nomer']} должно быть строкой", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertFalse(output.exists())

    def test_cli_with_supplied_data_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "результаты"
            command = [sys.executable, str(ROOT / "main.py"), "--output-dir", str(output)]
            completed = subprocess.run(command, cwd=directory, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            before = {}
            for filename, expected in (("result_z1.json", EXPECTED_Z1), ("result_z2.json", EXPECTED_Z2)):
                content = (output / filename).read_text(encoding="utf-8")
                self.assertEqual(json.loads(content), expected)
                before[filename] = (output / filename).read_bytes()
            repeated = subprocess.run(command, cwd=directory, capture_output=True)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            for filename, content in before.items():
                self.assertEqual((output / filename).read_bytes(), content)

    def test_delivered_results_match_manual_expectations(self):
        for filename, expected in (("result_z1.json", EXPECTED_Z1), ("result_z2.json", EXPECTED_Z2)):
            with self.subTest(filename=filename):
                self.assertEqual(json.loads((ROOT / filename).read_text(encoding="utf-8")), expected)

    def test_cli_missing_input_reports_error(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            completed = subprocess.run([
                sys.executable, str(ROOT / "main.py"), "--data-dir", directory,
                "--output-dir", str(output),
            ], capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue(completed.stderr)
            self.assertFalse(output.exists())

    def test_cli_does_not_write_results_if_second_task_input_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for filename in ("z1_zayavki.json", "z1_nakladnye.json"):
                (data / filename).write_bytes((ROOT / "data" / filename).read_bytes())
            (data / "z2_ostatki_1c.csv").write_bytes((ROOT / "data" / "z2_ostatki_1c.csv").read_bytes())
            (data / "z2_zhurnal.json").write_text("{invalid", encoding="utf-8")
            output = data / "output"
            completed = subprocess.run([
                sys.executable, str(ROOT / "main.py"), "--data-dir", str(data),
                "--output-dir", str(output),
            ], capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output.exists())
