import json
import re
import threading
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding
from flashrank import Ranker, RerankRequest
from rank_bm25 import BM25Okapi

from app.config import Settings
from app.ingestion import Chunk, ingest_policy


def tokens(text: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', text.lower())


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, index in enumerate(ranking, 1):
            scores[index] = scores.get(index, 0.0) + 1 / (k + rank)
    return scores


class PolicyIndex:
    def __init__(self, settings: Settings):
        self.chunks, self.policy_sha256 = ingest_policy(settings.policy_path)
        self.by_id = {c.chunk_id: c for c in self.chunks}
        self.lock = threading.Lock()
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_model = settings.embedding_model
        self.reranker_model = settings.reranker_model
        self.embedder = TextEmbedding(
            model_name=settings.embedding_model, cache_dir=str(settings.cache_dir / 'embeddings'),
            threads=2, enable_cpu_mem_arena=False,
        )
        cache_key = self.policy_sha256[:16] + '-' + settings.embedding_model.split('/')[-1]
        vector_path = settings.cache_dir / f'{cache_key}.npz'
        chunk_ids = [c.chunk_id for c in self.chunks]
        cached = np.load(vector_path, allow_pickle=False) if vector_path.exists() else None
        if cached is not None and cached['ids'].tolist() == chunk_ids:
            self.vectors = cached['vectors']
        else:
            self.vectors = np.array(list(self.embedder.embed(
                [c.section + '\n' + c.text for c in self.chunks], batch_size=8
            )), dtype=np.float32)
            np.savez_compressed(vector_path, vectors=self.vectors, ids=np.array(chunk_ids))
        if cached is not None:
            cached.close()
        self.vectors /= np.maximum(np.linalg.norm(self.vectors, axis=1, keepdims=True), 1e-12)
        self.bm25 = BM25Okapi([tokens(c.section + ' ' + c.text) for c in self.chunks])
        self.ranker = Ranker(
            model_name=settings.reranker_model, cache_dir=str(settings.cache_dir / 'reranker'),
            max_length=512,
        )

    def search(self, query: str, top_k: int = 4, mode: str = 'hybrid') -> list[dict]:
        lexical = np.asarray(self.bm25.get_scores(tokens(query)))
        sparse_order = np.argsort(-lexical)[:12].tolist()
        with self.lock:
            query_vector = np.array(list(self.embedder.query_embed(query))[0])
            query_vector /= max(np.linalg.norm(query_vector), 1e-12)
            dense = self.vectors @ query_vector
            dense_order = np.argsort(-dense)[:12].tolist()
            rankings = [dense_order, sparse_order] if mode == 'hybrid' else [dense_order if mode == 'dense' else sparse_order]
            fused = reciprocal_rank_fusion(rankings)
            candidates = sorted(fused, key=fused.get, reverse=True)[:18]
            passages = [{'id': i, 'text': self.chunks[i].section + '\n' + self.chunks[i].text} for i in candidates]
            ranked = self.ranker.rerank(RerankRequest(query=query, passages=passages))
        return [{
            **self.chunks[int(p['id'])].to_dict(),
            'query': query, 'rank': rank, 'dense_score': float(dense[int(p['id'])]),
            'bm25_score': float(lexical[int(p['id'])]), 'rrf_score': fused[int(p['id'])],
            'rerank_score': float(p['score']),
        } for rank, p in enumerate(ranked[:top_k], 1)]

    def investigate(self, queries: list[str], top_k: int = 4) -> tuple[list[dict], list[dict]]:
        evidence: dict[str, dict] = {}
        searches = []
        for query in dict.fromkeys(queries):
            results = self.search(query, top_k)
            searches.append({'query': query, 'top_k': top_k, 'results': [{
                k: r[k] for k in ('chunk_id', 'rank', 'dense_score', 'bm25_score', 'rrf_score', 'rerank_score')
            } for r in results]})
            for result in results:
                evidence.setdefault(result['chunk_id'], result)
        return list(evidence.values()), searches

    def export(self, path: Path):
        path.write_text(json.dumps([c.to_dict() for c in self.chunks], indent=2), encoding='utf-8')
