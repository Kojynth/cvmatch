import sys
import pathlib

def normalize_file(path: str) -> None:
    p = pathlib.Path(path)
    text = p.read_text(encoding='utf-8', errors='replace')
    # Replace tabs with 4 spaces
    lines = text.splitlines()
    new_lines = []
    for line in lines:
        # Only convert leading tabs
        i = 0
        while i < len(line) and line[i] in ('\t', ' '):
            i += 1
        indent = line[:i].replace('\t', '    ').replace('\u00A0', ' ')
        body = line[i:].replace('\u00A0', ' ')
        new_lines.append(indent + body)
    p.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')

if __name__ == '__main__':
    for arg in sys.argv[1:]:
        normalize_file(arg)
