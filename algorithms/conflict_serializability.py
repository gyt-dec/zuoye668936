"""通过优先图环检测判别冲突可串行性。"""
from __future__ import annotations
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class Operation:
    transaction: str
    kind: str
    item: str
    sequence: int=0
    def __post_init__(self):
        if not self.transaction or self.kind not in {"R","W"} or not self.item: raise ValueError("非法调度操作")
    def label(self): return f"{self.transaction}:{self.kind}({self.item})"

@dataclass
class SerializabilityResult:
    serializable: bool
    graph: dict[str,list[str]]
    conflicts: list[dict]
    topological_order: list[str]
    cycle: list[str]

PATTERN=re.compile(r"^([A-Za-z][A-Za-z0-9_]*):([RW])\(([^()]+)\)$")
def parse_schedule(tokens:list[str])->list[Operation]:
    result=[]
    for sequence,token in enumerate(tokens):
        match=PATTERN.fullmatch(token.strip())
        if not match: raise ValueError(f"非法操作：{token}")
        result.append(Operation(*match.groups(),sequence))
    return result

def analyze(operations:list[Operation])->SerializabilityResult:
    transactions=sorted({op.transaction for op in operations}); graph={t:set() for t in transactions}; evidence=[]
    for i,left in enumerate(operations):
        for right in operations[i+1:]:
            if left.transaction==right.transaction or left.item!=right.item or (left.kind==right.kind=="R"): continue
            graph[left.transaction].add(right.transaction)
            evidence.append({"from":left.transaction,"to":right.transaction,"earlier":left.label(),"later":right.label(),"item":left.item,"types":left.kind+right.kind})
    state={t:0 for t in transactions}; stack=[]; cycle=[]
    def dfs(node):
        nonlocal cycle
        state[node]=1; stack.append(node)
        for target in sorted(graph[node]):
            if state[target]==0 and dfs(target): return True
            if state[target]==1:
                start=stack.index(target); cycle=stack[start:]+[target]; return True
        stack.pop(); state[node]=2; return False
    has_cycle=any(state[t]==0 and dfs(t) for t in transactions)
    topo=[]
    if not has_cycle:
        indegree={t:0 for t in transactions}
        for targets in graph.values():
            for target in targets: indegree[target]+=1
        ready=sorted(t for t,d in indegree.items() if d==0)
        while ready:
            node=ready.pop(0); topo.append(node)
            for target in sorted(graph[node]):
                indegree[target]-=1
                if indegree[target]==0: ready.append(target); ready.sort()
    return SerializabilityResult(not has_cycle,{k:sorted(v) for k,v in graph.items()},evidence,topo,cycle)
