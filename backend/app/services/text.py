import hashlib
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from pypdf import PdfReader

from app.config import get_settings


SECRET_PATTERNS = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?i)(?:api[_ -]?key|access[_ -]?token|token|secret|password|密码)"
        r"\s*[:=]\s*[\"']?[^\s,;\"']{6,}[\"']?"
    ),
    re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"),
    re.compile(r"(?<!\d)(?:\d[ -]?){15,19}(?!\d)"),
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
]


@dataclass
class ParsedSection:
    content: str
    heading: str | None = None
    page_number: int | None = None


def redact_sensitive(text: str) -> str:
    clean = text
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[已脱敏]", clean)
    return clean.strip()


def tokenize(text: str) -> list[str]:
    lower = text.lower()
    latin = re.findall(r"[a-z0-9_.:/-]+", lower)
    chinese_sequences = re.findall(r"[\u4e00-\u9fff]+", lower)
    chinese: list[str] = []
    for sequence in chinese_sequences:
        chinese.extend(sequence)
        chinese.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return latin + chinese


def deterministic_embedding(text: str, dimensions: int | None = None) -> list[float]:
    dimensions = dimensions or get_settings().embedding_dimensions
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 + min(len(token), 12) / 12
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def get_embedding(text: str) -> list[float]:
    settings = get_settings()
    if not settings.embedding_base_url or not settings.embedding_model:
        return deterministic_embedding(text)
    response = None
    for attempt in range(3):
        try:
            response = httpx.post(
                f"{settings.embedding_base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {settings.embedding_api_key or ''}"},
                json={"model": settings.embedding_model, "input": text},
                timeout=settings.model_timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.RequestError):
            if attempt == 2:
                raise
            time.sleep(0.5 * (2**attempt))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 2:
                response.raise_for_status()
            time.sleep(0.5 * (2**attempt))
            continue
        response.raise_for_status()
        break
    if response is None:
        raise ValueError("Embedding 服务没有返回响应")
    try:
        embedding = response.json()["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("Embedding 服务返回格式无效") from exc
    if not isinstance(embedding, list) or len(embedding) != settings.embedding_dimensions:
        actual = len(embedding) if isinstance(embedding, list) else 0
        raise ValueError(
            f"Embedding 维度不匹配：期望 {settings.embedding_dimensions}，实际 {actual}"
        )
    if not all(isinstance(value, (int, float)) for value in embedding):
        raise ValueError("Embedding 服务返回了非数字向量")
    return [float(value) for value in embedding]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


def chunk_sections(sections: list[ParsedSection], target: int = 850, overlap: int = 100) -> list[ParsedSection]:
    chunks: list[ParsedSection] = []
    for section in sections:
        text = re.sub(r"\n{3,}", "\n\n", section.content).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + target, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", start, end), text.rfind("。", start, end))
                if boundary > start + target // 2:
                    end = boundary + 1
            chunks.append(
                ParsedSection(
                    content=text[start:end].strip(),
                    heading=section.heading,
                    page_number=section.page_number,
                )
            )
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks


def parse_file(path: Path) -> list[ParsedSection]:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8")
        if suffix == ".txt":
            return [ParsedSection(text)]
        sections: list[ParsedSection] = []
        heading: str | None = None
        buffer: list[str] = []
        for line in text.splitlines():
            if line.startswith("#"):
                if buffer:
                    sections.append(ParsedSection("\n".join(buffer), heading))
                heading = line.lstrip("# ").strip()
                buffer = []
            else:
                buffer.append(line)
        if buffer:
            sections.append(ParsedSection("\n".join(buffer), heading))
        return sections
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        sections = []
        for index, page in enumerate(reader.pages):
            content = (page.extract_text() or "").strip()
            if content:
                sections.append(ParsedSection(content, page_number=index + 1))
        if not sections:
            raise ValueError("该 PDF 未检测到可抽取文本，V1 暂不支持扫描件 OCR")
        return sections
    raise ValueError("仅支持 Markdown、TXT 和文本型 PDF")
