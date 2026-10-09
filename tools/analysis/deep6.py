import csv, sys, re, collections, unicodedata
from pathlib import Path
base = Path(sys.argv[1])
def rows(name):
    with open(base/name, encoding='cp1252', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
def is_del(v): return v.strip().lower() in ('s','si','sì','1')
opp = rows('opportunita.csv')
print("== importo with letters other than currency:")
odd = collections.Counter(re.sub(r'[\d.,\s€$£-]','',r['importo']) for r in opp)
for k,n in odd.most_common(): print(f"   {n:6d} {k!r}")
ex = [r for r in opp if 'mens' in r['importo'].lower()]
print("== 'mensili' examples:", [(r['titolo'], r['importo'], r['pipeline'], r['fase']) for r in ex[:8]])
print("== mensili by pipeline:", collections.Counter(r['pipeline'].strip().lower() for r in ex))
print("== other suffix examples:", [(r['titolo'], r['importo'], r['pipeline']) for r in opp if re.search(r'[A-Za-z]', r['importo'].replace('EUR','').replace('USD','').replace('GBP','')) and 'mens' not in r['importo'].lower()][:10])
# negative formats
print("== negative shapes:", collections.Counter(re.sub(r'\d+','9',r['importo']) for r in opp if '-' in r['importo']).most_common(20))
# user name resolution
users = rows('utenti.csv')
def norm(s): return unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower().strip()
byname = {}
for u in users:
    n, c = norm(u['nome']), norm(u['cognome'])
    for key in (f"{n} {c}", f"{c} {n}", f"{n[0]}. {c}", f"{c} {n[0]}."):
        byname.setdefault(key, []).append(u['id_utente'])
amb = {k:v for k,v in byname.items() if len(v)>1}
print("== ambiguous name keys:", amb)
unres = collections.Counter()
for r in opp:
    v = r['id_commerciale'].strip()
    if v and not re.fullmatch(r'U\d+', v):
        k = norm(v)
        if k not in byname: unres[v]+=1
        elif len(byname[k])>1: unres['AMBIG:'+v]+=1
print("== unresolved names:", unres)
print("== id_commerciale 'U..' not in users:", collections.Counter(r['id_commerciale'] for r in opp if re.fullmatch(r'U\d+', r['id_commerciale']) and r['id_commerciale'] not in {u['id_utente'] for u in users}))
# tickets
tk = rows('ticket.csv')
print("== ticket id_utente shapes:", collections.Counter(re.sub(r'\d','9',r['id_utente']) for r in tk))
da = [r for r in tk if r['descrizione'].startswith('Da:')]
print("== tickets with 'Da:' prefix:", len(da), "of which id_contatto empty:", sum(1 for r in da if not r['id_contatto']), "id_azienda empty:", sum(1 for r in da if not r['id_azienda']))
print("== tickets id_contatto empty total:", sum(1 for r in tk if not r['id_contatto']), " of these with Da::", sum(1 for r in tk if not r['id_contatto'] and r['descrizione'].startswith('Da:')))
ct = rows('contatti.csv')
EMAIL = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
emails = collections.defaultdict(list)
for r in ct:
    e = r['email'].strip().lower()
    if EMAIL.match(e) and not is_del(r['cancellato']): emails[e].append(r)
hit = miss = 0
for r in da:
    m = re.match(r'Da:\s*(\S+)', r['descrizione'])
    e = m.group(1).strip().lower()
    if e in emails: hit+=1
    else: miss+=1
print("== Da: email found among live contacts:", hit, "not found:", miss)
print("== Da: examples not found:", [re.match(r'Da:\s*(\S+)', r['descrizione']).group(1) for r in da if re.match(r'Da:\s*(\S+)', r['descrizione']).group(1).strip().lower() not in emails][:5])
# Da: tickets where id_contatto nonempty: does the email match that contact?
byid = {r['id_contatto']: r for r in ct}
agree = disagree = 0
for r in da:
    if r['id_contatto'] and r['id_contatto'] in byid:
        e = re.match(r'Da:\s*(\S+)', r['descrizione']).group(1).strip().lower()
        if byid[r['id_contatto']]['email'].strip().lower() == e: agree+=1
        else: disagree+=1
print("== Da: with id_contatto: agree", agree, "disagree", disagree)
print("== ticket descrizione multi-line with Da: - first line only?", [r['descrizione'][:80] for r in da[:3]])
print("== ticket stato dist:", collections.Counter(r['stato'].strip().lower() for r in tk))
print("== ticket priorita dist:", collections.Counter(r['priorita'].strip().lower() for r in tk))
print("== tickets closed stato but no chiuso_il:", sum(1 for r in tk if r['stato'].strip().lower() in ('chiuso','risolto') and not r['chiuso_il']), " open with chiuso_il:", sum(1 for r in tk if r['stato'].strip().lower() not in ('chiuso','risolto') and r['chiuso_il']))
print("== ticket oggetto ws:", sum(1 for r in tk if r['oggetto']!=r['oggetto'].strip()))
# ticket refs to deleted/missing
az = rows('aziende.csv'); azl = {r['id_azienda'] for r in az if not is_del(r['cancellato'])}; azall = {r['id_azienda'] for r in az}
ctl = {r['id_contatto'] for r in ct if not is_del(r['cancellato'])}
print("== ticket id_azienda missing:", sum(1 for r in tk if r['id_azienda'] and r['id_azienda'] not in azall), "deleted:", sum(1 for r in tk if r['id_azienda'] in azall and r['id_azienda'] not in azl))
print("== ticket id_contatto missing:", sum(1 for r in tk if r['id_contatto'] and r['id_contatto'] not in byid), "deleted:", sum(1 for r in tk if r['id_contatto'] in byid and r['id_contatto'] not in ctl))
# activities refs
att = rows('attivita.csv')
oppl = {r['id_opportunita'] for r in opp if not is_del(r['cancellato'])}; oppall = {r['id_opportunita'] for r in opp}
print("== att id_contatto missing:", sum(1 for r in att if r['id_contatto'] and r['id_contatto'] not in byid), "deleted:", sum(1 for r in att if r['id_contatto'] in byid and r['id_contatto'] not in ctl))
print("== att id_opp missing:", sum(1 for r in att if r['id_opportunita'] and r['id_opportunita'] not in oppall), "deleted:", sum(1 for r in att if r['id_opportunita'] in oppall and r['id_opportunita'] not in oppl))
# inactive users
inactive = {u['id_utente'] for u in users if u['attivo'].strip().lower() in ('n','no')}
print("== inactive users:", len(inactive), " deals assigned to inactive:", sum(1 for r in opp if r['id_commerciale'] in inactive), " tickets:", sum(1 for r in tk if r['id_utente'] in inactive), " activities:", sum(1 for r in att if r['id_utente'] in inactive))
# 115 won deals w/o closedate w/o storico-won: look
sf = rows('storico_fasi.csv'); byopp = collections.defaultdict(list)
for s in sf: byopp[s['id_opportunita']].append(s)
def won(f):
    f=f.strip().lower(); return 'vinta' in f or f=='06' or 'rinnovato' in f and 'non' not in f or f=='r3' or f.startswith('r3')
nocd = [r for r in opp if won(r['fase']) and not r['data_chiusura'] and not is_del(r['cancellato']) and not any(won(s['fase_nuova']) for s in byopp[r['id_opportunita']])]
print("== won w/o closedate & w/o storico-won:", len(nocd))
for r in nocd[:4]:
    print("   ", r['id_opportunita'], r['titolo'], '|', r['pipeline'], '|', r['fase'], '|', r['ultima_modifica'])
    for s in sorted(byopp[r['id_opportunita']], key=lambda s: s['data_cambio'][6:10]+s['data_cambio'][3:5]+s['data_cambio'][:2]): print("        ", s['fase_precedente'], '->', s['fase_nuova'], s['data_cambio'])
# is the storico final stage == deal stage generally?
def nstage(f):
    f=f.strip().lower()
    for k,v in [('vinta','06'),('persa','07'),('contatto','01'),('qualifica','02'),('presentazione','03'),('decisione','04'),('contratto','05'),('non rinnovato','r4'),('rinnovato','r3'),('in trattativa','r2'),('da rinnovare','r1')]:
        if k in f: return v
    m = re.match(r'(0\d|r\d)', f); return m.group(1) if m else f
agree=dis=0; exs=[]
for r in opp:
    hist = sorted(byopp[r['id_opportunita']], key=lambda s: s['data_cambio'][6:10]+s['data_cambio'][3:5]+s['data_cambio'][:2]+s['data_cambio'][11:])
    if nstage(hist[-1]['fase_nuova']) == nstage(r['fase']): agree+=1
    else:
        dis+=1
        if len(exs)<5: exs.append((r['titolo'], r['fase'], r['data_chiusura'], [(s['fase_nuova'], s['data_cambio']) for s in hist]))
print("== storico last stage agrees with deal stage:", agree, "disagree:", dis)
for e in exs: print("   ", e)
# closedate vs storico date for won deals with closedate: same day?
same=diff=0; exs=[]
for r in opp:
    if won(r['fase']) and re.fullmatch(r'\d{2}/\d{2}/\d{4}', r['data_chiusura']):
        w = [s for s in byopp[r['id_opportunita']] if won(s['fase_nuova'])]
        if w:
            if w[0]['data_cambio'][:10] == r['data_chiusura']: same+=1
            else:
                diff+=1
                if len(exs)<4: exs.append((r['data_chiusura'], w[0]['data_cambio']))
print("== won closedate == storico won date:", same, "differs:", diff, exs)
