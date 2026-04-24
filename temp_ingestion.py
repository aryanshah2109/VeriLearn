from langchain_community.document_loaders import PyMuPDFLoader
import re

file_path = "data/raw/college/Computer Networks.pdf"

def fix_hyphenation(text):
    """Fix broken words: physi-\ncal → physical"""
    return re.sub(r"-\n", "", text)


def normalize_newlines(text):
    """Remove excessive newlines"""
    return re.sub(r"\n{2,}", "\n\n", text)


def is_header_footer(line):
    """Detect headers/footers WITHOUT killing real sentences"""
    line = line.strip()

    return (
        line == "•" or
        re.match(r"^\d+(\.\d+)?$", line) or     # 1.2
        re.match(r"^\d+$", line) or             # 19
        (line.isupper() and len(line.split()) <= 4)  # THE NETWORK EDGE
    )


def is_heading(line):
    """
    Strong heading detection:
    Works for:
    - Twisted-Pair Copper Wire
    - INTRODUCTION
    - 1.2 Network Edge
    """
    line = line.strip()

    if len(line) < 5 or len(line) > 80:
        return False

    return (
        line.isupper() or
        re.match(r"^\d+(\.\d+)*\s+[A-Za-z].*", line) or
        (
            line[0].isupper() and
            not line.endswith('.') and
            len(line.split()) <= 8
        )
    )


def merge_lines_safely(lines):
    """
    Merge lines WITHOUT breaking:
    - headings
    - paragraph starts
    - sentence boundaries
    """
    merged = []
    buffer = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 🚨 If heading → keep separate
        if is_heading(line):
            if buffer:
                merged.append(buffer.strip())
                buffer = ""
            merged.append(line)
            continue

        # 🚨 New paragraph (capital start after full stop)
        if buffer and buffer.endswith('.') and line[0].isupper():
            merged.append(buffer.strip())
            buffer = line
        else:
            buffer = buffer + " " + line if buffer else line

    if buffer:
        merged.append(buffer.strip())

    return merged


# -----------------------------
# MAIN PIPELINE
# -----------------------------

cleaned_docs = []

current_chapter = None
current_section = None

for doc in docs:
    text = doc.page_content

    # Step 1: Fix broken words
    text = fix_hyphenation(text)

    # Step 2: Split into raw lines
    raw_lines = text.split("\n")

    # Step 3: Remove headers/footers
    lines = [l.strip() for l in raw_lines if not is_header_footer(l)]

    # Step 4: Remove very small noise lines
    lines = [l for l in lines if len(l) > 2]

    # Step 5: Detect headings FIRST
    structured_lines = []
    for line in lines:
        if is_heading(line):
            # classify
            if line.isupper():
                current_chapter = line
            else:
                current_section = line

            structured_lines.append(("HEADING", line))
        else:
            structured_lines.append(("TEXT", line))

    # Step 6: Merge only TEXT lines safely
    final_lines = []
    temp_text_block = []

    for tag, line in structured_lines:
        if tag == "HEADING":
            # flush previous text
            if temp_text_block:
                merged = merge_lines_safely(temp_text_block)
                final_lines.extend(merged)
                temp_text_block = []

            # store heading separately (not in text)
            continue

        else:
            temp_text_block.append(line)

    if temp_text_block:
        merged = merge_lines_safely(temp_text_block)
        final_lines.extend(merged)

    # Step 7: Build clean text
    cleaned_text = "\n\n".join(final_lines)
    cleaned_text = normalize_newlines(cleaned_text)

    # Step 8: Enrich metadata
    enriched_metadata = {
        "source": doc.metadata.get("source"),
        "page": doc.metadata.get("page"),
        "book": "Computer Networks",
        "subject": "Computer Networks",
        "chapter": current_chapter,
        "section": current_section
    }

    cleaned_docs.append({
        "text": cleaned_text,
        "metadata": enriched_metadata
    })


# -----------------------------
# CHECK OUTPUT
# -----------------------------
print("CLEANED TEXT:\n")
print(cleaned_docs[45]["text"][:1000])

print("\nMETADATA:\n")
print(cleaned_docs[45]["metadata"])