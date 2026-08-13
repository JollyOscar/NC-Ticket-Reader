import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend_logging import get_logger

logger = get_logger("ocr")

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads Early Prototype/.env if present
except ImportError:
    pass  # dotenv optional; env vars can be set at system level


def _norm_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_date(raw: str) -> str:
    if not raw:
        return ""

    import datetime as dt
    current_year = dt.datetime.now().year
    century = (current_year // 100) * 100

    months = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    date_digit_map = str.maketrans("SOIliBbGZz", "5011188620")

    # Month names must match as whole words (longest-first so "april" is tried
    # before "apr"). Without a trailing \b, OCR noise like "Apri/16/26" (a
    # dropped "l" from "April") can be misparsed as month="apr" + day="i"(→1),
    # silently producing a wrong date instead of failing safely.
    month_alt = "|".join(sorted(months.keys(), key=len, reverse=True))

    # 1. Format: "April16/26", "May 11/26", "May 8 2026", "May 8 26", "June 1 26", "MAY 3 7075"
    m = re.search(
        rf"\b({month_alt})\b\s*([0-9SOIliBbGZz]{{1,2}})(?:\s*[/.-]\s*|\s+)([0-9SOIliBbGZz]{{2,4}})\b",
        raw,
        re.IGNORECASE,
    )
    if m:
        month_name = m.group(1).lower()
        month = months.get(month_name)
        if month:
            day_raw = m.group(2).translate(date_digit_map)
            yr_raw  = m.group(3).translate(date_digit_map)
            if len(yr_raw) == 4 and not (yr_raw.startswith("19") or yr_raw.startswith("20")):
                year = str(current_year)
            elif len(yr_raw) == 2:
                year = str(century + int(yr_raw))
            else:
                year = yr_raw
            if day_raw.isdigit() and year.isdigit():
                day = int(day_raw)
                if 1 <= day <= 31:
                    return f"{int(year):04d}-{month:02d}-{day:02d}"

    # 2. Format without year: "ENTERED MAY 3", "June 1", "May 8"
    m2 = re.search(rf"\b({month_alt})\b\s*([0-9SOIliBbGZz]{{1,2}})\b", raw, re.IGNORECASE)
    if m2:
        month_name = m2.group(1).lower()
        month = months.get(month_name)
        if month:
            day_raw = m2.group(2).translate(date_digit_map)
            if day_raw.isdigit():
                day = int(day_raw)
                # A bare 2-digit number right after the month is often a
                # dropped-day fragment of "Month Day/Year" (e.g. OCR misses a
                # faint day digit, leaving "June 26" meaning day=1, year=26).
                # If it matches a plausible year suffix near today, treat the
                # date as unparseable rather than silently reporting a wrong day.
                year_suffixes = {str(y)[-2:] for y in range(current_year - 2, current_year + 3)}
                is_year_like = len(day_raw) == 2 and day_raw in year_suffixes
                if 1 <= day <= 31 and not is_year_like:
                    return f"{current_year:04d}-{month:02d}-{day:02d}"

    # 3. Numeric slash format: "04/16/26" or "5/11/26"
    m3 = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", raw)
    if m3:
        mo, da, yr = int(m3.group(1)), int(m3.group(2)), m3.group(3)
        if len(yr) == 2:
            yr = str(century + int(yr))
        if 1 <= mo <= 12 and 1 <= da <= 31:
            return f"{int(yr):04d}-{mo:02d}-{da:02d}"

    return ""


# Form labels that should NOT be returned as a field value
_FORM_LABELS = re.compile(
    r"^\s*(?:GROSS|TARE|NET|DATE|MATERIAL|TRUCKER|LICENSE\s*PLATE|"
    r"SOLD\s*TO|CHARGED\s*TO|DELIVER\s*TO|JOB\s*NO|RECEIVED\s*BY|"
    r"QUARRY|WHITE|CANARY|PINK|COPY|CUSTOMER|OFFICE)\b",
    re.IGNORECASE,
)


def _clean_candidate(value: str) -> str:
    return _norm_spaces(value).strip("|:;,.\"'`[](){}")


def _is_useful_value(value: str) -> bool:
    v = _clean_candidate(value)
    if not v:
        return False
    if _FORM_LABELS.match(v):
        return False
    # Reject values that are mostly punctuation/noise
    if re.fullmatch(r"[-_./\\|:;,'`\s]+", v):
        return False
    if len(re.sub(r"[^A-Za-z0-9]", "", v)) < 2:
        return False
    # The printed 3-ply copy legend ("WHITE - CUSTOMER COPY", "CANARY -
    # TRUCKER'S COPY", "PINK - OFFICE COPY") sits directly below RECEIVED BY
    # and can be mistaken for a signature when none was written. No genuine
    # handwritten field value would ever contain the word "copy".
    if re.search(r"\bcopy\b", v, re.IGNORECASE):
        return False
    return True


# ─────────────────────────────────────────────────────────────
# Spatial extraction — uses Google Vision bounding boxes
# ─────────────────────────────────────────────────────────────

def _build_word_index(response: Any) -> List[Dict]:
    """Return all words with normalised [0-1] bounding box coordinates."""
    words: List[Dict] = []
    if not response.full_text_annotation:
        return words
    for page in response.full_text_annotation.pages:
        img_h = max(page.height, 1)
        img_w = max(page.width, 1)
        for block in page.blocks:
            for para in block.paragraphs:
                for word in para.words:
                    txt = "".join(s.text for s in word.symbols)
                    vs  = word.bounding_box.vertices
                    xs  = [v.x for v in vs]
                    ys  = [v.y for v in vs]
                    wh  = max((max(ys) - min(ys)) / img_h, 0.005)
                    words.append({
                        "text": txt,
                        "cx":   sum(xs) / 4 / img_w,
                        "cy":   sum(ys) / 4 / img_h,
                        "x0":   min(xs) / img_w,
                        "x1":   max(xs) / img_w,
                        "y0":   min(ys) / img_h,
                        "y1":   max(ys) / img_h,
                        "wh":   wh,
                    })
    return words


def _build_tesseract_word_index(data: Dict[str, List[Any]], image_size: Tuple[int, int]) -> List[Dict]:
    image_width, image_height = image_size
    words: List[Dict] = []
    for index, text in enumerate(data.get("text", [])):
        text = str(text).strip()
        if not text:
            continue
        left = int(data["left"][index])
        top = int(data["top"][index])
        width = max(int(data["width"][index]), 1)
        height = max(int(data["height"][index]), 1)
        words.append({
            "text": text,
            "cx": (left + width / 2) / max(image_width, 1),
            "cy": (top + height / 2) / max(image_height, 1),
            "x0": left / max(image_width, 1),
            "x1": (left + width) / max(image_width, 1),
            "y0": top / max(image_height, 1),
            "y1": (top + height) / max(image_height, 1),
            "wh": max(height / max(image_height, 1), 0.005),
        })
    return words


def _build_easyocr_word_index(results: List[Any], image_size: Tuple[int, int]) -> List[Dict]:
    """Convert EasyOCR detections into word-sized normalized bounding boxes."""
    image_width, image_height = image_size
    words: List[Dict] = []
    for bbox, detected_text, _confidence in results:
        text = str(detected_text or "").strip()
        if not text or not bbox:
            continue
        xs = [float(point[0]) for point in bbox]
        ys = [float(point[1]) for point in bbox]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        text_parts = text.split()
        if not text_parts:
            continue
        total_chars = max(sum(len(part) for part in text_parts), 1)
        cursor = x0
        for index, part in enumerate(text_parts):
            if index == len(text_parts) - 1:
                part_x1 = x1
            else:
                part_x1 = cursor + (x1 - x0) * len(part) / total_chars
            words.append({
                "text": part,
                "cx": (cursor + part_x1) / 2 / max(image_width, 1),
                "cy": (y0 + y1) / 2 / max(image_height, 1),
                "x0": cursor / max(image_width, 1),
                "x1": part_x1 / max(image_width, 1),
                "y0": y0 / max(image_height, 1),
                "y1": y1 / max(image_height, 1),
                "wh": max((y1 - y0) / max(image_height, 1), 0.005),
            })
            cursor = part_x1
    return words


def _spatial_find_label(words: List[Dict], *parts: str) -> Optional[Dict]:
    """
    Locate a (possibly multi-word) label by matching consecutive words.
    Single-character separator tokens (e.g. '/') between target parts are skipped.
    Returns a dict describing the label's extent, or None.
    """
    targets = [p.lower().strip("/:.,") for p in parts]
    if not targets:
        return None
    for i, w in enumerate(words):
        if w["text"].lower().strip("/:.,") != targets[0]:
            continue
        span = [w]
        j    = i + 1
        ok   = True
        for t in targets[1:]:
            found = False
            for k in range(j, min(j + 5, len(words))):
                tok = words[k]["text"].lower().strip("/:.,")
                if tok == t:
                    span.append(words[k])
                    j = k + 1
                    found = True
                    break
                if len(tok) > 1:  # non-separator token breaks the search
                    break
            if not found:
                ok = False
                break
        if ok:
            avg_wh = max(sum(s["wh"] for s in span) / len(span), 0.005)
            return {
                "cy":     sum(s["cy"] for s in span) / len(span),
                "x0":     min(s["x0"] for s in span),
                "x1":     max(s["x1"] for s in span),
                "y0":     min(s["y0"] for s in span),
                "y1":     max(s["y1"] for s in span),
                "avg_wh": avg_wh,
                "span":   span,
            }
    return None


def _spatial_find_label_any(
    words: List[Dict], variants: List[List[str]]
) -> Optional[Dict]:
    """Try each label variant in order; return the first match found."""
    for variant in variants:
        lbl = _spatial_find_label(words, *variant)
        if lbl:
            return lbl
    return None


def _spatial_collect_value(
    words: List[Dict],
    label: Optional[Dict],
    stop_labels: Optional[List[Optional[Dict]]] = None,
    max_rows_below: float = 4.0,
) -> str:
    """
    Collect words spatially adjacent to *label* (right of, or below).
    Stops before any *stop_labels* that appear below the label.
    Returns a cleaned string, or "" when nothing useful is found.
    """
    if label is None:
        return ""
    if stop_labels is None:
        stop_labels = []

    lcy    = label["cy"]
    lx1    = label["x1"]
    lwh    = label["avg_wh"]
    s_ids  = {id(s) for s in label["span"]}

    # Nearest stop boundary below this label. Use the stop label's own TOP
    # edge (y0), not its average cy: a two-line printed label (e.g. "SOLD
    # TO" / "CHARGED TO") has an average cy that sinks toward the midpoint
    # between its two lines — right where a handwritten value answering
    # that label typically sits — which let a field ABOVE reach down and
    # steal half of that value (e.g. TRUCKER grabbing "fulton" off of the
    # SOLD TO/CHARGED TO row). The label's top edge is the one boundary
    # that's always safely above its own handwritten answer.
    below_stops = [sl["y0"] for sl in stop_labels if sl and sl["y0"] > lcy + lwh * 0.5]
    max_cy = min(below_stops) if below_stops else lcy + lwh * max_rows_below
    max_cy = min(max_cy, lcy + lwh * max_rows_below)

    same_row: List[Dict] = []
    below: List[Dict] = []
    same_ids: set = set()
    for w in words:
        if id(w) in s_ids:
            continue
        # Pure-punctuation tokens (a stray "/" from a label like "SOLD TO/",
        # a trailing ".") carry no value information, but if let through
        # they can sit right at the edge of the tight same-row window and
        # act as a bridging anchor that chains an entirely unrelated row
        # (e.g. the field ABOVE's value) into this field via the drift-
        # expansion pass below. Skip them as candidates entirely.
        if not re.search(r"[A-Za-z0-9]", w["text"]):
            continue
        dy = w["cy"] - lcy
        # Same-row values are written at-or-below the printed label's own
        # baseline (never meaningfully above it) — on densely packed tickets
        # a symmetric tolerance here reaches upward into the PREVIOUS
        # handwritten line (e.g. picking up the tail end of the TRUCKER
        # value as if it were on the SOLD TO row), so only allow a small
        # negative margin for bounding-box jitter, not a full row's worth.
        if -lwh * 0.4 <= dy <= lwh * 1.4 and w["x0"] >= lx1 - 0.03:   # same row, right
            same_row.append(w)
            same_ids.add(id(w))
        elif lwh * 0.3 < dy and w["cy"] <= max_cy:              # below, bounded
            below.append(w)

    # Second pass: pull in words that visually continue an already-confirmed
    # same-row word (e.g. handwriting that slants upward across the row, so
    # its later words end up above the tight vertical window used above).
    # Anchored to a real same-row match already found — never invents a row
    # out of nothing — so it can't reach into an unrelated field's value.
    below_ids = {id(w) for w in below}
    changed = True
    while same_row and changed:
        changed = False
        for w in words:
            if id(w) in s_ids or id(w) in same_ids or id(w) in below_ids:
                continue
            if not re.search(r"[A-Za-z0-9]", w["text"]):
                continue
            if w["x0"] < lx1 - 0.03:
                continue
            if any(abs(w["cy"] - r["cy"]) < lwh * 0.9 for r in same_row):
                same_row.append(w)
                same_ids.add(id(w))
                changed = True

    if not same_row and not below:
        return ""

    # Group ALL candidates into rows together (so a value spanning the
    # same-row/below-row boundary, e.g. wrapped handwriting, still merges
    # into one row) but remember which rows contain a genuine same-row word.
    all_candidates = sorted(same_row + below, key=lambda c: (c["cy"], c["cx"]))
    rows: List[List[Dict]] = []
    for c in all_candidates:
        # Compare against the most-recently-added word (not the row's first
        # word) so a row can accumulate gradual cy drift across several
        # words (common with slanted handwriting) without prematurely
        # splitting into two separate rows.
        if rows and abs(c["cy"] - rows[-1][-1]["cy"]) < lwh * 0.9:
            rows[-1].append(c)
        else:
            rows.append([c])

    # A row that contains an unrelated line above/below the label can still
    # fall within the "same row" vertical tolerance (e.g. a letterhead
    # phone/fax line close to the "DATE" row). Try rows that actually touch
    # the label's own vertical center first (closest first), then fall
    # through to rows further below in natural top-to-bottom order.
    def _row_sort_key(row: List[Dict]):
        row_cy = sum(w["cy"] for w in row) / len(row)
        is_same_row = any(id(w) in same_ids for w in row)
        return (0 if is_same_row else 1, abs(row_cy - lcy) if is_same_row else row_cy)

    rows.sort(key=_row_sort_key)

    for row in rows:
        row_text = " ".join(w["text"] for w in sorted(row, key=lambda x: x["cx"]))
        cleaned  = _clean_candidate(row_text)
        if not cleaned:
            continue
        # A merged row can begin with a leftover printed label fragment
        # (e.g. a second label line like "CHARGED TO" that wasn't part of
        # the label we searched for) immediately followed by the real
        # handwritten value on that same visual row. Strip just that
        # leading fragment instead of discarding the whole row.
        candidate = _FORM_LABELS.sub("", cleaned).strip(" |:;,.-/") or cleaned
        if _FORM_LABELS.match(candidate):
            continue
        if _is_useful_value(candidate):
            return candidate

    return ""


# ─────────────────────────────────────────────────────────────
# Text-based (regex) extraction — used as fallback
# ─────────────────────────────────────────────────────────────

def _extract_line(text: str, label: str) -> str:
    """Return the value for a printed label, checking the same line then the
    next non-label line (tickets often put the handwritten value below the label)."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not re.search(label, line, flags=re.IGNORECASE):
            continue
        # Value on the same line (text after the label)
        m = re.search(rf"(?:{label})\s*[:/.]?\s*(.+)", line, flags=re.IGNORECASE)
        if m:
            val = _clean_candidate(m.group(1))
            if _is_useful_value(val):
                return val
        # Value on the next non-empty, non-label line
        for j in range(i + 1, min(i + 7, len(lines))):
            nxt = _clean_candidate(lines[j])
            if not nxt:
                continue
            if _FORM_LABELS.match(nxt):
                break
            if _is_useful_value(nxt):
                return nxt
    return ""


def _extract_between_labels(text: str, label: str, stop_labels: Tuple[str, ...]) -> str:
    """Extract value from the region after a label until one of stop labels appears."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not re.search(label, line, flags=re.IGNORECASE):
            continue

        same_line = re.search(rf"(?:{label})\s*[:/.]?\s*(.+)", line, flags=re.IGNORECASE)
        if same_line:
            candidate = _clean_candidate(same_line.group(1))
            if _is_useful_value(candidate):
                return candidate

        for j in range(i + 1, min(i + 10, len(lines))):
            candidate = _clean_candidate(lines[j])
            if not candidate:
                continue
            if any(re.search(stop, candidate, flags=re.IGNORECASE) for stop in stop_labels):
                break
            if _is_useful_value(candidate):
                return candidate
    return ""


def _digits_only(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


# Common OCR character substitutions in numeric contexts
_DIGIT_CHAR_MAP = str.maketrans("SOIliBbGZz", "5011188620")


def _extract_weight(text: str, label: str) -> str:
    """Extract a weight value (large integer) near a label.
    Handles OCR digit-character confusion (S→5, O→0, I→1, Z→2 etc.) and
    comma/space formatting ('15, 200' → '15200')."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        lm = re.search(label, line, flags=re.IGNORECASE)
        if not lm:
            continue
        # Only take text AFTER the label on the same line, then next 3 lines
        # (avoids parsing the label word itself as a number, e.g. GROSS→6055)
        candidates = [line[lm.end():]] + lines[i + 1 : min(i + 4, len(lines))]
        for candidate in candidates:
            if _FORM_LABELS.match(candidate.strip()):
                continue  # skip lines that are themselves labels
            stripped = re.sub(r"[^\dSOIliBbGZz,\s]", " ", candidate)
            fixed = stripped.translate(_DIGIT_CHAR_MAP)
            # Collapse comma/space-separated digit groups: '15, 200' → '15200'
            merged = re.sub(r"(\d)\s*,?\s*(\d{3})\b", r"\1\2", fixed)
            for m in re.finditer(r"\b(\d{4,6})\b", merged):
                val = int(m.group(1))
                if val >= 1000:
                    return str(val)
    return ""


def _extract_weights_structured(text: str) -> Tuple[str, str, str]:
    """Extract GROSS, TARE, NET by bounding each search zone to stop at the
    next weight label.  Prevents a readable NET value being grabbed for TARE
    when TARE itself is blank (ticket 2 layout: GROSS / TARE / <blank> / NET / value)."""
    lines = text.split("\n")

    # Find first line index for each label
    label_pos: Dict[str, int] = {}
    for i, line in enumerate(lines):
        for lbl in ("GROSS", "TARE", "NET"):
            if lbl not in label_pos and re.search(lbl, line, flags=re.IGNORECASE):
                label_pos[lbl] = i

    results: Dict[str, str] = {}
    order = [l for l in ("GROSS", "TARE", "NET") if l in label_pos]

    for idx, label in enumerate(order):
        start = label_pos[label]
        # Don't search past the next weight label (prevents cross-label bleeding)
        zone_end = label_pos[order[idx + 1]] if idx + 1 < len(order) else len(lines)
        zone_end = min(zone_end, start + 4)  # cap at 4 lines regardless

        label_line = lines[start]
        lm = re.search(label, label_line, flags=re.IGNORECASE)
        if not lm:
            continue
        candidates = [label_line[lm.end():]] + lines[start + 1 : zone_end]

        for candidate in candidates:
            stripped = re.sub(r"[^\dSOIliBbGZz,\s]", " ", candidate)
            fixed = stripped.translate(_DIGIT_CHAR_MAP)
            merged = re.sub(r"(\d)\s*,?\s*(\d{3})\b", r"\1\2", fixed)
            for m in re.finditer(r"\b(\d{4,6})\b", merged):
                val = int(m.group(1))
                if val >= 1000:
                    results[label] = str(val)
                    break
            if label in results:
                break

    return results.get("GROSS", ""), results.get("TARE", ""), results.get("NET", "")


def _extract_ticket_number(text: str) -> str:
    """Ticket numbers are printed on the form (e.g. '07173', '0355').
    Try to find a 4-6 digit sequence near a 'No.' label first, then fall back
    to the last standalone 4-6 digit group in the text."""
    m = re.search(r"(?:No\.?|#|Ticket\s*(?:No\.?|#)?)\s*[:\s]?\s*(\d{4,6})\b", text, re.IGNORECASE)
    if m:
        return m.group(1)
    candidates = re.findall(r"\b(\d{4,6})\b", text)
    return candidates[-1] if candidates else ""


def _spatial_find_ticket_id(words: List[Dict], lbl_recv: Optional[Dict]) -> str:
    """The printed ticket number box sits on the same printed row as
    'RECEIVED BY' (bottom-left number box, bottom-right signature box),
    just to its left. Anchoring on that label (rather than an absolute
    image position) stays robust across different crops/scans, unlike a
    fixed-coordinate guess which breaks when photos are cropped differently."""
    if lbl_recv is None:
        return ""
    rcy = lbl_recv["cy"]
    rx0 = lbl_recv["x0"]
    tol = max(lbl_recv["avg_wh"] * 1.5, 0.02)
    candidates = [
        w for w in words
        if re.fullmatch(r"\d{3,6}", w["text"].strip("."))
        and abs(w["cy"] - rcy) <= tol
        and w["x1"] <= rx0 + 0.03
    ]
    if not candidates:
        return ""
    candidates.sort(key=lambda w: abs(w["cy"] - rcy))
    return candidates[0]["text"].strip(".")


def _extract_quarry_name(text: str) -> str:
    for line in text.splitlines():
        if not re.search(r"\bquarry\b", line, re.IGNORECASE):
            continue
        value = re.sub(r"\bquarry\b", "", line, flags=re.IGNORECASE)
        value = _clean_candidate(value)
        if _is_useful_value(value):
            return value.title()
    return ""


def parse_ticket_text(raw_text: str) -> Dict[str, str]:
    text = raw_text or ""

    quarry_name = _extract_quarry_name(text)

    # Use whole-text date search first; label-line OCR can be merged/noisy.
    ticket_date = _normalize_date(text) or _normalize_date(_extract_line(text, "Date"))
    ticket_id = _extract_ticket_number(text)

    gross, tare, net = _extract_weights_structured(text)
    if ticket_id:
        gross = "" if gross == ticket_id else gross
        tare = "" if tare == ticket_id else tare
        net = "" if net == ticket_id else net

    truck_or_plate = _extract_between_labels(
        text,
        "License Plate",
        ("Trucker", "Sold\\s*To", "Charged\\s*To", "Material", "Gross", "Tare", "Net"),
    )
    if "quarry" in truck_or_plate.lower():
        truck_or_plate = ""

    trucker = _extract_between_labels(
        text,
        "Trucker",
        ("Sold\\s*To", "Charged\\s*To", "Material", "Gross", "Tare", "Net", "License Plate"),
    )
    if "copy" in trucker.lower():
        trucker = ""

    sold_to = (
        _extract_between_labels(
            text,
            r"Sold\s*To\s*/\s*Charged\s*To",
            ("Deliver\\s*To", "Material", "Gross", "Tare", "Net", "License Plate", "Trucker"),
        )
        or _extract_between_labels(
            text,
            "Sold To",
            ("Charged\\s*To", "Deliver\\s*To", "Material", "Gross", "Tare", "Net"),
        )
        or _extract_between_labels(
            text,
            "Charged To",
            ("Deliver\\s*To", "Material", "Gross", "Tare", "Net"),
        )
    )
    if sold_to in {"/", "//"}:
        sold_to = ""

    deliver_to = _extract_between_labels(
        text,
        "Deliver To",
        ("Material", "Gross", "Tare", "Net", "License Plate", "Trucker"),
    )
    material_type = _extract_between_labels(
        text,
        "Material",
        ("Gross", "Tare", "Net", "License Plate", "Trucker", "Deliver\\s*To", "Sold\\s*To", "Charged\\s*To"),
    )
    if material_type and material_type.replace(",", "").isdigit():
        material_type = ""

    # If OCR likely put a customer name into material and Sold To is empty,
    # promote that value to Sold To.
    if (
        not sold_to
        and material_type
        and re.fullmatch(r"[A-Za-z][A-Za-z\s'.-]{4,}", material_type)
        and "quarry" not in material_type.lower()
    ):
        sold_to = material_type
        material_type = ""

    # Quarry header text is not a deliver-to value on these tickets.
    if deliver_to and "quarry" in deliver_to.lower():
        deliver_to = ""

    job_no = _extract_line(text, "Job No")
    if job_no in {".", ",", "-"} or "quarry" in job_no.lower() or "copy" in job_no.lower():
        job_no = ""

    received_by = _extract_line(text, "Received By") or _extract_line(text, "Recieved By")

    # Infer one missing weight when the other two are present and plausible.
    if gross.isdigit() and net.isdigit() and not tare:
        diff = int(gross) - int(net)
        if diff > 0:
            tare = str(diff)
    elif gross.isdigit() and tare.isdigit() and not net:
        diff = int(gross) - int(tare)
        if diff > 0:
            net = str(diff)

    return {
        "ticket_id": ticket_id,
        "ticket_date": ticket_date,
        "job_no": job_no,
        "quarry_name": quarry_name,
        "truck_or_plate": truck_or_plate,
        "trucker": trucker,
        "sold_to": sold_to,
        "deliver_to": deliver_to,
        "material_type": material_type,
        "received_by": received_by,
        "gross_weight": gross,
        "tare_weight": tare,
        "net_weight": net,
        "source_site": quarry_name,
        "destination_site": deliver_to,
    }


def _extract_with_google_vision(image_path: Path) -> Tuple[Dict[str, str], float]:
    from google.cloud import vision

    logger.info("google_vision_request_start image=%s", image_path)
    client = vision.ImageAnnotatorClient()
    content = image_path.read_bytes()
    image = vision.Image(content=content)
    detect_fn = getattr(client, "document_text_detection")
    response = detect_fn(image=image)

    if response.error.message:
        raise RuntimeError(response.error.message)

    # ── Dynamic Per-Ticket Auto-Orientation Solver ───────────────────────────
    # Detects if the ticket header (NOVA, QUARRY, etc.) is at the bottom or
    # side of the image (indicating upside-down or sideways scan) and rotates
    # the image so the header is at the top before re-sending to Vision.
    if response.text_annotations and len(response.text_annotations) > 1:
        try:
            from PIL import Image as PilImage
            # Fully load pixel data and release the file handle (Windows lock fix)
            pil_img = PilImage.open(image_path)
            pil_img.load()  # forces full pixel decode into memory
            w_img, h_img = pil_img.width, pil_img.height

            needs_rotation = None
            for anno in response.text_annotations[1:]:
                w_str = anno.description.upper()
                if w_str in ["NOVA", "CONSTRUCTION", "QUARRY", "ANTIGONISH"]:
                    verts = anno.bounding_poly.vertices
                    if verts:
                        avg_x = sum(v.x for v in verts) / len(verts) / max(1, w_img)
                        avg_y = sum(v.y for v in verts) / len(verts) / max(1, h_img)
                        logger.info(
                            "auto_orient_keyword word=%s avg_x=%.2f avg_y=%.2f image=%s",
                            w_str, avg_x, avg_y, image_path.name,
                        )
                        if avg_y > 0.60:
                            needs_rotation = 180  # header at bottom → upside down
                        elif avg_x > 0.65:
                            # Header at right edge → page was physically rotated
                            # 90° clockwise from upright, so undo with a 90° CCW
                            # turn. PIL's rotate() angle is CCW, so this is rotate(90),
                            # NOT rotate(270) (which would double the error to 180°).
                            needs_rotation = 90
                        elif avg_x < 0.35 and avg_y > 0.35:
                            # Header at left edge → page was physically rotated
                            # 90° counter-clockwise from upright, so undo with a
                            # 90° CW turn, i.e. rotate(270) in PIL's CCW convention.
                            needs_rotation = 270
                        break

            if needs_rotation:
                logger.info("auto_orient_applied image=%s angle=%d", image_path.name, needs_rotation)
                rotated_img = pil_img.rotate(needs_rotation, expand=True)
                # Close original handle explicitly before overwriting on disk
                pil_img.close()
                rotated_img.convert("RGB").save(image_path, format="JPEG")
                rotated_img.close()
                # Re-read the corrected image for a second Vision pass
                content = image_path.read_bytes()
                image = vision.Image(content=content)
                response = detect_fn(image=image)
                logger.info("auto_orient_resent image=%s", image_path.name)
            else:
                pil_img.close()
        except Exception as o_exc:
            logger.warning("auto_orient_failed image=%s error=%s", image_path.name, o_exc)

    raw_text = response.full_text_annotation.text if response.full_text_annotation else ""
    logger.info(
        "google_vision_raw_text image=%s chars=%d first_800=%s",
        image_path.name, len(raw_text),
        raw_text[:800].replace("\n", " | "),
    )

    # ── Build spatial word index ───────────────────────────────────────────────
    words = _build_word_index(response)

    # ── Locate printed labels ──────────────────────────────────────────────────
    lbl_date    = _spatial_find_label_any(words, [["date"]])
    lbl_job     = _spatial_find_label_any(words, [["job", "no"], ["job", "no."]])
    lbl_plate   = _spatial_find_label_any(words, [["license", "plate"], ["license"]])
    lbl_trucker = _spatial_find_label_any(words, [["trucker"]])
    lbl_sold    = _spatial_find_label_any(words, [
        ["sold", "to", "charged", "to"],
        ["sold", "to"],
        ["charged", "to"],
    ])
    lbl_deliver  = _spatial_find_label_any(words, [["deliver", "to"]])
    lbl_material = _spatial_find_label_any(words, [["material"]])
    lbl_gross    = _spatial_find_label_any(words, [["gross"]])
    lbl_tare     = _spatial_find_label_any(words, [["tare"]])
    lbl_net      = _spatial_find_label_any(words, [["net"]])
    lbl_recv     = _spatial_find_label_any(words, [["received", "by"], ["recieved", "by"]])

    # ── Extract values spatially ───────────────────────────────────────────────
    date_raw      = _spatial_collect_value(words, lbl_date,    [lbl_job, lbl_plate])
    job_no        = _spatial_collect_value(words, lbl_job,     [lbl_plate, lbl_trucker])
    truck_or_plate = _spatial_collect_value(words, lbl_plate,  [lbl_trucker, lbl_sold])
    trucker       = _spatial_collect_value(words, lbl_trucker, [lbl_sold, lbl_deliver])
    sold_to       = _spatial_collect_value(words, lbl_sold,    [lbl_deliver, lbl_material])
    deliver_to    = _spatial_collect_value(words, lbl_deliver, [lbl_material, lbl_gross])
    material_type = _spatial_collect_value(words, lbl_material,[lbl_gross, lbl_tare])
    received_by   = _spatial_collect_value(words, lbl_recv)

    # ── Ticket-level fields from text ──────────────────────────────────────────
    ticket_id = _spatial_find_ticket_id(words, lbl_recv) or _extract_ticket_number(raw_text)

    # ── Intelligent Weight Solver ──────────────────────────────────────────────
    def _solve_weights(raw_text: str, ticket_id: str) -> Tuple[str, str, str]:
        nums = []

        # Dynamically parse letterhead region for phone, fax, P.O. box, address, and year digits
        header_blacklist = set()
        header_lines = raw_text.split("\n")[:12]
        for line in header_lines:
            if any(kw in line.lower() for kw in ("phone", "fax", "box", "p.o.", "tel", "zip", "st", "road", "ave", "hwy", "entered")):
                for m in re.finditer(r"\b\d+\b", line):
                    header_blacklist.add(int(m.group(0)))

        import datetime as dt
        curr_yr = dt.datetime.now().year
        for yr in range(curr_yr - 2, curr_yr + 3):
            header_blacklist.add(yr)

        # Check for Tonne patterns ("14,000 Tonne", "15 T", "15 Tonne")
        for m in re.finditer(r"\b(\d{1,2})\s*(?:T|Tonne|Tonnes)\b", raw_text, re.IGNORECASE):
            val = int(m.group(1)) * 1000
            if 1000 <= val <= 300000 and val not in nums and val not in header_blacklist:
                nums.append(val)

        # Standard weight numbers
        for m in re.finditer(r"\b(\d{1,3}(?:[,\s]\d{3})+|\d{4,6})\b", raw_text):
            cleaned = re.sub(r"[^\d]", "", m.group(1))
            if cleaned.isdigit():
                val = int(cleaned)
                if 1000 <= val <= 300000 and val not in nums and val not in header_blacklist:
                    nums.append(val)

        text_g, text_t, text_n = _extract_weights_structured(raw_text)

        # Exclude ticket ID if present in nums or text fallbacks
        if ticket_id and re.sub(r"[^\d]", "", ticket_id).isdigit():
            tid_num = int(re.sub(r"[^\d]", "", ticket_id))
            nums = [n for n in nums if n != tid_num]
            if text_g and text_g.isdigit() and int(text_g) == tid_num: text_g = ""
            if text_t and text_t.isdigit() and int(text_t) == tid_num: text_t = ""
            if text_n and text_n.isdigit() and int(text_n) == tid_num: text_n = ""

        # Solve weight triples if at least 2 numbers exist
        if len(nums) >= 3:
            nums.sort(reverse=True)
            g = nums[0]
            for i in range(1, len(nums)):
                for j in range(i + 1, len(nums)):
                    if g == nums[i] + nums[j]:
                        return str(g), str(nums[j]), str(nums[i])

        if len(nums) == 2:
            nums.sort(reverse=True)
            g = nums[0]
            n = nums[1]
            if g > n:
                return str(g), str(g - n), str(n)

        # Fallback to structured text extractions
        g_out = text_g if text_g and text_g != ticket_id else (str(nums[0]) if nums else "")
        t_out = text_t if text_t and text_t != ticket_id else ""
        n_out = text_n if text_n and text_n != ticket_id else ""

        if g_out.isdigit() and t_out.isdigit() and not n_out:
            diff = int(g_out) - int(t_out)
            if diff > 0: n_out = str(diff)
        elif g_out.isdigit() and n_out.isdigit() and not t_out:
            diff = int(g_out) - int(n_out)
            if diff > 0: t_out = str(diff)

        return g_out, t_out, n_out

    gross, tare, net = _solve_weights(raw_text, ticket_id)
    quarry_name = _extract_quarry_name(raw_text)

    # ── Date normalisation ─────────────────────────────────────────────────────
    # Try spatial result first, then scan entire raw text as fallback
    ticket_date = _normalize_date(date_raw) or _normalize_date(raw_text)

    # ── Post-processing field sanitization ────────────────────────────────────
    def _strip_boilerplate(val: str, keep_digit_runs: bool = False) -> str:
        if not val:
            return ""
        s = val
        noise_patterns = [
            r"\bNOVA\b", r"\bCONSTRUCTION\b", r"\bPHONE\b", r"\bFAX\b", r"\bLICENSE\b",
            r"\bPLATE\b", r"\bTRUCKER\b", r"\bSOLD\b", r"\bDELIVER\b", r"\bCHARGED\b",
            r"\bMATERIAL\b", r"\bGROSS\b", r"\bTARE\b", r"\bNET\b", r"\bJOB\b",
            r"\bCUSTOMER\b", r"\bCOPY\b", r"\bOFFICE\b", r"\bCANARY\b", r"\bWHITE\b",
            r"\bPINK\b", r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
        ]
        if not keep_digit_runs:
            # A bare 5-6 digit run is usually another field's number (ticket
            # ID/job no.) bleeding into this one — but a license plate IS
            # often just digits, so this pattern must not apply to it.
            noise_patterns += [r"\b07\d{3}\b", r"\b\d{5,6}\b"]
        for pat in noise_patterns:
            s = re.sub(pat, "", s, flags=re.IGNORECASE)
        s = _norm_spaces(s).strip(" |:;,.-/")
        return s if len(s) >= 2 else ""

    sold_to       = _strip_boilerplate(sold_to)
    deliver_to    = _strip_boilerplate(deliver_to)
    material_type = _strip_boilerplate(material_type)
    trucker       = _strip_boilerplate(trucker)
    truck_or_plate = _strip_boilerplate(truck_or_plate, keep_digit_runs=True)

    if truck_or_plate and "quarry" in truck_or_plate.lower():
        truck_or_plate = ""
    if "copy" in trucker.lower() or "quarry" in trucker.lower():
        trucker = ""
    if sold_to in {"/", "//"}:
        sold_to = ""
    # Reject material that is clearly noise: all digits, too short, or pre-label text
    if material_type:
        stripped_mat = material_type.replace(",", "").replace(" ", "")
        if stripped_mat.isdigit() or len(material_type.strip()) < 4:
            material_type = ""
    # If material_type appears in the raw text BEFORE the MATERIAL label,
    # it is printed header text, not a handwritten value → discard it.
    if material_type:
        mat_pos = raw_text.lower().find(material_type.lower())
        lbl_pos = raw_text.lower().find("material")
        if mat_pos != -1 and lbl_pos != -1 and mat_pos < lbl_pos:
            material_type = ""
    # Strip deliver_to only when it is a bare quarry header with no address markers
    if deliver_to and "quarry" in deliver_to.lower():
        deliver_to = ""
    if deliver_to:
        has_addr = bool(re.search(
            r"\b(?:rd|road|st|street|ave|avenue|dr|drive|rr|route|hwy|lane|#|\d)",
            deliver_to, re.IGNORECASE
        ))
        has_quarry_marker = bool(re.search(r"\bquarry\b", deliver_to, re.IGNORECASE))
        if has_quarry_marker and not has_addr:
            deliver_to = ""
        # Strip bare directional residue with no address content
        # "Point Rd " passes (has "rd") — keep it
        # "Long Point" with no road markers — strip it
        elif not has_addr and len(re.sub(r"[^A-Za-z0-9]", "", deliver_to)) < 6:
            deliver_to = ""
    if job_no and ("quarry" in job_no.lower() or "copy" in job_no.lower()
                    or job_no in {".", ",", "-"}
                    or re.search(r"[A-Za-z]{3,}", job_no)):   # month name = date leaked in
        job_no = ""

    # If OCR placed a customer name in material and sold_to is still empty, promote it
    if not sold_to and material_type and re.fullmatch(r"[A-Za-z][A-Za-z\s'.\-]{3,}", material_type):
        if "quarry" not in material_type.lower():
            sold_to = material_type
            material_type = ""

    # received_by should not be a standalone number (ticket-id bleed)
    if received_by and received_by.strip().isdigit():
        received_by = ""

    # Normalise license plate: strip OCR noise (only keep standard plate chars)
    if truck_or_plate:
        truck_or_plate = re.sub(r"[^A-Z0-9\-]", "", truck_or_plate.upper())
        if len(truck_or_plate) < 3:
            truck_or_plate = ""

    # Weight integrity: gross = tare + net is the only valid constraint.
    # Infer a missing third value when the other two are present and consistent.
    if gross.isdigit() and tare.isdigit() and net.isdigit():
        g, ta, ne = int(gross), int(tare), int(net)
        # Structured text extractor sometimes returns the same number for tare
        # and net when tare is blank on the physical ticket (column-read artifact).
        # In that case infer the real tare from gross − net.
        if ta == ne and g > ne:
            tare = str(g - ne)
    elif gross.isdigit() and net.isdigit() and not tare:
        diff = int(gross) - int(net)
        if diff > 0:
            tare = str(diff)
    elif gross.isdigit() and tare.isdigit() and not net:
        diff = int(gross) - int(tare)
        if diff > 0:
            net = str(diff)

    # ── Confidence ────────────────────────────────────────────────────────────
    confidences = []
    if response.full_text_annotation:
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        if hasattr(word, "confidence"):
                            confidences.append(float(word.confidence))
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    logger.info(
        "google_vision_request_success image=%s avg_conf=%.2f ticket_id=%s date=%s sold_to=%s plate=%s trucker=%s",
        image_path.name, avg_conf, ticket_id, ticket_date, sold_to, truck_or_plate, trucker,
    )

    parsed = {
        "ticket_id":    ticket_id,
        "ticket_date":  ticket_date,
        "job_no":       job_no,
        "quarry_name":  quarry_name,
        "truck_or_plate": truck_or_plate,
        "trucker":      trucker,
        "sold_to":      sold_to,
        "deliver_to":   deliver_to,
        "material_type": material_type,
        "received_by":  received_by,
        "gross_weight": gross,
        "tare_weight":  tare,
        "net_weight":   net,
        "source_site":  quarry_name,
        "destination_site": deliver_to,
        "__raw_text":   raw_text,
    }
    return parsed, round(avg_conf, 2)


def _configure_tesseract_cmd() -> Optional[str]:
    """Use the active system Tesseract binary, falling back to Windows installs."""
    detected = shutil.which("tesseract")
    if detected:
        return detected

    windows_default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if windows_default.exists():
        return str(windows_default)

    return None


def _preprocess_for_ocr(img: Any) -> Any:
    """Normalize ticket images without relying on document-specific content."""
    from PIL import Image as PilImage, ImageEnhance, ImageFilter, ImageOps

    if hasattr(img, "mode") and img.mode == "RGB":
        r, g, b = img.split()
        img = ImageOps.exif_transpose(g)
    else:
        img = ImageOps.exif_transpose(img).convert("L")

    max_long_side = 3200
    min_short_side = 1400
    w, h = img.size
    long_side = max(w, h)
    short_side = min(w, h)
    if long_side > max_long_side:
        scale = max_long_side / long_side
        resample = getattr(PilImage, "LANCZOS", 3)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), resample)
    elif short_side < min_short_side:
        scale = min_short_side / short_side
        resample = getattr(PilImage, "LANCZOS", 3)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), resample)

    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3))

    return img


def _parsed_field_score(parsed: Dict[str, str]) -> int:
    fields = (
        "ticket_id", "ticket_date", "job_no", "quarry_name", "truck_or_plate",
        "trucker", "sold_to", "deliver_to", "material_type", "received_by",
        "gross_weight", "tare_weight", "net_weight",
    )
    score = sum(bool(str(parsed.get(field, "")).strip()) for field in fields)
    gross = parsed.get("gross_weight", "")
    tare = parsed.get("tare_weight", "")
    net = parsed.get("net_weight", "")
    if gross.isdigit() and tare.isdigit() and net.isdigit() and int(gross) == int(tare) + int(net):
        score += 3
    return score


_FORM_LABEL_PATTERNS = (
    r"\bdate\b", r"\bjob\s*no\b", r"\blicense\b", r"\btrucker\b",
    r"\bsold\s*to\b", r"\bdeliver\s*to\b", r"\bmaterial\b",
    r"\bgross\b", r"\btare\b", r"\bnet\b", r"\breceived\s*by\b",
)


def _form_label_hits(raw_text: str) -> int:
    return sum(bool(re.search(pattern, raw_text, re.IGNORECASE)) for pattern in _FORM_LABEL_PATTERNS)


def _tesseract_candidate_score(raw_text: str, parsed: Dict[str, str]) -> int:
    """Favor orientations that recognize both the form structure and its values."""
    return _parsed_field_score(parsed) * 100 + _form_label_hits(raw_text) * 10


def _select_tesseract_candidate(image: Any, read_text: Any) -> Tuple[Any, str, Dict[str, str], int, int]:
    """Run sparse-text OCR in each cardinal orientation and keep the best form read."""
    best: Optional[Tuple[Any, str, Dict[str, str], int, int]] = None
    for angle in (0, 90, 180, 270):
        candidate = image if angle == 0 else image.rotate(angle, expand=True)
        prepared = _preprocess_for_ocr(candidate)
        raw_text = read_text(prepared, angle)
        parsed = parse_ticket_text(raw_text)
        score = _tesseract_candidate_score(raw_text, parsed)
        if best is None or score > best[3]:
            best = (prepared, raw_text, parsed, score, angle)

    if best is None:
        raise RuntimeError("No Tesseract orientation candidates were generated.")
    return best


def _persist_upright_image(image_path: Path, source_image: Any, angle: int) -> None:
    """Store the selected orientation so the review image matches the OCR layout."""
    if angle == 0:
        return
    from PIL import ImageOps

    upright = ImageOps.exif_transpose(source_image).rotate(angle, expand=True)
    try:
        if image_path.suffix.lower() == ".png":
            upright.save(image_path, format="PNG")
        else:
            upright.convert("RGB").save(image_path, format="JPEG", quality=95)
    finally:
        upright.close()


def _extract_spatial_fields(words: List[Dict]) -> Dict[str, str]:
    labels = {
        "job_no": _spatial_find_label_any(words, [["job", "no"], ["job", "no."]]),
        "truck_or_plate": _spatial_find_label_any(words, [["license", "plate"], ["license"]]),
        "trucker": _spatial_find_label_any(words, [["trucker"]]),
        "sold_to": _spatial_find_label_any(words, [["sold", "to"], ["charged", "to"]]),
        "deliver_to": _spatial_find_label_any(words, [["deliver", "to"]]),
        "material_type": _spatial_find_label_any(words, [["material"]]),
        "received_by": _spatial_find_label_any(words, [["received", "by"], ["recieved", "by"]]),
    }
    values = {
        "job_no": _spatial_collect_value(words, labels["job_no"], [labels["truck_or_plate"], labels["trucker"]]),
        "truck_or_plate": _spatial_collect_value(words, labels["truck_or_plate"], [labels["trucker"], labels["sold_to"]]),
        "trucker": _spatial_collect_value(words, labels["trucker"], [labels["sold_to"], labels["deliver_to"]]),
        "sold_to": _spatial_collect_value(words, labels["sold_to"], [labels["deliver_to"], labels["material_type"]]),
        "deliver_to": _spatial_collect_value(words, labels["deliver_to"], [labels["material_type"]]),
        "material_type": _spatial_collect_value(words, labels["material_type"]),
        "received_by": _spatial_collect_value(words, labels["received_by"]),
    }
    if re.search(r"\b(?:quarry|copy)\b", values["job_no"], re.IGNORECASE):
        values["job_no"] = ""
    return values


def _extract_tesseract_spatial_fields(data: Dict[str, List[Any]], image_size: Tuple[int, int]) -> Dict[str, str]:
    return _extract_spatial_fields(_build_tesseract_word_index(data, image_size))


def _sanitize_untrusted_fields(parsed: Dict[str, str]) -> None:
    job_no = parsed.get("job_no", "")
    if re.search(r"\b(?:quarry|copy)\b", job_no, re.IGNORECASE):
        parsed["job_no"] = ""

    ticket_id = parsed.get("ticket_id", "")
    ticket_number = re.sub(r"[^\d]", "", ticket_id)
    for field in ("gross_weight", "tare_weight", "net_weight"):
        value_number = re.sub(r"[^\d]", "", str(parsed.get(field, "")))
        if ticket_number and value_number and int(value_number) == int(ticket_number):
            parsed[field] = ""
    received_number = re.sub(r"[^\d]", "", str(parsed.get("received_by", "")))
    if ticket_id and received_number == ticket_number:
        parsed["received_by"] = ""

    for field in ("deliver_to", "sold_to", "trucker", "material_type"):
        value = parsed.get(field, "")
        letters = len(re.findall(r"[A-Za-z]", value))
        symbols = len(re.findall(r"[^A-Za-z0-9\s.'-]", value))
        normalized = re.sub(r"[^a-z]", "", value.lower())
        is_label_fragment = normalized in {
            "gross", "gros", "tare", "net", "material", "sold", "deliver", "trucker",
        }
        is_repeated_noise = len(normalized) >= 2 and len(set(normalized)) == 1
        if letters < 2 or symbols > max(2, len(value) // 4) or is_label_fragment or is_repeated_noise:
            parsed[field] = ""


def _extract_with_pytesseract(image_path: Path) -> Tuple[Dict[str, str], float]:
    import pytesseract
    from PIL import Image as PilImage

    logger.info("pytesseract_request_start image=%s", image_path)
    configured_cmd = _configure_tesseract_cmd()
    if configured_cmd:
        pytesseract.pytesseract.tesseract_cmd = configured_cmd

    primary_config = "--oem 1 --psm 11"
    source_image = PilImage.open(image_path)
    source_image.load()
    img, raw_text, parsed, orientation_score, orientation_angle = _select_tesseract_candidate(
        source_image,
        lambda candidate, angle: pytesseract.image_to_string(candidate, config=primary_config),
    )
    _persist_upright_image(image_path, source_image, orientation_angle)
    source_image.close()
    selected_config = primary_config

    if _parsed_field_score(parsed) <= 2:
        fallback_config = "--oem 1 --psm 6"
        fallback_text = pytesseract.image_to_string(img, config=fallback_config)
        fallback_parsed = parse_ticket_text(fallback_text)
        if _parsed_field_score(fallback_parsed) > _parsed_field_score(parsed):
            raw_text = fallback_text
            parsed = fallback_parsed
            selected_config = fallback_config

    try:
        data = pytesseract.image_to_data(
            img, config=selected_config,
            output_type=pytesseract.Output.DICT,
        )
        confs = [float(c) for c in data.get("conf", []) if str(c).replace(".", "", 1).isdigit() and float(c) >= 0]
        avg_conf = round(sum(confs) / (len(confs) * 100.0), 2) if confs else 0.0
        spatial_fields = _extract_tesseract_spatial_fields(data, img.size)
        for field, value in spatial_fields.items():
            if value and not parsed.get(field):
                parsed[field] = value
    except Exception:
        avg_conf = 0.0

    _sanitize_untrusted_fields(parsed)
    parsed["source_site"] = parsed.get("quarry_name", "")
    parsed["destination_site"] = parsed.get("deliver_to", "")
    parsed["__raw_text"] = raw_text
    logger.info(
        "pytesseract_request_success image=%s config=%s score=%s angle=%s conf=%.2f",
        image_path, selected_config, orientation_score, orientation_angle, avg_conf,
    )
    return parsed, avg_conf


_EASYOCR_READER = None

def _get_easyocr_reader() -> Any:
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        try:
            import easyocr
            _EASYOCR_READER = easyocr.Reader(["en"], gpu=False)
        except Exception as exc:
            logger.warning("easyocr_init_failed error=%s", exc)
            return None
    return _EASYOCR_READER


def _extract_with_easyocr(image_path: Path) -> Tuple[Dict[str, str], float]:
    reader = _get_easyocr_reader()
    if reader is None:
        raise RuntimeError("EasyOCR is not installed or failed to initialize.")

    import io
    from PIL import Image as PilImage, ImageOps

    logger.info("easyocr_request_start image=%s", image_path)
    source_img = PilImage.open(image_path)
    source_img.load()
    source_img = ImageOps.exif_transpose(source_img)

    angles = (0, 90, 180, 270)

    best_candidate: Optional[Tuple[Dict[str, str], float, int, str, int]] = None

    for angle in angles:
        candidate_img = source_img if angle == 0 else source_img.rotate(angle, expand=True)
        prep_img = _preprocess_for_ocr(candidate_img)

        w, h = prep_img.size
        if max(w, h) > 1800:
            scale = 1800.0 / float(max(w, h))
            prep_img = prep_img.resize((int(w * scale), int(h * scale)), getattr(PilImage, "LANCZOS", 3))

        img_byte_arr = io.BytesIO()
        prep_img.save(img_byte_arr, format="PNG")
        img_bytes = img_byte_arr.getvalue()

        try:
            results = reader.readtext(
                img_bytes,
                detail=1,
                paragraph=False,
                canvas_size=2560,
                mag_ratio=1.5,
                contrast_ths=0.05,
                adjust_contrast=0.7,
            )
        except Exception as e_err:
            logger.warning("easyocr_angle_failed angle=%d error=%s", angle, e_err)
            continue

        results = sorted(
            results,
            key=lambda item: (
                item[0][0][1] if item[0] else 0,
                item[0][0][0] if item[0] else 0,
            ),
        )
        lines: List[str] = []
        conf_scores: List[float] = []
        for bbox, text, conf in results:
            t_clean = str(text or "").strip()
            if t_clean:
                lines.append(t_clean)
                conf_scores.append(float(conf))

        raw_text = "\n".join(lines)
        parsed = parse_ticket_text(raw_text)
        spatial_fields = _extract_spatial_fields(_build_easyocr_word_index(results, prep_img.size))
        for field, value in spatial_fields.items():
            if value:
                parsed[field] = value
        _sanitize_untrusted_fields(parsed)

        score = _tesseract_candidate_score(raw_text, parsed)
        avg_conf = (sum(conf_scores) / float(len(conf_scores))) if conf_scores else 0.5

        if best_candidate is None or score > best_candidate[4]:
            best_candidate = (parsed, avg_conf, angle, raw_text, score)

        # Recognizing the printed form labels is enough to establish that the
        # page is upright. Do not run three costly rotations just because
        # handwritten values are faint or incomplete.
        if _form_label_hits(raw_text) >= 6 or score >= 300:
            break

    if best_candidate is not None:
        best_parsed, best_conf, best_angle, best_raw_text, _ = best_candidate
        _persist_upright_image(image_path, source_img, best_angle)
        best_parsed["source_site"] = best_parsed.get("quarry_name", "")
        best_parsed["destination_site"] = best_parsed.get("deliver_to", "")
        best_parsed["__raw_text"] = best_raw_text
        source_img.close()
        logger.info("easyocr_request_success image=%s conf=%.2f angle=%d", image_path, best_conf, best_angle)
        return best_parsed, best_conf

    source_img.close()
    raise RuntimeError("EasyOCR failed to extract orientation candidates.")


def extract_ticket_data(image_path: Path, force_provider: Optional[str] = None) -> Tuple[Dict[str, str], float, str]:
    """
    Attempt OCR on a ticket image. Returns (fields_dict, confidence, provider_name).
    """
    provider = (force_provider or os.getenv("OCR_PROVIDER", "auto")).strip().lower()
    google_error = ""
    logger.info("ocr_extract_start image=%s provider_env=%s", image_path, provider or "<empty>")

    if provider == "google_vision" or force_provider == "google_vision":
        try:
            parsed, confidence = _extract_with_google_vision(image_path)
            logger.info("ocr_extract_provider_selected image=%s provider=google_vision confidence=%.2f", image_path, confidence)
            return parsed, confidence, "google_vision"
        except Exception as exc:
            google_error = f"{type(exc).__name__}: {exc}"
            logger.exception("ocr_extract_google_failed image=%s error=%s", image_path, google_error)

    # Try EasyOCR first for free local deep-learning AI OCR
    try:
        parsed, confidence = _extract_with_easyocr(image_path)
        if google_error:
            parsed["__ocr_warning"] = f"Google Vision failed, used EasyOCR fallback ({google_error})"
        logger.info("ocr_extract_provider_selected image=%s provider=easyocr confidence=%.2f", image_path, confidence)
        return parsed, confidence, "easyocr"
    except Exception as exc:
        logger.info("easyocr_fallback_to_pytesseract reason=%s", exc)

    # Fallback to pytesseract
    try:
        parsed, confidence = _extract_with_pytesseract(image_path)
        if google_error:
            parsed["__ocr_warning"] = f"Google Vision failed, used pytesseract fallback ({google_error})"
        logger.info("ocr_extract_provider_selected image=%s provider=pytesseract confidence=%.2f", image_path, confidence)
        return parsed, confidence, "pytesseract"
    except Exception as exc:
        logger.exception("ocr_extract_pytesseract_failed image=%s error=%s", image_path, exc)

    empty: Dict[str, str] = {
        "ticket_id": "", "ticket_date": "", "job_no": "", "quarry_name": "",
        "truck_or_plate": "", "trucker": "", "sold_to": "", "deliver_to": "",
        "material_type": "", "received_by": "", "gross_weight": "",
        "tare_weight": "", "net_weight": "", "source_site": "", "destination_site": "",
        "__raw_text": "",
    }
    if google_error:
        empty["__ocr_warning"] = f"Google Vision failed and local OCR fallbacks failed ({google_error})"
    logger.error("ocr_extract_failed image=%s returning_empty=true", image_path)
    return empty, 0.0, "none"
