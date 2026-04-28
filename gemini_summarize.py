"""Gemini-backed replacement for ytt.core.summarize_with_claude.

Same return shape (`{short_summary, long_summary}`) so monitor.py's process_video
can swap implementations without touching anything else.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

PROMPTS: Dict[str, Dict[str, str]] = {
    "ko": {
        "chunk": (
            "당신은 YouTube 영상을 요약하는 어시스턴트입니다. "
            "제공된 오디오 전사 chunk를 명확한 한국어 bullet point로 요약하세요. "
            "주요 정보·인용·숫자만 추출하고, 잡담은 생략합니다."
        ),
        "final": (
            "다음 부분 요약들을 한국어 1~2문장의 TL;DR로 응축하세요. "
            "영상의 핵심 메시지가 한 번에 전달되어야 합니다."
        ),
    },
    "en": {
        "chunk": (
            "You summarize YouTube transcripts. Reduce the provided chunk to clear "
            "bullet points covering the key facts, quotes, and numbers."
        ),
        "final": "Compress the chunk summaries below into a 1-2 sentence TL;DR.",
    },
    "ja": {
        "chunk": "YouTube動画の文字起こしを日本語の箇条書きで要約してください。",
        "final": "以下の要約を日本語の1〜2文のTL;DRにまとめてください。",
    },
}

DEFAULT_MODEL = "gemini-2.5-flash"


def summarize_with_gemini(
    transcripts: List[Dict],
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    language: str = "ko",
    max_workers: int = 2,
) -> Dict[str, str]:
    """Summarize a list of transcript chunks via the Gemini API.

    `transcripts` matches ytt's shape: each entry has a `segments` list whose items
    have a `text` field. The function flattens segments per chunk, asks Gemini for a
    chunk-level summary in parallel (max_workers caps free-tier RPM exposure), then
    asks Gemini once more to compress the joined chunk summaries into a TL;DR.

    Returns: `{"short_summary": str, "long_summary": str}` — same as ytt's helper.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set; pass --no-process to skip summarization"
        )

    if language not in PROMPTS:
        logger.warning("Unsupported language %r; defaulting to ko", language)
        language = "ko"
    chunk_prompt = PROMPTS[language]["chunk"]
    final_prompt = PROMPTS[language]["final"]

    client = genai.Client(api_key=api_key)
    chunk_texts = [
        " ".join(seg["text"] for seg in chunk["segments"])
        for chunk in transcripts
    ]
    logger.info(
        "Gemini summary: %d chunks, model=%s, language=%s",
        len(chunk_texts), model, language,
    )

    def _summarize_chunk(idx_text):
        idx, text = idx_text
        try:
            response = client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=chunk_prompt,
                    temperature=0.3,
                    max_output_tokens=2048,
                ),
            )
            return idx, (response.text or "").strip()
        except Exception as exc:
            logger.error("Chunk %d summary failed: %s", idx + 1, exc)
            return idx, f"[요약 실패: {exc}]"

    chunk_results: Dict[int, str] = {}
    workers = max(1, min(max_workers, len(chunk_texts)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_summarize_chunk, (i, t))
            for i, t in enumerate(chunk_texts)
        ]
        for fut in as_completed(futures):
            idx, summary = fut.result()
            chunk_results[idx] = summary

    long_summary = "\n\n".join(chunk_results[i] for i in sorted(chunk_results))

    try:
        response = client.models.generate_content(
            model=model,
            contents=long_summary,
            config=types.GenerateContentConfig(
                system_instruction=final_prompt,
                temperature=0.3,
                max_output_tokens=512,
            ),
        )
        short_summary = (response.text or "").strip() or "[최종 요약 비어있음]"
    except Exception as exc:
        logger.error("Final TL;DR summary failed: %s", exc)
        short_summary = f"[최종 요약 실패: {exc}]"

    return {"long_summary": long_summary, "short_summary": short_summary}
