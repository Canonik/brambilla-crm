import csv, sys, re, collections
from pathlib import Path
base = Path(sys.argv[1])
def rows(name):
    with open(base/name, encoding='cp1252', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
def is_del(v): return v.strip().lower() in ('s','si','sì','1')
ct = rows('contatti.csv')
live = [r for r in ct if not is_del(r['cancellato'])]
print("live contacts:", len(live))
EMAIL = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
def norm_email(s):
    s = s.strip().lower()
    return s if EMAIL.match(s) else ''
inv = collections.Counter(r['email'].strip() for r in live if r['email'].strip() and not norm_email(r['email']))
print("== invalid email shapes (top 30):")
for k,n in inv.most_common(30): print(f"   {n:5d} {k!r}")
print("== invalid '(at)' count:", sum(1 for r in live if '(at)' in r['email']))
em = collections.defaultdict(list)
for r in live:
    e = norm_email(r['email'])
    if e: em[e].append(r)
dups = {e:v for e,v in em.items() if len(v)>1}
print("== contacts with valid email:", sum(len(v) for v in em.values()), "distinct emails:", len(em), "dup groups:", len(dups), "rows:", sum(len(v) for v in dups.values()))
print("== dup group size dist:", collections.Counter(len(v) for v in dups.values()))
for e, v in list(dups.items())[:6]:
    print("  ", e)
    for r in v: print("      ", r['id_contatto'], r['nome'], r['cognome'], '|', repr(r['email']), '|', r['telefono'], '|', r['id_azienda'], '|', r['tipo'], '|', r['ultima_modifica'])
# in dup groups, do fields differ?
diff = collections.Counter()
for e, v in dups.items():
    for f in ('nome','cognome','telefono','id_azienda','tipo'):
        vals = {r[f].strip().lower() for r in v if r[f].strip()}
        if len(vals)>1: diff[f]+=1
        if len(vals)==1 and any(not r[f].strip() for r in v): diff[f+'_partial']+=1
print("== field differences within dup groups:", diff)
# names with whitespace / case
print("== nome with surrounding ws:", sum(1 for r in ct if r['nome']!=r['nome'].strip()), "cognome:", sum(1 for r in ct if r['cognome']!=r['cognome'].strip()))
print("== nome shapes:", collections.Counter(re.sub(r'[a-zà-ÿ]','a',re.sub(r'[A-ZÀ-Ý]','A',r['nome'])) for r in ct).most_common(10))
print("== cognome shapes:", collections.Counter(re.sub(r'[a-zà-ÿ]','a',re.sub(r'[A-ZÀ-Ý]','A',r['cognome'])) for r in ct).most_common(10))
# email case: uppercase emails
print("== uppercase emails:", sum(1 for r in ct if r['email'] != r['email'].lower()))
# id_azienda refs
az = rows('aziende.csv'); azids = {r['id_azienda'] for r in az}; azdel = {r['id_azienda'] for r in az if is_del(r['cancellato'])}
print("== contact id_azienda: missing:", sum(1 for r in live if r['id_azienda'] and r['id_azienda'] not in azids), "deleted:", sum(1 for r in live if r['id_azienda'] in azdel), "empty:", sum(1 for r in live if not r['id_azienda']))
# R12: contacts w/o company whose email domain matches a company domain
def norm_domain(s):
    s = s.strip().lower(); s = re.sub(r'^https?://', '', s); s = re.sub(r'^www\.', '', s); return s.split('/')[0]
doms = {norm_domain(r['sito_web']) for r in az if not is_del(r['cancellato']) and norm_domain(r['sito_web'])}
nc = [r for r in live if not r['id_azienda'] and norm_email(r['email'])]
m = sum(1 for r in nc if norm_email(r['email']).split('@')[1] in doms)
print("== contacts w/o company with valid email:", len(nc), "whose domain matches a company:", m)
print("== free-mail domains among contacts:", collections.Counter(norm_email(r['email']).split('@')[1] for r in live if norm_email(r['email'])).most_common(12))
print("== tipo values:", collections.Counter(r['tipo'].strip().lower() for r in ct))
