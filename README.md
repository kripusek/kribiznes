# KriBusiness 1.1

Autorska, samodzielnie hostowana szkolna symulacja zarządzania firmą. Przypomina rundowe symulacje biznesowe w rodzaju REVAS pod względem sposobu prowadzenia zajęć, ale używa własnego kodu, wyglądu i jawnego modelu ekonomicznego. **To działająca pierwsza wersja, nie wierna kopia REVAS ani jego wszystkich branż i algorytmów.**

## Co działa

- Administrator zakłada konta nauczycieli; nauczyciel tworzy klasy/rozgrywki.
- Uczniowie rejestrują się kodem klasy, zakładają firmy lub dołączają kodem zespołu. W firmie jest do 5 osób z osobnymi loginami.
- Do 40 konkurujących firm, od 1 do 24 rund; miesiąc = jedna runda.
- Trzy parametryzowane scenariusze: agencja IT, restauracja, warsztat. Każdy ma trzy usługi, inne ceny, popyt, koszty, czasy pracy i cenę stanowiska.
- Oferta, ceny, plan realizacji, jakość, zatrudnienie, pensje, szkolenia, zakup stanowisk, marketing, kredyt i spłata.
- Trzy poziomy dostawców dla każdej usługi, trzy banki i dwa warianty księgowości. Ostrzeżenia o kosztach, jakości i niewystarczających zasobach.
- Raport przepływów pieniężnych oraz marży każdej usługi przed kosztami stałymi. Zabezpieczenie przed nadpisaniem nowszego planu zespołu starym formularzem.
- Szkic decyzji, kontrola budżetu, zatwierdzenie i cofnięcie zatwierdzenia przez członków zespołu.
- Jeden wspólny konkurencyjny rynek na klasę, ograniczona liczba klientów i moce realizacji usług.
- Nauczyciel ustawia kryzys, wzrost gospodarczy lub wzrost kosztów materiałów. Zmiana zdarzenia cofa zatwierdzenia, by zespoły mogły zmienić plany.
- Raport każdej rundy: sprzedaż, koszty, zysk, podatek, gotówka, kapitał własny, reputacja, roboczogodziny i wskazówki.
- Ranking, eksport CSV z wszystkich rund, historia działań, trwała baza SQLite.
- Upadłość firmy z niewystarczającą płynnością i wyłączanie jej z dalszej konkurencji.
- Hasła PBKDF2, sesje HttpOnly, CSRF, walidacja po stronie serwera, oddzielne uprawnienia, transakcje rozliczeń i odrzucanie starych formularzy rundy.

**Python 3.12+, bez dodatkowych paczek, bez Supabase, bez płatnej usługi.**

## Najszybciej: Pelican

1. Rozpakuj paczkę na swoim komputerze.
2. W panelu administratora Pelicana wybierz **Eggs → Import** i wgraj `deploy/egg-kribusiness.json` (format `PLCN_v3`).
3. Utwórz serwer z tym eggiem. Wybierz dostępny node i **jeden port TCP**, np. 8080. Zalecany start: 512 MB RAM, 1 GB dysku; wymagania dla konkretnej klasy należy sprawdzić na swoim serwerze.
4. Ustaw `ADMIN_USERNAME`, np. `admin`, i własne `ADMIN_PASSWORD` (minimum 12 znaków). Puste `GIT_REPOSITORY` oznacza instalację ręczną, więc nie potrzebujesz repozytorium GitHub.
5. Po zakończeniu instalacji w menedżerze plików serwera prześlij **zawartość** rozpakowanego katalogu projektu: `app.py`, `engine.py`, `manage.py` oraz cały katalog `static/`. Plik `app.py` musi być bezpośrednio w katalogu głównym serwera, nie wewnątrz dodatkowego `kribusiness/`.
6. Kliknij **Start**. Konsola powinna pokazać `KriBusiness ready on 0.0.0.0:TWÓJ_PORT`.
7. Otwórz `http://IP_SERWERA:TWÓJ_PORT` i zaloguj się danymi administratora. Potrzebne jest otwarte przekierowanie tego portu lub reverse proxy.
8. Utwórz nauczyciela albo jako administrator utwórz rozgrywkę. Przekaż uczniom adres `http://IP_SERWERA:TWÓJ_PORT/join` oraz kod klasy.
9. Gdy co najmniej dwie firmy dołączą, rozpocznij grę. Poczekaj na zatwierdzenia i rozlicz rundę.

`SERVER_PORT` dostarczany przez Wings jest odczytywany automatycznie. Aplikacja nasłuchuje na `0.0.0.0`, a dane zapisuje w `data/business.sqlite3` w katalogu serwera. **Nie kasuj `data/` przy aktualizacji.**

Egg używa obrazu Yolk `ghcr.io/parkervcp/yolks:python_3.12`. Zwykły `Dockerfile` z tego projektu służy do Docker Compose; w Pelicanie użyj Yolka z egga.

Dla Pterodactyla lub instalacji wymagającej starszego formatu dołączony jest `deploy/egg-kribusiness-pterodactyl.json` (`PTDL_v2`).

### Opcjonalna instalacja z Git

Po umieszczeniu kodu w swoim repo ustaw `GIT_REPOSITORY` na pełny adres HTTPS oraz `GIT_BRANCH` na właściwą gałąź (domyślnie `main`). Repo musi mieć `app.py` w katalogu głównym. Instalator pobierze kod. Dla prywatnego repo GitHub ustaw dodatkowo `GIT_TOKEN`: token z dostępem tylko do odczytu zawartości tego repo. Token podawany jest przez Git askpass, nie w adresie repo ani argumentach polecenia. Panel i administrator serwera nadal mają dostęp do ustawionych zmiennych. Przy tokenie instalator akceptuje tylko adresy `https://github.com/`. Nigdy nie wpisuj tokena do kodu ani pliku wysyłanego do repo. Aktualizacje istniejącego serwera wykonuj przez przesłanie nowych plików po zatrzymaniu aplikacji; instalator zachowuje istniejący kod i bazę.

## Uruchomienie lokalne

W terminalu otwartym w katalogu z `app.py`:

**Windows / PowerShell**

```powershell
$env:ADMIN_USERNAME = 'admin'
$env:ADMIN_PASSWORD = Read-Host 'Podaj własne hasło administratora (min. 12 znaków)'
python app.py
```

**Linux / macOS**

```bash
read -rs -p 'Hasło administratora (min. 12 znaków): ' ADMIN_PASSWORD
export ADMIN_PASSWORD
python3 app.py
```

Otwórz **http://localhost:8080**. Hasło z powyższych poleceń służy wyłącznie do utworzenia administratora przy pierwszym starcie; nie zmienia istniejącego konta.

Inny port: `PORT=8090 python3 app.py` (Linux). Inny katalog danych: zmienna `DATA_DIR`.

## Docker Compose

```bash
cp .env.example .env
```

Wpisz własne hasło w `.env`, a następnie:

```bash
docker compose up --build -d
```

Otwórz http://localhost:8080. Nazwany wolumen `business-data` zachowuje bazę. Nie wykonuj `docker compose down -v`, jeśli chcesz zachować dane. Pliku `.env` nie umieszczaj w publicznym repo.

## Demo bez zakładania zespołów

```bash
python3 demo.py
```

Skrypt tworzy **oddzielną** bazę `demo-data/` z czterema firmami po pierwszej rundzie. Odmawia nadpisania istniejącej bazy.

Linux:

```bash
DATA_DIR=demo-data python3 app.py
```

PowerShell:

```powershell
$env:DATA_DIR = 'demo-data'
python app.py
```

Demo: `admin` / `DemoAdmin2026!`; uczniowie `team1`–`team4` / `DemoStudent2026!`. **To publiczne dane testowe; demo uruchamiaj lokalnie.** Wyłącz ustawione wcześniej `ADMIN_PASSWORD`/`ADMIN_USERNAME`, jeśli chcesz użyć domyślnych danych demo. Do prawdziwej klasy uruchom zwykłą aplikację z inną bazą i własnym hasłem.

## Jak poprowadzić zajęcia

1. Nauczyciel zakłada rozgrywkę i wybiera scenariusz oraz liczbę rund.
2. Lider tworzy firmę podczas rejestracji. Pozostali uczniowie wpisują kod klasy i kod tej firmy, który lider widzi w fazie zapisów.
3. Przed rozpoczęciem uczniowie ustalają podział pracy. Po starcie zapisy są zamknięte.
4. W każdej rundzie zespoły planują ofertę i zasoby. Najpierw zapisują szkic, by zobaczyć kontrolę budżetu. Plan jest wspólny dla całej firmy. Próba zapisu nieaktualnego formularza zostanie odrzucona; odśwież stronę i uwzględnij zmiany kolegi.
5. Zatwierdzenie blokuje edycję. Każdy członek zespołu może je cofnąć przed rozliczeniem.
6. Nauczyciel widzi gotowość firm. Rozliczenie jest dostępne dopiero po zatwierdzeniu wszystkich aktywnych firm. Przechodzi automatycznie do następnej rundy.
7. Uczniowie analizują raporty. Gotówka nie oznacza zysku; wysoki przychód nie oznacza dobrej rentowności.
8. Po ostatniej rundzie nauczyciel pobiera CSV. Ranking używa kapitału własnego, a nie samego przychodu.

## Model ekonomiczny (jawny i uproszczony)

Stan początkowy: 100 000 zł gotówki, bez długu, pracowników i stanowisk; reputacja 50/100, kompetencje 40/100.

- Zatrudnienie oznacza **docelową** liczbę pracowników, a stanowiska oznaczają **zakup nowych** stanowisk w danym miesiącu. Zakup nie jest powtarzany automatycznie.
- Roboczogodziny = `min(pracownicy, stanowiska) × 160 × wpływ_pensji × (0,7 + kompetencje/200)`.
- Gdy plan wymaga za dużo czasu, ilości wszystkich usług zmniejszają się proporcjonalnie. Pełne jednostki są zaokrąglane w dół.
- Popyt bazowy scenariusza jest mnożony przez liczbę firm w klasie, zdarzenie i niewielką deterministyczną sezonowość.
- Atrakcyjność zależy od ceny, jakości, marketingu, reputacji i kompetencji. Cena względem bazowej ma potęgę 1,5; marketing działa logarytmicznie.
- Klienci mogą zrezygnować, gdy oferty rynku są drogie. Akceptacja cen ogranicza łączny popyt; dzięki temu podniesienie wszystkich cen nie zachowuje takiej samej sprzedaży.
- Popyt jest dzielony według atrakcyjności i limitów realizacji; niewykorzystane możliwości konkurencji mogą przejąć inne firmy. Liczba sprzedanych usług nigdy nie przekracza możliwości ani liczby klientów.
- Materiały = zrealizowany plan × bazowy koszt × `(0,7 + jakość/100 × 0,6)` × mnożnik zdarzenia × mnożnik dostawcy. Efektywna jakość jest ograniczona jakością dostawcy; wpływa na koszty i atrakcyjność. Niesprzedane przygotowane usługi nie przechodzą na kolejny miesiąc.
- Przychód = sprzedaż × cena. Koszt pracodawcy to pensja × 1,20; zwolnienia kosztują pół poprzedniej pensji odprawy za osobę. Szkolenia są kosztem miesiąca i podnoszą kompetencje tylko przy zatrudnionych pracownikach. Brak sprzedaży nie zwiększa reputacji.
- Koszty wyniku: materiały, wynagrodzenia, czynsz, marketing, szkolenia, odprawy, odsetki, opłata bankowa, księgowość i amortyzacja. Amortyzacja miesięczna: 2% wartości zakupowej stanowisk. Wartość księgowa nie spada poniżej zera.
- Podatek = 19% dodatniego wyniku przed podatkiem. Strata nie generuje podatku ani zwrotu. To parametry gry, nie implementacja polskich przepisów podatkowych.
- Nowy kredyt: do 100 000 zł/rundę i do 150 000 zł łącznego długu. Odsetki i opłata zależą od banku: 1% + 0 zł, 0,8% + 150 zł albo 0,5% + 350 zł za rundę. Można spłacić cały dług w jednej rundzie. Księgowość nalicza abonament oraz koszt umownych dokumentów: pracowników, aktywnych usług i operacji inwestycji/kredytu/spłaty.
- Zatwierdzenie decyzji wymaga gotówki i nowego kredytu pokrywających maksymalny koszt planu jeszcze przed sprzedażą. Szkic może przekraczać budżet i pokazuje ostrzeżenie.
- Firma bankrutuje, jeśli po rundzie gotówka i dostępny kredyt nie wystarczą na żaden z analizowanych minimalnych planów kolejnego miesiąca, uwzględniających utrzymanie lub zwolnienie pracowników, czynsz, bank i księgowość. Jej wynik i zobowiązania zostają w rankingu; dalej nie bierze udziału w sprzedaży. To uproszczony stan zakończenia działalności, bez likwidacji majątku czy rzeczywistego postępowania upadłościowego.

Kod modelu jest w `engine.py`. Scenariusze korzystają z jednego modelu usługowego; restauracja nie ma jeszcze magazynu składników, a warsztat nie ma osobnego katalogu części. Nie są to trzy niezależne pełne symulatory branż.

## Kopie, odzyskanie hasła i aktualizacje

Kopia SQLite, także podczas działania aplikacji:

```bash
python3 manage.py backup backups/klasa-2026-10-02.sqlite3
```

Skrypt używa SQLite Backup API, więc kopia jest spójna nawet przy włączonym WAL. Na Pelicanie najlepiej dodatkowo korzystać z kopii serwera w panelu. Kopia zawiera konta i wyniki; trzymaj ją prywatnie.

Reset hasła z terminala serwera:

```bash
python3 manage.py password admin
```

Podaj hasło interaktywnie. Wszystkie sesje tego konta zostaną wylogowane. Ustaw `DATA_DIR`, jeśli baza jest w innym katalogu.

Przywracanie: zatrzymaj aplikację, zachowaj starą bazę jako kopię, zastąp `data/business.sqlite3` kopią i usuń pozostałe pliki starego WAL/SHM **dopiero po zatrzymaniu procesu**. Uruchom ponownie. Używaj kopii ze zgodnej wersji aplikacji.

Aktualizacja: wykonaj kopię, zatrzymaj aplikację, wymień pliki kodu i `static/`, zachowaj `data/`, uruchom ponownie. Wersja 1.1 automatycznie dodaje do bazy 1.0 licznik wersji decyzji (schemat 2). Zachowuje dotychczasowe konta, decyzje i wyniki. Stare wyniki nie są przeliczane; nowe rundy korzystają z nowego modelu. Jeżeli stary stan nie zawiera poprzedniej pensji, pierwsza odprawa użyje pensji bazowej scenariusza. Zmianę modelu najlepiej wprowadzić pomiędzy rozgrywkami.

## Wystawienie przez domenę

Dla prawdziwej klasy użyj reverse proxy z HTTPS, skierowanego na przydzielony port aplikacji, i ustaw `COOKIE_SECURE=true`. Przykładowa konfiguracja Caddy jest w `deploy/Caddyfile.example`. Proxy jest osobną usługą przed serwerem Pelicana. HTTP z `COOKIE_SECURE=true` nie pozwala przeglądarce przesłać sesji.

Wbudowany serwer HTTP jest przeznaczony do pierwszej wersji i małej klasy za proxy. Nie jest to przetestowana platforma dla wielu szkół ani system wysokiej dostępności. Nie ma odzyskiwania hasła przez e-mail, integracji dziennika, automatycznych terminów rund, zarządzania usuwaniem kont, indywidualnych kart pracownika, magazynu, rozbudowanego VAT, progresywnego odblokowywania zakładek ani wszystkich branż REVAS. Nauczyciel obserwuje gotowość i wyniki, ale nie podgląda bieżących planów konkurencji.

## Weryfikacja

```bash
python3 -m unittest discover -s tests -v
```

Testy sprawdzają mechanikę podziału klientów, limity mocy, tożsamości finansowe, reakcję popytu na cenę, błędne decyzje, zdarzenia i upadłość. Test integracyjny uruchamia realny serwer HTTP, tworzy nauczycieli i zespoły, rozgrywa dwie rundy oraz sprawdza CSRF, uprawnienia, eksport, ponowne inicjalizowanie bazy i odrzucenie powtórnego rozliczenia.

Dodatkowe testy sprawdzają 24 rundy w każdym scenariuszu, rozliczenia co do grosza, migrację starej bazy, wersjonowanie wspólnego planu oraz skrypt instalacji z atrapą Git. Pełna lista i ograniczenia: `VALIDATION.md`. Porównanie zakresu: `COMPARISON-REVAS.md`.

Docker Compose i import do działającego Pelicana wymagają sprawdzenia na docelowym serwerze; nie są potwierdzone wdrożeniem w tej paczce.

## Pliki i licencja

`app.py` — serwer, konta, klasy, formularze i raporty; `engine.py` — model rynku; `static/` — wygląd; `manage.py` — kopie i reset hasła; `demo.py` — dane demonstracyjne; `deploy/` — eggi i reverse proxy; `tests/` — testy.

Kod projektu: MIT, patrz `LICENSE`. REVAS jest nazwą odrębnego produktu; projekt nie jest z nim powiązany.

Źródła formatu wdrożenia (sprawdzone 2.10.2026):
- https://pelican.dev/docs/eggs/creating-a-custom-egg/
- https://hub.pelican.dev/eggs/python-generic
- https://hub.pelican.dev/eggs/python-generic/download
