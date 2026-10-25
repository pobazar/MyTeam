"""Generate web Day tokens from the owner's unmodified TUI catalog."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
colors = json.loads((root / 'design-system/tokens/colors.json').read_text())
lines = ['/* Generated from design-system/tokens/colors.json — Day semantic tokens. */', ':root {']
for token in colors:
    fills = token.get('fills', [])
    if not token['name'].startswith('Day/') or len(fills) != 1 or fills[0].get('type') != 'SOLID':
        continue
    fill = fills[0]
    color = fill.get('color')
    if not color:
        continue
    if fill.get('opacity', 1) != 1 and len(color) == 7:
        color += format(round(fill['opacity'] * 255), '02x')
    name = token['name'][4:].lower().replace('/', '-').replace(' ', '-')
    lines.append(f'  --{name}: {color};')
lines += [
    '  --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;',
    '  --border-normal: var(--background-neutral-3);',
    '  --border-focus: var(--text-action);',
    '  --state-background-accent-1-hover: var(--background-accent-1-hover);',
    '}',
]
(root / 'web/tokens.css').write_text('\n'.join(lines) + '\n')
