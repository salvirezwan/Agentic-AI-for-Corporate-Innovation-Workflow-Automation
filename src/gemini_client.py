# src/gemini_client.py
import os
import json
import re
from dotenv import load_dotenv
load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# Basic wrapper for calling Gemini via google-genai SDK if available.
# If google-genai isn't installed or not configured, this will raise an informative error.

def raw_model_call(prompt: str) -> str:
    """Return raw text from the model. Raise RuntimeError with helpful message if call fails."""
    try:
        from google import genai
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set in environment")
        genai.api_key = GEMINI_API_KEY
        client = genai.Client()
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        # try common fields
        if hasattr(resp, "text"):
            return getattr(resp, "text")
        # fallback: stringify
        return str(resp)
    except Exception as e:
        # Provide explicit guidance so callers can debug quickly
        raise RuntimeError(
            "Gemini call failed. Ensure google-genai is installed and GEMINI_API_KEY is set. "
            f"Original error: {e}"
        )


# Helpers for extracting JSON from model responses
_json_re = re.compile(r"(\[\s*\{.*?\}\s*\])", re.DOTALL)
_obj_re = re.compile(r"(\{.*\})", re.DOTALL)


def _extract_json_with_regex(text: str):
    # try array first
    m = _json_re.search(text)
    if m:
        return m.group(1)
    m = _obj_re.search(text)
    if m:
        return m.group(1)
    return None


def generate_text(prompt: str) -> str:
    return raw_model_call(prompt)


def generate_json(prompt: str, debug=False, cleanup_attempt=True):
    """Return (parsed, raw_text) or (None, raw_text) if parsing fails.
    Attempts direct JSON, then regex extraction, then a cleanup pass asking the model to return only JSON.
    """
    raw = generate_text(prompt)
    if debug:
        print("[DEBUG] Gemini raw (first call):", raw[:1200])

    # try direct parse
    try:
        parsed = json.loads(raw)
        return parsed, raw
    except Exception:
        pass

    # regex extraction
    candidate = _extract_json_with_regex(raw)
    if candidate:
        try:
            parsed = json.loads(candidate)
            return parsed, raw
        except Exception:
            if debug:
                print("[DEBUG] regex found JSON-like content but json.loads failed")

    # cleanup attempt — ask model to return only JSON
    if cleanup_attempt:
        cleanup_prompt = (
            "The text below may contain commentary and JSON. Extract and return ONLY the JSON array or object present. "
            "If there is no JSON, return an empty array []\n\n"
            "ORIGINAL TEXT:\n----START----\n"
            f"{raw}\n"
            "----END----\n\nReturn only JSON."
        )
        try:
            raw2 = generate_text(cleanup_prompt)
            if debug:
                print("[DEBUG] Gemini raw (cleanup call):", raw2[:1200])
            try:
                parsed2 = json.loads(raw2)
                return parsed2, raw2
            except Exception:
                candidate2 = _extract_json_with_regex(raw2)
                if candidate2:
                    try:
                        parsed2 = json.loads(candidate2)
                        return parsed2, raw2
                    except Exception:
                        pass
        except Exception as e:
            # If cleanup call fails, return best-effort raw
            if debug:
                print("[DEBUG] cleanup call failed:", e)
    return None, raw