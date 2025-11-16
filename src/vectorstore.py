# src/vectorstore.py
"""
Robust wrapper for Chroma vector store used by the project.
- Creates client/collection lazily and tolerates migration/deprecation errors.
- Falls back to an in-memory store if Chroma is unavailable for developer convenience.
"""

from typing import List, Dict, Any, Optional
import os
import logging

logging.basicConfig(level=logging.INFO)

# Try to import chromadb; if not available or misconfigured, provide a memory fallback
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.errors import NotFoundError
    CHROMA_AVAILABLE = True
except Exception as e:
    chromadb = None
    NotFoundError = Exception
    CHROMA_AVAILABLE = False
    logging.warning("Chroma not available or failed to import: %s", e)

_collection_name = os.getenv("CHROMA_COLLECTION", "competencies")
_client = None
_collection = None

# In-memory fallback store
_memory_store: Dict[str, Dict[str, Any]] = {}


def _init_chroma_client():
    global _client, _collection
    if not CHROMA_AVAILABLE:
        return False
    if _client is not None:
        return True
    try:
        # Use persist_directory to keep data between runs
        settings = Settings(persist_directory=os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"), anonymized_telemetry=False)
        _client = chromadb.Client(settings)
        try:
            _collection = _client.get_collection(name=_collection_name)
        except Exception:
            # create if missing
            _collection = _client.create_collection(name=_collection_name)
        logging.info("Chroma client initialized with collection '%s'", _collection_name)
        return True
    except Exception as e:
        logging.warning("Failed to initialize Chroma client: %s", e)
        _client = None
        _collection = None
        return False


def add_competency_doc(doc_id: str, text: str, metadata: Optional[dict] = None):
    """Add one document to the vector store. If Chroma not available, store in memory.
    metadata is a dict of key->value.
    """
    if metadata is None:
        metadata = {}
    if _init_chroma_client():
        try:
            # Chroma expects lists
            _collection.add(ids=[doc_id], documents=[text], metadatas=[metadata])
            return True
        except Exception as e:
            logging.warning("Chroma add failed, falling back to memory store: %s", e)
    # fallback memory
    _memory_store[doc_id] = {"text": text, "metadata": metadata}
    return True


def query_similar(text: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """Return a list of matches with at least ids and distances (if available) and metadatas.
    If Chroma available, return chroma response; otherwise do a simple substring scoring on memory store.
    """
    if _init_chroma_client():
        try:
            resp = _collection.query(query_texts=[text], n_results=n_results)
            # The exact return shape depends on chroma versions. Normalize to a list of hits.
            hits = []
            # Example resp structure: { 'ids': [[...]], 'metadatas': [[...]], 'distances': [[...]] }
            ids = resp.get("ids", [[]])[0] if isinstance(resp, dict) else []
            metas = resp.get("metadatas", [[]])[0] if isinstance(resp, dict) else []
            dists = resp.get("distances", [[]])[0] if isinstance(resp, dict) else []
            for i, _id in enumerate(ids):
                hit = {"id": _id}
                try:
                    hit["metadata"] = metas[i] if i < len(metas) else {}
                except Exception:
                    hit["metadata"] = {}
                try:
                    hit["distance"] = dists[i] if i < len(dists) else None
                except Exception:
                    hit["distance"] = None
                hits.append(hit)
            return hits
        except Exception as e:
            logging.warning("Chroma query failed, falling back to memory scan: %s", e)
    # memory fallback — naive substring match and simple score
    results = []
    q = text.lower()
    for doc_id, v in _memory_store.items():
        txt = v.get("text", "").lower()
        score = 0
        if q in txt:
            score = 0.0
        elif any(w in txt for w in q.split()[:3] if w):
            score = 0.5
        else:
            score = 1.0
        results.append({"id": doc_id, "metadata": v.get("metadata", {}), "distance": score})
    # sort by distance ascending (lower = better)
    results = sorted(results, key=lambda x: x.get("distance", 1.0))[:n_results]
    return results


