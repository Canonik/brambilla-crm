import csv, sys, re, collections
from pathlib import Path
base = Path(sys.argv[1])
def rows(name):
    with open(base/name, encoding='cp1252', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
def is_del(v): return v.strip().lower() in ('s','si','sì','1','true','y','yes')
az = rows('aziende.csv')
print("== aziende cancellato values:", collections.Counter(r['cancellato'] for r in az))
live = [r for r in az if not is_del(r['cancellato'])]
print("live companies:", len(live))
def norm_domain(s):
    s = s.strip().lower()
    s = re.sub(r'^https?://', '', s); s = re.sub(r'^www\.', '', s); s = s.split('/')[0]
    return s
dom = collections.defaultdict(list)
for r in live:
    d = norm_domain(r['sito_web'])
    if d: dom[d].append(r)
dups = {d:v for d,v in dom.items() if len(v)>1}
print("== distinct domains:", len(dom), "domains with >1 live company:", len(dups), "rows involved:", sum(len(v) for v in dups.values()))
print("== dup group size dist:", collections.Counter(len(v) for v in dups.values()))
for d, v in list(dups.items())[:5]:
    print("  ", d)
    for r in v: print("      ", r['id_azienda'], r['ragione_sociale'], '|', r['sito_web'], '|', r['citta'], r['provincia'], '|', r['note'][:60], '|', r['ultima_modifica'])
# same name different domain?
nm = collections.defaultdict(set)
for r in live:
    nm[r['ragione_sociale'].strip().lower()].add(norm_domain(r['sito_web']))
print("== names with >1 distinct nonempty domains:", sum(1 for k,v in nm.items() if len([x for x in v if x])>1))
print("== names with multiple rows and empty domains:", sum(1 for k,v in nm.items() if len(v)>=1 and '' in v and len(v)>1))
# partita iva in notes
piva = collections.Counter()
ex = []
for r in az:
    m = re.search(r'(p\.?\s*iva|partita\s*iva|pi)\s*[:\s]*\s*(it\s*)?([\d\s]{11,})', r['note'], re.I)
    if m:
        piva['found'] += 1
        digits = re.sub(r'\D','', m.group(3))
        piva[f'len{len(digits)}'] += 1
        if len(ex) < 12: ex.append((r['note'], digits))
    elif re.search(r'iva|\bpi\b|p\.i', r['note'], re.I): piva['iva-mentioned-not-matched'] += 1; 
print("== partita iva in notes:", piva)
for e in ex: print("   ", e)
print("== notes mentioning iva but not matched:", [r['note'] for r in az if re.search(r'iva|\bpi\b|p\.i', r['note'], re.I) and not re.search(r'(p\.?\s*iva|partita\s*iva|pi)\s*[:\s]*\s*(it\s*)?([\d\s]{11,})', r['note'], re.I)][:10])
# duplicates piva among live companies
pv = collections.defaultdict(list)
for r in live:
    m = re.search(r'(p\.?\s*iva|partita\s*iva|pi)\s*[:\s]*\s*(it\s*)?([\d\s]{11,})', r['note'], re.I)
    if m: pv[re.sub(r'\D','', m.group(3))].append(r)
pd = {k:v for k,v in pv.items() if len(v)>1}
print("== piva shared by >1 live companies:", len(pd))
for k,v in list(pd.items())[:5]:
    print("  ", k)
    for r in v: print("      ", r['id_azienda'], r['ragione_sociale'], '|', r['sito_web'], '|', r['ultima_modifica'])
# do piva-dups overlap domain dups?
print("== piva dup groups where domains differ:", sum(1 for k,v in pd.items() if len({norm_domain(r['sito_web']) for r in v})>1))
print("== piva dup groups where domains differ and both nonempty:", sum(1 for k,v in pd.items() if len({norm_domain(r['sito_web']) for r in v if norm_domain(r['sito_web'])})>1))
# names whitespace
print("== names with surrounding whitespace:", sum(1 for r in az if r['ragione_sociale'] != r['ragione_sociale'].strip()))
print("== citta with surrounding whitespace:", sum(1 for r in az if r['citta'] != r['citta'].strip()))
# sito_web weird values
print("== sito_web without dot:", [r['sito_web'] for r in az if r['sito_web'] and '.' not in r['sito_web']][:10])
print("== sito_web with uppercase:", sum(1 for r in az if r['sito_web'] != r['sito_web'].lower()))
