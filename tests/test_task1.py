import copy
import unittest
from decimal import Decimal

from task1 import allocate_nakladnye, split_mass


def zayavka(nomer="a", klient="client", vagonov=10, nachalo="01.09.2026",
                konec="30.09.2026", postupila="31.08.2026 10:00:00", sostoyanie="Принята"):
    return {
        "nomer": nomer, "klient": klient, "vagonov": vagonov,
        "nachalo": nachalo, "konec": konec, "postupila": postupila, "sostoyanie": sostoyanie,
    }


def nakladnaya(nomer="n", klient="client", vagonov=1, massa_t="10", data_otpravki="10.09.2026 10:00:00"):
    return {
        "nomer": nomer, "klient": klient, "vagonov": vagonov,
        "massa_t": massa_t, "data_otpravki": data_otpravki,
    }


class AllocationTests(unittest.TestCase):
    def test_queue_progress_is_independent_and_keeps_future_application(self):
        result = allocate_nakladnye([
            zayavka("zero", vagonov=0),
            zayavka("a", vagonov=2),
            zayavka("future", vagonov=2, nachalo="11.09.2026"),
            zayavka("b", klient="other", vagonov=2),
        ], [
            nakladnaya("n1", vagonov=1, data_otpravki="09.09.2026 10:00:00"),
            nakladnaya("other1", klient="other", data_otpravki="10.09.2026 09:00:00"),
            nakladnaya("n2", vagonov=2, data_otpravki="10.09.2026 10:00:00"),
            nakladnaya("n3", vagonov=1, data_otpravki="11.09.2026 10:00:00"),
            nakladnaya("other2", klient="other", data_otpravki="12.09.2026 10:00:00"),
        ])
        self.assertEqual(result["po_zayavkam"]["zero"], [])
        self.assertEqual(
            [(row["nakladnaya"], row["vagonov"], row["sverh_zayavki"])
             for row in result["po_zayavkam"]["a"]],
            [("n1", 1, 0), ("n2", 2, 1)],
        )
        self.assertEqual(result["po_zayavkam"]["future"][0]["nakladnaya"], "n3")
        self.assertEqual([row["sverh_zayavki"] for row in result["po_zayavkam"]["b"]], [0, 0])

    def test_period_accepts_dates_and_datetimes_as_inclusive_days(self):
        for nachalo in ("01.09.2026", "01.09.2026 12:30:00"):
            for konec in ("30.09.2026", "30.09.2026 00:00:00"):
                with self.subTest(nachalo=nachalo, konec=konec):
                    result = allocate_nakladnye(
                        [zayavka(vagonov=0, nachalo=nachalo, konec=konec)],
                        [nakladnaya("first", data_otpravki="01.09.2026 00:00:00"),
                         nakladnaya("last", data_otpravki="30.09.2026 23:59:59")],
                    )
                    self.assertEqual(result, allocate_nakladnye(
                        [zayavka(vagonov=0)],
                        [nakladnaya("first", data_otpravki="01.09.2026 00:00:00"),
                         nakladnaya("last", data_otpravki="30.09.2026 23:59:59")],
                    ))
                    self.assertEqual(len(result["po_zayavkam"]["a"]), 2)

    def test_invalid_period_date_or_time_is_rejected(self):
        for field in ("nachalo", "konec"):
            for value in ("31.02.2026", "01.09.2026 25:00:00", "01.09.2026 garbage"):
                with self.subTest(field=field, value=value):
                    row = zayavka()
                    row[field] = value
                    with self.assertRaisesRegex(ValueError, "Некорректная дата периода заявки"):
                        allocate_nakladnye([row], [])

    def test_rule1_withdrawn_applications_are_excluded(self):
        for sostoyanie in ("Отозвана", "Отозвана до обработки", "Отозвана после согласования"):
            with self.subTest(sostoyanie=sostoyanie):
                result = allocate_nakladnye([zayavka(sostoyanie=sostoyanie)], [nakladnaya()])
                self.assertEqual(result["po_zayavkam"], {})
                self.assertEqual(result["bez_zayavki"]["client"][0]["vagonov"], 1)

    def test_rule2_clients_do_not_share_capacity_or_overflow(self):
        result = allocate_nakladnye(
            [zayavka(klient="other")], [nakladnaya(vagonov=15)],
        )
        self.assertEqual(result["po_zayavkam"]["a"], [])
        self.assertEqual(result["bez_zayavki"]["client"][0]["vagonov"], 15)

    def test_rule3_start_date_has_priority_over_received_date(self):
        result = allocate_nakladnye([
            zayavka("later", nachalo="05.09.2026", postupila="01.08.2026 10:00:00"),
            zayavka("earlier", postupila="31.08.2026 10:00:00"),
        ], [nakladnaya()])
        self.assertEqual(result["po_zayavkam"]["later"], [])
        self.assertEqual(result["po_zayavkam"]["earlier"][0]["vagonov"], 1)

    def test_rule3_received_date_breaks_tie_not_number(self):
        result = allocate_nakladnye([
            zayavka("001", postupila="31.08.2026 10:00:00"),
            zayavka("999", postupila="30.08.2026 10:00:00"),
        ], [nakladnaya()])
        self.assertEqual(result["po_zayavkam"]["001"], [])
        self.assertEqual(result["po_zayavkam"]["999"][0]["vagonov"], 1)

    def test_exact_queue_tie_preserves_input_order(self):
        result = allocate_nakladnye([zayavka("z"), zayavka("a")], [nakladnaya()])
        self.assertEqual(result["po_zayavkam"]["a"], [])
        self.assertEqual(result["po_zayavkam"]["z"][0]["vagonov"], 1)

    def test_rule4_invoices_sorted_by_timestamp(self):
        result = allocate_nakladnye([zayavka(vagonov=1)], [
            nakladnaya("late", data_otpravki="10.09.2026 11:00:00"),
            nakladnaya("early", data_otpravki="10.09.2026 09:00:00"),
        ])
        self.assertEqual(
            [(row["nakladnaya"], row["sverh_zayavki"]) for row in result["po_zayavkam"]["a"]],
            [("early", 0), ("late", 1)],
        )

    def test_rule5_future_application_cannot_accept(self):
        result = allocate_nakladnye([zayavka(nachalo="11.09.2026")], [nakladnaya()])
        self.assertEqual(result["po_zayavkam"]["a"], [])
        self.assertEqual(result["bez_zayavki"]["client"][0]["vagonov"], 1)

    def test_rule5_expired_application_filled_before_current(self):
        result = allocate_nakladnye([
            zayavka("old", konec="09.09.2026"),
            zayavka("current", nachalo="10.09.2026"),
        ], [nakladnaya()])
        self.assertEqual(result["po_zayavkam"]["old"][0]["sverh_zayavki"], 0)
        self.assertEqual(result["po_zayavkam"]["current"], [])

    def test_rule6_invoice_split_and_mass_preserved(self):
        result = allocate_nakladnye(
            [zayavka("a", vagonov=1), zayavka("b", vagonov=2)],
            [nakladnaya(vagonov=3, massa_t="10")],
        )
        self.assertEqual(result["po_zayavkam"], {
            "a": [{"nakladnaya": "n", "vagonov": 1, "massa_t": 3.3, "sverh_zayavki": 0}],
            "b": [{"nakladnaya": "n", "vagonov": 2, "massa_t": 6.7, "sverh_zayavki": 0}],
        })

    def test_rule7_overflow_uses_last_matching_period_in_queue(self):
        result = allocate_nakladnye([
            zayavka("a", vagonov=0), zayavka("b", vagonov=0),
            zayavka("expired", vagonov=0, nachalo="02.09.2026", konec="09.09.2026"),
            zayavka("future", vagonov=100, nachalo="11.09.2026"),
        ], [nakladnaya(vagonov=2)])
        self.assertEqual(result["po_zayavkam"]["b"][0]["sverh_zayavki"], 2)
        self.assertTrue(all(not result["po_zayavkam"][key] for key in ("a", "expired", "future")))

    def test_rule7_regular_and_overflow_parts_are_combined(self):
        result = allocate_nakladnye([zayavka(vagonov=1)], [nakladnaya(vagonov=3, massa_t="30")])
        self.assertEqual(
            [(row["vagonov"], row["sverh_zayavki"], row["massa_t"])
             for row in result["po_zayavkam"]["a"]],
            [(3, 2, 30.0)],
        )

    def test_mass_is_rounded_after_combining_parts_by_application(self):
        result = allocate_nakladnye(
            [zayavka("a", vagonov=1), zayavka("b", vagonov=1)],
            [nakladnaya(vagonov=3, massa_t="0.1")],
        )
        self.assertEqual(result["po_zayavkam"], {
            "a": [{"nakladnaya": "n", "vagonov": 1, "massa_t": 0.0, "sverh_zayavki": 0}],
            "b": [{"nakladnaya": "n", "vagonov": 2, "massa_t": 0.1, "sverh_zayavki": 1}],
        })

    def test_overflow_combines_with_earlier_application(self):
        result = allocate_nakladnye([
            zayavka("a", vagonov=1),
            zayavka("b", vagonov=1, nachalo="02.09.2026", konec="09.09.2026"),
        ], [nakladnaya(vagonov=3, massa_t="30")])
        self.assertEqual(result["po_zayavkam"], {
            "a": [{"nakladnaya": "n", "vagonov": 2, "massa_t": 20.0, "sverh_zayavki": 1}],
            "b": [{"nakladnaya": "n", "vagonov": 1, "massa_t": 10.0, "sverh_zayavki": 0}],
        })

    def test_rule7_period_boundaries_include_whole_day(self):
        for data_otpravki in ("01.09.2026 00:00:00", "30.09.2026 23:59:59"):
            with self.subTest(data_otpravki=data_otpravki):
                result = allocate_nakladnye([zayavka(vagonov=0)], [nakladnaya(data_otpravki=data_otpravki)])
                self.assertEqual(result["po_zayavkam"]["a"][0]["sverh_zayavki"], 1)

    def test_rule8_leftover_outside_period_has_no_application(self):
        result = allocate_nakladnye(
            [zayavka(vagonov=1, konec="09.09.2026")], [nakladnaya(vagonov=3, massa_t="30")],
        )
        self.assertEqual(result["bez_zayavki"], {
            "client": [{"nakladnaya": "n", "vagonov": 2, "massa_t": 20.0}],
        })

    def test_rule8_missing_clients_have_separate_list(self):
        result = allocate_nakladnye([], [nakladnaya("empty", klient=""), nakladnaya("null", klient=None)])
        self.assertEqual(result["bez_klienta"], ["empty", "null"])
        self.assertEqual(result["bez_zayavki"], {})

    def test_mass_rounding_uses_largest_remainders_and_stable_ties(self):
        self.assertEqual(split_mass(Decimal("1"), [1, 1, 1]),
                         [Decimal("0.4"), Decimal("0.3"), Decimal("0.3")])
        self.assertEqual(split_mass(Decimal("0.1"), [1, 1, 1]),
                         [Decimal("0.1"), Decimal("0"), Decimal("0")])
        self.assertEqual(split_mass(Decimal("1.25"), [1]), [Decimal("1.3")])

    def test_mass_and_wagons_conserved_for_many_small_allocations(self):
        for vagonov in range(5):
            for vagonov in range(1, 12):
                for massa_t in ("0", "0.1", "1", "100.7"):
                    result = allocate_nakladnye(
                        [zayavka("a", vagonov=vagonov), zayavka("b", vagonov=vagonov)],
                        [nakladnaya(vagonov=vagonov, massa_t=massa_t)],
                    )
                    rows = [row for group in result["po_zayavkam"].values() for row in group]
                    self.assertEqual(sum(row["vagonov"] for row in rows), vagonov)
                    self.assertEqual(sum(Decimal(str(row["massa_t"])) for row in rows), Decimal(massa_t))
                    self.assertTrue(all(row["massa_t"] >= 0 for row in rows))

    def test_inputs_are_not_modified_and_repeated_runs_equal(self):
        zayavki, nakladnye = [zayavka()], [nakladnaya()]
        original = copy.deepcopy((zayavki, nakladnye))
        first = allocate_nakladnye(zayavki, nakladnye)
        self.assertEqual(first, allocate_nakladnye(zayavki, nakladnye))
        self.assertEqual((zayavki, nakladnye), original)

    def test_invalid_data_rejected(self):
        cases = [
            ([zayavka(), zayavka()], [nakladnaya()]),
            ([zayavka()], [nakladnaya(), nakladnaya()]),
            ([zayavka(konec="01.08.2026")], []),
            ([zayavka(vagonov=-1)], []),
            ([], [nakladnaya(vagonov=0)]),
            ([], [nakladnaya(vagonov=True)]),
            ([], [nakladnaya(massa_t="-1")]),
            ([], [nakladnaya(massa_t="NaN")]),
        ]
        for zayavki, nakladnye in cases:
            with self.subTest(zayavki=zayavki, nakladnye=nakladnye):
                with self.assertRaises(ValueError):
                    allocate_nakladnye(zayavki, nakladnye)

    def test_empty_inputs(self):
        self.assertEqual(allocate_nakladnye([], []), {
            "po_zayavkam": {}, "bez_zayavki": {}, "bez_klienta": [],
        })
