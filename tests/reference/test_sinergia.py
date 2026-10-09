"""Unit tests pinning the parsing rules of the reference migration (no server, no network)."""
from decimal import Decimal

import pytest

from tests.reference import sinergia as S


@pytest.mark.parametrize("raw,expected", [
    ("488210,35", "488210.35"), ("€ -5.131,24", "-5131.24"), ("€24,376.08", "24376.08"),
    ("1,004,693.23", "1004693.23"), ("1.247.204,29", "1247204.29"), ("EUR 3425.95", "3425.95"),
    ("€206,5k", "206500.00"), ("6.5mila", "6500.00"), ("152.5 mila", "152500.00"), ("1,4 Mln", "1400000.00"),
    ("€8mila", "8000.00"), ("€ 9k", "9000.00"), ("$ 772K", "772000.00"), ("2 mln", "2000000.00"),
    ("(20020,40)", "-20020.40"), ("4,086.16-", "-4086.16"), ("- 21.527,35", "-21527.35"),
    ("51.315,91 mensili", "615790.92"), ("500,59 /mese", "6007.08"), ("€ 1,641.59 al mese", "19699.08"),
    ("€ 77.505,65/mese", "930067.80"), ("112,98", "112.98"), ("1,732.87", "1732.87"), ("", None),
])
def test_parse_money(raw, expected):
    got = S.parse_money(raw)
    assert (None if got is None else str(got)) == expected


@pytest.mark.parametrize("valuta,importo,expected", [
    ("EUR", "1", "EUR"), ("Euro", "1", "EUR"), ("€", "1", "EUR"), ("eur", "1", "EUR"),
    ("USD", "1", "USD"), ("usd", "1", "USD"), ("$", "1", "USD"), ("gbp", "1", "GBP"), ("£", "1", "GBP"),
    ("", "USD 184246,02", "USD"), ("", "$1.412.837,37", "USD"), ("", "£ 10", "GBP"), ("", "GBP 10", "GBP"),
    ("", "€ 10", "EUR"), ("", "10", "EUR"),
])
def test_parse_currency(valuta, importo, expected):
    assert S.parse_currency(valuta, importo) == expected


@pytest.mark.parametrize("raw,expected", [
    ("18/01/2015", "2015-01-18T00:00:00Z"), ("2018-05-17", "2018-05-17T00:00:00Z"), ("20-04-2017", "2017-04-20T00:00:00Z"),
    ("42466", "2016-04-06T00:00:00Z"), ("45570", "2024-10-05T00:00:00Z"), ("04.09.18", "2018-09-04T00:00:00Z"),
    ("25/03/2014 00:00:00", "2014-03-25T00:00:00Z"), ("7/11/2022", "2022-11-07T00:00:00Z"), ("19/9/2015", "2015-09-19T00:00:00Z"),
    ("17/08/2021 09:02", "2021-08-17T09:02:00Z"), ("2024-08-17 12:14:15", "2024-08-17T12:14:15Z"),
    ("05/02/2016 19:18:50", "2016-02-05T19:18:50Z"), ("", None), ("non una data", None),
])
def test_parse_dt(raw, expected):
    assert S.iso(S.parse_dt(raw)) == expected


@pytest.mark.parametrize("raw,expected", [
    ("06 - Vinta", ("sales", "06")), ("06", ("sales", "06")), ("06 VINTA", ("sales", "06")), (" vinta", ("sales", "06")),
    ("Vinta", ("sales", "06")), ("07 PERSA", ("sales", "07")), ("Persa", ("sales", "07")), ("01 - Contatto", ("sales", "01")),
    (" contatto", ("sales", "01")), ("Contratto", ("sales", "05")), ("05 CONTRATTO", ("sales", "05")),
    ("02 QUALIFICA", ("sales", "02")), ("Qualifica", ("sales", "02")), ("03", ("sales", "03")), ("Presentazione", ("sales", "03")),
    ("04 - Decisione", ("sales", "04")), ("Decisione", ("sales", "04")),
    ("R1", ("renewals", "r1")), ("r1", ("renewals", "r1")), ("R1 - Da rinnovare", ("renewals", "r1")), ("DA RINNOVARE", ("renewals", "r1")),
    ("R2 - In trattativa", ("renewals", "r2")), ("IN TRATTATIVA", ("renewals", "r2")), ("r3", ("renewals", "r3")),
    ("Rinnovato", ("renewals", "r3")), ("RINNOVATO", ("renewals", "r3")), ("R4 - Non rinnovato", ("renewals", "r4")),
    ("Non rinnovato", ("renewals", "r4")), ("NON RINNOVATO", ("renewals", "r4")), ("", None),
])
def test_parse_stage(raw, expected):
    assert S.parse_stage(raw) == expected


def test_parse_pipeline():
    assert S.parse_pipeline("vendite ", ("sales", "01")) == "sales"
    assert S.parse_pipeline("RINNOVI", ("renewals", "r1")) == "renewals"
    assert S.parse_pipeline("", ("renewals", "r3")) == "renewals"
    assert S.parse_pipeline("", ("sales", "06")) == "sales"
    assert S.parse_pipeline("", None) == "sales"


@pytest.mark.parametrize("raw,expected", [
    ("www.nuovaimpiantibenedetti.eu", "nuovaimpiantibenedetti.eu"), ("http://www.trasportiperego.it/", "trasportiperego.it"),
    ("https://nuovacablagginegri.it", "nuovacablagginegri.it"), ("WWW.Officinefarina13.it", "officinefarina13.it"),
    ("https://www.ferriforniturenovara.com/it/home", "ferriforniturenovara.com"), ("SIRONIGROUP53.IT", "sironigroup53.it"), ("", ""),
])
def test_norm_domain(raw, expected):
    assert S.norm_domain(raw) == expected


@pytest.mark.parametrize("note,expected", [
    ("pagamento 60gg DF FM, partita iva 84874 281912", "84874281912"),
    ("P. IVA: IT 40969350707; cliente storico", "40969350707"),
    ("PI: 34340014470", "34340014470"),
    ("P.IVA 67105837370; sconto 3%", "67105837370"),
    ("referente amm.ne sig.ra Colombo, p.iva IT11476373136", "11476373136"),
    ("sconto 3% su ordini > 5.000; PI: 73176170824; referente", "73176170824"),
    ("cliente storico, referente amm.ne sig.ra Colombo", None), ("", None),
])
def test_extract_vat(note, expected):
    assert S.extract_vat(note) == expected


@pytest.mark.parametrize("raw,expected", [
    ("e.bellini@libero.it", "e.bellini@libero.it"), ("ROBERTOPOZZI@VALSECCHIMARTINELLI36.IT", "robertopozzi@valsecchimartinelli36.it"),
    (" pagani.franco@outlook.it  ", "pagani.franco@outlook.it"), ("alessia.vitale(at)gmail.com", None),
    ("beatrice.testa @libero.it", None), ("nessuna", None),
    ("NO EMAIL", None), ("n.d.", None), ("da chiedere", None), ("-", None), ("irene.bellini@", None), ("riccardo.leone@gmail", None), ("", None),
])
def test_norm_email(raw, expected):
    assert S.norm_email(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("gallo.enrico@fratellinegri89.it e enrico.gallo@hotmail.it", ("gallo.enrico@fratellinegri89.it", ["enrico.gallo@hotmail.it"], None)),
    ("robertabellini@fratelligrasso67.it / roberta.bellini545@libero.it", ("robertabellini@fratelligrasso67.it", ["roberta.bellini545@libero.it"], None)),
    ("monica.dalo@fratellipanzeri46.it; monica.dalo@hotmail.it", ("monica.dalo@fratellipanzeri46.it", ["monica.dalo@hotmail.it"], None)),
    ("A@B.IT, nessuna", ("a@b.it", [], None)), ("x(at)y.it e y@z.it", ("y@z.it", [], None)),
    ("04/6074577", (None, [], "04/6074577")), ("+39 393 111 5646", (None, [], "+39 393 111 5646")),
    ("n.d.", (None, [], None)), ("", (None, [], None)),
])
def test_parse_email_field(raw, expected):
    assert S.parse_email_field(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("BF-62989", "BF-62989"), ("BF38295", "BF-38295"), (" BF-89712", "BF-89712"), ("art. 12345", "BF-12345"), ("55091", "BF-55091"),
    ("BF.49711", "BF-49711"), ("BF 7096", "BF-07096"), ("BF.537", "BF-00537"), ("bf-68456", "BF-68456"), ("", None),
])
def test_norm_sku(raw, expected):
    assert S.norm_sku(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("1 pz", "1"), ("20", "20"), ("2,5 kg", "2.5"), ("197,2 m", "197.2"), ("5 conf", "5"), ("20,00", "20"),
])
def test_parse_quantity(raw, expected):
    assert S.num_str(S.parse_quantity(raw)) == expected


@pytest.mark.parametrize("raw,expected", [
    ("", "0"), ("0", "0"), ("0%", "0"), ("15,0", "15"), ("10%", "10"), ("25 %", "25"), ("15", "15"),
    ("0,03", "3"), ("0.2", "20"), ("0,25", "25"), ("9,9", "9.9"), ("1", "1"), ("12,5%", "12.5"),
])
def test_parse_discount(raw, expected):
    assert S.num_str(S.parse_discount(raw)) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Societ\u00c3\u00a0 Verniciature", "Societ\u00e0 Verniciature"),   # UTF-8 bytes C3 A0 read as cp1252
    ("Errore di quantit\u00c3\u00a0", "Errore di quantit\u00e0"),        # trailing: must be repaired before strip
    ("Dal\u00c3\u00b2", "Dal\u00f2"), ("Cant\u00c3\u00b9", "Cant\u00f9"), ("D\u00c3\u00a9bora", "D\u00e9bora"),
    ("venerd\u00c3\u00ac", "venerd\u00ec"), ("Societ\u00e0 gi\u00e0 ok", "Societ\u00e0 gi\u00e0 ok"), ("Nuova Impianti", "Nuova Impianti"),
    ("", ""),
])
def test_fix_encoding(raw, expected):
    assert S.fix_encoding(raw) == expected


def test_load_export_repairs_mixed_rows(tmp_path):
    d = tmp_path / "exp"
    d.mkdir()
    for name in S.FILES:
        (d / f"{name}.csv").write_bytes(b"")
    (d / "aziende.csv").write_bytes(
        "id_azienda;ragione_sociale;sito_web;note;citta;provincia;cancellato;ultima_modifica\n".encode("cp1252")
        + "1;Societ\u00e0 Uno;;;Cant\u00f9;CO;;01/01/2020 10:00:00\n".encode("utf-8")
        + "2;Societ\u00e0 Due;;;Forl\u00ec;FC;;01/01/2020 10:00:00\n".encode("cp1252")
        + "3;Errore di quantit\u00e0;;;;;;01/01/2020 10:00:00\n".encode("utf-8")
    )
    for name in S.FILES:
        if name != "aziende":
            (d / f"{name}.csv").write_bytes(b"a;b\n")
    rows = S.load_export(d)["aziende"]
    assert [r["ragione_sociale"] for r in rows] == ["Societ\u00e0 Uno", "Societ\u00e0 Due", "Errore di quantit\u00e0"]
    assert [r["citta"] for r in rows] == ["Cant\u00f9", "Forl\u00ec", ""]


def test_truthy():
    for v in ["S", "s", "SI", "Sì", "1", " si "]:
        assert S.truthy(v)
    for v in ["", "0", "N", "NO", "n", "no"]:
        assert not S.truthy(v)


def test_users_resolve_names_and_initials():
    users = S.Users([
        {"id_utente": "U36", "nome": "Elisa", "cognome": "Mazza", "email": "elisa.mazza@x.it", "ruolo": "", "responsabile": "", "attivo": "s"},
        {"id_utente": "U41", "nome": "Paola", "cognome": "De Luca", "email": "paola.deluca@x.it", "ruolo": "", "responsabile": "", "attivo": "s"},
        {"id_utente": "U72", "nome": "Serena", "cognome": "Neri", "email": "serena.neri@x.it", "ruolo": "", "responsabile": "", "attivo": "NO"},
        {"id_utente": "U80", "nome": "Serena", "cognome": "Neri", "email": "s.neri@x.it", "ruolo": "", "responsabile": "", "attivo": "SI"},
        {"id_utente": "U24", "nome": "Débora", "cognome": "Pozzi", "email": "debora.pozzi@x.it", "ruolo": "", "responsabile": "", "attivo": "s"},
    ])
    assert users.resolve("U36")["id"] == "U36"
    assert users.resolve("Mazza E.")["id"] == "U36"
    assert users.resolve("Elisa Mazza")["id"] == "U36"
    assert users.resolve("De Luca Paola")["id"] == "U41"
    assert users.resolve("DE LUCA PAOLA")["id"] == "U41"
    assert users.resolve("Pozzi Débora")["id"] == "U24"
    assert users.resolve("pozzi debora")["id"] == "U24"
    assert users.resolve("Serena Neri")["id"] == "U80", "ambiguous name resolves to the active user"
    assert users.resolve("Serena Neri", {"U72"})["id"] == "U72", "unless the deal history names the other"
    assert users.resolve("Nessuno Qui") is None
    assert users.resolve("") is None


def test_migrate_small_fixture():
    data = {
        "utenti": [
            {"id_utente": "U01", "nome": "Anna", "cognome": "Sala", "email": "anna.sala@b.it", "ruolo": "", "responsabile": "", "attivo": "s"},
            {"id_utente": "U02", "nome": "Ex", "cognome": "Dipendente", "email": "ex@b.it", "ruolo": "", "responsabile": "", "attivo": "n"},
        ],
        "aziende": [
            {"id_azienda": "1", "ragione_sociale": " Alfa S.r.l. ", "sito_web": "www.alfa.it", "note": "PI: 11111111111", "citta": "Como", "provincia": "co", "cancellato": "", "ultima_modifica": "01/01/2020 10:00:00"},
            {"id_azienda": "2", "ragione_sociale": "Alfa", "sito_web": "https://alfa.it/", "note": "", "citta": "", "provincia": "", "cancellato": "0", "ultima_modifica": "01/01/2021 10:00:00"},
            {"id_azienda": "3", "ragione_sociale": "Alfa Group", "sito_web": "alfa-group.it", "note": "p.iva IT11111111111", "citta": "Lecco", "provincia": "LC", "cancellato": "N", "ultima_modifica": "01/01/2019 10:00:00"},
            {"id_azienda": "4", "ragione_sociale": "Beta", "sito_web": "beta.it", "note": "", "citta": "Milano", "provincia": "MI", "cancellato": "S", "ultima_modifica": "01/01/2022 10:00:00"},
            {"id_azienda": "5", "ragione_sociale": "Gamma", "sito_web": "gamma.it", "note": "", "citta": "Monza", "provincia": "MB", "cancellato": "", "ultima_modifica": "01/01/2022 10:00:00"},
        ],
        "contatti": [
            {"id_contatto": "10", "nome": "Luca", "cognome": "Bianchi", "email": "LUCA@alfa.it", "telefono": "", "id_azienda": "3", "tipo": "Cliente", "cancellato": "", "ultima_modifica": "01/01/2020 10:00:00"},
            {"id_contatto": "11", "nome": "Luca", "cognome": "Bianchi", "email": "luca@alfa.it", "telefono": "123", "id_azienda": "", "tipo": " lead ", "cancellato": "", "ultima_modifica": "01/01/2021 10:00:00"},
            {"id_contatto": "12", "nome": "Sara", "cognome": "Verdi", "email": "sara@gamma.it", "telefono": "", "id_azienda": "999999999", "tipo": "Prospect", "cancellato": "", "ultima_modifica": "01/01/2021 10:00:00"},
            {"id_contatto": "13", "nome": "Gone", "cognome": "Away", "email": "gone@gamma.it", "telefono": "", "id_azienda": "5", "tipo": "Cliente", "cancellato": "1", "ultima_modifica": "01/01/2021 10:00:00"},
            {"id_contatto": "14", "nome": "Alessia", "cognome": "Bianchi", "email": "alessia(at)gmma.it", "telefono": "", "id_azienda": "5", "tipo": "Lead", "cancellato": "", "ultima_modifica": "01/01/2020 10:00:00"},
            {"id_contatto": "15", "nome": " alessia ", "cognome": "BIANCHI", "email": "nessuna", "telefono": "02/111", "id_azienda": "5", "tipo": "Lead", "cancellato": "", "ultima_modifica": "01/01/2022 10:00:00"},
            {"id_contatto": "16", "nome": "Marco", "cognome": "Rossi", "email": "marco@uno.it", "telefono": "", "id_azienda": "5", "tipo": "Lead", "cancellato": "", "ultima_modifica": "01/01/2022 10:00:00"},
            {"id_contatto": "17", "nome": "Marco", "cognome": "Rossi", "email": "marco@due.it", "telefono": "", "id_azienda": "5", "tipo": "Lead", "cancellato": "", "ultima_modifica": "01/01/2022 10:00:00"},
            {"id_contatto": "18", "nome": "Marco", "cognome": "Rossi", "email": "", "telefono": "", "id_azienda": "", "tipo": "Lead", "cancellato": "", "ultima_modifica": "01/01/2022 10:00:00"},
            {"id_contatto": "19", "nome": "Due", "cognome": "Indirizzi", "email": "due@gamma.it e due@hotmail.it", "telefono": "", "id_azienda": "5", "tipo": "Lead", "cancellato": "", "ultima_modifica": "01/01/2022 10:00:00"},
            {"id_contatto": "20", "nome": "Due", "cognome": "Indirizzi", "email": "DUE@HOTMAIL.IT", "telefono": "", "id_azienda": "", "tipo": "Cliente", "cancellato": "", "ultima_modifica": "01/01/2023 10:00:00"},
            {"id_contatto": "21", "nome": "Tel", "cognome": "Solo", "email": "02/1234567", "telefono": "", "id_azienda": "", "tipo": "Lead", "cancellato": "", "ultima_modifica": "01/01/2023 10:00:00"},
        ],
        "opportunita": [
            {"id_opportunita": "100", "titolo": "Fornitura Alfa", "id_azienda": "2", "contatti": "10; 11, 13", "importo": "€ 100.000,00", "valuta": "", "pipeline": "Vendite", "fase": "06 - Vinta", "data_chiusura": "15/03/2025", "id_commerciale": "U01", "cancellato": "", "ultima_modifica": "01/01/2025 10:00:00"},
            {"id_opportunita": "101", "titolo": "Storno Alfa", "id_azienda": "1", "contatti": "", "importo": "(1.000,00)", "valuta": "EUR", "pipeline": "", "fase": "Vinta", "data_chiusura": "", "id_commerciale": "Sala Anna", "cancellato": "", "ultima_modifica": "01/01/2025 10:00:00"},
            {"id_opportunita": "102", "titolo": "Rinnovo Gamma", "id_azienda": "5", "contatti": "12", "importo": "1.000,00 mensili", "valuta": "USD", "pipeline": "rinnovi ", "fase": "R3", "data_chiusura": "2025-06-30", "id_commerciale": "U02", "cancellato": "", "ultima_modifica": "01/01/2025 10:00:00"},
            {"id_opportunita": "103", "titolo": "Con righe", "id_azienda": "5", "contatti": "", "importo": "999", "valuta": "", "pipeline": "vendite", "fase": "02", "data_chiusura": "", "id_commerciale": "", "cancellato": "", "ultima_modifica": "01/01/2025 10:00:00"},
            {"id_opportunita": "104", "titolo": "Cancellata", "id_azienda": "5", "contatti": "", "importo": "5", "valuta": "", "pipeline": "vendite", "fase": "06", "data_chiusura": "01/01/2025", "id_commerciale": "", "cancellato": "SI", "ultima_modifica": "01/01/2025 10:00:00"},
        ],
        "storico_fasi": [
            {"id_opportunita": "101", "fase_precedente": "05", "fase_nuova": " vinta", "data_cambio": "20/02/2025 09:00:00", "id_utente": "U01"},
        ],
        "listino": [
            {"codice_articolo": "BF-00001", "descrizione": "Vite", "unita": "pz", "prezzo_listino": "1,00", "cancellato": "", "ultima_modifica": "01/01/2020 10:00:00"},
            {"codice_articolo": "bf00001", "descrizione": "Vite M8", "unita": "pz", "prezzo_listino": "2,00", "cancellato": "", "ultima_modifica": "01/01/2021 10:00:00"},
        ],
        "righe_offerta": [
            {"id_riga": "500", "id_opportunita": "103", "codice_articolo": "art. 1", "descrizione": "", "quantita": "10 pz", "prezzo_unitario": "", "sconto": "0,1"},
            {"id_riga": "501", "id_opportunita": "103", "codice_articolo": "BF-99999", "descrizione": "Altro", "quantita": "3", "prezzo_unitario": "€ 2,50", "sconto": "50%"},
            {"id_riga": "502", "id_opportunita": "104", "codice_articolo": "BF-00001", "descrizione": "x", "quantita": "1", "prezzo_unitario": "1", "sconto": ""},
        ],
        "ticket": [
            {"id_ticket": "900", "oggetto": "Problema", "descrizione": "Da: sara@gamma.it\nNon funziona", "stato": "Risolto", "priorita": "URGENTE!!", "id_contatto": "", "id_azienda": "5", "aperto_il": "2025-01-02 10:00:00", "chiuso_il": "03/01/2025 11:00", "id_utente": "U02", "cancellato": "", "ultima_modifica": "x"},
        ],
        "attivita": [
            {"id_attivita": "7000", "tipo": "Tel.", "data": "10/01/2025 10:00", "testo": " chiamato ", "id_contatto": "10", "id_opportunita": "", "id_utente": "U02", "cancellato": ""},
            {"id_attivita": "7001", "tipo": "Appunto", "data": "2024-05-05 10:00:00", "testo": "nota", "id_contatto": "", "id_opportunita": "102", "id_utente": "U01", "cancellato": ""},
            {"id_attivita": "7002", "tipo": "Meeting", "data": "2025-05-05 10:00:00", "testo": "vecchia", "id_contatto": "", "id_opportunita": "104", "id_utente": "U01", "cancellato": ""},
        ],
    }
    ex = S.migrate(data)
    # companies: 1, 2, 3 merge (domain alfa.it links 1-2, VAT links 1-3); 4 deleted; 5 alone
    assert set(ex.companies) == {"2", "5"}
    alfa = ex.companies["2"]
    assert alfa["name"] == "Alfa" and alfa["domain"] == "alfa.it" and alfa["partita_iva"] == "11111111111"
    assert alfa["city"] == "Como" and alfa["state"] == "CO" and alfa["hs_additional_domains"] == "alfa-group.it"
    assert ex.merged_into["companies"] == {"1": "2", "2": "2", "3": "2", "5": "5"}
    # contacts: 10 and 11 merge on email, survivor 11 (newer); company from the most recent valid reference (10 -> 3 -> survivor 2)
    # 14+15 join by name inside company 5 (no valid email on either); 16 and 17 stay apart (two valid emails);
    # 18 has no company so it never joins by name; 19+20 join through the second address of 19
    assert set(ex.contacts) == {"11", "12", "15", "16", "17", "18", "20", "21"}
    assert ex.contacts["15"]["email"] is None and ex.contacts["15"]["phone"] == "02/111" and ex.merged_into["contacts"]["14"] == "15"
    assert ex.contacts["20"]["email"] == "due@hotmail.it" and ex.contacts["20"]["hs_additional_emails"] == "due@gamma.it"
    assert ex.contacts["20"]["lifecyclestage"] == "customer" and ex.contacts["20"]["_company"] == "5"
    assert ex.contacts["21"]["email"] is None and ex.contacts["21"]["phone"] == "02/1234567"
    assert ex.contacts["11"]["email"] == "luca@alfa.it" and ex.contacts["11"]["phone"] == "123" and ex.contacts["11"]["lifecyclestage"] == "lead"
    assert ("contacts", "11", "companies", "2") in ex.associations
    # R12: 12 has a dangling company and an email domain of company 5
    assert ("contacts", "12", "companies", "5") in ex.associations
    # deals
    assert set(ex.deals) == {"100", "101", "102", "103"}
    d = ex.deals["100"]
    assert d["amount"] == "100000.00" and d["deal_currency_code"] == "EUR" and d["dealstage"] == "closedwon" and d["pipeline"] == "default"
    assert d["commerciale"] == "anna.sala@b.it" and d["closedate"] == "2025-03-15T00:00:00Z"
    assert {t for (f, fl, tt, t) in ex.associations if f == "deals" and fl == "100" and tt == "contacts"} == {"11"}
    assert ex.deals["101"]["amount"] == "-1000.00" and ex.deals["101"]["closedate"] == "2025-02-20T09:00:00Z"
    assert ex.deals["101"]["commerciale"] == "anna.sala@b.it"
    r = ex.deals["102"]
    assert r["amount"] == "12000.00" and r["deal_currency_code"] == "USD" and r["_dealstage_label"] == "Rinnovato" and r["commerciale"] is None
    lines = ex.deals["103"]
    # line 500: qty 10, price from product 2.00, discount 10% -> 18.00; line 501: 3 x 2.50 x 0.5 = 3.75
    assert ex.line_items["500"]["name"] == "Vite M8" and ex.line_items["500"]["price"] == "2.00" and ex.line_items["500"]["amount"] == "18.00"
    assert ex.line_items["500"]["hs_discount_percentage"] == "10"
    assert ex.line_items["501"]["amount"] == "3.75" and ex.line_items["501"]["_product"] is None
    assert "502" not in ex.line_items
    assert lines["amount"] == "21.75" and lines["deal_currency_code"] == "EUR"
    assert ex.products["BF-00001"] == {"hs_sku": "BF-00001", "name": "Vite M8", "price": "2.00"}
    # ticket: contact from the Da: header, inactive assignee -> empty, priority URGENT, stage Chiuso
    t = ex.tickets["900"]
    assert t["_contact"] == "12" and t["assegnatario"] is None and t["hs_ticket_priority"] == "URGENT" and t["_stage_label"] == "Chiuso"
    assert t["createdate"] == "2025-01-02T10:00:00Z" and t["closed_date"] == "2025-01-03T11:00:00Z"
    # activities
    assert ex.calls["7000"]["hs_call_body"] == "chiamato" and ex.calls["7000"]["autore"] == "ex@b.it"
    assert ("calls", "7000", "contacts", "11") in ex.associations
    assert ex.notes["7001"]["_deal"] == "102" and ex.meetings["7002"]["_deal"] is None
    # R8: company 2 gets 100000 - 1000 = 99000 -> B; company 5 gets 12000 * 0.92 = 11040 -> C
    assert ex.companies["2"]["fatturato_2025"] == "99000.00" and ex.companies["2"]["classe_cliente"] == "B"
    assert ex.companies["5"]["fatturato_2025"] == "11040.00" and ex.companies["5"]["classe_cliente"] == "C"
    # R9: company 2 has a 2025 call on contact 11 -> not dormant; company 5 has only a 2024 note on its deal -> dormant
    assert ex.dormant == {"5"}
