import random
import unittest
from algorithms.bplus_tree import BPlusTree

class BPlusTreeTests(unittest.TestCase):
    def test_orders_insert_search_range_update(self):
        for order in (3,4,5):
            tree=BPlusTree(order)
            for key in range(1,80): tree.insert(key,f"v{key}")
            self.assertEqual(tree.search(40),"v40"); self.assertIsNone(tree.search(100))
            self.assertEqual([k for k,_ in tree.range_search(17,31)],list(range(17,32)))
            tree.insert(40,"updated"); self.assertEqual(tree.search(40),"updated"); tree.validate()
            events={row["event"] for row in tree.events}
            self.assertIn("leaf_split",events); self.assertIn("internal_split",events)

    def test_delete_is_incremental_and_contracts_root(self):
        tree=BPlusTree(4)
        for key in range(1,60): tree.insert(key,key)
        original_height=tree.height()
        for key in range(1,59): self.assertTrue(tree.delete(key)); tree.validate()
        self.assertFalse(tree.delete(999)); self.assertEqual(list(tree.items()),[(59,59)])
        self.assertLess(tree.height(),original_height)
        events={row["event"] for row in tree.events}
        self.assertIn("leaf_merge",events); self.assertIn("internal_merge",events); self.assertIn("root_contraction",events)

    def test_borrow_paths_occur(self):
        observed=set()
        for order in (3,4,5):
            for seed in range(20):
                rng=random.Random(seed); keys=list(range(1,45)); rng.shuffle(keys); tree=BPlusTree(order)
                for key in keys: tree.insert(key,key)
                rng.shuffle(keys)
                for key in keys[:-3]: tree.delete(key)
                observed.update(row["event"] for row in tree.events)
        self.assertTrue({"leaf_borrow_left","leaf_borrow_right"}&observed)
        self.assertTrue({"internal_borrow_left","internal_borrow_right"}&observed)

    def test_fixed_seed_differential(self):
        for order in (3,4,5):
            rng=random.Random(20261110+order); tree=BPlusTree(order); reference={}
            for _ in range(500):
                key=rng.randrange(150)
                if rng.random()<0.62:
                    value=f"value-{rng.randrange(10000)}"; tree.insert(key,value); reference[key]=value
                else:
                    self.assertEqual(tree.delete(key),key in reference); reference.pop(key,None)
                tree.validate(); self.assertEqual(list(tree.items()),sorted(reference.items()))
                probe=rng.randrange(150); self.assertEqual(tree.search(probe),reference.get(probe))

    def test_empty_and_invalid_range(self):
        tree=BPlusTree(3); self.assertEqual(tree.range_search(10,1),[]); self.assertFalse(tree.delete(1)); self.assertTrue(tree.validate())
        with self.assertRaises(ValueError): BPlusTree(2)
