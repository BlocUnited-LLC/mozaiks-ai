from pathlib import Path
text = Path('core/workflow/orchestration_patterns.py').read_text(encoding='utf-8')
start = text.index("TextEvent details") - 200
print(text[start:start+600])
