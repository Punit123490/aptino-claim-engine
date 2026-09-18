"""Layout-aware clause extraction with stable, source-derived identifiers."""
import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class Chunk:
    chunk_id: str
    text: str
    section: str
    pages: list[int]
    source: str

    def to_dict(self):
        return asdict(self)


MAJOR = {
    'DEFINITIONS', 'SCOPE OF COVER', 'WHAT WE COVER', 'WHAT WE EXCLUDE',
    'EXTENSIONS', 'CLAIMS PROCEDURE', 'STANDARD TERMS AND CONDITIONS:',
}


def clean(line: str) -> str:
    return re.sub(r'\s+', ' ', line).strip().replace('\u201f', "'").replace('\u2019', "'")


def heading(line: str) -> bool:
    return bool(
        line in MAJOR
        or re.match(r'^NB\d+:', line)
        or re.match(r'^\d+\.\s+[A-Z0-9]', line)
        or re.match(r'^\([A-C]\)\s+', line)
        or re.match(r'^[A-Z][A-Za-z /()\-]{1,65}\smeans\b', line)
        or line in {'Day Care Treatment', 'Critical Illness', 'Note'}
    )


def ingest_policy(path: Path) -> tuple[list[Chunk], str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    chunks: list[Chunk] = []
    section = 'Policy contract'
    subsection = ''
    lines: list[str] = []
    pages: list[int] = []

    def flush():
        nonlocal lines, pages
        text = '\n'.join(lines).strip()
        if text and len(text) > 35:
            identity = f'{digest}|{pages}|{text}'
            chunks.append(Chunk(
                chunk_id='clause-' + hashlib.sha256(identity.encode()).hexdigest()[:12],
                text=text, section=f'{section} / {subsection}' if subsection else section,
                pages=sorted(set(pages)), source=path.name,
            ))
        lines, pages = [], []

    for page_no, page in enumerate(PdfReader(path).pages, start=1):
        # Layout mode repairs the PDF content-stream reading order on page 8.
        raw = page.extract_text(extraction_mode='layout') or ''
        for raw_line in raw.splitlines():
            line = clean(raw_line)
            if not line:
                # Split only at paragraph boundaries, retaining parent heading context.
                if sum(map(len, lines)) > 1600:
                    flush()
                continue
            if 'UNIVERSAL SOMPO GENERAL INSURANCE CO LTD' in line or 'IRDAI Reg No' in line:
                continue
            # The source numbers domiciliary subconditions 18-20 as if they were
            # standalone exclusions. Keep them under their explicit parent (17).
            domiciliary_child = section == 'WHAT WE EXCLUDE' and subsection.startswith('17.') and bool(
                re.match(r'^(18|19|20)\.', line)
            )
            if heading(line) and not domiciliary_child:
                flush()
                if line in MAJOR:
                    section, subsection = line.rstrip(':'), ''
                else:
                    subsection = line[:160]
            lines.append(line)
            if page_no not in pages:
                pages.append(page_no)
    flush()
    if len(chunks) < 20:
        raise ValueError('Policy extraction produced too few clauses; check the PDF text layer.')
    return chunks, digest
