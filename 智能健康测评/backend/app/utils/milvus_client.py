"""Milvus 向量库封装：知识库文本分块向量化 + 相似度检索"""
import logging
import uuid
from typing import List, Dict, Any, Optional

from pymilvus import (
    connections, Collection, CollectionSchema, FieldSchema,
    DataType, utility,
)

from app.core.config import settings
from app.services.llm_client import get_llm

logger = logging.getLogger("milvus_client")

DIM = 1024  # bge-m3 向量维度


class MilvusStore:
    def __init__(self):
        self.collection_name = settings.MILVUS_COLLECTION
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
        )
        self._ensure_collection()

    def _ensure_collection(self):
        if utility.has_collection(self.collection_name, using="default"):
            self.collection = Collection(self.collection_name)
            logger.info("已连接 Milvus collection: %s", self.collection_name)
        else:
            self._create_collection()
        # 加载到内存便于检索
        try:
            self.collection.load()
        except Exception as e:  # noqa: BLE001
            logger.warning("load collection warning: %s", e)

    def _create_collection(self):
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=DIM),
            FieldSchema(name="file_id", dtype=DataType.INT64),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=20000),
        ]
        schema = CollectionSchema(fields, description="健康知识库文档分块向量")
        self.collection = Collection(self.collection_name, schema)
        # 建 IVF_FLAT 索引
        index = {
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 128},
        }
        self.collection.create_index("vector", index)
        logger.info("已创建 Milvus collection: %s", self.collection_name)

    # ---------------- 写入 ----------------
    def add_chunks(self, file_id: int, source: str,
                   chunks: List[str]) -> int:
        """向量化文本分块并入库，返回入库块数"""
        if not chunks:
            return 0
        llm = get_llm()
        # 分批向量化（每批 16 条）
        batch = 16
        rows = []
        for start in range(0, len(chunks), batch):
            part = chunks[start:start + batch]
            vectors = llm.embed_texts(part)
            for idx, (chunk, vec) in enumerate(zip(part, vectors)):
                rows.append({
                    "vector": vec,
                    "file_id": file_id,
                    "source": source,
                    "chunk_index": start + idx,
                    "content": chunk[:19000],
                })
        if rows:
            self.collection.insert(rows)
            self.collection.flush()
        return len(rows)

    # ---------------- 检索 ----------------
    def search(self, query: str, top_k: int = 5,
               file_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """向量相似度检索，返回 [{content, source, distance}, ...]"""
        llm = get_llm()
        qvec = llm.embed_query(query)

        expr = None
        if file_id is not None:
            expr = f"file_id == {file_id}"

        results = self.collection.search(
            data=[qvec],
            anns_field="vector",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            expr=expr,
            output_fields=["content", "source", "file_id", "chunk_index"],
        )
        out = []
        for hit in results[0]:
            out.append({
                "content": hit.entity.get("content"),
                "source": hit.entity.get("source"),
                "file_id": hit.entity.get("file_id"),
                "distance": round(hit.distance, 4),
            })
        return out

    def delete_by_file(self, file_id: int):
        """按文件删除向量"""
        try:
            self.collection.delete(f"file_id == {file_id}")
            self.collection.flush()
        except Exception as e:  # noqa: BLE001
            logger.warning("删除向量失败 file_id=%s: %s", file_id, e)

    def count(self) -> int:
        return self.collection.num_entities


_milvus: Optional[MilvusStore] = None


def get_milvus() -> MilvusStore:
    global _milvus
    if _milvus is None:
        _milvus = MilvusStore()
    return _milvus
