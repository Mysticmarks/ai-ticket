import re

pattern = r"You\s+are\s+(?P<name>[^,]+),"

def find_name(text):
    if not text:
        return False
    if not isinstance(text,str):
        return False
    match = re.search(pattern, text)
    if not match:
        return None

    extracted_name = match.group("name")
    if extracted_name:
        return extracted_name.strip()
    return None
