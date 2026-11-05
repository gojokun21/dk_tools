# DK Tools

Aplicatie Frappe pentru ERPNext v16, facuta pentru Demo Kit SRL. Firma cumpara componente, asambleaza din ele kituri cu senzor de temperatura (KIT-TEMP) si le vinde, iar unele comenzi includ si instalarea la client.

Aplicatia rezolva trei lucruri:

- cand se confirma o comanda care contine serviciul de instalare, se creeaza automat un **Installation Request** pentru tehnician;
- comenzile **peste 10.000 RON** nu le poate confirma vanzatorul singur, ele trebuie aprobate de un Sales Manager;
- tehnicianul are rolul lui (**Installation Technician**): vede cererile de instalare si raportul cu ce are de facut, dar nu vede comenzi sau facturi.

E proiectul meu de onboarding (8 zile). Am lucrat pe trei site-uri:

- `dk.localhost`, unde am facut totul manual, din interfata;
- `dk-api.localhost`, pentru scriptul de seed;
- `final.localhost`, site-ul curat de la final, unde am verificat ca totul vine din aplicatie.

## Instalare

Ai nevoie de un bench Frappe v16 care are deja ERPNext. Din folderul `frappe-bench`:

```bash
bench get-app https://github.com/gojokun21/dk_tools --branch main

bench new-site final.localhost --mariadb-user-host-login-scope=% \
      --db-root-password <parola-root-mariadb> --admin-password <parola-admin>

bench --site final.localhost install-app erpnext
bench --site final.localhost install-app dk_tools
```

`--mariadb-user-host-login-scope=%` e necesar in Docker, altfel site-ul nu se poate conecta la baza de date.

Dupa instalare intri pe site si treci prin Setup Wizard: Romania, RON, compania **Demo Kit SRL** cu abrevierea **DK**. In v16 wizard-ul te pune sa-ti creezi si un cont, iar la final esti logat cu el, nu cu Administrator.

Nu mai trebuie configurat nimic de mana. Rolul, campurile de pe Sales Order, workflow-ul, Client Script-ul si raportul vin toate din aplicatie, la `install-app`.

La mine site-ul se deschide pe portul **8100** (`http://final.localhost:8100`), pentru ca pe Windows 8000 e ocupat de XAMPP. In container serverul ramane pe 8000.

## Seed

Scriptul `scripts/seed.py` umple un site gol cu tot ce am facut manual in primele zile, prin REST API. Datele sunt in `scripts/seed_data.json`.

1. Te loghezi ca **Administrator**, deschizi userul, sectiunea **API Access** si apesi **Generate Keys**. Secretul apare o singura data, deci il copiezi pe loc.
2. Copiezi `scripts/.env.example` in `scripts/.env` si completezi:
   - `ERP_URL`: adresa site-ului. Din Windows e `http://final.localhost:8100`, din container e `http://final.localhost:8000`.
   - `ERP_KEY` si `ERP_SECRET`: cheile de la pasul 1.
   - `DEMO_PASSWORD`: parola pentru cei trei useri demo, ca sa poti intra cu ei in browser.
3. Rulezi scriptul (ai nevoie de Python 3 si `requests`):

```bash
python scripts/seed.py
```

`.env` si `seed_state.json` sunt in `.gitignore`. Cheile nu ajung niciodata in git.

**Ce creeaza scriptul:**

- master data: UOM, grupe de articole, depozite, articole, furnizori, clienti si BOM-ul pentru KIT-TEMP;
- trei useri demo:

| User | Roluri | Pentru ce |
|---|---|---|
| `vanzari@demokit.local` | Sales User | face comenzile si le trimite la aprobare |
| `manager@demokit.local` | Sales User, Sales Manager | aproba comenzile mari |
| `tehnician@demokit.local` | Installation Technician | vede cererile de instalare |

- tranzactiile **P1, P2** (cumparare), **M1** (productie) si **S1, S2, S3** (vanzare). S3 trece prin aprobare: o trimite `vanzari@`, o aproba `manager@`.

Scriptul poate fi rulat de cate ori vrei. Master data o cauta dupa nume inainte s-o creeze. Pentru tranzactii tine minte in `seed_state.json` ce document a creat la fiecare pas, separat pe fiecare site. A doua rulare doar afiseaza `exista deja` si nu dubleaza nimic.

La final compara rezultatul cu cifrele asteptate (13 verificari):

- stocul: 30 din fiecare componenta in Materii Prime, 5 KIT-TEMP in Produse Finite si nimic ramas in Lucru in Curs;
- de incasat: Alfa Tech 0, Beta Industries 2.250 RON; de platit la furnizori: 0;
- comanda S1 are un Installation Request;
- comanda S3 e aprobata (docstatus 1), are 13.500 RON si nu e livrata.

Daca totul e bine, scrie `REZULTAT: toate verificarile au trecut`.

## Fluxul de business

Desenul complet, cu ce document misca stocul si ce document misca doar contabilitatea, e in [docs/flux.md](docs/flux.md). Pe scurt:

**Cumparare (Procure-to-Pay).** Cumparam cate 50 din fiecare componenta.

- **P1:** placa, senzorul si cablul de la Electro Parts SRL, pornind de la un Material Request.
- **P2:** carcasa de la Plastix SRL, direct cu Purchase Order.

La amandoua urmeaza Purchase Receipt (marfa intra in Materii Prime), Purchase Invoice si plata.

**Productie (M1).** Un kit are 4 componente, cate una din fiecare, deci costa 150 RON. Work Order-ul e pe 20 de kituri. Primul Stock Entry muta componentele din Materii Prime in Lucru in Curs. Al doilea (Manufacture) le consuma si scoate 20 de KIT-TEMP in Produse Finite.

**Vanzare (Order-to-Cash).**

- **S1, Alfa Tech:** Quotation, apoi Sales Order cu 10 kituri plus instalarea, livrare, factura de 4.800 RON, platita. Pentru ca are instalare, la confirmarea comenzii apare singur Installation Request-ul.
- **S2, Beta Industries:** 5 kituri, livrate si facturate (2.250 RON), dar inca neplatite.
- **S3, Gamma Lab:** 30 de kituri, 13.500 RON. E peste 10.000, deci trece prin aprobarea managerului. Nu e livrata.

La final raman 30 din fiecare componenta (50 - 20) si 5 kituri (20 - 10 - 5). Beta ne datoreaza 2.250, iar noi nu datoram nimic furnizorilor.

## Ce contine aplicatia

| Ce | Unde | Ce face |
|---|---|---|
| DocType **Installation Request** | `dk_tools/dk_tools/doctype/installation_request/` | cererea de instalare: client, comanda, status (Open / Scheduled / Done / Cancelled), data programata, tehnician, notite. Serie `INST-.YYYY.-.#####` |
| Campuri custom pe Sales Order | fixture `3_custom_field.json` | `requires_installation` (bifa, read-only) si `installation_notes` (apare doar cand comanda are instalare) |
| doc_events pe Sales Order | `dk_tools/events/sales_order.py` | `validate` bifeaza `requires_installation` daca un articol e din grupa Servicii. `before_submit` blocheaza confirmarea care ocoleste workflow-ul. `on_submit` creeaza Installation Request-ul cu notitele din comanda |
| Workflow **Sales Order Approval** | fixtures 5, 6, 7 | pana in 10.000 RON vanzatorul face Submit direct. Peste, face Send for Approval (Pending Approval) si managerul da Approve sau Reject |
| Rol **Installation Technician** | fixtures 1 si 2 | citeste, modifica si vede raportul pe Installation Request (nu poate crea cereri) si poate citi clientii |
| Client Script | fixture `4_client_script.json` | face notitele obligatorii cand comanda are instalare. Pe comanda confirmata pune butonul **Installation Requests**, care deschide cererile acelei comenzi |
| Script Report **Installation Backlog** | `dk_tools/dk_tools/report/installation_backlog/` | cererile care nu sunt Done sau Cancelled, ordonate dupa data programata, cu filtre pe status si tehnician. Respecta permisiunile userului |
| Fixtures | `dk_tools/fixtures/` + `hooks.py` | exportate cu `bench export-fixtures`. Cu `fixture_auto_order = True` se importa in ordinea din `hooks.py` (1_ ... 7_) |
| Seed | `scripts/` | `seed.py`, `seed_data.json`, `.env.example` |

## Ce am invatat / ce m-a surprins

**Workflow-ul nu te opreste daca dai submit prin API.** Documentul de la inceput spunea ca `frappe.client.submit` pe o comanda cu workflow activ da eroare. In v16 nu da. Frappe pune singur starea "Approved" si comanda de 13.500 RON e confirmata fara manager. Am inchis portita cu un `before_submit` care cere `workflow_state == "Approved"`. In seed am trecut pe `frappe.model.workflow.apply_workflow`, adica exact ce face butonul din meniul Actions. Seed-ul vechi a picat dupa asta cu 417, si de fapt asta era dovada ca merge.

**Role Permission Manager copiaza tot.** Cand i-am dat tehnicianului drept de citire pe Customer, Frappe a copiat toate regulile standard de pe Customer in Custom DocPerm. Daca exportam doar randul tehnicianului, pe un site nou celelalte roluri ramaneau fara acces la clienti. De aceea fixture-ul ia tot ce are `parent = Customer` (24 de randuri). Pe `final.localhost` am verificat ca vanzatorul vede in continuare toti clientii.

**Prefixul `custom_`.** In v16, in Customize Form nu poti scrie fieldname-ul, iar serverul pune singur `custom_` in fata. Mi-a iesit `custom_requires_installation` si l-am redenumit cu butonul **Rename Fieldname**, pentru ca tot codul foloseste `requires_installation`.

**Ordinea la fixtures conteaza.** Alfabetic, `workflow.json` s-ar importa inaintea starilor si actiunilor de care are nevoie. Cu `fixture_auto_order = True` fisierele primesc prefix in ordinea din `hooks.py`. Am mai aflat ca `export-fixtures` nu sterge fisierele vechi, asa ca le-am sters eu inainte de export.

**Starile din workflow trebuie sa fie exact cele bune.** Am ales din greseala starea "Pending" in loc de "Pending Approval" si am primit `Pending Approval not a valid State`. Tot acolo lasasem "Approved" cu doc_status 0, deci aprobarea nu confirma de fapt comanda. Si actiunea "Submit" nu exista pe site, a trebuit s-o creez in Workflow Action Master.

**Browserul tine minte formularul vechi.** Dupa ce am activat workflow-ul, Sales Order dadea `Field workflow_state not found`. Nu era nimic stricat, doar tab-ul avea inca definitia veche a formularului. Ctrl+Shift+R a rezolvat.

**Raportul.** Prima data l-am salvat ca Report Builder, pe "Installation Note" (care e DocType-ul din ERPNext, nu al meu) si cu rolul Sales User pus automat. Corect e:

- Script Report pe Installation Request;
- Is Standard = Yes, ca sa ajunga in aplicatie;
- fara roluri, pentru ca accesul vine din permisiunea Report pe Installation Request. Fara bifa Report, tehnicianul nu-l poate deschide.

L-am cautat si la `/desk/build/report/...`, care e doar pagina de setari. Raportul propriu-zis e la `/desk/query-report/Installation Backlog`.

**Docker pe Windows.** Fisierele salvate din Windows apareau in container ca executabile, iar git-ul le vedea modificate fara sa fi schimbat nimic in ele. Am setat `core.fileMode false` si le-am readus la 100644. Tot la mediu am mai invatat doua lucruri:

- `default_site` facea ca `bench serve` sa serveasca un singur site, asa ca l-am scos;
- portul din container (8000) nu e acelasi cu cel de pe Windows (8100), si asta conteaza la `ERP_URL`.

**Plata in avans la S1.** Cand am facut fluxul manual, am inregistrat plata din Sales Order (ca avans), iar pe factura am folosit **Get Advances Received**. Iese la fel, Alfa nu mai datoreaza nimic, dar asa am inteles cum se leaga plata de factura.

## Licenta

MIT
