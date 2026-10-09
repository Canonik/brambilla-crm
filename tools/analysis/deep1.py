import csv, sys, re, collections
from pathlib import Path
base = Path(sys.argv[1])
def rows(name):
    with open(base/name, encoding='cp1252', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
opp = rows('opportunita.csv'); print("== all fase values:")
for k,n in collections.Counter(r['fase'] for r in opp).most_common(): print(f"  {n:5d} {k!r}")
print("== pipeline x fase crosstab (normalized pipeline):")
ct = collections.Counter((r['pipeline'].strip().lower(), r['fase'].strip().lower()) for r in opp)
for k,n in sorted(ct.items()): print(f"  {n:5d} {k}")
print("== id_commerciale not matching U\\d+:")
users = {r['id_utente']: r for r in rows('utenti.csv')}
odd = collections.Counter(r['id_commerciale'] for r in opp if r['id_commerciale'] not in users)
for k,n in odd.most_common(40): print(f"  {n:5d} {k!r}")
print("== valuta vs importo symbol conflicts:")
conf = collections.Counter()
for r in opp:
    imp = r['importo']; val = r['valuta'].strip().lower()
    sym = 'EUR' if ('€' in imp or 'EUR' in imp.upper()) else 'USD' if ('$' in imp or 'USD' in imp.upper()) else 'GBP' if ('£' in imp or 'GBP' in imp.upper()) else None
    vn = {'eur':'EUR','euro':'EUR','€':'EUR','usd':'USD','$':'USD','gbp':'GBP','£':'GBP','':None}[val]
    conf[(sym, vn)] += 1
for k,n in conf.most_common(): print(f"  {n:6d} importo_sym={k[0]} valuta={k[1]}")
print("== negative amounts:", sum(1 for r in opp if '-' in r['importo']))
neg = [r for r in opp if '-' in r['importo']][:8]
for r in neg: print("   ", r['titolo'], '|', r['importo'], '|', r['fase'], '|', r['pipeline'], '|', r['data_chiusura'])
print("== titles containing 'storno':", sum(1 for r in opp if 'storno' in r['titolo'].lower()), " of which negative:", sum(1 for r in opp if 'storno' in r['titolo'].lower() and '-' in r['importo']))
print("== storno fase distribution:", collections.Counter(r['fase'].strip().lower() for r in opp if 'storno' in r['titolo'].lower()).most_common())
print("== data_chiusura excel serial examples:", [r['data_chiusura'] for r in opp if re.fullmatch(r'\d+', r['data_chiusura'])][:10])
print("== data_chiusura dd.mm.yy examples:", [r['data_chiusura'] for r in opp if re.fullmatch(r'[\d.]+', r['data_chiusura']) and '.' in r['data_chiusura']][:10])
print("== dd/mm/yyyy ambiguous? check any first part >12:", sum(1 for r in opp if re.fullmatch(r'\d{2}/\d{2}/\d{4}.*', r['data_chiusura']) and int(r['data_chiusura'][:2])>12), "second>12:", sum(1 for r in opp if re.fullmatch(r'\d{2}/\d{2}/\d{4}.*', r['data_chiusura']) and int(r['data_chiusura'][3:5])>12))
# won deals without closedate
def won(r):
    f = r['fase'].strip().lower(); return ('vinta' in f or f=='06' or 'rinnovato' in f or f=='r3' or 'r3' in f)
print("== won deals w/o data_chiusura:", sum(1 for r in opp if won(r) and not r['data_chiusura']), "of", sum(1 for r in opp if won(r)))
print("== deals w/ pipeline empty: fase distribution:", collections.Counter(r['fase'].strip().lower() for r in opp if not r['pipeline'].strip()).most_common(30))
print("== rinnovi deals titles sample:", [r['titolo'] for r in opp if 'rinnov' in r['pipeline'].lower()][:10])
print("== rinnovi deals: has data_chiusura:", sum(1 for r in opp if 'rinnov' in r['pipeline'].lower() and r['data_chiusura']), "/", sum(1 for r in opp if 'rinnov' in r['pipeline'].lower()))
# contatti large ids
cont = {r['id_contatto'] for r in rows('contatti.csv')}
refs = collections.Counter()
for r in opp:
    for c in re.split(r'[;,]', r['contatti']):
        c=c.strip()
        if c: refs['exists' if c in cont else 'missing'] += 1
print("== deal contact refs:", refs)
print("== dup contact ids inside one deal:", sum(1 for r in opp if (lambda xs: len(xs)!=len(set(xs)))([c.strip() for c in re.split(r'[;,]', r['contatti']) if c.strip()])))
az = {r['id_azienda'] for r in rows('aziende.csv')}
print("== deal id_azienda missing from aziende:", sum(1 for r in opp if r['id_azienda'] and r['id_azienda'] not in az))
