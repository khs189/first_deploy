import re
from .sanitize import sanitize_keyword

def normalize_region_prefix(addr: str) -> str:
    if not addr:
        return addr
    replacements = [
        ("서울특별시", "서울"), ("서울시", "서울"),
        ("경기도", "경기"),
        ("부산광역시", "부산"), ("부산시", "부산"),
        ("대구광역시", "대구"), ("대구시", "대구"),
        ("인천광역시", "인천"), ("인천시", "인천"),
        ("광주광역시", "광주"), ("광주시", "광주"),
        ("대전광역시", "대전"), ("대전시", "대전"),
        ("울산광역시", "울산"), ("울산시", "울산"),
        ("세종특별자치시", "세종"), ("세종시", "세종"),
        ("제주특별자치도", "제주"), ("제주시", "제주"),
        ("경상북도", "경북"), ("경상남도", "경남"),
        ("전라북도", "전북"), ("전라남도", "전남"),
    ]
    for old, new in replacements:
        if addr.startswith(old):
            return addr.replace(old, new, 1)
    return addr

def split_base_detail(raw: str):
    if not raw:
        return "", ""
    raw = str(raw).strip()
    if "," in raw:
        base, detail = raw.split(",", 1)
        return base.strip(), detail.strip()
    return raw, ""

def strip_parentheses(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\([^)]*\)", "", text).strip()

def extract_building_name_from_part2(part2: str) -> str:
    if not part2:
        return ""
    m = re.match(r"^\((.*)\)$", part2.strip())
    if not m:
        return ""
    inside = m.group(1)
    parts = [p.strip() for p in inside.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[-1]
    return ""

def normalize_detail(detail: str, building_name: str) -> str:
    if not detail:
        return ""
    d = detail.strip()
    d = strip_parentheses(d)
    if building_name:
        d = d.replace(building_name, "").strip()
    d = d.replace(")", "").replace("(", "").strip()
    d = re.sub(r"\s+", " ", d).strip()
    d = re.sub(r"(\d+)\s*동\s*(\d+)\s*호", r"\1동 \2호", d)
    return d

def prepare_api_keyword(base: str) -> str:
    s = base.strip()
    s = strip_parentheses(s)
    s = re.sub(r"\s+\d+\s*동.*$", "", s)
    s = re.sub(r"\s+\d+\s*층.*$", "", s)
    s = re.sub(r"\s+\d+\s*호.*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return sanitize_keyword(s)

def build_road_address_and_zip(juso_item: dict, original_detail: str):
    part1 = (juso_item.get("roadAddrPart1") or "").strip()
    part2 = (juso_item.get("roadAddrPart2") or "").strip()
    road_full = (juso_item.get("roadAddr") or "").strip()
    zip_no = (juso_item.get("zipNo") or "").strip()

    base = part1 if part1 else road_full
    building_name = extract_building_name_from_part2(part2)
    detail = normalize_detail(original_detail, building_name)

    if detail:
        addr = (base + ", " + detail + (part2 if part2 else "")).strip()
    else:
        addr = road_full if road_full else (part1 + part2).strip()

    return addr, zip_no
