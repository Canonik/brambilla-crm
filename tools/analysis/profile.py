import csv, sys, re, collections
from pathlib import Path
base = Path(sys.argv[1])
def rows(name):
    with open(base/name, encoding='cp1252', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
def shape(v):
    # replace digits with 9, letters with a, keep punctuation
    s = re.sub(r'[0-9]', '9', v)
    s = re.sub(r'[A-Za-zÀ-ÿ]', 'a', s)
    s = re.sub(r'a+', 'a', s); s = re.sub(r'9+', '9', s)
    return s
def profile(name, cols=None, topn=25, shape_cols=()):
    rs = rows(name)
    print(f"\n######## {name}: {len(rs)} rows; cols={list(rs[0].keys())}")
    for c in (cols or rs[0].keys()):
        vals = [r[c] for r in rs]
        cnt = collections.Counter(vals)
        empties = cnt.get('', 0)
        print(f"\n--- {c}: distinct={len(cnt)} empty={empties}")
        if c in shape_cols:
            sc = collections.Counter(shape(v) for v in vals)
            for k, n in sc.most_common(topn): 
                ex = next(v for v in vals if shape(v)==k)
                print(f"   SHAPE {n:7d}  {k!r}   e.g. {ex!r}")
        elif len(cnt) <= 60:
            for k, n in cnt.most_common(topn): print(f"   {n:7d}  {k!r}")
        else:
            for k, n in cnt.most_common(8): print(f"   {n:7d}  {k!r}")
            print("   sample:", [v for v in vals[:12]])
profile('utenti.csv')
profile('aziende.csv', shape_cols=('sito_web','ultima_modifica','id_azienda'))
profile('contatti.csv', shape_cols=('email','telefono','ultima_modifica','id_contatto','id_azienda'))
profile('opportunita.csv', shape_cols=('importo','data_chiusura','ultima_modifica','contatti','id_azienda','id_opportunita'))
profile('righe_offerta.csv', shape_cols=('codice_articolo','quantita','prezzo_unitario','sconto'))
profile('listino.csv', shape_cols=('codice_articolo','prezzo_listino','ultima_modifica'))
profile('ticket.csv', shape_cols=('aperto_il','chiuso_il','ultima_modifica','id_contatto','id_azienda'))
profile('attivita.csv', shape_cols=('data','id_contatto','id_opportunita'))
profile('storico_fasi.csv', shape_cols=('data_cambio',))
