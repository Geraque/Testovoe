import copy
import unittest
from datetime import date, timedelta

from task2 import reconcile_stock


def zapis(identifier=1, kind="vydacha_podryadchiku", recorded="2026-09-10",
          mol="warehouse", kontragent_id="k1", stroki=None, status="vydano"):
    return {
        "id": identifier, "tip": kind, "data": recorded, "mol": mol,
        "kontragent_id": kontragent_id, "stroki": stroki if stroki is not None else [{"kod": "x", "kol": "2"}],
        "status": status,
    }


def dokument(identifier="d1", kind="peredacha_podryadchiku", recorded="2026-09-10",
             mol="warehouse", kontragent_id="k1", stroki=None):
    return {
        "id": identifier, "vid": kind, "data": recorded, "mol": mol,
        "kontragent_id": kontragent_id, "stroki": stroki if stroki is not None else [{"kod": "x", "kol": "2"}],
    }


def ostatok(account="10.01", mol="warehouse", kontragent_id="", kod="x", kol="10"):
    return {"schet": account, "mol": mol, "kontragent_id": kontragent_id, "kod": kod, "kol": kol}


def get_operativnyj_ostatok(result):
    return {(row["mol"], row["kod"]): row["operativnyj"] for row in result["operativnyj_ostatok"]}


def get_u_podryadchikov(result):
    return {(row["kontragent_id"], row["kod"]): row["kol"] for row in result["u_podryadchikov"]}


class ReconciliationTests(unittest.TestCase):
    def test_supported_kind_pairs(self):
        for journal_kind, document_kind in (
            ("vydacha_podryadchiku", "peredacha_podryadchiku"),
            ("vydacha_svoim", "trebovanie"),
        ):
            with self.subTest(kind=journal_kind):
                result = reconcile_stock([zapis(kind=journal_kind)], [dokument(kind=document_kind)], [])
                self.assertEqual(result["svyazi"], {"1": "d1"})

    def test_kind_mol_contractor_and_quantities_must_match(self):
        for changed in (
            {"kind": "trebovanie"}, {"mol": "another warehouse"}, {"kontragent_id": "k2"},
            {"stroki": [{"kod": "x", "kol": "3"}]},
            {"stroki": [{"kod": "y", "kol": "2"}]},
            {"stroki": [{"kod": "x", "kol": "2"}, {"kod": "y", "kol": "1"}]},
        ):
            with self.subTest(changed=changed):
                result = reconcile_stock([zapis()], [dokument(**changed)], [])
                self.assertEqual(result["svyazi"], {})
                self.assertEqual(result["ne_najdeno"], [1])

    def test_internal_issue_does_not_match_by_contractor(self):
        result = reconcile_stock([zapis(kind="vydacha_svoim", kontragent_id="")],
                                 [dokument(kind="trebovanie", kontragent_id="irrelevant")], [])
        self.assertEqual(result["svyazi"], {"1": "d1"})

    def test_line_order_decimal_notation_and_duplicate_codes(self):
        result = reconcile_stock([zapis(stroki=[
            {"kod": "x", "kol": "15,9"}, {"kod": "y", "kol": "0.1"}, {"kod": "y", "kol": "0.2"},
        ])], [dokument(stroki=[{"kod": "y", "kol": "0.30"}, {"kod": "x", "kol": "15.90"}])], [])
        self.assertEqual(result["svyazi"], {"1": "d1"})

    def test_date_window_boundaries(self):
        for delta, expected in ((-3, False), (-2, True), (0, True), (14, True), (15, False)):
            with self.subTest(delta=delta):
                recorded = (date(2026, 9, 10) + timedelta(days=delta)).isoformat()
                result = reconcile_stock([zapis()], [dokument(recorded=recorded)], [])
                self.assertEqual(result["svyazi"], {"1": "d1"} if expected else {})

    def test_cancelled_and_draft_entries_do_not_match_or_change_stock(self):
        for status in ("otmeneno", "draft"):
            with self.subTest(status=status):
                result = reconcile_stock([zapis(status=status)], [dokument()], [ostatok()])
                self.assertEqual(result["svyazi"], {})
                self.assertEqual(result["ne_najdeno"], [])
                self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 10.0})
                self.assertEqual(get_u_podryadchikov(result), {})

    def test_ambiguous_candidates_are_sorted_and_remain_unlinked(self):
        result = reconcile_stock([zapis()], [dokument("d2"), dokument("d1")], [ostatok()])
        self.assertEqual(result["svyazi"], {})
        self.assertEqual(result["neodnoznachno"], {"1": ["d1", "d2"]})
        self.assertEqual(result["ne_najdeno"], [])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 8.0})
        self.assertEqual(get_u_podryadchikov(result), {("k1", "x"): 2.0})

    def test_one_document_used_once_oldest_record_first(self):
        result = reconcile_stock([
            zapis(1, recorded="2026-09-11"), zapis(2, recorded="2026-09-10"),
        ], [dokument()], [ostatok()])
        self.assertEqual(result["svyazi"], {"2": "d1"})
        self.assertEqual(result["ne_najdeno"], [1])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 8.0})

    def test_same_date_competition_uses_lowest_id(self):
        result = reconcile_stock([zapis(2), zapis(1)], [dokument()], [])
        self.assertEqual(result["svyazi"], {"1": "d1"})
        self.assertEqual(result["ne_najdeno"], [2])

    def test_ambiguity_does_not_reserve_documents_or_trigger_rematching(self):
        result = reconcile_stock([
            zapis(1, recorded="2026-09-10"), zapis(2, recorded="2026-09-13"),
        ], [dokument("d1", recorded="2026-09-10"), dokument("d2", recorded="2026-09-13")], [])
        self.assertEqual(result["neodnoznachno"], {"1": ["d1", "d2"]})
        self.assertEqual(result["svyazi"], {"2": "d2"})

    def test_linked_issue_not_subtracted_twice(self):
        result = reconcile_stock([zapis()], [dokument()], [
            ostatok(), ostatok(account="10.07", mol="", kontragent_id="k1", kol="2"),
        ])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 10.0})
        self.assertEqual(get_u_podryadchikov(result), {("k1", "x"): 2.0})

    def test_unlinked_contractor_issue_and_return_have_opposite_signs(self):
        returned = zapis(2, kind="vozvrat", stroki=[{"kod": "x", "kol": "0,5"}])
        returned["iskhodnaya_id"] = 1
        result = reconcile_stock([zapis(), returned], [], [
            ostatok(), ostatok(account="10.07", kontragent_id="k1", kol="3"),
        ])
        self.assertEqual(result["ne_najdeno"], [1, 2])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 8.5})
        self.assertEqual(get_u_podryadchikov(result), {("k1", "x"): 4.5})

    def test_return_from_linked_issue_is_still_applied(self):
        returned = zapis(2, kind="vozvrat")
        returned["iskhodnaya_id"] = 1
        result = reconcile_stock([zapis(), returned], [dokument()], [ostatok()])
        self.assertEqual(result["svyazi"], {"1": "d1"})
        self.assertEqual(result["ne_najdeno"], [2])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 12.0})
        self.assertEqual(get_u_podryadchikov(result), {("k1", "x"): -2.0})

    def test_internal_issue_and_return_do_not_change_contractor_stock(self):
        result = reconcile_stock([
            zapis(kind="vydacha_svoim", kontragent_id=""),
            zapis(2, kind="vozvrat", kontragent_id="", stroki=[{"kod": "x", "kol": "1"}]),
        ], [], [ostatok()])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 9.0})
        self.assertEqual(get_u_podryadchikov(result), {})

    def test_balance_accounts_and_rows_aggregated_by_exact_keys(self):
        result = reconcile_stock([], [], [
            ostatok(kol="0.1"), ostatok(account="10.09", kol="0,2"),
            ostatok(mol="other", kol="7"),
            ostatok(account="10.07", kontragent_id="k1", kol="1"),
            ostatok(account="10.07", kontragent_id="k1", kol="2"),
            ostatok(account="10.07", kontragent_id="k2", kol="4"),
        ])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 0.3, ("other", "x"): 7.0})
        self.assertEqual(get_u_podryadchikov(result), {("k1", "x"): 3.0, ("k2", "x"): 4.0})

    def test_missing_balance_starts_at_zero_and_negative_is_kept(self):
        result = reconcile_stock([zapis()], [], [])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): -2.0})
        self.assertEqual(get_u_podryadchikov(result), {("k1", "x"): 2.0})

    def test_zero_contractor_rows_removed_but_mol_zero_kept(self):
        result = reconcile_stock([], [], [
            ostatok(kol="0"),
            ostatok(account="10.07", kontragent_id="k1", kol="0.3"),
            ostatok(account="10.07", kontragent_id="k1", kol="-0,3"),
        ])
        self.assertEqual(get_operativnyj_ostatok(result), {("warehouse", "x"): 0.0})
        self.assertEqual(get_u_podryadchikov(result), {})

    def test_inputs_not_modified_and_order_does_not_change_result(self):
        zhurnal = [zapis(2), zapis(1)]
        dokumenty = [dokument("d2"), dokument("d1")]
        ostatki_1c = [ostatok()]
        original = copy.deepcopy((zhurnal, dokumenty, ostatki_1c))
        result = reconcile_stock(zhurnal, dokumenty, ostatki_1c)
        self.assertEqual(result, reconcile_stock(zhurnal[::-1], dokumenty[::-1], ostatki_1c))
        self.assertEqual((zhurnal, dokumenty, ostatki_1c), original)

    def test_invalid_data_rejected(self):
        cases = [
            ([zapis(), zapis()], [], []),
            ([], [dokument(), dokument()], []),
            ([zapis(kind="unknown")], [], []),
            ([zapis(kontragent_id="")], [], []),
            ([zapis(stroki=[])], [], []),
            ([zapis(stroki=[{"kod": "x", "kol": "0"}])], [], []),
            ([zapis(stroki=[{"kod": "x", "kol": "-2"}])], [], []),
            ([], [], [ostatok(kol="Infinity")]),
            ([], [], [ostatok(account="10.07", kontragent_id="")]),
        ]
        for zhurnal, dokumenty, ostatki_1c in cases:
            with self.subTest(zhurnal=zhurnal, dokumenty=dokumenty, ostatki_1c=ostatki_1c):
                with self.assertRaises(ValueError):
                    reconcile_stock(zhurnal, dokumenty, ostatki_1c)

    def test_empty_inputs(self):
        self.assertEqual(reconcile_stock([], [], []), {
            "svyazi": {}, "ne_najdeno": [], "neodnoznachno": {},
            "operativnyj_ostatok": [], "u_podryadchikov": [],
        })
