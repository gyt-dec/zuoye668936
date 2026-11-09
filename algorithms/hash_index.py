"""使用拉链法处理冲突的教学Hash索引。"""
from __future__ import annotations
from typing import Any


class HashIndex:
    def __init__(self, capacity: int = 8, load_factor: float = 0.75):
        if capacity < 2 or not 0 < load_factor < 1: raise ValueError("非法Hash参数")
        self.buckets=[[] for _ in range(capacity)]; self.size=0; self.load_factor=load_factor; self.resize_count=0

    def _index(self,key): return hash(key)%len(self.buckets)
    def put(self,key,value):
        bucket=self.buckets[self._index(key)]
        for i,(old,_) in enumerate(bucket):
            if old==key: bucket[i]=(key,value); return False
        bucket.append((key,value)); self.size+=1
        if self.size/len(self.buckets)>self.load_factor: self._resize(len(self.buckets)*2)
        return True
    def get(self,key,default=None):
        for old,value in self.buckets[self._index(key)]:
            if old==key:return value
        return default
    def delete(self,key):
        bucket=self.buckets[self._index(key)]
        for i,(old,value) in enumerate(bucket):
            if old==key: bucket.pop(i); self.size-=1; return value
        return None
    def _resize(self,capacity):
        rows=[row for bucket in self.buckets for row in bucket]
        self.buckets=[[] for _ in range(capacity)]; self.size=0; self.resize_count+=1
        for key,value in rows:
            bucket=self.buckets[self._index(key)]; bucket.append((key,value)); self.size+=1
    @property
    def collision_count(self): return sum(max(0,len(bucket)-1) for bucket in self.buckets)
    def items(self): return [row for bucket in self.buckets for row in bucket]
