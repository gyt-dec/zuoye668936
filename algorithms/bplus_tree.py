"""唯一键B+树：插入、检索、范围查询及真实借位/合并删除。"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from math import ceil
from typing import Any, Iterator


@dataclass
class BPlusNode:
    is_leaf: bool
    keys: list[int] = field(default_factory=list)
    values: list[Any] = field(default_factory=list)
    children: list["BPlusNode"] = field(default_factory=list)
    parent: "BPlusNode | None" = None
    next_leaf: "BPlusNode | None" = None
    previous_leaf: "BPlusNode | None" = None


class BPlusTree:
    def __init__(self, order: int = 4):
        if order < 3:
            raise ValueError("B+树阶数至少为3")
        self.order = order
        self.root = BPlusNode(is_leaf=True)
        self.events: list[dict[str, Any]] = []

    @property
    def max_keys(self) -> int:
        return self.order - 1

    @property
    def min_leaf_keys(self) -> int:
        return ceil((self.order - 1) / 2)

    @property
    def min_internal_children(self) -> int:
        return ceil(self.order / 2)

    def _find_leaf(self, key: int) -> BPlusNode:
        node = self.root
        while not node.is_leaf:
            node = node.children[bisect_right(node.keys, key)]
        return node

    def search(self, key: int):
        leaf = self._find_leaf(key)
        index = bisect_left(leaf.keys, key)
        return leaf.values[index] if index < len(leaf.keys) and leaf.keys[index] == key else None

    def insert(self, key: int, value: Any) -> None:
        leaf = self._find_leaf(key)
        index = bisect_left(leaf.keys, key)
        if index < len(leaf.keys) and leaf.keys[index] == key:
            leaf.values[index] = value
            self.events.append({"event": "update", "key": key})
        else:
            leaf.keys.insert(index, key)
            leaf.values.insert(index, value)
            self.events.append({"event": "insert", "key": key})
            if len(leaf.keys) > self.max_keys:
                self._split_leaf(leaf)
        self._refresh_keys(self.root)
        self.validate()

    def _split_leaf(self, leaf: BPlusNode) -> None:
        split = (len(leaf.keys) + 1) // 2
        right = BPlusNode(True, leaf.keys[split:], leaf.values[split:], parent=leaf.parent)
        leaf.keys, leaf.values = leaf.keys[:split], leaf.values[:split]
        right.next_leaf, right.previous_leaf = leaf.next_leaf, leaf
        if leaf.next_leaf:
            leaf.next_leaf.previous_leaf = right
        leaf.next_leaf = right
        self.events.append({"event": "leaf_split", "separator": right.keys[0]})
        self._insert_right_child(leaf, right)

    def _insert_right_child(self, left: BPlusNode, right: BPlusNode) -> None:
        if left.parent is None:
            self.root = BPlusNode(False, children=[left, right])
            left.parent = right.parent = self.root
            self.events.append({"event": "new_root"})
            return
        parent = left.parent
        parent.children.insert(parent.children.index(left) + 1, right)
        right.parent = parent
        self._refresh_keys(parent)
        if len(parent.children) > self.order:
            self._split_internal(parent)

    def _split_internal(self, node: BPlusNode) -> None:
        split = len(node.children) // 2
        right_children = node.children[split:]
        node.children = node.children[:split]
        right = BPlusNode(False, children=right_children, parent=node.parent)
        for child in right.children:
            child.parent = right
        self._refresh_keys(node)
        self._refresh_keys(right)
        self.events.append({"event": "internal_split", "separator": self._subtree_min(right)})
        self._insert_right_child(node, right)

    def range_search(self, start: int, end: int) -> list[tuple[int, Any]]:
        if start > end:
            return []
        leaf = self._find_leaf(start)
        result = []
        while leaf:
            for key, value in zip(leaf.keys, leaf.values):
                if key < start:
                    continue
                if key > end:
                    return result
                result.append((key, value))
            leaf = leaf.next_leaf
        return result

    def delete(self, key: int) -> bool:
        leaf = self._find_leaf(key)
        index = bisect_left(leaf.keys, key)
        if index == len(leaf.keys) or leaf.keys[index] != key:
            return False
        leaf.keys.pop(index)
        leaf.values.pop(index)
        self.events.append({"event": "delete", "key": key})
        if leaf is not self.root and len(leaf.keys) < self.min_leaf_keys:
            self._rebalance_leaf(leaf)
        self._contract_root()
        self._refresh_keys(self.root)
        self.validate()
        return True

    def _siblings(self, node: BPlusNode):
        parent = node.parent
        index = parent.children.index(node)
        left = parent.children[index - 1] if index > 0 else None
        right = parent.children[index + 1] if index + 1 < len(parent.children) else None
        return parent, left, right

    def _rebalance_leaf(self, leaf: BPlusNode) -> None:
        parent, left, right = self._siblings(leaf)
        if left and len(left.keys) > self.min_leaf_keys:
            leaf.keys.insert(0, left.keys.pop())
            leaf.values.insert(0, left.values.pop())
            self.events.append({"event": "leaf_borrow_left"})
            return
        if right and len(right.keys) > self.min_leaf_keys:
            leaf.keys.append(right.keys.pop(0))
            leaf.values.append(right.values.pop(0))
            self.events.append({"event": "leaf_borrow_right"})
            return
        if left:
            left.keys.extend(leaf.keys); left.values.extend(leaf.values)
            left.next_leaf = leaf.next_leaf
            if leaf.next_leaf: leaf.next_leaf.previous_leaf = left
            parent.children.remove(leaf)
        else:
            leaf.keys.extend(right.keys); leaf.values.extend(right.values)
            leaf.next_leaf = right.next_leaf
            if right.next_leaf: right.next_leaf.previous_leaf = leaf
            parent.children.remove(right)
        self.events.append({"event": "leaf_merge"})
        self._rebalance_internal(parent)

    def _rebalance_internal(self, node: BPlusNode) -> None:
        if node is self.root:
            self._contract_root()
            return
        if len(node.children) >= self.min_internal_children:
            return
        parent, left, right = self._siblings(node)
        if left and len(left.children) > self.min_internal_children:
            child = left.children.pop(); node.children.insert(0, child); child.parent = node
            self.events.append({"event": "internal_borrow_left"})
            return
        if right and len(right.children) > self.min_internal_children:
            child = right.children.pop(0); node.children.append(child); child.parent = node
            self.events.append({"event": "internal_borrow_right"})
            return
        if left:
            for child in node.children: child.parent = left
            left.children.extend(node.children); parent.children.remove(node)
        else:
            for child in right.children: child.parent = node
            node.children.extend(right.children); parent.children.remove(right)
        self.events.append({"event": "internal_merge"})
        self._rebalance_internal(parent)

    def _contract_root(self) -> None:
        if not self.root.is_leaf and len(self.root.children) == 1:
            self.root = self.root.children[0]
            self.root.parent = None
            self.events.append({"event": "root_contraction"})

    def _subtree_min(self, node: BPlusNode) -> int:
        while not node.is_leaf:
            node = node.children[0]
        if not node.keys:
            raise AssertionError("非空内部子树不能没有键")
        return node.keys[0]

    def _refresh_keys(self, node: BPlusNode) -> None:
        if node.is_leaf:
            return
        for child in node.children:
            self._refresh_keys(child)
        node.keys = [self._subtree_min(child) for child in node.children[1:]]

    def items(self) -> Iterator[tuple[int, Any]]:
        node = self.root
        while not node.is_leaf: node = node.children[0]
        while node:
            yield from zip(node.keys, node.values)
            node = node.next_leaf

    def height(self) -> int:
        height, node = 1, self.root
        while not node.is_leaf: height += 1; node = node.children[0]
        return height

    def dump_structure(self) -> dict:
        levels, current = [], [self.root]
        while current:
            levels.append([{"leaf": n.is_leaf, "keys": list(n.keys)} for n in current])
            current = [child for node in current if not node.is_leaf for child in node.children]
        return {"order": self.order, "height": self.height(), "levels": levels, "items": list(self.items()), "events": list(self.events)}

    def validate(self) -> bool:
        leaf_depths, leaves = set(), []
        def visit(node: BPlusNode, depth: int, is_root=False):
            if node.keys != sorted(node.keys) or len(node.keys) != len(set(node.keys)):
                raise AssertionError("节点键无序或重复")
            if node.is_leaf:
                if len(node.keys) != len(node.values) or len(node.keys) > self.max_keys:
                    raise AssertionError("叶子容量或键值数量错误")
                if not is_root and len(node.keys) < self.min_leaf_keys:
                    raise AssertionError("叶子下溢")
                leaf_depths.add(depth); leaves.append(node); return
            if len(node.children) != len(node.keys) + 1 or len(node.children) > self.order:
                raise AssertionError("内部节点键与子节点数量错误")
            if is_root and len(node.children) < 2: raise AssertionError("内部根至少两个子节点")
            if not is_root and len(node.children) < self.min_internal_children: raise AssertionError("内部节点下溢")
            for child in node.children:
                if child.parent is not node: raise AssertionError("父指针错误")
                visit(child, depth + 1)
            expected = [self._subtree_min(child) for child in node.children[1:]]
            if node.keys != expected: raise AssertionError("分隔键错误")
        visit(self.root, 0, True)
        if len(leaf_depths) != 1: raise AssertionError("叶子不在同一层")
        for index, leaf in enumerate(leaves):
            if leaf.previous_leaf is not (leaves[index-1] if index else None): raise AssertionError("叶子前向链错误")
            if leaf.next_leaf is not (leaves[index+1] if index+1<len(leaves) else None): raise AssertionError("叶子后向链错误")
        all_keys=[key for leaf in leaves for key in leaf.keys]
        if all_keys != sorted(all_keys) or len(all_keys)!=len(set(all_keys)): raise AssertionError("叶子全局顺序错误")
        return True
