import copy
import unittest
from decimal import Decimal

from task1 import allocate_invoices, split_mass


def application(number="a", client="client", capacity=10, start="01.09.2026",
                end="30.09.2026", received="31.08.2026 10:00:00", state="Принята"):
    return {
        "nomer": number, "klient": client, "vagonov": capacity,
        "nachalo": start, "konec": end, "postupila": received, "sostoyanie": state,
    }


def invoice(number="n", client="client", count=1, mass="10", sent="10.09.2026 10:00:00"):
    return {
        "nomer": number, "klient": client, "vagonov": count,
        "massa_t": mass, "data_otpravki": sent,
    }


class AllocationTests(unittest.TestCase):
    def test_period_accepts_dates_and_datetimes_as_inclusive_days(self):
        for start in ("01.09.2026", "01.09.2026 12:30:00"):
            for end in ("30.09.2026", "30.09.2026 00:00:00"):
                with self.subTest(start=start, end=end):
                    result = allocate_invoices(
                        [application(capacity=0, start=start, end=end)],
                        [invoice("first", sent="01.09.2026 00:00:00"),
                         invoice("last", sent="30.09.2026 23:59:59")],
                    )
                    self.assertEqual(result, allocate_invoices(
                        [application(capacity=0)],
                        [invoice("first", sent="01.09.2026 00:00:00"),
                         invoice("last", sent="30.09.2026 23:59:59")],
                    ))
                    self.assertEqual(len(result["po_zayavkam"]["a"]), 2)

    def test_invalid_period_date_or_time_is_rejected(self):
        for field in ("nachalo", "konec"):
            for value in ("31.02.2026", "01.09.2026 25:00:00", "01.09.2026 garbage"):
                with self.subTest(field=field, value=value):
                    row = application()
                    row[field] = value
                    with self.assertRaisesRegex(ValueError, "Некорректная дата периода заявки"):
                        allocate_invoices([row], [])

    def test_rule1_withdrawn_applications_are_excluded(self):
        for state in ("Отозвана", "Отозвана до обработки", "Отозвана после согласования"):
            with self.subTest(state=state):
                result = allocate_invoices([application(state=state)], [invoice()])
                self.assertEqual(result["po_zayavkam"], {})
                self.assertEqual(result["bez_zayavki"]["client"][0]["vagonov"], 1)

    def test_rule2_clients_do_not_share_capacity_or_overflow(self):
        result = allocate_invoices(
            [application(client="other")], [invoice(count=15)],
        )
        self.assertEqual(result["po_zayavkam"]["a"], [])
        self.assertEqual(result["bez_zayavki"]["client"][0]["vagonov"], 15)

    def test_rule3_start_date_has_priority_over_received_date(self):
        result = allocate_invoices([
            application("later", start="05.09.2026", received="01.08.2026 10:00:00"),
            application("earlier", received="31.08.2026 10:00:00"),
        ], [invoice()])
        self.assertEqual(result["po_zayavkam"]["later"], [])
        self.assertEqual(result["po_zayavkam"]["earlier"][0]["vagonov"], 1)

    def test_rule3_received_date_breaks_tie_not_number(self):
        result = allocate_invoices([
            application("001", received="31.08.2026 10:00:00"),
            application("999", received="30.08.2026 10:00:00"),
        ], [invoice()])
        self.assertEqual(result["po_zayavkam"]["001"], [])
        self.assertEqual(result["po_zayavkam"]["999"][0]["vagonov"], 1)

    def test_exact_queue_tie_preserves_input_order(self):
        result = allocate_invoices([application("z"), application("a")], [invoice()])
        self.assertEqual(result["po_zayavkam"]["a"], [])
        self.assertEqual(result["po_zayavkam"]["z"][0]["vagonov"], 1)

    def test_rule4_invoices_sorted_by_timestamp(self):
        result = allocate_invoices([application(capacity=1)], [
            invoice("late", sent="10.09.2026 11:00:00"),
            invoice("early", sent="10.09.2026 09:00:00"),
        ])
        self.assertEqual(
            [(row["nakladnaya"], row["sverh_zayavki"]) for row in result["po_zayavkam"]["a"]],
            [("early", 0), ("late", 1)],
        )

    def test_rule5_future_application_cannot_accept(self):
        result = allocate_invoices([application(start="11.09.2026")], [invoice()])
        self.assertEqual(result["po_zayavkam"]["a"], [])
        self.assertEqual(result["bez_zayavki"]["client"][0]["vagonov"], 1)

    def test_rule5_expired_application_filled_before_current(self):
        result = allocate_invoices([
            application("old", end="09.09.2026"),
            application("current", start="10.09.2026"),
        ], [invoice()])
        self.assertEqual(result["po_zayavkam"]["old"][0]["sverh_zayavki"], 0)
        self.assertEqual(result["po_zayavkam"]["current"], [])

    def test_rule6_invoice_split_and_mass_preserved(self):
        result = allocate_invoices(
            [application("a", capacity=1), application("b", capacity=2)],
            [invoice(count=3, mass="10")],
        )
        self.assertEqual(result["po_zayavkam"], {
            "a": [{"nakladnaya": "n", "vagonov": 1, "massa_t": 3.3, "sverh_zayavki": 0}],
            "b": [{"nakladnaya": "n", "vagonov": 2, "massa_t": 6.7, "sverh_zayavki": 0}],
        })

    def test_rule7_overflow_uses_last_matching_period_in_queue(self):
        result = allocate_invoices([
            application("a", capacity=0), application("b", capacity=0),
            application("expired", capacity=0, start="02.09.2026", end="09.09.2026"),
            application("future", capacity=100, start="11.09.2026"),
        ], [invoice(count=2)])
        self.assertEqual(result["po_zayavkam"]["b"][0]["sverh_zayavki"], 2)
        self.assertTrue(all(not result["po_zayavkam"][key] for key in ("a", "expired", "future")))

    def test_rule7_regular_and_overflow_parts_are_combined(self):
        result = allocate_invoices([application(capacity=1)], [invoice(count=3, mass="30")])
        self.assertEqual(
            [(row["vagonov"], row["sverh_zayavki"], row["massa_t"])
             for row in result["po_zayavkam"]["a"]],
            [(3, 2, 30.0)],
        )

    def test_mass_is_rounded_after_combining_parts_by_application(self):
        result = allocate_invoices(
            [application("a", capacity=1), application("b", capacity=1)],
            [invoice(count=3, mass="0.1")],
        )
        self.assertEqual(result["po_zayavkam"], {
            "a": [{"nakladnaya": "n", "vagonov": 1, "massa_t": 0.0, "sverh_zayavki": 0}],
            "b": [{"nakladnaya": "n", "vagonov": 2, "massa_t": 0.1, "sverh_zayavki": 1}],
        })

    def test_overflow_combines_with_earlier_application(self):
        result = allocate_invoices([
            application("a", capacity=1),
            application("b", capacity=1, start="02.09.2026", end="09.09.2026"),
        ], [invoice(count=3, mass="30")])
        self.assertEqual(result["po_zayavkam"], {
            "a": [{"nakladnaya": "n", "vagonov": 2, "massa_t": 20.0, "sverh_zayavki": 1}],
            "b": [{"nakladnaya": "n", "vagonov": 1, "massa_t": 10.0, "sverh_zayavki": 0}],
        })

    def test_rule7_period_boundaries_include_whole_day(self):
        for sent in ("01.09.2026 00:00:00", "30.09.2026 23:59:59"):
            with self.subTest(sent=sent):
                result = allocate_invoices([application(capacity=0)], [invoice(sent=sent)])
                self.assertEqual(result["po_zayavkam"]["a"][0]["sverh_zayavki"], 1)

    def test_rule8_leftover_outside_period_has_no_application(self):
        result = allocate_invoices(
            [application(capacity=1, end="09.09.2026")], [invoice(count=3, mass="30")],
        )
        self.assertEqual(result["bez_zayavki"], {
            "client": [{"nakladnaya": "n", "vagonov": 2, "massa_t": 20.0}],
        })

    def test_rule8_missing_clients_have_separate_list(self):
        result = allocate_invoices([], [invoice("empty", client=""), invoice("null", client=None)])
        self.assertEqual(result["bez_klienta"], ["empty", "null"])
        self.assertEqual(result["bez_zayavki"], {})

    def test_mass_rounding_uses_largest_remainders_and_stable_ties(self):
        self.assertEqual(split_mass(Decimal("1"), [1, 1, 1]),
                         [Decimal("0.4"), Decimal("0.3"), Decimal("0.3")])
        self.assertEqual(split_mass(Decimal("0.1"), [1, 1, 1]),
                         [Decimal("0.1"), Decimal("0"), Decimal("0")])
        self.assertEqual(split_mass(Decimal("1.25"), [1]), [Decimal("1.3")])

    def test_mass_and_wagons_conserved_for_many_small_allocations(self):
        for capacity in range(5):
            for count in range(1, 12):
                for mass in ("0", "0.1", "1", "100.7"):
                    result = allocate_invoices(
                        [application("a", capacity=capacity), application("b", capacity=capacity)],
                        [invoice(count=count, mass=mass)],
                    )
                    rows = [row for group in result["po_zayavkam"].values() for row in group]
                    self.assertEqual(sum(row["vagonov"] for row in rows), count)
                    self.assertEqual(sum(Decimal(str(row["massa_t"])) for row in rows), Decimal(mass))
                    self.assertTrue(all(row["massa_t"] >= 0 for row in rows))

    def test_inputs_are_not_modified_and_repeated_runs_equal(self):
        applications, invoices = [application()], [invoice()]
        original = copy.deepcopy((applications, invoices))
        first = allocate_invoices(applications, invoices)
        self.assertEqual(first, allocate_invoices(applications, invoices))
        self.assertEqual((applications, invoices), original)

    def test_invalid_data_rejected(self):
        cases = [
            ([application(), application()], [invoice()]),
            ([application()], [invoice(), invoice()]),
            ([application(end="01.08.2026")], []),
            ([application(capacity=-1)], []),
            ([], [invoice(count=0)]),
            ([], [invoice(count=True)]),
            ([], [invoice(mass="-1")]),
            ([], [invoice(mass="NaN")]),
        ]
        for applications, invoices in cases:
            with self.subTest(applications=applications, invoices=invoices):
                with self.assertRaises(ValueError):
                    allocate_invoices(applications, invoices)

    def test_empty_inputs(self):
        self.assertEqual(allocate_invoices([], []), {
            "po_zayavkam": {}, "bez_zayavki": {}, "bez_klienta": [],
        })
