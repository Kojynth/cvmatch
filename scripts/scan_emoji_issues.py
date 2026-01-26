import os
import sys
import json
from pathlib import Path

# Emojis of interest (eye, eyes, magnifying glass)
EMOJI_TARGETS = {
    "\U0001F50D": "magnifying_glass_tilted_left",
    "\U0001F50E": "magnifying_glass_tilted_right",
    "\U0001F441": "eye",
    "\U0001F440": "eyes",
}

# Problematic modifiers/controls often causing blank squares next to emoji
PROBLEM_CHARS = {
    "\uFE0F": "VS16_emoji_presentation",
    "\uFE0E": "VS15_text_presentation",
    "\u200D": "ZWJ",
    "\u200B": "ZWSP",
    "\u2060": "WORD_JOINER",
    "\u200E": "LRM",
    "\u200F": "RLM",
    "\uFFFD": "REPLACEMENT_CHAR",
}

def scan_file(p: Path):
    try:
        text = p.read_text(encoding='utf-8', errors='replace')
    except Exception:
        text = p.read_bytes().decode('utf-8', 'replace')
    issues = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        line_issues = []
        has_target = any(ch in line for ch in EMOJI_TARGETS)
        has_problem = any(ch in line for ch in PROBLEM_CHARS)
        mojibake_marks = []
        # Heuristic mojibake markers frequently seen in this repo
        if '??' in line:
            mojibake_marks.append('double_question_marks')
        if '�' in line:  # U+FFFD likely rendered as this
            mojibake_marks.append('replacement_glyph_visible')
        if has_target or has_problem or mojibake_marks:
            # classify exact target emojis present
            present_targets = [ name for ch,name in EMOJI_TARGETS.items() if ch in line ]
            present_problems = [ PROBLEM_CHARS[ch] for ch in PROBLEM_CHARS if ch in line ]
            # Compact preview of line
            preview = line
            if len(preview) > 200:
                preview = preview[:200] + '…'
            issues.append({
                'line': i,
                'targets': present_targets,
                'problems': present_problems,
                'mojibake': mojibake_marks,
                'text': preview,
            })
    return issues

def main():
    root = Path('app')
    report = {
        'root': str(root),
        'files': [],
        'summary': {
            'files_with_issues': 0,
            'total_issue_lines': 0,
        }
    }
    for p in root.rglob('*.py'):
        issues = scan_file(p)
        if issues:
            report['files'].append({
                'path': str(p),
                'issue_count': len(issues),
                'issues': issues,
            })
    report['summary']['files_with_issues'] = len(report['files'])
    report['summary']['total_issue_lines'] = sum(f['issue_count'] for f in report['files'])

    out_txt = Path('scripts/emoji_issues_report.txt')
    out_json = Path('scripts/emoji_issues_report.json')

    # Write human-readable report
    with out_txt.open('w', encoding='utf-8') as f:
        f.write(f"Emoji/Mojibake issue scan under: {root}\n")
        f.write(f"Files with issues: {report['summary']['files_with_issues']}\n")
        f.write(f"Total issue lines: {report['summary']['total_issue_lines']}\n\n")
        for file_entry in report['files']:
            f.write(f"--- {file_entry['path']} ({file_entry['issue_count']}) ---\n")
            for iss in file_entry['issues']:
                parts = []
                if iss['targets']:
                    parts.append('targets=' + ','.join(iss['targets']))
                if iss['problems']:
                    parts.append('problems=' + ','.join(iss['problems']))
                if iss['mojibake']:
                    parts.append('mojibake=' + ','.join(iss['mojibake']))
                meta = ' | '.join(parts) if parts else 'no-meta'
                f.write(f"L{iss['line']}: {meta}\n    {iss['text']}\n")
            f.write("\n")

    # Write JSON report for tooling
    with out_json.open('w', encoding='utf-8') as jf:
        json.dump(report, jf, ensure_ascii=False, indent=2)

    print(f"Wrote {out_txt} and {out_json}")
    print(f"Files with issues: {report['summary']['files_with_issues']}, lines: {report['summary']['total_issue_lines']}")

if __name__ == '__main__':
    main()

