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

Rulează testele și apoi serverul:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Dacă ai Node.js instalat, testele pentru previzualizarea din browser se rulează
cu `node --test tests/test_preview_urls.mjs tests/test_mirrored_video.mjs`.

La pornire, aplicația verifică prezența setărilor obligatorii și formatul
adresei Supabase. Acest control nu verifică încă accesul efectiv la Supabase
sau Google Drive. Oprește serverul cu `Ctrl+C`.

Uploadul acceptă imagini JPEG, PNG și WebP de cel mult 25 MB și video MP4 sau
WebM de cel mult 250 MB. Controlul actual al antetului video nu verifică dacă
întregul fișier poate fi redat.
Cererea completă de upload, inclusiv formularul, este limitată la 251 MB.
