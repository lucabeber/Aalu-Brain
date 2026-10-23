# AALU — Roadmap di sviluppo del computer di bordo

**Versione:** 0.1 — 23 ottobre 2026  
**Piattaforma:** Raspberry Pi 5, 16 GB RAM  
**Veicolo:** Mercedes-Benz G 280 ambulanza camperizzato  
**Stato:** progetto iniziale; interfacce e componenti da validare sul banco e sul veicolo

## 1. Visione

Realizzare un sistema locale, offline-first e manutenibile che fornisca una dashboard di guida e una dashboard camper con navigazione, telecamere, musica dal telefono, monitoraggio dell'impianto elettrico e controllo protetto delle utenze. Il sistema NON sostituisce gli strumenti di guida originali né deve rendere indispensabile il computer per l'utilizzo sicuro del veicolo e degli impianti.

### Principi vincolanti

1. **Offline-first:** le funzioni essenziali devono funzionare senza Internet.
2. **Fail-safe:** nessuna utenza essenziale deve dipendere esclusivamente dall'app; i carichi devono avere protezioni e, ove opportuno, comandi manuali.
3. **Modularità:** GUI, logica veicolo, video e hardware comunicano tramite interfacce documentate.
4. **Simulazione iniziale:** sviluppo e test su PC prima di collegare relè o installare nel camper.
5. **Hardware automotive:** mai applicare direttamente tensioni del veicolo ai GPIO; ingressi protetti e preferibilmente isolati; fusibili, transitori, inversione polarità e massa da progettare.
6. **Osservabilità:** errori, stato dei dispositivi e allarmi sono diagnostici e tracciabili.
7. **Degradazione controllata:** ogni sorgente dati può diventare non disponibile senza bloccare l'interfaccia.
8. **Manutenzione semplice:** avvio automatico, configurazione versionata, backup e aggiornamenti reversibili.

## 2. Ambito funzionale

| ID | Funzione | Priorità | Target |
|---|---|---|---|
| D-01 | Dashboard guida Qt/QML | P0 | Primo prototipo |
| D-02 | Dashboard camper Qt/QML | P0 | Primo prototipo |
| D-03 | Navigazione offline e posizione GNSS | P0 | MVP guida |
| A-01 | Smartphone Bluetooth come sorgente audio | P0 | MVP guida |
| A-02 | Play/pausa, successivo, metadati ove disponibili | P0 | MVP guida |
| A-03 | Volume, mute, preset equalizzazione | P1 | Integrazione audio |
| V-01 | Retrocamera su evento retromarcia | P0 | MVP guida successivo |
| V-02 | Registrazione automatica delle dashcam | P1 | Modulo video |
| E-01 | Tensione/corrente/SOC batteria servizi | P0 | MVP camper |
| E-02 | MPPT e dati Victron | P1 | Modulo energia |
| W-01 | Livelli acqua e stato pompa | P1 | Modulo camper |
| C-01 | Comandi luci e utenze | P1 | Dopo elettronica protetta |
| S-01 | IMU: inclinazione veicolo | P2 | Modulo sensori |
| S-02 | Temperature interne/esterne | P2 | Modulo sensori |
| P-01 | Gestione ACC, avvio e spegnimento | P0 | Prima del montaggio permanente |
| X-01 | OTA/aggiornamento locale con rollback | P2 | Versione consolidata |

**P0:** indispensabile per lo specifico traguardo; **P1:** previsto e importante; **P2:** miglioramento successivo.

### Fuori ambito della versione iniziale

- Sostituzione di tachimetro, indicatori originali o sistemi di sicurezza del veicolo.
- Controllo diretto del motore, ABS, frenata, sterzo o altre centraline di sicurezza.
- CarPlay/Android Auto completi: possibile studio successivo, non prerequisito per ascoltare musica.
- Progettazione immediata della PCB di amplificazione: prima validazione acustica ed elettrica con moduli commerciali.
- Navigazione turn-by-turn riscritta da zero.

## 3. Stack e architettura

| Livello | Scelta iniziale | Note |
|---|---|---|
| OS | Raspberry Pi OS Desktop 64-bit, Debian Trixie | Versione fissata e testata |
| GUI | Qt 6, Qt Quick/QML, PySide6 | 2 finestre, una per touchscreen |
| Logica | Python 3, typing, asyncio ove utile | Processi non proliferati inutilmente |
| Audio | BlueZ, PipeWire, WirePlumber | A2DP sink + AVRCP via D-Bus |
| Video | GStreamer, processo indipendente | Ring recording e preview |
| GNSS | gpsd, adattatore Python | Seriale USB/UART, test no-fix |
| Offline maps | Pure Maps + OSM Scout Server | Prototipo separato prima dell'integrazione |
| Dati Victron | VE.Direct-USB isolato e/o interfaccia documentata | Scelta per dispositivo effettivo |
| Sensori e attuatori | MCU dedicato, USB seriale robusta | ESP32/STM32 da selezionare |
| Dati locali | SQLite, JSON/TOML/YAML | DB per eventi, conf per parametri |
| Avvio | systemd + sessione Wayland/labwc | watchdog e servizi separati |
| Sviluppo | Git, GitHub, pytest, Ruff, mypy opzionale | CI e issue suddivise in milestone |

### Architettura logica

```text
Bluetooth phone ──> BlueZ/PipeWire ────────────> USB DAC / amp (prototipo)
                          │                               │
                          ▼                               └──> woofer+tweeter L/R
Touchscreen guida ──> Qt/QML ─┐
                              ├─> Vehicle Core (Python) ─> State Store / Event Bus
Touchscreen camper ──> Qt/QML ─┘       │   │   │
                                      │   │   ├─> GNSS/gpsd
                                      │   │   ├─> VE.Direct / Victron
                                      │   │   └─> MCU sensori+comandi
                                      │   └─> Config / SQLite / diagnosi
                                      └─> Video supervisor ──> GStreamer + SSD

Alimentazione automotive con power supervisor dedicato e logica ACC/spegnimento.
```

**Decisione di architettura:** iniziare con **un unico backend Python modulare** e servizi dedicati solo per video, eventuale supervisore hardware e componenti di sistema. Preferire un modello stato/eventi locale rispetto a microservizi distribuiti, Docker o rete MQTT per ogni semplice lettura.

### Contratti minimi dei dati (esempi)

```json
{
  "schema_version": 1,
  "source": "gnss",
  "ts_utc": "2026-10-23T12:00:00Z",
  "quality": "valid",
  "speed_kmh": 73.4,
  "lat": 46.0,
  "lon": 11.0,
  "heading_deg": 285.0
}
```

```json
{
  "schema_version": 1,
  "source": "house_battery",
  "ts_utc": "2026-10-23T12:00:00Z",
  "quality": "stale",
  "soc_pct": null,
  "voltage_v": null
}
```

Non riutilizzare valori vecchi come se fossero misure correnti; distinguere sempre `valid`, `stale`, `disconnected`, `error` e `simulated`. Non impostare coordinate GPS da NMEA con fix non valido; niente data 1980 inventata nelle dashboard.

## 4. Fasi di sviluppo e gate

### FASE 0 — Specifiche e disegno architetturale

**Output:** `docs/requirements.md`, `docs/architecture.md`, `docs/hardware-inventory.md`, `docs/decisions/`.

**Attività**
- Inventario preciso: versione OS, alimentazione, SSD, display, risoluzioni, rotazioni, touch USB, GNSS, telecamere, sensori, dispositivi Victron, pulsanti, carichi.
- Definire modalità `drive`, `camp`, `standby`, `shutdown`, `fault`; decidere cosa cambia con ACC e retromarcia.
- Mappa ingressi/uscite prevista (non ancora cablata); definire priorità dei comandi manuali.
- Mockup e wireframe con dimensioni fisiche/ergonomiche dei touchscreen.
- Descrivere requisiti offline, recupero dopo guasti, budget energetico e diagnostica.
- Scrivere ADR per stack Qt/Python, mappe, video, audio e microcontrollore.

**Gate G0:** i requisiti della prima release sono approvati, le dipendenze hardware non note sono documentate come `TBD` e nessuna scelta di PCB dipende da assunzioni non verificate.

### FASE 1 — Repository, ambiente di sviluppo e simulatore

**Output:** app dimostrativa desktop su Linux, test e pipeline GitHub.

**Attività**
- Repository Git privata inizialmente; protezione branch `main`, pull request anche per modifiche di agenti.
- Python `venv`, `pyproject.toml`, versioni dipendenze fissate, `ruff`, `pytest`, tipizzazione.
- App Qt/QML che si avvia da riga di comando e chiude senza errori.
- Fake adapters per GPS, batteria, audio, serbatoi, GPIO e video; fixture riproducibili.
- Simulazione guasti: dati vecchi, connessione persa, SOC basso, inserimento retromarcia.
- CI: lint, unit test, test adapter, sanity check QML (ove disponibile).
- Script `scripts/run_demo.sh` e `scripts/check_environment.sh`.

**Gate G1:** nuova macchina Linux esegue la demo seguendo il README; CI verde; nessun hardware fisico necessario.

### FASE 2 — UI/UX e doppia dashboard

**Output:** due interfacce cliccabili con dati simulati, design system e componenti riutilizzabili.

**Attività**
- Tema diurno/notturno; modalità scura con contrasto adatto alla guida, luminosità regolabile.
- Componenti QML condivisi: cards, barre, tile, warning, indicatori, slider, modal, status bar.
- Layout guida: mappa centrale, mini-player, speed/GPS, stato connessioni, accesso camera.
- Layout camper: SOC, autonomia indicativa, correnti, MPPT, luci, acqua e pannello allarmi.
- Gestione stati loading/empty/disconnected/stale e valori simulati etichettati.
- Animazioni minime; target touch comodi, niente testo piccolo essenziale in marcia.
- Modello di stato condiviso, ma finestre e navigazione indipendenti sui due schermi.
- Pulsanti fisici opzionali e blocco delle impostazioni complesse durante la guida.

**Gate G2:** mockup end-to-end, navigazione tra pagine stabile, test con display a risoluzioni diverse, dati disconnessi mostrati correttamente.

### FASE 3 — Porting su Raspberry Pi e touchscreen

**Output:** dashboard avviata automaticamente sul Pi 5.

**Attività**
- Installazione OS 64-bit e SSH; utenti non privilegiati; pacchetti minimi.
- Prima installazione su microSD; pianificare SSD per contenuti video e, se scelto, sistema operativo.
- Test HDMI singolo e poi due HDMI; configurare rotazione/orientamento.
- Mappare ogni touchscreen USB al monitor corretto; test multitouch e riconnessione.
- Abilitare kiosk Qt con sessione Wayland/labwc; verificare posizionamento persistente finestre.
- systemd per backend; autoavvio GUI in sessione utente grafica, senza lanciare UI da un servizio senza sessione.
- Ventola, temperatura, throttling, uso RAM/CPU e alimentazione USB misurati.

**Gate G3:** dopo riavvio automatico si aprono le due dashboard; disconnessione temporanea di un monitor non blocca il resto; il touch di ogni monitor rimane corretto.

### FASE 4 — GNSS e navigazione offline

**Output:** posizione e navigazione offline attendibili.

**Attività**
- Riusare il GNSS già testato a 115200 baud con frasi NMEA; interpretare correttamente `V`/assenza fix e numero satelliti zero.
- Collegare a `gpsd`, test all'aperto del primo fix, coordinate, timestamp, quota, velocità, heading.
- Filtrare dati implausibili e marcare il fix perso; associare timestamp e età del dato.
- Verificare Pure Maps + OSM Scout Server sul Pi ARM64; download di mappe prova e percorsi senza Wi-Fi.
- Inizialmente far girare la navigazione come applicazione separata, richiamata dalla dashboard (non riscriverla).
- Valutare integrazione in finestra Qt solo dopo benchmark e verifica delle opzioni tecniche/licenze.
- Preferiti, waypoint, coordinate da salvare, posizione parcheggio, esportazione traccia (successivamente).

**Gate G4:** localizzazione corretta all'aperto, nessuna posizione inventata al chiuso, mappa e route funzionanti senza Internet nel percorso di prova.

### FASE 5 — Musica Bluetooth e impianto audio

**Output:** musica del telefono riprodotta nell'auto e controllata dalla dashboard.

**Attività software**
- Configurare Pi come A2DP **sink** (telefono come source) usando BlueZ/PipeWire/WirePlumber.
- Pairing iniziale, dispositivi fidati, riconnessione, gestione fallback a telefono scollegato.
- BlueZ AVRCP via D-Bus: play, pausa, next/previous, metadati se esposti.
- Gestire volume/mute senza scatti e senza doppia amplificazione digitale incontrollata.
- Mini-player persistente nella dashboard guida; pagina impostazioni audio nella dashboard camper.
- Valutare EQ/DSP software con benchmark CPU; preset `flat`, `voice`, `drive`, `night` come punto di partenza, senza aumenti automatici pericolosi di volume.

**Attività hardware**
- Versione prototipale: DAC USB o interfaccia audio adatta + amplificatore stereo classe D pronto.
- Due woofer da circa 6,5 pollici nei kick panel e due tweeter separati sulla plancia, con crossover appropriati; **nessun sub in prima versione**.
- Volume acustico, struttura meccanica, cablaggio e classe di amplificatore da dimensionare dopo misure.
- Solo dopo test su strada: studio PCB custom con stadio di alimentazione protetto, mute, diagnostics e DSP.

**Gate G5:** telefono si collega e riproduce musica; pause/skip dal touchscreen verificati su telefoni reali; audio senza ronzii/pop significativi durante accensione/spegnimento.

### FASE 6 — Telecamere e dashcam

**Output:** preview affidabile e registrazioni indipendenti dalla GUI.

**Attività**
- Scegliere prima la camera testando formati UVC realmente emessi (`H.264`, `MJPEG`, raw), fps e latenza.
- Preferire camera con H.264 già compresso se disponibile, per evitare due codifiche software continue; Pi 5 non ha encoder H.264 hardware.
- Pipeline GStreamer dedicata per ciascuna camera, con registrazione a file segmentati e retention.
- Policy circolare: quando lo spazio SSD scende sotto soglia eliminare i segmenti più vecchi, mai i segmenti protetti da un evento.
- Video service separato con auto-restart; interfaccia visualizza lo stream ma non controlla il ciclo di registrazione.
- Trigger retromarcia da ingresso protetto/isolato su microcontrollore; cambiamento automatico schermata, senza distruggere la navigazione.
- Prevedere test di latenza dopo avvio e dopo sospensione; la retrocamera software non deve essere l'unico ausilio visivo per manovre sicure.
- Politica chiara sulla registrazione di audio, privacy e cancellazione.

**Dimensionamento di esempio:** due stream H.264 da 4 Mbit/s ciascuno occupano circa **3,6 GB/ora** complessivi, esclusi overhead: il dato reale va misurato.

**Gate G6:** registrazione continua per diverse ore, segmenti riproducibili, ripartenza dopo scollegamento di una camera; finestra reverse reattiva su Raspberry acceso; GUI crash non interrompe le registrazioni.

### FASE 7 — Monitoraggio energia e acqua

**Output:** pannello camper con dati reali, aggiornati e diagnostici.

**Attività**
- Elencare dispositivi effettivi (SmartShunt, MPPT, Orion, MultiPlus e loro interfacce vere).
- Favorire VE.Direct-USB **isolato**, ufficiale o equivalente adeguato, dove supportato; per MultiPlus serve verificare la specifica interfaccia (non assumere VE.Direct su tutti i modelli).
- Parser rigoroso, unità fisiche, rate di polling, riconnessioni, plausibility checks.
- Stato batteria: SOC disponibile, V, A, W, energia, storico e indicazione sorgente del dato.
- Sensori livelli acqua, temperature e pompe, inizialmente con simulatore e poi tramite MCU.
- Log dati selettivo SQLite per grafici storici senza scritture eccessive.
- Allarmi per soglie configurabili con isteresi e indicazione `dati non disponibili` dove opportuno.

**Gate G7:** valori della dashboard confrontati con misure/strumenti Victron; errori e disconnessioni non causano false letture.

### FASE 8 — Controllo utenze e PCB di I/O

**Output:** controllo verificato di una prima utenza non critica, poi estensione modulare.

**Attività**
- Definire carichi: luci, pompa, prese USB selezionate, ventilazione, riscaldatore **solo via interfaccia autorizzata**.
- Per ogni carico: tensione, corrente nominale e di spunto, fusibile, sezioni cavo, duty cycle, comando manuale e comportamento allo spegnimento.
- MCU di interfaccia; protocollo con frame, CRC/checksum, ACK, sequence number, timeout e stato rilevato.
- Ingressi ACC/reverse isolati e filtrati; uscite per relè o MOSFET automotive con driver/protezioni dimensionati.
- Definire stati sicuri: watchdog MCU, perdita comunicazione Pi, brownout, power-off, recovery dopo boot.
- Validare **un singolo carico da banco**, non collegare subito tutta la pulsantiera.
- PCB: schematico, PCB, clearances, connettori, thermal e prova EMI/rumore a banco.
- Comandi manuali indipendenti e priorità prevedibile rispetto a quelli software.

**Gate G8:** fallimento controllato di alimentazione/comunicazione senza accensioni non volute; override manuale operativo; nessun GPIO direttamente connesso a 12 V.

### FASE 9 — Alimentazione, affidabilità e release veicolo

**Output:** release installabile per utilizzo reale, con documentazione di manutenzione.

**Attività**
- Dimensionare DC/DC 12 V → 5.1 V e cablaggio per Pi + periferiche; compatibilità con picchi/transitori e spegnimento dell'alimentazione servizi.
- Supervisore alimentazione e hold-up per spegnimento pulito; distinguere ACC da alimentazione sempre presente.
- Definire le modalità ACC ON, CAMP, PARKED, LOW BATTERY e POWER FAIL; evitare consumo a riposo eccessivo.
- Riduzione scritture, filesystem robusto, politiche SSD/SD, backup configurazione e SQLite.
- systemd Restart/Watchdog, logging limitato con rotazione, health checks e pagina Diagnostica.
- Installazioni reproducibili; backup release precedente, aggiornamento eseguibile localmente e rollback.
- Misure di consumo a riposo e durante l'uso; idle power riscontrato realmente prima di fissare il timeout.
- Test su strada con vibrazioni, caldo, avviamento motore, accensione/spegnimento, connessioni intermittenti.

**Gate G9:** passaggio di una matrice di test su banco e a bordo, nessuna perdita critica dei dati e nessuna dipendenza da Internet per le funzioni fondamentali.

## 5. Release incrementali

| Milestone | Include | Uso possibile |
|---|---|---|
| **M0 — Demo** | Fake backend, dashboard guida/camper, navigazione GUI | PC |
| **M1 — Pi UI** | Uno/due touch reali, autoavvio e log | Raspberry a banco |
| **M2 — Infotainment** | GPS offline + Bluetooth + audio stereo | Prima prova nel veicolo |
| **M3 — Video** | Retrocamera, dashcam e storage circolare | Guida, dopo validazione |
| **M4 — Camper Monitor** | Batterie, Victron, acqua, sensori | Parte abitativa |
| **M5 — Camper Control** | PCB I/O, comandi protetti, supervisore | Utenze non critiche |
| **M6 — Stable** | Diagnostic, backup, rollback, prove su strada | Utilizzo consolidato |

**Ordine consigliato:** F0 → F1 → F2 → F3 → (F4 e F5) → F6 → F7 → F8 → F9. Le validazioni di alimentazione base e sicurezza della retrocamera si anticipano prima di M2/M3.

## 6. Repository proposta

```text
aalu-dashboard/
├── README.md
├── pyproject.toml
├── .github/workflows/ci.yml
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   ├── hardware-inventory.md
│   ├── acceptance-tests.md
│   ├── wiring/              # disegni, NON sostituiscono verifica elettrica
│   └── decisions/           # ADR tecniche
├── apps/
│   ├── dashboard/
│   │   ├── main.py
│   │   ├── qml/
│   │   │   ├── Main.qml
│   │   │   ├── screens/Drive.qml
│   │   │   ├── screens/Camper.qml
│   │   │   └── components/
│   │   └── assets/
│   └── diagnostics/
├── src/aalu/
│   ├── core/                # modelli, stati, eventi, policy
│   ├── adapters/            # adapter simulati e reali
│   │   ├── gps/
│   │   ├── audio/
│   │   ├── victron/
│   │   ├── video/
│   │   └── mcu/
│   ├── services/            # logiche applicative
│   └── storage/
├── firmware/                # quando selezionata MCU
├── config/
│   ├── dev.toml
│   └── pi.toml.example
├── scripts/
│   ├── run_demo.sh
│   ├── install_pi.sh
│   └── capture_diagnostics.sh
├── systemd/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── simulated/
│   └── hardware/
└── assets/sample-data/
```

### Regole per l'AI coding

- Ogni issue deve specificare **obiettivo, file consentiti, comportamento atteso, test e criteri di accettazione**.
- Gli agenti possono proporre modifiche architetturali, ma non cambiarla di nascosto.
- Ogni integrazione hardware ha un `FakeAdapter` e un `RealAdapter` con la stessa interfaccia.
- Gli agenti non devono introdurre nuove dipendenze senza motivazione o modificare pinout/fusibili senza verifica umana.
- Per le parti critiche (alimentazione, reverse, pompe/relè), revisione umana obbligatoria e prova sul banco.
- Evitare di consegnare UI basate su numeri finti non etichettati: `SIMULATED` deve essere evidente.
- Tutti i cambi vanno in PR piccole, con screenshot UI e output test.

### Template issue per agenti

```md
## Obiettivo
<singolo risultato verificabile>
## Contesto e contratti
<file, interfacce, payload>
## Vincoli
<offline, no side effects, API, ergonomia, ecc.>
## Criteri di accettazione
- [ ] ...
## Test obbligatori
- ...
## Fuori ambito
- ...
```

## 7. Dati sensori e attuazione: gestione degli errori

| Caso | Comportamento atteso |
|---|---|
| GNSS non ha fix | Trattini/stato ricerca; non inventare velocità o posizione |
| Victron scollegato | Dati marcati `stale` e poi `disconnected`; allarme non invasivo |
| Smartphone scollegato | Player disabilitato; nessuna eccezione nella UI |
| Telecamera scollegata | Registrazione altra camera continua; tentativo recovery/log |
| UI in crash | Servizio video continua; backend riavvia UI, utenze non cambiano stato in modo imprevisto |
| MCU scollegato | Comandi da GUI disabilitati; watchdog hardware applica policy definita |
| Pi perde 12 V | Supervisore se possibile concede shutdown; nessun impulso spurio ai relè |
| ACC spento | Policy selezionabile parcheggio/camper, senza spegnere automaticamente funzioni camper autorizzate |
| Display guida disconnesso | Dashboard camper e acquisizioni continuano |
| SSD quasi pieno | Video cancella segmenti vecchi secondo retention; log e sistema non saturano disco |

## 8. Prestazioni e test: target iniziali da verificare

| Misura | Target progettuale provvisorio | Procedura |
|---|---|---|
| Rendering dashboard | Interazione fluida, idealmente 30–60 fps | Benchmark reale con 2 schermi |
| Reattività touch | <150 ms nelle azioni locali ordinarie | Video/high-speed o timestamp |
| Avvio sistema | Misurare; obiettivo operativo GUI <30 s da boot freddo | 20 power cycle |
| Retrocamera | <2 s da comando con Pi già acceso | 30 inserimenti reverse simulati |
| Disconnessione GNSS | Dato scaduto visibile secondo soglia configurata | Staccare seriale |
| Memoria | Niente crescita senza limite in prova prolungata | RSS per processo 8–24 h |
| Temperature | Nessun throttling persistente nel carico di utilizzo | Logging 1h-4h |
| Registrazione video | Niente segmenti corrotti nei casi normali | 4h+, clip casuali |
| Reconnect Bluetooth | Riconnessione ordinata e comprensibile | On/off telefono 20 volte |
| Perdita 12 V | Nessun comando indesiderato e strategia shutdown definita | banco protetto |
| Consumi standby | Misura e definizione di un budget realistico | amperometro su batteria servizi |

I numeri temporali sono **obiettivi di ingegneria da validare**, non prestazioni garantite. Non effettuare test di reverse, alimentazione o carichi in marcia finché non superati i test al banco.

## 9. Hardware da validare / non acquistare alla cieca

| Componente | Stato attuale | Decisione aperta |
|---|---|---|
| Raspberry Pi 5 16 GB | Confermato | contenitore, ventola, alimentazione |
| GNSS seriale | Dati NMEA già ricevuti a 115200, ma senza fix | antenna e fix all'aperto |
| Due touchscreen | Previsti | diagonale, risoluzione, controller touch, layout |
| SSD | Proposto | interfaccia USB/PCIe, capacità, ruggedness |
| Camera anteriore e posteriore | Previste | USB/UVC, codec, qualità notte, alimentazione |
| DAC / amp provvisorio | Da selezionare | test acustico prima PCB |
| 2 woofer + 2 tweeter | Configurazione proposta | driver, box/adattatori 3D, crossover |
| Dispositivi Victron | Impianto in definizione | modelli e porte precise |
| MCU I/O | Da scegliere | numero I/O, CAN? GPIO? seriale, watchdog |
| Power supervisor | Necessario per montaggio | batteria servizi/ACC/standby/shutdown |

### Separazione fisica delle alimentazioni

- **Batteria servizi → linea Pi:** DC/DC automotive protetto e dimensionato per Pi + periferiche, proprio fusibile.
- **Batteria servizi → linea audio:** fusibile e cablaggio dedicati, amplificatore classe D e gestione mute/remote.
- **Batteria servizi → carichi:** distribuzione con protezioni appropriate; la MCU comanda, NON sostituisce i fusibili.
- **Segnali veicolo ACC/reverse:** leggere tramite ingressi protetti; non collegare direttamente alla testata GPIO.

## 10. Sequenza concreta di prime issue GitHub

1. `INIT-01` — Creare repository e template issue/PR.
2. `DOC-01` — Definire scope v0.1 e mockup delle due dashboard.
3. `CORE-01` — Modelli `VehicleState` e `DataQuality` tipizzati.
4. `SIM-01` — Fake GNSS, Victron, media player e water tank.
5. `UI-01` — Shell QML avviabile su Linux desktop.
6. `UI-02` — Dashboard guida con dati simulati.
7. `UI-03` — Dashboard camper con dati simulati.
8. `UI-04` — Componenti `StatusIndicator`, `MetricTile`, `MediaMiniPlayer`.
9. `TEST-01` — Unit test dei modelli ed eventi, lint CI.
10. `PI-01` — Script di installazione Pi OS e dipendenze testate.
11. `PI-02` — Autostart UI + backend e log con journalctl.
12. `GNSS-01` — Lettura NMEA e fix logic; unit test con log salvati.
13. `AUDIO-01` — A2DP sink reale su Pi e test con smartphone.
14. `AUDIO-02` — Comandi AVRCP e UI player.
15. `NAV-01` — Prova offline Pure Maps/OSM Scout su ARM64.
16. `VIDEO-01` — Benchmark codec e pipeline registrazione da una camera.

## 11. Design dell'esperienza utente

### Drive home

- Mappa o navigazione prevalente.
- Mini-player Bluetooth, volume, connessione telefono.
- Piccola barra stato: GNSS, tensione servizi, camera recording, temperatura Pi/avvisi.
- Accesso retrocamera e viste anteriori a un solo tocco.
- Niente comandi elettrici complessi in vista guida.

### Camper home

- Card batteria: SOC, corrente, potenza, tempo stimato solo se calcolabile in modo attendibile.
- Card energia solare e alimentazione esterna.
- Card acqua: livelli, pompa ON/OFF e stato comando ricevuto.
- Card illuminazione per aree; preset con feedback di stato reale.
- Accesso temperature, log e diagnostica.

### Stato veicolo

Stati distinti da modellare formalmente:

- `DRIVE`: ACC presente; schermo guida prioritario; funzioni pericolose bloccate.
- `CAMP`: ACC spento ma impianto servizi attivo; controllo abitativo disponibile.
- `STANDBY`: consumo ridotto, wake policy specifica.
- `SHUTDOWN`: commit configurazioni, drain video, power-off controllato.
- `FAULT`: warning e stato degradato; nessun fail-dangerous.

La modalità reale va determinata con un **state machine**, non con una sola condizione `if ACC`.

## 12. Rischi e mitigazioni

| Rischio | Impatto | Strategia |
|---|---|---|
| Interfaccia QML consuma troppe risorse | Medio | benchmark presto, evitare effetti pesanti |
| Integrazione Pure Maps complessa | Medio | iniziare separata, cambiare front-end senza riscrivere GPS |
| Bluetooth metadata variabile tra telefoni | Basso | fallback senza copertina/titolo |
| Camera richiede H.264 software continuo | Alto | selezionare camera codec-aware, benchmark 2 stream |
| Picchi 12 V e cadute durante avvio motore | Alto | automotive DC/DC + supervisor, test a banco |
| Controlli relè non fail-safe | Alto | MCU watchdog, comandi manuali e schema verificato |
| SD/SSD corrotto dopo interruzione | Alto | shutdown, file segmentati, fs strategy, backup |
| Driver display/touch incompatibili | Medio | comprare solo dopo prova su stesso OS |
| Rumore audio da masse/alimentazione | Medio | alimentazioni separate, cavi e layout, bench audio |
| Scope troppo ampio per agenti | Alto | PR piccole, versioni incrementali, regression test |

## 13. Definition of Done generale

Una feature è completata solo se:

- [ ] Ha specifica e criteri di accettazione verificabili.
- [ ] Funziona in demo simulata e con errori/disconnessioni.
- [ ] Ha test automatici su logica e adapter (ove tecnicamente possibile).
- [ ] È utilizzabile da touchscreen senza tastiera e senza mouse.
- [ ] Non blocca video, altri dispositivi o comandi manuali.
- [ ] Registra errori diagnosticabili senza esporre dati privati.
- [ ] È descritta nel README/architettura e verificata sul Raspberry per le parti hardware.

## 14. Punto di partenza consigliato

Non iniziare da PCB, dashcam o mappe complete. Eseguire `INIT-01` → `CORE-01` → `SIM-01` → `UI-01` → `UI-02` e `UI-03`. A quel punto avremo una dashboard su Linux desktop, completamente funzionante con dati simulati, pronta per il Pi. Il GNSS già disponibile è la **prima integrazione hardware semplice**, seguita dal Bluetooth musicale: entrambe aggiungono valore immediato.

## 15. Fonti tecniche da usare come riferimenti di progetto

- Raspberry Pi OS (release 6 ottobre 2026): https://www.raspberrypi.com/software/operating-systems/
- Raspberry Pi 5, porte, power budget: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html
- Qt for Python / Qt Quick: https://doc.qt.io/qtforpython-6/PySide6/QtQuick/index.html
- BlueZ MediaPlayer D-Bus: https://github.com/bluez/bluez/blob/master/doc/org.bluez.MediaPlayer.rst
- WirePlumber Bluetooth: https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/bluetooth.html
- GStreamer splitmuxsink: https://gstreamer.freedesktop.org/documentation/multifile/splitmuxsink.html
- VE.Direct FAQ, isolamento: https://www.victronenergy.com/live/vedirect_protocol:faq
- OSM Scout Server: https://github.com/rinigus/osmscout-server
- Pure Maps: https://flathub.org/apps/io.github.rinigus.PureMaps
- Raspberry Pi 5 H.264 software encoding: https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-010033-WP-1-H.264%20encoding%20performance%20on%20Raspberry%20Pi%205_series%20computers.pdf

---

**Nota:** questo documento è una specifica tecnica iniziale. Dimensioni degli schermi, caratteristiche delle telecamere, disposizione e protezione dei cablaggi, protocolli Victron e GPIO definitivi devono essere fissati **dopo** le relative verifiche hardware. Non è una scheda di cablaggio omologata per il veicolo.
