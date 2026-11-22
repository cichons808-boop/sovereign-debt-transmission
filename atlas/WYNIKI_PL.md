# Atlas transmisji monetarnej — stan empiryczny 22.11.2026

Zbudowano rozszerzenie istniejącego repozytorium. Każdy model wykorzystuje jeden szok i najwyżej jedną charakterystykę strukturalną. Roczne obserwacje nie są interpolowane do kwartałów.

## Zasięg i aktualność

| Warstwa | Rzeczywisty zakres |
|---|---|
| CWY: krajowe i odziedziczone szoki | 176 krajów w pobranym pliku, 175 z niezerową wariancją; 159 kwalifikuje się do LP PKB, 145 do LP CPI; ostatni rok 2019 |
| Odtworzone reguły reakcji | 85 gospodarek rocznie w wariancie z jednym opóźnieniem, 71 z trzema; 50 kwartalnie; do 2025 / 2026Q3 |
| USA, surowe dane intraday | ostatnia obserwacja 28.10.2026; osobno odtworzony czynnik i własna dekompozycja monetarna/informacyjna |
| EBC, nowe EA-EMPD | posiedzenia do 11.06.2026; odtworzona metoda JK, bez doklejania do starszego wydania |
| Wielka Brytania | oficjalne czynniki target/path do 30.04.2026, osobne instrumenty |
| Osobny szok zewnętrzny Fed | roczne LP PKB dla 197 gospodarek, CPI dla 172; to transmisja zagraniczna, nie własna polityka tych państw |

Pobrano stopy polityki, dyskontowe lub refinansowania dla 149 gospodarek. Odnalezienie stopy nie wystarcza do identyfikacji egzogenicznego szoku. Reguły Taylora pozostają klasą słabszej identyfikacji. Około 60% obserwacji CWY dziedziczy szok kotwicy; kraje te nie dostarczają niezależnych realizacji polityki pieniężnej.

## Wykonane regresje i wyniki

W aktualnym zestawie zapisano **102 914 prób specyfikacji**, w tym **66 680 oszacowanych**. Liczby obejmują horyzonty, kraje, grupy i warianty wrażliwości. Nie oznaczają tylu niezależnych odkryć. Powstały wykresy IRF dla 203 krajów/terytoriów.

Zakończono cztery osobne chunki: dług publiczny/PKB (F01), krajowi wierzyciele poza bankiem centralnym/PKB (F04), refinansowanie kapitału w ciągu roku (R01) i import energii netto (E01).

- **Dług publiczny:** w BDY interakcja dla PKB po 8 kwartałach wynosi +0,109 pkt proc. na 10 pb czynnika monetarnego i +10 pkt proc. długu/PKB. Raw p = 0,000993, diagnostyka bootstrap blokowy p = 0,045; 38 krajów i 20 emitentów. Dodatnia interakcja oznacza wyższą reakcję przy większym długu. Nie dowodzi dodatniej całkowitej reakcji PKB. CWY i nowe EBC nie potwierdzają jednolicie tego wyniku.
- **Rezydencja wierzycieli:** prosty model z jednym Z nie daje jednolitego potwierdzenia dodatniego kanału dochodów odsetkowych. Dla CPI w EBC interakcja po 8 kwartałach jest ujemna (około −0,132; raw p = 0,0135; blokowe p = 0,0225; 14 krajów, jeden wspólny emitent).
- **Refinansowanie:** CPI w EBC po 8 kwartałach ma dodatnią interakcję +0,445; raw p = 0,029, ale blokowe p = 0,098 (15 krajów). Pozostałe porównania nie dają stabilnego potwierdzenia.
- **Energia:** na ustalonym horyzoncie dwóch lat / ośmiu kwartałów wszystkie globalne interakcje PKB i CPI w siedmiu wspieranych rodzinach są nieistotne na poziomie 5%.

Rozrzut krajowych oszacowań jest duży, lecz diagnostyka uwzględniająca wspólne zaburzenia nie daje mocnego potwierdzenia heterogeniczności ponad błąd estymacji: dla PKB po 8 kwartałach p = 0,118 w BDY i p = 0,460 w nowym EBC; w CWY po dwóch latach p = 0,060. To nie dowodzi jednak identyczności reakcji.

## Co można zweryfikować

[Pełny notebook](RESEARCH_NOTEBOOK.md), [wykresy krajowe](figures/country_IRFs.pdf), [indeks krajów](figures/country_IRF_index.csv), [rzeczywista kwalifikowalność](audit/final_effective_LP_coverage.csv), [walidacja numeryczna](audit/numerical_validation.json).

Każda próba zachowuje status, specyfikację, N i daty; wyniki dodatkowo współczynniki, pełną macierz kowariancji, błędy standardowe, surowe p, przedziały oraz diagnostyki. Odtworzony oficjalny czynnik USA różni się maksymalnie o 1,53e−16; odtworzona stara seria JK o 8,56e−9. LP i HAC sprawdzono na rzeczywistych obserwacjach przez niezależne estymacje.

## Otwarte zadania

Wykaz luk obejmuje 251 jednostek ISO/World Bank. Nie ukończono poszukiwań w każdym krajowym archiwum ani identyfikacji własnych szoków dla każdego państwa. Nie rozpoczęto pozostałych moderatorów. Potrzebne są m.in. pełniejsze autentyczne kwartalne CPI Australii/NZ, dalsze krajowe szoki oraz wspólne reguły dla unii walutowych poza strefą euro. Szczegółowy status jest zapisany w rejestrze. Żadna z tych prac nie trwa dalej w tle.
