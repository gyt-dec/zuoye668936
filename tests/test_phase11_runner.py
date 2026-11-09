import tempfile,unittest
from pathlib import Path
from src.phase11_algorithm_experiments import bplus_demo,conflict_demo,hash_demo,paxos_demo,write_results

class RunnerTests(unittest.TestCase):
    def test_all_demos(self):
        self.assertIn("leaf_split",bplus_demo()["covered_events"])
        self.assertGreater(hash_demo()["resize_count"],0)
        self.assertTrue(conflict_demo()["serializable"]["serializable"])
        self.assertEqual(paxos_demo()["competing_proposers"]["second"]["learned_value"],"OLD")
    def test_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path,csv_path=write_results(Path(directory),{"ok":True})
            self.assertTrue(json_path.exists()); self.assertTrue(csv_path.exists())
            self.assertIn("algorithm",csv_path.read_text(encoding="utf-8-sig"))
