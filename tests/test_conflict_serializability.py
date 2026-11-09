import unittest
from algorithms.conflict_serializability import analyze,parse_schedule

class ConflictTests(unittest.TestCase):
    def test_serializable_schedule_with_evidence(self):
        result=analyze(parse_schedule(["T1:R(A)","T2:W(A)","T1:W(B)","T2:R(B)"]))
        self.assertTrue(result.serializable); self.assertEqual(result.graph,{"T1":["T2"],"T2":[]}); self.assertEqual(result.topological_order,["T1","T2"])
        self.assertEqual({row["types"] for row in result.conflicts},{"RW","WR"})
    def test_nonserializable_cycle(self):
        result=analyze(parse_schedule(["T1:W(A)","T2:R(A)","T2:W(B)","T1:R(B)"]))
        self.assertFalse(result.serializable); self.assertEqual(result.cycle[0],result.cycle[-1]); self.assertEqual(set(result.cycle[:-1]),{"T1","T2"})
    def test_read_read_and_same_transaction_do_not_conflict(self):
        result=analyze(parse_schedule(["T1:R(A)","T2:R(A)","T1:W(B)","T1:R(B)"]))
        self.assertTrue(result.serializable); self.assertEqual(result.conflicts,[])
    def test_three_transaction_cycle_and_bad_input(self):
        result=analyze(parse_schedule(["T1:W(A)","T2:R(A)","T2:W(B)","T3:R(B)","T3:W(C)","T1:R(C)"]))
        self.assertFalse(result.serializable); self.assertEqual(set(result.cycle[:-1]),{"T1","T2","T3"})
        with self.assertRaises(ValueError): parse_schedule(["T1:X(A)"])
        self.assertTrue(analyze([]).serializable)
