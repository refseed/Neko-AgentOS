from __future__ import annotations

from types import SimpleNamespace

from agent_os.memory.blackboard.global_blackboard import GlobalBlackboard
from agent_os.memory.cache.episodic_cache import EpisodicCache
from agent_os.memory.compression.compressor import compress_text, keep_cache_refs
from agent_os.memory.disk.semantic_disk import SemanticDisk
from agent_os.memory.ram.working_ram import WorkingRam


def test_memory_layers_store_different_scopes(tmp_path) -> None:
    ram = WorkingRam()
    cache = EpisodicCache()
    disk = SemanticDisk(tmp_path / "semantic")
    blackboard = GlobalBlackboard()

    ram_ref = ram.put("run1", "current_claim", "claim text")
    cache_ref = cache.append("run1", {"event_type": "reasoning"})
    disk_ref = disk.save_fact("run1", "fact text")
    blackboard.set_constant("term", "definition")

    assert ram_ref.startswith("ram:")
    assert cache_ref.startswith("cache:")
    assert disk_ref.startswith("disk:")
    assert blackboard.get_constant("term") == "definition"
    assert disk.load_by_ref(disk_ref, detail_level="L1") is not None


def test_compressor_outputs_l1_l2_l3() -> None:
    pack = compress_text("A " * 500)
    assert len(pack.l1) <= len(pack.l2) <= len(pack.l3)


def test_semantic_disk_returns_requested_detail_level(tmp_path) -> None:
    disk = SemanticDisk(tmp_path / "semantic")
    ref_id = disk.save_memory("run1", "Very long fact " * 100)
    l1 = disk.load_by_ref(ref_id, detail_level="L1")
    l3 = disk.load_by_ref(ref_id, detail_level="L3")
    assert l1 is not None and l3 is not None
    assert len(l1) <= len(l3)


def test_memory_forgetting_can_use_model_indexes() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            return SimpleNamespace(text='{"keep_indexes":[1,3,4]}')

    refs = ["cache:run1:0", "cache:run1:1", "cache:run1:2", "cache:run1:3", "cache:run1:4"]
    kept = keep_cache_refs(refs, model_gateway=FakeGateway(), model_tier="small", keep_limit=3)
    assert kept == ["cache:run1:1", "cache:run1:3", "cache:run1:4"]
