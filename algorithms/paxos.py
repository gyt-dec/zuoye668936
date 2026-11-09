"""可注入节点故障和消息丢失的确定性单值Paxos模拟器。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True,order=True)
class ProposalNumber:
    round: int
    proposer_id: str

@dataclass
class Promise:
    acceptor_id: str
    accepted_number: ProposalNumber|None
    accepted_value: Any

class Acceptor:
    def __init__(self,node_id):
        self.node_id=node_id; self.promised_number=None; self.accepted_number=None; self.accepted_value=None; self.failed=False
    def prepare(self,number):
        if self.failed or (self.promised_number is not None and number<self.promised_number): return None
        self.promised_number=number; return Promise(self.node_id,self.accepted_number,self.accepted_value)
    def accept(self,number,value):
        if self.failed or (self.promised_number is not None and number<self.promised_number): return False
        self.promised_number=number; self.accepted_number=number; self.accepted_value=value; return True

class Learner:
    def __init__(self,quorum): self.quorum=quorum; self.votes={}; self.learned_value=None
    def observe(self,acceptor_id,number,value):
        key=(number,value); self.votes.setdefault(key,set()).add(acceptor_id)
        if len(self.votes[key])>=self.quorum:
            if self.learned_value is not None and self.learned_value!=value: raise AssertionError("Paxos安全性违反：学习了两个值")
            self.learned_value=value
        return self.learned_value

class Proposer:
    def __init__(self,proposer_id): self.proposer_id=proposer_id; self.round=0
    def next_number(self): self.round+=1; return ProposalNumber(self.round,self.proposer_id)

@dataclass
class PaxosResult:
    success: bool
    proposal_number: ProposalNumber
    proposed_value: Any
    chosen_value: Any
    promise_count: int
    accepted_count: int
    learned_value: Any
    events: list[dict]

class PaxosCluster:
    def __init__(self,acceptor_count=5):
        if acceptor_count<1: raise ValueError("至少一个Acceptor")
        self.acceptors={f"A{i}":Acceptor(f"A{i}") for i in range(1,acceptor_count+1)}
        self.quorum=acceptor_count//2+1; self.learner=Learner(self.quorum); self.proposers={}; self.events=[]
    def proposer(self,proposer_id): return self.proposers.setdefault(proposer_id,Proposer(proposer_id))
    def set_failed(self,*ids):
        for node_id in ids: self.acceptors[node_id].failed=True
    def _log(self,**event): self.events.append({"sequence":len(self.events)+1,**event})
    def propose(self,proposer_id,value,drop_prepare=frozenset(),drop_accept=frozenset(),number=None):
        proposer=self.proposer(proposer_id); number=number or proposer.next_number(); promises={}
        for node_id,acceptor in self.acceptors.items():
            if node_id in drop_prepare: self._log(type="PREPARE",sender=proposer_id,receiver=node_id,delivered=False,number=str(number)); continue
            promise=acceptor.prepare(number); self._log(type="PROMISE" if promise else "REJECT",sender=node_id,receiver=proposer_id,delivered=True,number=str(number))
            if promise: promises[node_id]=promise
        if len(promises)<self.quorum: return PaxosResult(False,number,value,None,len(promises),0,self.learner.learned_value,list(self.events))
        prior=[p for p in promises.values() if p.accepted_number is not None]
        chosen=max(prior,key=lambda p:p.accepted_number).accepted_value if prior else value
        accepted=set()
        for node_id,acceptor in self.acceptors.items():
            if node_id in drop_accept: self._log(type="ACCEPT_REQUEST",sender=proposer_id,receiver=node_id,delivered=False,number=str(number),value=chosen); continue
            ok=acceptor.accept(number,chosen); self._log(type="ACCEPTED" if ok else "REJECT",sender=node_id,receiver=proposer_id,delivered=True,number=str(number),value=chosen)
            if ok: accepted.add(node_id); self.learner.observe(node_id,number,chosen)
        success=len(accepted)>=self.quorum
        return PaxosResult(success,number,value,chosen,len(promises),len(accepted),self.learner.learned_value,list(self.events))
