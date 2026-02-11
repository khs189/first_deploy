import re

SQL_WORDS = [
    "OR","SELECT","INSERT","DELETE","UPDATE","CREATE","DROP","EXEC",
    "UNION","FETCH","DECLARE","TRUNCATE"
]

def sanitize_keyword(s: str) -> str:
    if s is None:
        return ""
    s = s.strip()
    s = re.sub(r"[%=><]", "", s)
    for w in SQL_WORDS:
        s = re.sub(rf"\b{w}\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s
