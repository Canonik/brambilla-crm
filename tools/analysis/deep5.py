import csv, sys, re, collections
from pathlib import Path
base = Path(sys.argv[1])
def rows(name):
    with open(base/name, encoding='cp1252', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
def is_del(v): return v.strip().lower() in ('s','si','sì','1')
lst = rows('listino.csv')
def norm_code(s):
    d = re.sub(r'\D','', s)
    return 'BF-' + d.zfill(5) if d else ''
codes = collections.defaultdict(list)
for r in lst: codes[norm_code(r['codice_articolo'])].append(r)
print("== listino distinct norm codes:", len(codes), "groups >1:", sum(1 for v in codes.values() if len(v)>1))
print("== digit lengths:", collections.Counter(len(re.sub(r'\D','',r['codice_articolo'])) for r in lst))
for k,v in [(k,v) for k,v in codes.items() if len(v)>1][:4]:
    print("  ", k)
    for r in v: print("      ", repr(r['codice_articolo']), r['descrizione'], r['unita'], r['prezzo_listino'], repr(r['cancellato']), r['ultima_modifica'])
# groups where all deleted / some deleted
print("== groups with deleted rows:", sum(1 for v in codes.values() if any(is_del(r['cancellato']) for r in v)), "all deleted:", sum(1 for v in codes.values() if all(is_del(r['cancellato']) for r in v)))
print("== groups >1 where latest row is deleted but another isn't:", sum(1 for v in codes.values() if len(v)>1 and is_del(max(v, key=lambda r: r['ultima_modifica'][6:10]+r['ultima_modifica'][3:5]+r['ultima_modifica'][0:2]+r['ultima_modifica'][11:])['cancellato']) and not all(is_del(r['cancellato']) for r in v)))
print("== descrizione differs within group:", sum(1 for v in codes.values() if len({r['descrizione'].strip() for r in v})>1))
print("== descrizione ws:", sum(1 for r in lst if r['descrizione']!=r['descrizione'].strip()))
ro = rows('righe_offerta.csv')
print("== righe codes digit len:", collections.Counter(len(re.sub(r'\D','',r['codice_articolo'])) for r in ro))
print("== righe codes matched in listino (any):", sum(1 for r in ro if norm_code(r['codice_articolo']) in codes), "of", len(ro))
livecodes = {k for k,v in codes.items() if not all(is_del(r['cancellato']) for r in v)}
print("== righe codes matched in live listino:", sum(1 for r in ro if norm_code(r['codice_articolo']) in livecodes))
print("== righe unmatched examples:", [r['codice_articolo'] for r in ro if norm_code(r['codice_articolo']) not in codes][:10])
opp = {r['id_opportunita']: r for r in rows('opportunita.csv')}
print("== righe with missing opp:", sum(1 for r in ro if r['id_opportunita'] not in opp), "deleted opp:", sum(1 for r in ro if r['id_opportunita'] in opp and is_del(opp[r['id_opportunita']]['cancellato'])))
print("== quantita unit suffixes:", collections.Counter(re.sub(r'[\d,.]+','',r['quantita']).strip() for r in ro).most_common())
print("== quantita non-integer:", [r['quantita'] for r in ro if re.search(r',\d*[1-9]', r['quantita'])][:10])
print("== sconto values:", collections.Counter(r['sconto'] for r in ro).most_common(45))
print("== prezzo empty count:", sum(1 for r in ro if not r['prezzo_unitario'].strip()))
print("== prezzo empty & code in listino:", sum(1 for r in ro if not r['prezzo_unitario'].strip() and norm_code(r['codice_articolo']) in codes))
# deals with line items: does importo equal sum? compare for a few
def num(s):
    s = s.strip().replace('€','').replace('EUR','').replace('USD','').replace('GBP','').replace('$','').replace('£','').strip()
    if not s: return None
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'): s = s.replace('.','').replace(',','.')
        else: s = s.replace(',','')
    elif ',' in s:
        s = s.replace(',','.') if len(s.split(',')[-1])<=2 else s.replace(',','')
    return float(s)
def disc(s):
    s = s.strip().replace('%','').strip()
    if not s: return 0.0
    v = num(s)
    return v*100 if v < 1 and '.' in s or (v<1 and ',' in s) else v
by = collections.defaultdict(list)
for r in ro: by[r['id_opportunita']].append(r)
match=mismatch=0; exs=[]
for oid, lines in list(by.items()):
    o = opp.get(oid)
    if not o or not o['importo'].strip(): continue
    tot = 0; ok=True
    for l in lines:
        q = num(re.sub(r'[^\d,.]','', l['quantita'])); p = num(l['prezzo_unitario']) if l['prezzo_unitario'].strip() else None
        if p is None:
            # use listino price
            g = codes.get(norm_code(l['codice_articolo']))
            if g: p = num(sorted(g, key=lambda r: r['ultima_modifica'][6:10]+r['ultima_modifica'][3:5]+r['ultima_modifica'][0:2]+r['ultima_modifica'][11:])[-1]['prezzo_listino'])
            else: ok=False; break
        d = disc(l['sconto'])
        tot += round(q*p*(1-d/100), 2)
    if not ok: continue
    imp = abs(num(o['importo']))
    if abs(round(tot,2) - imp) < 0.011: match+=1
    else:
        mismatch+=1
        if len(exs)<6: exs.append((oid, o['importo'], round(tot,2), [(l['quantita'], l['prezzo_unitario'], l['sconto']) for l in lines]))
print("== deals importo vs line total: match", match, "mismatch", mismatch)
for e in exs: print("   ", e)
print("== deals with lines but empty importo:", sum(1 for oid in by if oid in opp and not opp[oid]['importo'].strip()))
print("== sconto '0,03'-style fractions:", collections.Counter(r['sconto'] for r in ro if re.fullmatch(r'0[.,]\d+', r['sconto'])).most_common())
