from __future__ import annotations

import json
from pathlib import Path

from agent_os.memory.compression.compressor import CompressionPack, compress_text


class SemanticDisk:
    """Store reusable fact summaries in local JSON files."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def save_memory(
        self,
        run_id: str,
        text: str,
        metadata: dict[str, object] | None = None,
        compression_pack: CompressionPack | None = None,
    ) -> str:
        entries = self._load_entries(run_id)
        entry_index = len(entries)
        ref_id = f"disk:{run_id}:{entry_index}"
        packed = compression_pack or compress_text(text)
        entries.append(
            {
                "ref_id": ref_id,
                "l1": packed.l1,
                "l2": packed.l2,
                "l3": packed.l3,
                "metadata": metadata or {},
            }
        )
        self._write_entries(run_id, entries)
        return ref_id

    def save_fact(self, run_id: str, fact: str) -> str:
        return self.save_memory(run_id=run_id, text=fact, metadata={"type": "fact"})

    def load_by_ref(self, ref_id: str, detail_level: str = "L2") -> str | None:
        parts = ref_id.split(":")
        if len(parts) != 3:
            return None
        _, run_id, index_text = parts
        if not index_text.isdigit():
            return None

        entries = self._load_entries(run_id)
        index = int(index_text)
        if index >= len(entries):
            return None
        key = detail_level.lower()
        if key not in {"l1", "l2", "l3"}:
            key = "l2"
        return str(entries[index].get(key, ""))

    def load_facts(self, run_id: str, detail_level: str = "L2") -> list[str]:
        key = detail_level.lower()
        if key not in {"l1", "l2", "l3"}:
            key = "l2"
        return [str(entry.get(key, "")) for entry in self._load_entries(run_id)]

    def _load_entries(self, run_id: str) -> list[dict[str, object]]:
        run_file = self._root_dir / f"{run_id}.json"
        if not run_file.exists():
            return []
        raw = json.loads(run_file.read_text(encoding="utf-8"))
        # Backward-compatible path for legacy flat list[str] storage.
        if raw and isinstance(raw, list) and isinstance(raw[0], str):
            entries: list[dict[str, object]] = []
            for idx, text in enumerate(raw):
                packed = compress_text(text)
                entries.append(
                    {
                        "ref_id": f"disk:{run_id}:{idx}",
                        "l1": packed.l1,
                        "l2": packed.l2,
                        "l3": packed.l3,
                        "metadata": {"migrated": True},
                    }
                )
            self._write_entries(run_id, entries)
            return entries
        return raw

    def _write_entries(self, run_id: str, entries: list[dict[str, object]]) -> None:
        run_file = self._root_dir / f"{run_id}.json"
        run_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
