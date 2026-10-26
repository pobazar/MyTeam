"""Build an isolated local review gallery outside the public repository."""
import html
import json
import re
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = Path(sys.argv[1] if len(sys.argv)>1 else '/workspace/myteam-state-review')
out = Path(sys.argv[2] if len(sys.argv)>2 else '/tmp/myteam-review-gallery').resolve()
if out == root or root in out.parents:
    raise SystemExit('Keep review artifacts outside the repository.')
out.mkdir(parents=True,exist_ok=True)
manifest = json.loads((source/'manifest.json').read_text())
result = json.loads((source/'result.json').read_text())
for item in manifest:
    item['title']=re.sub(r'(?<=[А-Яа-я])(?=\d)', ' ', re.sub(r'·(?=\d)', '· ', item['title']))
assert result['status']=='passed' and result['screenshots']==len(manifest)
for p in out.glob('[0-9]*.png'):
    p.unlink()
for item in manifest:
    assert re.fullmatch(r'\d{2,3}\.png',item['file'])
    shutil.copyfile(source/item['file'],out/item['file'])
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
esc = html.escape
groups = list(dict.fromkeys(x['group'] for x in manifest))
parts=['''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>МАЙТИМ · состояния для ревью</title><link rel="stylesheet" href="review.css"><script src="review.js" defer></script></head><body><main><header><p class="eyebrow">МАЙТИМ · 25 октября 2026</p><h1>Состояния приложения</h1>''',f'<p>{len(manifest)} скриншот · один размер: desktop 1440×1000 · Chromium.</p>', '''<p>Вымышленные пользователи и изолированные ответы JSON API. Состояния загрузки, ошибок и времени моделируются; реальные участники и Telegram не затронуты. Серверная логика отдельно проверена 76 тестами PostgreSQL. Проверки мобильных устройств в этот прогон не входят.</p><p>Запись и отмена проверены без повторного GET и замены DOM: кнопка, статус и счётчик меняются на месте. Тосты, валидация, история, награда и обе ветки оценки включены.</p><p><a href="../../../">Открыть приложение</a> · <a href="manifest.json">Список состояний</a> · <a href="result.json">Результат браузерного прогона</a></p></header><nav aria-label="Фильтр состояний"><label for="group">Раздел</label><select id="group"><option value="">Все состояния</option>''']
for group in groups:
    parts.append(f'<option value="{esc(group)}">{esc(group)}</option>')
parts.append('''</select><label class="search-label" for="search">Поиск</label><input id="search" type="search" placeholder="Например: записан, ошибка, оценка"><span id="visible-count" role="status"></span></nav><div class="gallery">''')
for i,item in enumerate(manifest,1):
    parts.append(f'''<article class="shot" id="state-{i:02}" data-group="{esc(item['group'])}"><a class="preview" href="{item['file']}" data-index="{i-1}" aria-label="Открыть: {esc(item['title'])}"><img src="{item['file']}" loading="lazy" alt="{esc(item['title'])}" width="1440" height="1000"></a><div class="caption"><p class="tag">{i:02} · {esc(item['group'])}</p><h2>{esc(item['title'])}</h2><p>{esc(item['notes'])}</p><a href="{item['file']}" target="_blank" rel="noopener">Оригинал ↗</a></div></article>''')
parts.append('''</div><footer>Старые галереи заменены этой версией. Скриншоты не являются подтверждением реальной доставки Telegram или проверкой физических устройств.</footer></main><dialog id="viewer" aria-labelledby="viewer-title"><div class="viewer-bar"><button id="previous" type="button" aria-label="Предыдущий скриншот">←</button><h2 id="viewer-title"></h2><button id="next" type="button" aria-label="Следующий скриншот">→</button><button id="close" type="button" aria-label="Закрыть просмотр">✕</button></div><img id="viewer-image" alt=""></dialog></body></html>''')
(out/'index.html').write_text('\n'.join(parts))
print(f'Gallery: {len(manifest)} states, {out}')
