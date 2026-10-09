import csv, sys, re, collections
from pathlib import Path
base = Path(sys.argv[1])
def rows(name):
    with open(base/name, encoding='cp1252', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
def is_del(v): return v.strip().lower() in ('s','si','sì','1')
att = rows('attivita.csv')
print("== attivita tipo:", collections.Counter(r['tipo'] for r in att).most_common())
print("== attivita cancellato:", collections.Counter(r['cancellato'] for r in att).most_common())
print("== attivita data shapes:", collections.Counter(re.sub(r'\d','9',r['data']) for r in att).most_common())
print("== attivita id_utente not U:", collections.Counter(r['id_utente'] for r in att if not re.fullmatch(r'U\d+', r['id_utente'])).most_common(10))
print("== attivita with both contact & opp:", sum(1 for r in att if r['id_contatto'] and r['id_opportunita']), "only contact:", sum(1 for r in att if r['id_contatto'] and not r['id_opportunita']), "only opp:", sum(1 for r in att if not r['id_contatto'] and r['id_opportunita']), "neither:", sum(1 for r in att if not r['id_contatto'] and not r['id_opportunita']))
print("== attivita text with surrounding ws:", sum(1 for r in att if r['testo']!=r['testo'].strip()), "empty text:", sum(1 for r in att if not r['testo'].strip()))
print("== attivita year dist (2025 share):")
yrs = collections.Counter()
for r in att:
    d = r['data']
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', d) or None
    if m: yrs[m.group(3)] += 1
    else:
        m = re.match(r'(\d{4})-', d)
        if m: yrs[m.group(1)] += 1
        else: yrs['?'+re.sub(r'\d','9',d)] += 1
print(sorted(yrs.items()))
print("== id_attivita unique:", len({r['id_attivita'] for r in att}), "of", len(att))
sf = rows('storico_fasi.csv')
print("== storico rows:", len(sf))
print("== storico fase_nuova values:")
for k,n in collections.Counter(r['fase_nuova'] for r in sf).most_common(): print(f"   {n:6d} {k!r}")
print("== storico fase_precedente values (top):", collections.Counter(r['fase_precedente'] for r in sf).most_common(60))
print("== storico data_cambio shapes:", collections.Counter(re.sub(r'\d','9',r['data_cambio']) for r in sf).most_common())
print("== storico id_utente shapes:", collections.Counter(re.sub(r'\d','9',r['id_utente']) for r in sf).most_common())
opp = rows('opportunita.csv')
oppids = {r['id_opportunita'] for r in opp}
print("== storico refs to missing opps:", sum(1 for r in sf if r['id_opportunita'] not in oppids))
# how many deals have a storico? do deals without data_chiusura but won have a storico entry into vinta?
byopp = collections.defaultdict(list)
for r in sf: byopp[r['id_opportunita']].append(r)
print("== deals with storico:", len(byopp), "of", len(opp))
def won(f):
    f=f.strip().lower(); return 'vinta' in f or f=='06' or 'rinnovato' in f or f=='r3' or f.startswith('r3')
nocd = [r for r in opp if won(r['fase']) and not r['data_chiusura'] and not is_del(r['cancellato'])]
print("== live won deals w/o data_chiusura:", len(nocd), "of which with storico entry into won:", sum(1 for r in nocd if any(won(s['fase_nuova']) for s in byopp.get(r['id_opportunita'], []))))
for r in nocd[:5]:
    print("   ", r['id_opportunita'], r['titolo'], r['pipeline'], r['fase'], r['ultima_modifica'])
    for s in byopp.get(r['id_opportunita'], []): print("        ", s)
# closed lost no closedate
def lost(f):
    f=f.strip().lower(); return 'persa' in f or f=='07' or 'non rinnovato' in f or f.startswith('r4')
nocl = [r for r in opp if lost(r['fase']) and not r['data_chiusura'] and not is_del(r['cancellato'])]
print("== live lost deals w/o data_chiusura:", len(nocl), "with storico into lost:", sum(1 for r in nocl if any(lost(s['fase_nuova']) for s in byopp.get(r['id_opportunita'], []))))
# open deals with data_chiusura?
print("== live open deals WITH data_chiusura:", sum(1 for r in opp if not won(r['fase']) and not lost(r['fase']) and r['data_chiusura'] and not is_del(r['cancellato'])))
# rinnovi: "annual" - check closedate vs title year; deals in rinnovi w/o closedate
rin = [r for r in opp if 'rinnov' in r['pipeline'].lower() and not is_del(r['cancellato'])]
print("== live rinnovi:", len(rin), "w/o closedate:", sum(1 for r in rin if not r['data_chiusura']), "won:", sum(1 for r in rin if won(r['fase'])), "won w/o closedate:", sum(1 for r in rin if won(r['fase']) and not r['data_chiusura']))
print("== rinnovi titles:", collections.Counter(re.sub(r'\d{4}','YYYY',r['titolo']).split(' ')[0] for r in rin).most_common(10))
print("== sample rinnovi:", [(r['titolo'], r['importo'], r['fase'], r['data_chiusura']) for r in rin[:10]])
# does storico have multiple won entries for same deal (renewed each year?)
multi = sum(1 for k,v in byopp.items() if sum(1 for s in v if won(s['fase_nuova']))>1)
print("== deals with >1 storico entries into won:", multi)
ex = [k for k,v in byopp.items() if sum(1 for s in v if won(s['fase_nuova']))>1][:3]
for k in ex:
    o = next(r for r in opp if r['id_opportunita']==k)
    print("   ", o['titolo'], o['pipeline'], o['fase'], o['data_chiusura'], o['importo'])
    for s in sorted(byopp[k], key=lambda s:s['data_cambio']): print("        ", s)
