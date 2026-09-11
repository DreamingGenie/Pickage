import unittest
import uuid
import time

import numpy as np

from .historical_gpu import cpu_ranks
from .historical_gpu_owner import MAX_FRAME, Owner, OwnerError, Client, _identity, _pack


def identity(partition=0):
    return {"run_plan_sha256": "a" * 64, "epoch": "b" * 32,
            "attempt": f"partitions/{partition:03d}/attempts/" + "c" * 32,
            "partition_id": partition}


def plan(version="1.0.0"):
    return {"snapshot_count": 3, "known_package": True,
            "rank_to_version": [version], "birth_by_rank": [0],
            "earliest_accepted_birth": 0,
            "lookups": [{"requirement": "*", "normalized_range": "*", "fixed_status": None, "spans": [[0, 1]]}]}


class OwnerContractTests(unittest.TestCase):
    def test_identity_and_frame_caps(self):
        _identity(identity())
        with self.assertRaises(ValueError): _identity({**identity(), "epoch": "x"})
        with self.assertRaises(ValueError): _identity({**identity(), "partition_id": 256})
        with self.assertRaises(ValueError): _pack("x" * (MAX_FRAME + 1))

    @unittest.skipUnless(__import__('torch').cuda.is_available(), "requires CUDA owner")
    def test_two_clients_interleave_and_match_cpu(self):
        owner = Owner(2, workspace_mib=1)
        clients = []
        try:
            owner.__enter__()
            for _ in range(2): clients.append(Client(owner.address, owner.authkey, owner.runtime))
            p1, p2 = plan(), plan("2.0.0")
            clients[0].bind(identity(0)); clients[1].bind({**identity(1), "attempt": "partitions/001/attempts/" + "d" * 32})
            clients[0].begin("pkg-a", p1); clients[1].begin("pkg-b", p2)
            r1, _ = clients[0].ranks("pkg-a", p1); r2, _ = clients[1].ranks("pkg-b", p2)
            np.testing.assert_array_equal(r1, cpu_ranks(p1)[0]); np.testing.assert_array_equal(r2, cpu_ranks(p2)[0])
            clients[0].end("pkg-a"); clients[1].end("pkg-b")
        finally:
            for client in clients: client.close()
            owner.close()

    @unittest.skipUnless(__import__('torch').cuda.is_available(), "requires CUDA owner")
    def test_owner_latches_worker_death_and_bad_sequence_is_fatal(self):
        owner = Owner(1, workspace_mib=1)
        client = None
        try:
            owner.__enter__()
            client = Client(owner.address, owner.authkey, owner.runtime)
            with self.assertRaises(OwnerError): client._request({'op': 'hello'})
            deadline = time.monotonic() + 5
            while True:
                try: owner.check()
                except OwnerError: break
                if time.monotonic() >= deadline: self.fail("Owner did not latch protocol failure")
                time.sleep(0.05)
            owner.close()
            owner = Owner(1, workspace_mib=1); owner.__enter__()
            client.close(); client = Client(owner.address, owner.authkey, owner.runtime)
            owner.pool.slots[0]['process'].terminate()
            deadline = time.monotonic() + 5
            while True:
                try: owner.check()
                except OwnerError: break
                if time.monotonic() >= deadline: self.fail("Owner did not latch worker death")
                time.sleep(0.05)
        finally:
            if client: client.close()
            owner.close()


if __name__ == "__main__": unittest.main()
