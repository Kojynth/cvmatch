import sys
path = sys.argv[1]
start = int(sys.argv[2])
end = int(sys.argv[3])
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.read().splitlines()
for i in range(start, end+1):
    line = lines[i-1] if 0 < i <= len(lines) else ''
    indent = line[:len(line) - len(line.lstrip())]
    print(f"{i}: indent={list(map(ord, indent))} -> {line!r}")

