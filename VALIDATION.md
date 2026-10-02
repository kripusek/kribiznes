# Weryfikacja wersji 1.1 — 2 października 2026

`python3 -m unittest discover -s tests -v` — 24 testy zakończone powodzeniem.

## Potwierdzone automatycznie

- Podział klientów, ograniczenia popytu i mocy, reakcja rynku na cenę.
- Trzy scenariusze i cztery zdarzenia; dodatkowo 24 rundy dla ośmiu firm w każdym scenariuszu.
- Zgodność gotówki, długu, majątku, wyniku i przepływów co do grosza.
- Odprawy według poprzedniej pensji; zwolnienia uwzględnione w ocenie płynności.
- Dostawcy wpływają na jakość i koszty; bank i księgowość naliczają opłaty.
- Brak wzrostu reputacji bez sprzedaży i kompetencji bez pracowników.
- Spłata całych 150 000 zł długu; jednorazowe zakupy i kredyt nie powtarzają się automatycznie.
- Szkic ponad budżet jest zachowany, ale nie można go zatwierdzić.
- Rzeczywiste żądania HTTP: konta, klasy, zespoły, decyzje, raporty i eksport CSV.
- CSRF, oddzielenie uprawnień, zmiana zdarzenia i odrzucenie powtórnego rozliczenia.
- Stary formularz członka zespołu nie nadpisuje nowszej decyzji (HTTP 409).
- Migracja bazy 1.0 zachowuje decyzje i toleruje ponowne uruchomienie.
- Wygenerowany instalator: ścieżka ręczna, prywatne repo przez askpass, odrzucenie innego hosta przy tokenie i zachowanie istniejącej instalacji. Test używa atrapy Git i sztucznego tokena.
- JavaScript: poprawna składnia (`node --check static/app.js`).

## Granice weryfikacji

- Nie wykonano rzeczywistego importu do Pelicana/Wings ani budowy Docker Compose: brak tych usług w środowisku.
- Nie potwierdzono pobrania prywatnego repo prawdziwym tokenem. Dostęp GitHub Connector do prywatnego repo potwierdzono po ukończeniu instalacji aplikacji.
- Nie wykonano wizualnego testu w przeglądarce desktop/mobile. Formularze przetestowano przez HTTP.
- Testy wielorundowe sprawdzają spójność, a nie pełny balans pedagogiczny czy wydajność dla wielu klas.
- To autorski uproszczony model. Nie potwierdzono zgodności algorytmów z REVAS.

Przed zajęciami należy uruchomić próbną klasę na docelowym serwerze i przejść dwie rundy.
