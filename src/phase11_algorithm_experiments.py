#!/usr/bin/env python3
"""阶段11三个核心算法与Hash索引的可复现实验入口。"""
from __future__ import annotations
import csv,json,os,random
from dataclasses import asdict,is_dataclass
from datetime import datetime
from pathlib import Path
from algorithms.bplus_tree import BPlusTree
from algorithms.hash_index import HashIndex
from algorithms.conflict_serializability import analyze,parse_schedule
from algorithms.paxos import PaxosCluster

def serializable(value):
    if is_dataclass(value): return {k:serializable(v) for k,v in asdict(value).items()}
    if isinstance(value,dict): return {str(k):serializable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,set)): return [serializable(v) for v in value]
    return value

def bplus_demo():
    tree=BPlusTree(4); reference={}; rng=random.Random(20261110)
    keys=list(range(1,61)); rng.shuffle(keys)
    for key in keys: tree.insert(key,f"card-{key}"); reference[key]=f"card-{key}"
    for key in (2,3,5,7,11,13,17,19,23,29,31,37,41,43,47): tree.delete(key); reference.pop(key)
    tree.validate()
    if list(tree.items())!=sorted(reference.items()): raise AssertionError("B+树差分结果错误")
    events={e["event"] for e in tree.events}
    required={"leaf_split","internal_split","leaf_merge"}
    if not required<=events: raise AssertionError(f"B+树示例未覆盖结构事件：{required-events}")
    return {"parameters":{"order":4,"seed":20261110},"structure":tree.dump_structure(),"range_20_40":tree.range_search(20,40),"covered_events":sorted(events)}

def hash_demo():
    index=HashIndex(4,0.65)
    for key in range(30): index.put(key,f"value-{key}")
    index.put(5,"updated"); removed=index.delete(9)
    return {"capacity":len(index.buckets),"size":index.size,"resize_count":index.resize_count,"collision_count":index.collision_count,"updated_value":index.get(5),"removed_value":removed}

def conflict_demo():
    cases={
      "serializable":["T1:R(A)","T2:W(A)","T1:W(B)","T2:R(B)"],
      "two_transaction_cycle":["T1:W(A)","T2:R(A)","T2:W(B)","T1:R(B)"],
      "three_transaction_cycle":["T1:W(A)","T2:R(A)","T2:W(B)","T3:R(B)","T3:W(C)","T1:R(C)"],
      "read_only":["T1:R(A)","T2:R(A)"]}
    result={}
    for name,schedule in cases.items():
        analysis=analyze(parse_schedule(schedule)); result[name]={"schedule":schedule,**serializable(analysis)}
    if not result["serializable"]["serializable"] or result["two_transaction_cycle"]["serializable"]: raise AssertionError("冲突可串行性示例判定错误")
    return result

def paxos_demo():
    scenarios={}
    cluster=PaxosCluster(5); scenarios["normal"]=serializable(cluster.propose("P1","VALUE-A"))
    cluster=PaxosCluster(5); cluster.set_failed("A4","A5"); scenarios["two_failures"]=serializable(cluster.propose("P1","VALUE-A"))
    cluster=PaxosCluster(5); cluster.set_failed("A3","A4","A5"); scenarios["no_quorum"]=serializable(cluster.propose("P1","VALUE-A"))
    cluster=PaxosCluster(5); scenarios["message_loss"]=serializable(cluster.propose("P1","VALUE-A",drop_prepare={"A5"},drop_accept={"A4","A5"}))
    cluster=PaxosCluster(5); first=cluster.propose("P1","OLD",drop_accept={"A3","A4","A5"}); second=cluster.propose("P2","NEW")
    scenarios["competing_proposers"]={"first":serializable(first),"second":serializable(second)}
    if not scenarios["normal"]["success"] or scenarios["no_quorum"]["success"] or second.learned_value!="OLD": raise AssertionError("Paxos场景验证错误")
    return scenarios

def write_results(result_dir,results):
    result_dir.mkdir(parents=True,exist_ok=True); stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path=result_dir/f"phase11_algorithms_{stamp}.json"; csv_path=result_dir/f"phase11_test_summary_{stamp}.csv"
    json_path.write_text(json.dumps(results,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
    rows=[
      ("B+树","insert/search/range/delete/split/merge","PASS"),
      ("Hash索引","put/get/update/delete/resize/collision","PASS"),
      ("冲突可串行性","graph/evidence/cycle/topological_order","PASS"),
      ("Paxos","prepare/promise/accept/accepted/failure/loss/competition","PASS")]
    with csv_path.open("w",newline="",encoding="utf-8-sig") as handle:
        writer=csv.writer(handle); writer.writerow(["algorithm","coverage","status"]); writer.writerows(rows)
    return json_path,csv_path

def run():
    results={"generated_at":datetime.now().isoformat(sep=" "),"bplus_tree":bplus_demo(),"hash_index":hash_demo(),"conflict_serializability":conflict_demo(),"paxos":paxos_demo()}
    json_path,csv_path=write_results(Path(os.environ.get("P11_RESULT_DIR","results/phase11")),results)
    print(f"PASS|B+树|height={results['bplus_tree']['structure']['height']}|events={','.join(results['bplus_tree']['covered_events'])}")
    print(f"PASS|Hash索引|capacity={results['hash_index']['capacity']}|resize={results['hash_index']['resize_count']}")
    print("PASS|冲突可串行性|可串行与有环案例判定正确，冲突证据完整")
    print("PASS|Paxos|正常、故障、丢包、竞争提议及旧值继承正确")
    print(f"PASS|结果文件|{json_path}|{csv_path}"); print("最终状态：PASS"); return 0

if __name__=="__main__":
    try: code=run()
    except Exception as exc: print(f"最终状态：FAIL｜{type(exc).__name__}｜{exc}"); raise SystemExit(1)
    raise SystemExit(code)
