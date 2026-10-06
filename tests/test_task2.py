import copy
import unittest
from datetime import date, timedelta

from task2 import reconcile_stock


def issue(identifier=1, kind="vydacha_podryadchiku", recorded="2026-09-10",
          mol="warehouse", contractor="k1", lines=None, status="vydano"):
    return {
        "id": identifier, "tip": kind, "data": recorded, "mol": mol,
        "kontragent_id": contractor, "stroki": lines if lines is not None else [{"kod": "x", "kol": "2"}],
        "status": status,
    }


def document(identifier="d1", kind="peredacha_podryadchiku", recorded="2026-09-10",
             mol="warehouse", contractor="k1", lines=None):
    return {
        "id": identifier, "vid": kind, "data": recorded, "mol": mol,
        "kontragent_id": contractor, "stroki": lines if lines is not None else [{"kod": "x", "kol": "2"}],
    }


def balance(account="10.01", mol="warehouse", contractor="", code="x", quantity="10"):
    return {"schet": account, "mol": mol, "kontragent_id": contractor, "kod": code, "kol": quantity}


def stock(result):
    return {(row["mol"], row["kod"]): row["operativnyj"] for row in result["operativnyj_ostatok"]}


def contractors(result):
    return {(row["kontragent_id"], row["kod"]): row["kol"] for row in result["u_podryadchikov"]}


class ReconciliationTests(unittest.TestCase):
    def test_supported_kind_pairs(self):
        for journal_kind, document_kind in (
            ("vydacha_podryadchiku", "peredacha_podryadchiku"),
            ("vydacha_svoim", "trebovanie"),
        ):
            with self.subTest(kind=journal_kind):
                result = reconcile_stock([issue(kind=journal_kind)], [document(kind=document_kind)], [])
                self.assertEqual(result["svyazi"], {"1": "d1"})

    def test_kind_mol_contractor_and_quantities_must_match(self):
        for changed in (
            {"kind": "trebovanie"}, {"mol": "another warehouse"}, {"contractor": "k2"},
            {"lines": [{"kod": "x", "kol": "3"}]},
            {"lines": [{"kod": "y", "kol": "2"}]},
            {"lines": [{"kod": "x", "kol": "2"}, {"kod": "y", "kol": "1"}]},
        ):
            with self.subTest(changed=changed):
                result = reconcile_stock([issue()], [document(**changed)], [])
                self.assertEqual(result["svyazi"], {})
                self.assertEqual(result["ne_najdeno"], [1])

    def test_internal_issue_does_not_match_by_contractor(self):
        result = reconcile_stock([issue(kind="vydacha_svoim", contractor="")],
                                 [document(kind="trebovanie", contractor="irrelevant")], [])
        self.assertEqual(result["svyazi"], {"1": "d1"})

    def test_line_order_decimal_notation_and_duplicate_codes(self):
        result = reconcile_stock([issue(lines=[
            {"kod": "x", "kol": "15,9"}, {"kod": "y", "kol": "0.1"}, {"kod": "y", "kol": "0.2"},
        ])], [document(lines=[{"kod": "y", "kol": "0.30"}, {"kod": "x", "kol": "15.90"}])], [])
        self.assertEqual(result["svyazi"], {"1": "d1"})

    def test_date_window_boundaries(self):
        for delta, expected in ((-3, False), (-2, True), (0, True), (14, True), (15, False)):
            with self.subTest(delta=delta):
                recorded = (date(2026, 9, 10) + timedelta(days=delta)).isoformat()
                result = reconcile_stock([issue()], [document(recorded=recorded)], [])
                self.assertEqual(result["svyazi"], {"1": "d1"} if expected else {})

    def test_cancelled_and_draft_entries_do_not_match_or_change_stock(self):
        for status in ("otmeneno", "draft"):
            with self.subTest(status=status):
                result = reconcile_stock([issue(status=status)], [document()], [balance()])
                self.assertEqual(result["svyazi"], {})
                self.assertEqual(result["ne_najdeno"], [])
                self.assertEqual(stock(result), {("warehouse", "x"): 10.0})
                self.assertEqual(contractors(result), {})

    def test_ambiguous_candidates_are_sorted_and_remain_unlinked(self):
        result = reconcile_stock([issue()], [document("d2"), document("d1")], [balance()])
        self.assertEqual(result["svyazi"], {})
        self.assertEqual(result["neodnoznachno"], {"1": ["d1", "d2"]})
        self.assertEqual(result["ne_najdeno"], [])
        self.assertEqual(stock(result), {("warehouse", "x"): 8.0})
        self.assertEqual(contractors(result), {("k1", "x"): 2.0})

    def test_one_document_used_once_oldest_record_first(self):
        result = reconcile_stock([
            issue(1, recorded="2026-09-11"), issue(2, recorded="2026-09-10"),
        ], [document()], [balance()])
        self.assertEqual(result["svyazi"], {"2": "d1"})
        self.assertEqual(result["ne_najdeno"], [1])
        self.assertEqual(stock(result), {("warehouse", "x"): 8.0})

    def test_same_date_competition_uses_lowest_id(self):
        result = reconcile_stock([issue(2), issue(1)], [document()], [])
        self.assertEqual(result["svyazi"], {"1": "d1"})
        self.assertEqual(result["ne_najdeno"], [2])

    def test_ambiguity_does_not_reserve_documents_or_trigger_rematching(self):
        result = reconcile_stock([
            issue(1, recorded="2026-09-10"), issue(2, recorded="2026-09-13"),
        ], [document("d1", recorded="2026-09-10"), document("d2", recorded="2026-09-13")], [])
        self.assertEqual(result["neodnoznachno"], {"1": ["d1", "d2"]})
        self.assertEqual(result["svyazi"], {"2": "d2"})

    def test_linked_issue_not_subtracted_twice(self):
        result = reconcile_stock([issue()], [document()], [
            balance(), balance(account="10.07", mol="", contractor="k1", quantity="2"),
        ])
        self.assertEqual(stock(result), {("warehouse", "x"): 10.0})
        self.assertEqual(contractors(result), {("k1", "x"): 2.0})

    def test_unlinked_contractor_issue_and_return_have_opposite_signs(self):
        returned = issue(2, kind="vozvrat", lines=[{"kod": "x", "kol": "0,5"}])
        returned["iskhodnaya_id"] = 1
        result = reconcile_stock([issue(), returned], [], [
            balance(), balance(account="10.07", contractor="k1", quantity="3"),
        ])
        self.assertEqual(result["ne_najdeno"], [1, 2])
        self.assertEqual(stock(result), {("warehouse", "x"): 8.5})
        self.assertEqual(contractors(result), {("k1", "x"): 4.5})

    def test_return_from_linked_issue_is_still_applied(self):
        returned = issue(2, kind="vozvrat")
        returned["iskhodnaya_id"] = 1
        result = reconcile_stock([issue(), returned], [document()], [balance()])
        self.assertEqual(result["svyazi"], {"1": "d1"})
        self.assertEqual(result["ne_najdeno"], [2])
        self.assertEqual(stock(result), {("warehouse", "x"): 12.0})
        self.assertEqual(contractors(result), {("k1", "x"): -2.0})

    def test_internal_issue_and_return_do_not_change_contractor_stock(self):
        result = reconcile_stock([
            issue(kind="vydacha_svoim", contractor=""),
            issue(2, kind="vozvrat", contractor="", lines=[{"kod": "x", "kol": "1"}]),
        ], [], [balance()])
        self.assertEqual(stock(result), {("warehouse", "x"): 9.0})
        self.assertEqual(contractors(result), {})

    def test_balance_accounts_and_rows_aggregated_by_exact_keys(self):
        result = reconcile_stock([], [], [
            balance(quantity="0.1"), balance(account="10.09", quantity="0,2"),
            balance(mol="other", quantity="7"),
            balance(account="10.07", contractor="k1", quantity="1"),
            balance(account="10.07", contractor="k1", quantity="2"),
            balance(account="10.07", contractor="k2", quantity="4"),
        ])
        self.assertEqual(stock(result), {("warehouse", "x"): 0.3, ("other", "x"): 7.0})
        self.assertEqual(contractors(result), {("k1", "x"): 3.0, ("k2", "x"): 4.0})

    def test_missing_balance_starts_at_zero_and_negative_is_kept(self):
        result = reconcile_stock([issue()], [], [])
        self.assertEqual(stock(result), {("warehouse", "x"): -2.0})
        self.assertEqual(contractors(result), {("k1", "x"): 2.0})

    def test_zero_contractor_rows_removed_but_mol_zero_kept(self):
        result = reconcile_stock([], [], [
            balance(quantity="0"),
            balance(account="10.07", contractor="k1", quantity="0.3"),
            balance(account="10.07", contractor="k1", quantity="-0,3"),
        ])
        self.assertEqual(stock(result), {("warehouse", "x"): 0.0})
        self.assertEqual(contractors(result), {})

    def test_inputs_not_modified_and_order_does_not_change_result(self):
        journal = [issue(2), issue(1)]
        documents = [document("d2"), document("d1")]
        balances = [balance()]
        original = copy.deepcopy((journal, documents, balances))
        result = reconcile_stock(journal, documents, balances)
        self.assertEqual(result, reconcile_stock(journal[::-1], documents[::-1], balances))
        self.assertEqual((journal, documents, balances), original)

    def test_invalid_data_rejected(self):
        cases = [
            ([issue(), issue()], [], []),
            ([], [document(), document()], []),
            ([issue(kind="unknown")], [], []),
            ([issue(contractor="")], [], []),
            ([issue(lines=[])], [], []),
            ([issue(lines=[{"kod": "x", "kol": "0"}])], [], []),
            ([issue(lines=[{"kod": "x", "kol": "-2"}])], [], []),
            ([], [], [balance(quantity="Infinity")]),
            ([], [], [balance(account="10.07", contractor="")]),
        ]
        for journal, documents, balances in cases:
            with self.subTest(journal=journal, documents=documents, balances=balances):
                with self.assertRaises(ValueError):
                    reconcile_stock(journal, documents, balances)

    def test_empty_inputs(self):
        self.assertEqual(reconcile_stock([], [], []), {
            "svyazi": {}, "ne_najdeno": [], "neodnoznachno": {},
            "operativnyj_ostatok": [], "u_podryadchikov": [],
        })
