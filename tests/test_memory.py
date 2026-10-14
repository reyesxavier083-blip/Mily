import unittest
from mily_core.memory import MemoryEntry, MemoryStore, MemoryType

class MemoryStoreTests(unittest.TestCase):
    def test_add_and_search(self):
        store = MemoryStore()
        item = store.add(MemoryEntry('MILY modular architecture'))
        self.assertEqual([item], store.search('mily'))

    def test_type_filter(self):
        store = MemoryStore()
        store.add(MemoryEntry('project note', memory_type=MemoryType.SEMANTIC))
        self.assertEqual(1, len(store.search(memory_type=MemoryType.SEMANTIC)))

    def test_capacity(self):
        store = MemoryStore(max_entries=1)
        first = store.add(MemoryEntry('first'))
        store.add(MemoryEntry('second'))
        self.assertIsNone(store.get(first.entry_id))

    def test_invalid_values(self):
        with self.assertRaises(ValueError):
            MemoryEntry(' ')
        with self.assertRaises(ValueError):
            MemoryStore(max_entries=0)

if __name__ == '__main__':
    unittest.main()
