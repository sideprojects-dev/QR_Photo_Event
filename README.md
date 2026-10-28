# QR Photo Event

## Pornire locală pe Windows

Proiectul folosește Python 3.13. Din folderul proiectului, în PowerShell:

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
```

Configurează local un fișier `.env` în folderul proiectului. `.env.example`
arată numele setărilor obligatorii, fără credențiale reale. `ADMIN_PASSWORD`
trebuie să fie o parolă unică de cel puțin 12 caractere. Fișierele `.env`,
`.venv` și credențialele Google sunt excluse din Git prin `.gitignore`.
`QR_ACCESS_SECRET` este un secret aleatoriu de cel puțin 32 de caractere,
păstrat doar în `.env` și în setările serverului unde rulează aplicația.
Schimbarea lui invalidează linkurile și codurile QR deja generate.

Rulează testele și apoi serverul:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Dacă ai Node.js instalat, testele pentru previzualizarea din browser se rulează
cu `node --test tests/test_preview_urls.mjs tests/test_mirrored_video.mjs tests/test_gallery_upload.mjs`.

La pornire, aplicația verifică prezența setărilor obligatorii și formatul
adresei Supabase. Acest control nu verifică încă accesul efectiv la Supabase
sau Google Drive. Oprește serverul cu `Ctrl+C`.

Uploadul acceptă imagini JPEG, PNG și WebP de cel mult 25 MB și video MP4 sau
WebM de cel mult 250 MB. Controlul actual al antetului video nu verifică dacă
întregul fișier poate fi redat.
Cererea completă de upload, inclusiv formularul, este limitată la 251 MB.
Serverul admite implicit cel mult 3 uploaduri simultane. Bugetul de ritm
pornește cu 30 de cereri și se reîncarcă apoi cu 120 de cereri pe minut.
Pe Render, limitele pot fi
configurate prin `UPLOAD_MAX_ACTIVE`, `UPLOADS_PER_MINUTE` și `UPLOAD_BURST`
(numere întregi pozitive). Cererile care depășesc limita primesc HTTP 429 și
`Retry-After`; invitații pot reîncerca manual, fără retransmitere automată.
Limitele sunt globale pentru fiecare proces, fără identificare după IP sau
codul QR, astfel încât invitații de pe aceeași rețea nu împart o cotă personală.
Cu mai multe procese sau instanțe, fiecare aplică propriile limite; pentru o
cotă comună ar fi necesar un coordonator extern.

Pentru verificarea manuală a consistenței unui singur eveniment, rulează
`python storage_consistency.py SLUG_EVENIMENT`. Scriptul citește înregistrările
Supabase și conținutul folderului Drive asociat, apoi raportează referințele
absente din foldere și fișierele fără referință. Nu modifică și nu șterge date.
Un fișier mutat în afara folderului sau adăugat manual poate apărea în raport;
verifică rezultatele înainte de orice intervenție.

Codurile QR se descarcă din panoul Admin al serverului pe care va fi folosită
aplicația. Codul permanent al locației duce la evenimentul ei activ. Linkul
conține un cod de acces și poate fi distribuit mai departe de oricine îl are.
Pagina, galeria, fișierele și încărcarea verifică acel cod la fiecare cerere.
Linkurile vechi, fără cod de acces, nu mai funcționează și trebuie regenerate.
Pe Render, URL-urile absolute din codurile QR folosesc variabila furnizată de
platformă `RENDER_EXTERNAL_URL` (HTTPS). Local, se folosește adresa cererii.
Pornirea din `Dockerfile` dezactivează jurnalul automat al cererilor Uvicorn;
erorile aplicației rămân vizibile.

## Activarea atomică a evenimentelor

Endpointul Admin de activare folosește funcția PostgreSQL din
`20261029_ATOMIC_EVENT_ACTIVATION.sql`. Crearea unui eveniment îl salvează mai
întâi cu statusul `archived`, apoi folosește aceeași funcție pentru activare.
Dacă funcția PostgreSQL eșuează, evenimentul nou și folderul său rămân
disponibile pentru verificare, iar evenimentul activ anterior nu este arhivat.
Dacă răspunsul RPC se pierde după commit, rezultatul este neclar: reîncarcă
lista înainte de a încerca din nou.

**Migrarea este obligatorie înainte de publicarea backendului nou.** Nu este
aplicată automat. Mai întâi, în SQL Editor Supabase, verifică schema reală
(`public.locations`: `id`, `slug`; `public.events`: `id`, `slug`, `location_id`,
`status`) și datele existente, folosind interogări numai de citire:

```sql
select table_name, column_name, data_type, udt_name
from information_schema.columns
where table_schema = 'public' and table_name in ('locations', 'events')
order by table_name, ordinal_position;

select indexname, indexdef from pg_indexes
where schemaname = 'public' and tablename = 'events';

select location_id, count(*) from public.events
where status = 'active' and location_id is not null
group by location_id having count(*) > 1;

select slug, count(*) from public.events
group by slug having count(*) > 1;

select e.id, e.slug from public.events e
left join public.locations l on l.id = e.location_id
where e.location_id is not null and l.id is null;
```

Dacă schema diferă sau oricare dintre interogările pentru duplicate ori
locații lipsă întoarce rânduri, oprește migrarea și revizuiește datele; scriptul
nu le corectează. Dacă există deja indexuri echivalente, revizuiește scriptul
înainte de aplicare pentru a evita indexuri redundante.

Într-o fereastră fără operații Admin de creare sau activare, aplică întregul
fișier SQL ca o singură tranzacție. Verifică apoi că funcția există și că
rolurile publice nu o pot executa:

```sql
select
  has_function_privilege('anon', 'public.activate_event_atomic(text,text)', 'EXECUTE') as anon_can_execute,
  has_function_privilege('authenticated', 'public.activate_event_atomic(text,text)', 'EXECUTE') as user_can_execute,
  has_function_privilege('service_role', 'public.activate_event_atomic(text,text)', 'EXECUTE') as service_can_execute;
```

Primele două valori trebuie să fie `false`, iar ultima `true`. Abia apoi
publică backendul. Nu activa evenimente prin vechea versiune a aplicației în
intervalul dintre migrare și deployment: vechea creare încă folosește două
apeluri Supabase separate. Indexul unic împiedică două evenimente active în
aceeași locație, iar funcția blochează doar rândul locației vizate, astfel că
activările din locații diferite pot continua independent.

Testele PostgreSQL locale din `tests/test_atomic_event_postgres.py` folosesc o
schemă minimă cu coloanele întâlnite în cod. Ele pornesc numai dacă există un
container `postgres:16-alpine` numit `qr-h6-pg-test`, fără rețea, porturi sau
volume conectate la gazdă. Creează și elimină baze de date temporare numai în
acel container. De exemplu, în PowerShell:

```powershell
docker run --rm --name qr-h6-pg-test --network none -e POSTGRES_PASSWORD=local-h6-only -d postgres:16-alpine
$env:H6_PG_CONTAINER = 'qr-h6-pg-test'
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p test_atomic_event_postgres.py -v
Remove-Item Env:H6_PG_CONTAINER
docker stop qr-h6-pg-test
```

Aceste teste confirmă comportamentul în PostgreSQL, dar nu confirmă că schema
reală sau permisiunile proiectului Supabase sunt identice. Verificările de
mai sus rămân obligatorii înainte de aplicarea migrării.

## Reautorizarea Google Drive

Dacă fotografiile din galerie dau eroare și conexiunea Google raportează
`invalid_grant`, oprește Uvicorn cu `Ctrl+C`, apoi rulează local:

```powershell
& '.\.venv\Scripts\python.exe' reauthorize_drive.py
```

Se deschide autentificarea Google. Alege contul care deține fișierele din Drive.
Scriptul verifică accesul și salvează noul token numai în `.env`, apoi trebuie
repornit Uvicorn. Scriptul folosește temporar portul din `REDIRECT_URI`, de
aceea Uvicorn trebuie oprit. Dacă aplicația rulează și pe Render, variabila
`GOOGLE_DRIVE_TOKEN_JSON` de acolo trebuie actualizată separat. Vechile rute
`/auth/login` și `/auth/callback` nu mai sunt folosite.
