# src/nodes/search_agent.py
import os
import requests
import json
import time
from dotenv import load_dotenv

load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# small helper for safe JSON parsing
def _safe_load_json(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def tavily_search(company_name: str, max_results: int = 5, retries: int = 2, backoff: float = 1.0):
    """
    Call Tavily search endpoint (POST JSON). Returns a list of {url, snippet}.
    Retries on transient errors. Raises RuntimeError if API key missing.
    """
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY not set")

    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": company_name,
        "max_results": max_results
    }

    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            # debug raw
            print("RAW Tavily Response:", resp.text)
            results = data.get("results") or data.get("items") or []
            snippets = []
            for item in results[:max_results]:
                url_val = item.get("url") or item.get("link") or item.get("page_url") or ""
                snippet_val = item.get("content") or item.get("snippet") or item.get("summary") or item.get("text") or ""
                if snippet_val:
                    snippets.append({"url": url_val, "snippet": snippet_val})
            return snippets
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status and (status >= 500 or status == 429) and attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            raise
        except Exception as e:
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            raise


from src.gemini_client import generate_text


def search_company(company_name: str, max_results: int = 5):
    """
    Phase 1 search. Try Tavily first (recommended). If Tavily fails or returns nothing,
    fallback to a Gemini-generated conservative summary (JSON array of {url, snippet}).
    """
    # 1) Try Tavily
    if TAVILY_API_KEY:
        try:
            snippets = tavily_search(company_name, max_results=max_results)
            if snippets:
                print(f"[INFO] Tavily returned {len(snippets)} snippets for '{company_name}'")
                return snippets
            else:
                print(f"[WARN] Tavily returned no snippets for '{company_name}'")
        except Exception as e:
            print("[WARN] Tavily search failed:", e)

    # 2) Fallback: use Gemini to synthesize conservative snippets
    prompt = (
        "You are a conservative researcher. Simulate 4 concise, fact-oriented web snippets "
        f"about the public capabilities of the company '{company_name}'. For any claim that is not certain, "
        "include the word 'may' or 'possibly' in the snippet. Return a JSON array of objects with fields: url, snippet. "
        "If you don't have a real URL, set url to an empty string. Return only valid JSON."
    )

    try:
        raw = generate_text(prompt)
        parsed = _safe_load_json(raw)
        if isinstance(parsed, list) and parsed:
            normalized = []
            for r in parsed[:max_results]:
                url_val = r.get("url", "") if isinstance(r, dict) else ""
                snippet_val = r.get("snippet", "") if isinstance(r, dict) else ""
                if snippet_val:
                    normalized.append({"url": url_val, "snippet": snippet_val})
            if normalized:
                print(f"[INFO] Gemini fallback produced {len(normalized)} snippets for '{company_name}'")
                return normalized
    except Exception as e:
        print("[WARN] Gemini fallback failed to produce snippets:", e)

    # 3) Final fallback: single minimal snippet prompting the user to confirm competencies
    return [{"url": "", "snippet": f"{company_name} - no web API available; please confirm core competencies."}]