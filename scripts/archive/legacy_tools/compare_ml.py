import json
from pathlib import Path


def load_json(path: str):
    data = Path(path).read_text(encoding='utf-8', errors='ignore')
    i = data.find('{')
    j = data.rfind('}')
    if i != -1 and j != -1 and j > i:
        data = data[i:j+1]
    return json.loads(data)


def main():
    b = load_json('scripts/before_ml_refactor.json')
    a = load_json('scripts/after_ml_refactor.json')
    bm = b.get('ml_settings_widget')
    am = a.get('ml_settings_widget')
    eq = bm == am
    print(f"ML settings equal: {eq}")
    if not eq:
        Path('scripts/ml_diff_before.json').write_text(json.dumps(bm, ensure_ascii=False, indent=2), encoding='utf-8')
        Path('scripts/ml_diff_after.json').write_text(json.dumps(am, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Wrote scripts/ml_diff_before.json and scripts/ml_diff_after.json')


if __name__ == '__main__':
    main()
