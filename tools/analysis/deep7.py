import csv, sys, re, collections
from pathlib import Path
base = Path(sys.argv[1])
def rows(name):
    with open(base/name, encoding='cp1252', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
def is_del(v): return v.strip().lower() in ('s','si','sì','1')
opp = rows('opportunita.csv')
nums = [r['importo'] for r in opp] + [r['prezzo_unitario'] for r in rows('righe_offerta.csv')] + [r['prezzo_listino'] for r in rows('listino.csv')]
onlyc = [n for n in nums if ',' in n and '.' not in n]
print("== only-comma: digits after last comma:", collections.Counter(len(re.sub(r'\D','',n.split(',')[-1])) for n in onlyc))
onlyd = [n for n in nums if '.' in n and ',' not in n]
print("== only-dot: digits after last dot:", collections.Counter(len(re.sub(r'\D','',n.split('.')[-1])) for n in onlyd))
print("== only-dot with 3 digits after:", [n for n in onlyd if len(re.sub(r'\D','',n.split('.')[-1]))==3][:10])
print("== only-comma with 3 digits after:", [n for n in onlyc if len(re.sub(r'\D','',n.split(',')[-1]))==3][:10])
print("== paren examples:", [(r['titolo'], r['importo'], r['fase']) for r in opp if '(' in r['importo']][:6])
cred = [r for r in opp if re.search(r'storno|nota di credito|\bNC\b', r['titolo'], re.I)]
print("== credit-titled deals:", len(cred), "negative:", sum(1 for r in cred if '-' in r['importo']), "paren:", sum(1 for r in cred if '(' in r['importo']), "neither:", [(r['titolo'], r['importo']) for r in cred if '-' not in r['importo'] and '(' not in r['importo']][:8])
print("== paren deals not credit-titled:", [(r['titolo'], r['importo']) for r in opp if '(' in r['importo'] and not re.search(r'storno|nota di credito|\bNC\b', r['titolo'], re.I)][:5])
print("== credit deals stage:", collections.Counter(r['fase'].strip().lower() for r in cred), "pipeline:", collections.Counter(r['pipeline'].strip().lower() for r in cred))
print("== credit deals with lines:", len({r['id_opportunita'] for r in rows('righe_offerta.csv')} & {r['id_opportunita'] for r in cred}))
print("== credit deals with empty importo:", sum(1 for r in cred if not r['importo'].strip()))
# (at) twins
ct = rows('contatti.csv'); live=[r for r in ct if not is_del(r['cancellato'])]
EMAIL = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
valid = {r['email'].strip().lower() for r in live if EMAIL.match(r['email'].strip())}
for pat, fix in [('(at)', lambda e: e.replace('(at)','@')), (' @', lambda e: e.replace(' @','@'))]:
    xs = [r for r in live if pat in r['email']]
    tw = sum(1 for r in xs if fix(r['email'].strip().lower()) in valid)
    print(f"== {pat!r}: {len(xs)} rows, with a valid twin: {tw}")
    # same name twin?
    byname = collections.defaultdict(list)
    for r in live: byname[(r['nome'].strip().lower(), r['cognome'].strip().lower())].append(r)
    print("    with same-name other rows:", sum(1 for r in xs if len(byname[(r['nome'].strip().lower(), r['cognome'].strip().lower())])>1))
# truncated '@gmail' / 'x@' twins by name
xs = [r for r in live if r['email'].strip() and not EMAIL.match(r['email'].strip()) and '@' in r['email']]
byname = collections.defaultdict(list)
for r in live: byname[(r['nome'].strip().lower(), r['cognome'].strip().lower())].append(r)
print("== invalid-with-@ rows:", len(xs), "same-name twins:", sum(1 for r in xs if len(byname[(r['nome'].strip().lower(), r['cognome'].strip().lower())])>1))
# how common are same-name twins among valid-email contacts (baseline)
vs = [r for r in live if EMAIL.match(r['email'].strip())]
print("== baseline same-name twin rate among valid:", sum(1 for r in vs if len(byname[(r['nome'].strip().lower(), r['cognome'].strip().lower())])>1)/len(vs))
# company name+city dup w/o domain & piva
az = rows('aziende.csv'); lv=[r for r in az if not is_del(r['cancellato'])]
def nd(s):
    s=s.strip().lower(); s=re.sub(r'^https?://','',s); s=re.sub(r'^www\.','',s); return s.split('/')[0]
def piva(n):
    m = re.search(r'(p\.?\s*iva|partita\s*iva|pi)\s*[:\s]*\s*(it\s*)?([\d\s]{11,})', n, re.I); return re.sub(r'\D','',m.group(3)) if m else ''
nokey = [r for r in lv if not nd(r['sito_web']) and not piva(r['note'])]
print("== live companies with neither domain nor piva:", len(nokey))
g = collections.defaultdict(list)
for r in nokey: g[(r['ragione_sociale'].strip().lower(), r['citta'].strip().lower())].append(r)
print("   name+city groups >1 among them:", sum(1 for v in g.values() if len(v)>1))
for k,v in [(k,v) for k,v in g.items() if len(v)>1][:3]:
    for r in v: print("      ", r['id_azienda'], r['ragione_sociale'], r['citta'], r['note'][:50], r['ultima_modifica'])
# in domain-dup groups: is name+city same?
dom = collections.defaultdict(list)
for r in lv:
    if nd(r['sito_web']): dom[nd(r['sito_web'])].append(r)
dd = [v for v in dom.values() if len(v)>1]
print("== domain-dup groups: same city:", sum(1 for v in dd if len({r['citta'].strip().lower() for r in v})==1), "diff city:", sum(1 for v in dd if len({r['citta'].strip().lower() for r in v})>1))
# ambiguous user names: active status
users = rows('utenti.csv')
for ids in (['U22','U84'],['U29','U81'],['U47','U83'],['U65','U85'],['U72','U80'],['U78','U82']):
    print("  ", [(u['id_utente'], u['nome'], u['cognome'], u['attivo']) for u in users if u['id_utente'] in ids])
# for name-assigned deals with ambiguous names: does storico id_utente disambiguate?
sf = rows('storico_fasi.csv'); byopp = collections.defaultdict(set)
for s in sf: byopp[s['id_opportunita']].add(s['id_utente'])
import unicodedata
def norm(s): return unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower().strip()
amb = {'niccolo bassi','bassi niccolo','n. bassi','bassi n.','marco costa','costa marco','m. costa','costa m.','luca santoro','santoro luca','l. santoro','santoro l.','mattia panzeri','panzeri mattia','m. panzeri','panzeri m.','serena neri','neri serena','s. neri','neri s.','sara colombo','colombo sara','s. colombo','colombo s.'}
for r in opp:
    if norm(r['id_commerciale']) in amb: print("   AMBIG deal", r['id_opportunita'], r['id_commerciale'], "storico users:", byopp[r['id_opportunita']])
# deals assigned by Uxx: does storico user match the commerciale? (to validate the disambiguation idea)
m=n=0
for r in opp:
    if re.fullmatch(r'U\d+', r['id_commerciale']):
        if r['id_commerciale'] in byopp[r['id_opportunita']]: m+=1
        else: n+=1
print("== Uxx commerciale appears in storico users:", m, "not:", n)
