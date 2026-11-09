import unittest
from algorithms.paxos import Learner,PaxosCluster,ProposalNumber

class PaxosTests(unittest.TestCase):
    def test_normal_consensus(self):
        cluster=PaxosCluster(5); result=cluster.propose("P1","CARD-USED")
        self.assertTrue(result.success); self.assertEqual(result.promise_count,5); self.assertEqual(result.accepted_count,5); self.assertEqual(result.learned_value,"CARD-USED")
        self.assertIn("PROMISE",{e["type"] for e in result.events}); self.assertIn("ACCEPTED",{e["type"] for e in result.events})
    def test_minority_failures_and_message_loss(self):
        cluster=PaxosCluster(5); cluster.set_failed("A4","A5")
        self.assertTrue(cluster.propose("P1","V").success)
        cluster=PaxosCluster(5)
        self.assertTrue(cluster.propose("P1","V",drop_prepare={"A4","A5"},drop_accept={"A4","A5"}).success)
    def test_no_quorum(self):
        cluster=PaxosCluster(5); cluster.set_failed("A3","A4","A5")
        result=cluster.propose("P1","V"); self.assertFalse(result.success); self.assertIsNone(result.learned_value)
        cluster=PaxosCluster(5); self.assertFalse(cluster.propose("P1","V",drop_prepare={"A1","A2","A3"}).success)
    def test_new_proposer_inherits_highest_accepted_value(self):
        cluster=PaxosCluster(5)
        first=cluster.propose("P1","OLD",drop_accept={"A3","A4","A5"})
        self.assertFalse(first.success); self.assertEqual(first.accepted_count,2)
        second=cluster.propose("P2","NEW")
        self.assertTrue(second.success); self.assertEqual(second.chosen_value,"OLD"); self.assertEqual(second.learned_value,"OLD")
    def test_stale_number_rejected(self):
        cluster=PaxosCluster(5); cluster.propose("P2","V",number=ProposalNumber(10,"P2"))
        stale=cluster.propose("P1","X",number=ProposalNumber(1,"P1")); self.assertFalse(stale.success); self.assertEqual(stale.promise_count,0)
    def test_learner_deduplicates_and_rejects_two_values(self):
        learner=Learner(2); number=ProposalNumber(1,"P1")
        learner.observe("A1",number,"V"); learner.observe("A1",number,"V"); self.assertIsNone(learner.learned_value)
        learner.observe("A2",number,"V"); self.assertEqual(learner.learned_value,"V")
        with self.assertRaises(AssertionError):
            learner.observe("A3",ProposalNumber(2,"P2"),"X"); learner.observe("A4",ProposalNumber(2,"P2"),"X")
