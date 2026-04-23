# =========================
# 📦 IMPORTS
# =========================
import re
import fitz  # pymupdf
import pdfplumber
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter


# =========================
# ⚙️ CONFIG
# =========================
@dataclass
class ParserConfig:
    max_words_per_chunk: int = 200
    min_words_noise_threshold: int = 5
    front_matter_skip: int = 0
    heading_font_percentile: float = 0.80
    bold_as_heading: bool = True
    extra_noise_patterns: list = field(default_factory=list)
    extra_low_value_keywords: list = field(default_factory=list)
    domain_chunk_tags: dict = field(default_factory=dict)


# =========================
# 🔍 FONT ANALYSIS
# Scans entire PDF to build a font-size distribution.
# Body size = most word-heavy font. Heading = anything >= 1.15x body.
# =========================
def analyze_font_sizes(file_path: str) -> dict:
    doc = fitz.open(file_path)
    size_counter = Counter()

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    size = round(span["size"], 1)
                    size_counter[size] += len(span["text"].split())

    doc.close()

    if not size_counter:
        return {"body_size": 11.0, "heading_threshold": 13.0}

    body_size = size_counter.most_common(1)[0][0]
    heading_threshold = round(body_size * 1.15, 1)

    return {
        "body_size": body_size,
        "heading_threshold": heading_threshold,
        "size_distribution": dict(size_counter)
    }


# =========================
# 🧠 PYMUPDF PARSER
# =========================
def parse_with_pymupdf(file_path: str, config: "ParserConfig") -> list[dict]:
    font_info = analyze_font_sizes(file_path)
    heading_threshold = font_info["heading_threshold"]
    body_size = font_info["body_size"]

    print(f"   📐 Body font size: {body_size}pt | Heading threshold: >{heading_threshold}pt")

    doc = fitz.open(file_path)
    chunks = []
    current_title = ""
    current_text = ""

    def flush_chunk(title, text, level):
        text = text.strip()
        if text:
            chunks.append({
                "text": text,
                "title": title,
                "type": "section",
                "heading_level": level,
                "source": "pymupdf"
            })

    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        # Sort blocks top-to-bottom, left-to-right (fixes multi-column ordering)
        blocks = sorted(blocks, key=lambda b: (round(b["bbox"][1] / 20), b["bbox"][0]))

        for block in blocks:
            if block["type"] != 0:
                continue

            for line in block["lines"]:
                line_text = ""
                max_size = 0
                is_bold = False

                for span in line["spans"]:
                    line_text += span["text"]
                    span_size = round(span["size"], 1)
                    if span_size > max_size:
                        max_size = span_size
                    if span["flags"] & 16:  # bit 4 = bold
                        is_bold = True

                line_text = line_text.strip()
                if not line_text:
                    continue

                # ── Heading detection ──────────────────────────────────
                is_large_heading = max_size >= heading_threshold

                # FIX: Tightened bold heading — reject mid-sentence bold spans.
                # Real sub-headings: short, don't end with lowercase or trailing punct.
                last_char = line_text.rstrip()[-1] if line_text.rstrip() else ""
                ends_like_sentence = (
                    last_char.islower()
                    or last_char in (",", ";", "–", "-")
                )

                is_bold_heading = (
                    config.bold_as_heading
                    and is_bold
                    and max_size >= body_size
                    and max_size < heading_threshold
                    and len(line_text.split()) <= 10   # tightened from 12
                    and not ends_like_sentence
                )

                if is_large_heading:
                    flush_chunk(current_title, current_text, level=1)
                    current_title = line_text
                    current_text = line_text
                elif is_bold_heading:
                    flush_chunk(current_title, current_text, level=2)
                    current_title = line_text
                    current_text = line_text
                else:
                    current_text += " " + line_text

    flush_chunk(current_title, current_text, level=1)
    doc.close()

    return chunks


# =========================
# 📊 PDFPLUMBER TABLE PARSER
# FIX: is_fake_table() removes page header/footer misreads
# =========================
def is_fake_table(rows: list) -> bool:
    """
    NCERT's two-column page layout gets misread as tables by pdfplumber.
    These fake tables are small (≤4 rows) and contain page numbers / subject names.
    """
    if len(rows) > 4:
        return False  # real tables have more rows

    full_text = " | ".join(rows)

    # Page number sandwiched in pipes: "| 229 |"
    has_page_number = bool(re.search(r"\|\s*\d{1,3}\s*\|", full_text))

    # Subject name + page number combo (running header pattern)
    has_chapter_header = bool(re.search(
        r"(biology|chemistry|physics|mathematics|history|geography|civics|economics)\s*\|\s*\d+",
        full_text, re.IGNORECASE
    ))

    # All cells are very short (headers/footers have no real content)
    cells = [c.strip() for c in full_text.split("|") if c.strip()]
    all_cells_short = all(len(c.split()) <= 4 for c in cells) if cells else True

    return has_page_number or has_chapter_header or (all_cells_short and len(cells) <= 4)


def parse_tables_with_pdfplumber(file_path: str) -> list[dict]:
    structured_chunks = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue

                rows = []
                for row in table:
                    if not row:
                        continue
                    cleaned_row = [cell.strip() if cell else "" for cell in row]
                    if any(cleaned_row):
                        rows.append(" | ".join(cleaned_row))

                # FIX: skip fake tables before appending
                if not rows or is_fake_table(rows):
                    continue

                structured_chunks.append({
                    "text": "\n".join(rows),
                    "title": "",
                    "type": "table",
                    "heading_level": 0,
                    "source": "pdfplumber"
                })

    return structured_chunks


# =========================
# 🔗 MERGE
# =========================
def merge_chunks(text_chunks: list, table_chunks: list) -> list:
    return text_chunks + table_chunks


# =========================
# 🧹 REMOVE DUPLICATES
# =========================
def remove_duplicates(chunks: list) -> list:
    seen = set()
    unique = []
    for ch in chunks:
        text = ch["text"]
        if text not in seen:
            unique.append(ch)
            seen.add(text)
    return unique


# =========================
# 🧼 CLEAN TEXT
# =========================
def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}(.*?)_{1,2}", r"\1", text)
    text = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", text)   # hyphenated line breaks
    text = re.sub(r"\f", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# =========================
# 🚫 NOISE FILTER
# FIX: Added ToC entry patterns and page range patterns
# =========================
UNIVERSAL_NOISE_PATTERNS = [
    r"\bISBN[-:\s][\d\-X]+\b",
    r"\bcopyright\b",
    r"\ball rights reserved\b",
    r"^\s*\d{1,4}\s*$",                              # standalone page numbers
    r"www\.[a-z0-9\-]+\.[a-z]{2,}",                  # URLs
    r"doi:\s*10\.\d{4,}",
    r"^\s*(figure|fig\.?|table)\s*\d+\s*$",          # standalone fig/table labels
    r"reprint\s*\d{4}[-–]\d{2}",                     # NCERT reprint lines
    r"^\s*chapter\s*\d+\s*$",                        # bare "Chapter 5"
    r"chapter\s*\d+\s*:[\w\s,\-]+\d{1,3}\s*$",      # FIX: ToC "Chapter 1 : Title 3"
    r"^\d{1,3}-\d{1,3}\s*$",                         # FIX: page ranges "1-54"
    r"^\s*unit\s*[ivxlcdm\d]+\s*$",                  # bare "Unit IV"
]

def is_noise(text: str, extra_patterns: list = []) -> bool:
    for p in UNIVERSAL_NOISE_PATTERNS + extra_patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


# =========================
# 🧠 LOW VALUE FILTER
# =========================
UNIVERSAL_LOW_VALUE = [
    "acknowledgement", "preface", "foreword",
    "about the author", "about the book",
    "editorial board", "table of contents",
    "bibliography",
]

def is_low_value(text: str, extra_keywords: list = []) -> bool:
    return any(kw in text for kw in UNIVERSAL_LOW_VALUE + extra_keywords)


def is_too_short(text: str, min_words: int = 5) -> bool:
    return len(text.split()) < min_words


# =========================
# 📌 CHUNK CLASSIFIER
# =========================
UNIVERSAL_TYPE_RULES = {
    "example":    ["example", "e.g.", "for instance", "illustration"],
    "exercise":   ["exercise", "problem", "question", "activity", "task"],
    "definition": ["definition", "define", "is defined as", "refers to"],
    "theorem":    ["theorem", "lemma", "corollary", "proposition"],
    "summary":    ["summary", "in conclusion", "to summarize", "key points"],
    "derivation": ["derivation", "derive", "differentiating", "integrating"],
    "law":        ["law of", "newton's", "snell's", "ohm's", "faraday"],
}

def classify_chunk(text: str, chunk_type: str, domain_tags: dict = {}) -> str:
    if chunk_type in ("table", "listitem"):
        return chunk_type
    all_rules = {**UNIVERSAL_TYPE_RULES, **domain_tags}
    for label, keywords in all_rules.items():
        if any(kw in text for kw in keywords):
            return label
    return "concept"


# =========================
# 🔥 FILTER PIPELINE
# =========================
def filter_chunks(chunks: list, config: ParserConfig) -> list:
    filtered = []
    for ch in chunks:
        text = clean_text(ch["text"])

        if is_too_short(text, config.min_words_noise_threshold):
            continue
        if is_noise(text, config.extra_noise_patterns):
            continue
        if is_low_value(text, config.extra_low_value_keywords):
            continue

        ch["text"] = text
        ch["type"] = classify_chunk(text, ch["type"], config.domain_chunk_tags)
        filtered.append(ch)

    return filtered


# =========================
# 🚫 FRONT MATTER REMOVAL
# =========================
def remove_front_matter(chunks: list, skip: int = 0) -> list:
    return chunks[skip:] if skip > 0 else chunks


# =========================
# ✂️ SEMANTIC CHUNKING
# =========================
def semantic_chunking(chunks: list, max_words: int = 200) -> list:
    final_chunks = []

    for ch in chunks:
        text = ch["text"]
        title = ch.get("title", "")

        if ch["type"] == "table":
            final_chunks.append(ch)
            continue

        sentences = re.split(r'(?<=[.?!])\s+', text)
        current: list = []
        count = 0

        for sent in sentences:
            words = sent.split()
            if count + len(words) > max_words and current:
                final_chunks.append({
                    "text": " ".join(current),
                    "title": title,
                    "type": ch["type"],
                    "heading_level": ch.get("heading_level", 0),
                    "source": ch["source"]
                })
                current = []
                count = 0
            current.append(sent)
            count += len(words)

        if current:
            final_chunks.append({
                "text": " ".join(current),
                "title": title,
                "type": ch["type"],
                "heading_level": ch.get("heading_level", 0),
                "source": ch["source"]
            })

    return final_chunks


# =========================
# 🧠 ADD TITLE CONTEXT
# =========================
def add_title_context(chunks: list) -> list:
    enhanced = []
    for ch in chunks:
        title = ch.get("title", "")
        text = ch["text"]
        combined = f"{title}\n{text}" if title and title.lower() not in text else text
        enhanced.append({
            "text": combined,
            "type": ch["type"],
            "heading_level": ch.get("heading_level", 0),
            "source": ch["source"],
            "title": title
        })
    return enhanced


# =========================
# 🏷️ OUTPUT FILENAME BUILDER
# Derives output name from folder structure.
#
# data/raw/ncert/biology/class_11/part_1.pdf
#   → biology_class11_part1_chunks.txt
#
# Skips generic folder names (data, raw, ncert, etc.)
# Strips underscores for cleaner joining, then rejoins with _.
# =========================
def build_output_name(file_path: Path) -> str:
    skip_folders = {"data", "raw", "ncert", "processed", "output", "outputs", "."}

    meaningful = []
    for part in file_path.parts[:-1]:   # exclude filename
        clean = part.lower().replace("_", "").replace(" ", "")
        if clean not in skip_folders and not clean.startswith("."):
            meaningful.append(clean)

    stem = file_path.stem.lower().replace("_", "").replace(" ", "")
    return "_".join(meaningful + [stem])


# =========================
# 🚀 FULL PIPELINE
# =========================
def parse_pdf_pipeline(file_path: str, config: Optional[ParserConfig] = None) -> list[dict]:
    if config is None:
        config = ParserConfig()

    print("🔹 Parsing text with PyMuPDF...")
    text_chunks = parse_with_pymupdf(file_path, config)
    print(f"   ✅ {len(text_chunks)} raw text chunks")

    print("🔹 Parsing tables with pdfplumber...")
    table_chunks = parse_tables_with_pdfplumber(file_path)
    print(f"   ✅ {len(table_chunks)} table chunks")

    print("🔹 Merging...")
    merged = merge_chunks(text_chunks, table_chunks)

    print("🔹 Removing duplicates...")
    merged = remove_duplicates(merged)

    print("🔹 Removing front matter...")
    merged = remove_front_matter(merged, skip=config.front_matter_skip)

    print("🔹 Filtering noise...")
    merged = filter_chunks(merged, config)
    print(f"   ✅ {len(merged)} chunks after filtering")

    print("🔹 Semantic chunking...")
    chunks = semantic_chunking(merged, max_words=config.max_words_per_chunk)
    print(f"   ✅ {len(chunks)} final chunks after splitting")

    print("🔹 Adding title context...")
    final_chunks = add_title_context(chunks)

    return final_chunks


# =========================
# ⚙️ SUBJECT CONFIGS
# Add a new entry for each subject folder name under data/raw/ncert/
# =========================
SUBJECT_CONFIGS = {
    "biology": ParserConfig(
        max_words_per_chunk=200,
        min_words_noise_threshold=5,
        bold_as_heading=True,
        extra_noise_patterns=[
            r"reprint\s*\d{4}[-–]\d{2}",
            r"national council of educational",
        ],
        domain_chunk_tags={
            "classification": ["kingdom", "phylum", "class", "order", "family", "genus", "species"],
            "process":        ["photosynthesis", "respiration", "digestion", "reproduction"],
        }
    ),
    "physics": ParserConfig(
        max_words_per_chunk=200,
        min_words_noise_threshold=5,
        bold_as_heading=True,
        extra_noise_patterns=[
            r"reprint\s*\d{4}[-–]\d{2}",
            r"national council of educational",
        ],
        domain_chunk_tags={
            "derivation": ["derivation", "derive", "differentiating", "integrating"],
            "law":        ["law of", "newton's", "snell's", "ohm's", "faraday"],
            "formula":    ["formula", "equation", "given by", "expressed as"],
        }
    ),
    "chemistry": ParserConfig(
        max_words_per_chunk=200,
        min_words_noise_threshold=5,
        bold_as_heading=True,
        extra_noise_patterns=[
            r"reprint\s*\d{4}[-–]\d{2}",
            r"national council of educational",
        ],
        domain_chunk_tags={
            "reaction": ["reacts with", "reaction", "yields", "product"],
            "formula":  ["formula", "molecular weight", "molar mass"],
            "law":      ["law of", "avogadro", "dalton", "boyle"],
        }
    ),
    "mathematics": ParserConfig(
        max_words_per_chunk=200,
        min_words_noise_threshold=5,
        bold_as_heading=True,
        domain_chunk_tags={
            "theorem":    ["theorem", "lemma", "corollary", "proof"],
            "derivation": ["differentiating", "integrating", "derive"],
            "formula":    ["formula", "equation", "expressed as"],
        }
    ),
    # history, civics, economics, geography → generic config (no domain tags needed)
}

GENERIC_CONFIG = ParserConfig(
    max_words_per_chunk=200,
    min_words_noise_threshold=5,
    bold_as_heading=True,
    extra_noise_patterns=[
        r"reprint\s*\d{4}[-–]\d{2}",
        r"national council of educational",
    ],
)


def get_config_for_file(file_path: Path) -> ParserConfig:
    """Pick subject config based on folder name in path, fallback to generic."""
    path_str = str(file_path).lower()
    for subject, config in SUBJECT_CONFIGS.items():
        if subject in path_str:
            return config
    return GENERIC_CONFIG


# =========================
# 🧪 RUN
# =========================
if __name__ == "__main__":

    output_dir = Path("output/chunks")
    output_dir.mkdir(parents=True, exist_ok=True)

    all_files = sorted(Path("data/raw").rglob("*.pdf"))

    if not all_files:
        print("⚠️  No PDFs found in data/raw/")

    for file_path in all_files:
        print(f"\n{'='*60}")
        print(f"📄 {file_path}")
        print(f"{'='*60}")

        config = get_config_for_file(file_path)

        try:
            chunks = parse_pdf_pipeline(str(file_path), config=config)
            print(f"\n✅ Total chunks: {len(chunks)}")

            # Output filename derived from folder structure
            # e.g. data/raw/ncert/biology/class_11/part_1.pdf
            #   →  output/chunks/biology_class11_part1_chunks.txt
            output_name = build_output_name(file_path)
            txt_out = output_dir / f"{output_name}_chunks.txt"

            with open(txt_out, "w", encoding="utf-8") as f:
                for i, item in enumerate(chunks):
                    f.write(f"[{i+1}] TYPE={item['type']} | LEVEL={item['heading_level']} | SOURCE={item['source']}\n")
                    f.write(f"TITLE: {item['title']}\n")
                    f.write(f"TEXT: {item['text']}\n")
                    f.write("-" * 60 + "\n")

            print(f"💾 Saved → {txt_out}")

        except Exception as e:
            print(f"❌ Failed on {file_path.name}: {e}")