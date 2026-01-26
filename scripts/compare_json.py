import json
from pathlib import Path

def load_json(path: str):
    data = Path(path).read_bytes()
    # Try common encodings for PowerShell redirection
    for enc in ('utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be'):
        try:
            text = data.decode(enc)
            # Trim any leading log lines before the JSON payload
            first_brace = text.find('{')
            if first_brace > 0:
                text = text[first_brace:]
            return json.loads(text)
        except Exception:
            continue
    # Last resort: ignore errors
    text = data.decode('utf-8', errors='ignore')
    first_brace = text.find('{')
    if first_brace > 0:
        text = text[first_brace:]
    return json.loads(text)

def main():
    before = load_json('scripts/before_refactor.json')
    after = load_json('scripts/after_refactor.json')
    same = before == after
    print(f"Equal: {same}")
    if not same:
        print("Before:")
        print(json.dumps(before, ensure_ascii=False, indent=2))
        print("After:")
        print(json.dumps(after, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
