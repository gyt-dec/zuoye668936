import unittest
from algorithms.hash_index import HashIndex

class SameHash:
    def __init__(self,value): self.value=value
    def __hash__(self): return 1
    def __eq__(self,other): return isinstance(other,SameHash) and self.value==other.value

class HashIndexTests(unittest.TestCase):
    def test_insert_update_lookup_delete_resize(self):
        index=HashIndex(2,0.6)
        for key in range(30): self.assertTrue(index.put(key,key*2))
        self.assertGreater(index.resize_count,0); self.assertEqual(index.get(10),20)
        self.assertFalse(index.put(10,999)); self.assertEqual(index.get(10),999)
        self.assertEqual(index.delete(10),999); self.assertIsNone(index.get(10)); self.assertIsNone(index.delete(999))
    def test_chaining_collision(self):
        index=HashIndex(8)
        for i in range(4): index.put(SameHash(i),i)
        self.assertEqual(index.collision_count,3)
        for i in range(4): self.assertEqual(index.get(SameHash(i)),i)
    def test_invalid_parameters(self):
        with self.assertRaises(ValueError): HashIndex(1)
