# DNX Styler — Technische Architektur-, Key- & Verbindungsreferenz

Ergänzende Detailreferenz zu [`README.md`](../README.md).

![Gesamtarchitektur](dnx-architektur-verbindungen.png)
![Datenflüsse und Speicherung](dnx-datenfluss-speicherung.png)

---

## 1. Alle Browser-`localStorage`-Schlüssel

| Schlüssel | Modul / Bereich | Gespeicherter Inhalt |
|---|---|---|
| `dnx_styler_theme` | Receiver-Darstellung | Aktives Preset/Theme, Farben (`bg`, `panel`, `accent`, `btn`, `text`, `btntext`), `radius`, `glow`, `fx`, `sound`, `hover`, `pitch`, `rh`, `stan`, `stf`, `staus`, `stx`, `sty`, `mt*` |
| `dnx_styler_palettes` | Paletten-Creator | Liste selbst erstellter 3-Stopp-Verläufe (`dnxPalNeu`) |
| `dnx_styler_pillen_fx` | Effekte | Gewählte Mode-Pillen-Animation (`15` Varianten von `keiner` bis `blitz`) |
| `dnx_styler_tools` | Werkzeuge an / aus | Zustand der `TOOL_DEFS`-Werkzeugschalter (`t_*`, inkl. `t_wfglaettung`) |
| `dnx.spectrum.darstellung.v2` | Spektrum & Zahnrad (`⚙`) | `pal`, `hg`, `hoehe`, `hell`, `kont`, `saett`, `hue`, `weich`, `deck`, `raster`, `rasterDeck`, `skala` (`pegel` / `auto`) |
| `dnx.farben.v1` | Farben & Linien | Synchronisierter Satz für Wasserfall (`wf`), 3D-Palette (`cmap3d`), 3D-Hintergrund (`bg3d`), Linienfarbe (`linieFarbe`) & Liniendicke (`linieDicke`) |
| `dnx_styler_top_h` | Obere rote Ziehleiste | Pixelhöhe von `.webrx-top-container` (`96–600 px`, CSS-Var `--dnx-top-h`) |
| `dnx_styler_fft_h` | Untere rote Ziehleiste | Pixelhöhe des Spektrums (`24–400 px`, Doppelklick `50 px`, CSS-Var `--dnx-fft-h`) |
| `dnx_styler_smeter*` | S-Meter (Nadel) | Modell (`neu`, `georg1`, `georg2`, `alan48`), LCD-Farbe (`7` Farben), Effekt (`5`), Ein/Aus, X/Y-Offset (`DNX_SM_SX`/`SY`) |
| `dnx.zeitachse.*` / `dnx.<k>.seite` | Seiten & Zeitachse | Zeitabstand, Transparenz, Scroller sowie linke/rechte Dockseite (`L`/`R`) für `zeitachse`, `pegel`, `dmr` |
| `dnx_orig_slots_aus` | DMR-Slots | Ausblenden der Original-OpenWebRX-DMR-Slots zugunsten des DNX-Moduls |
| `dnx_styler_share_tok_<id>` | Teilen-Client | Lösch-Token zu selbst hochgeladenen Community-Skins auf `:8098` |
| `dnx_styler_std_signatur_v1` / `STD_TS_KEY` | Global-Standard-Sync | Zuletzt angewandte Standard-Revision (verhindert Überschreiben späterer lokaler Änderungen) |
| `dnx_3dtool` | `DNX-Integrated-Waterfall-3D` | `viewMode` (`std`/`3d`/`both`), `splitFlip`, `style`, `colormap`, `bg`, `heightScale`, `brightness`, `kontrast`, `gleich` (`⌂ 2D`), `linear`, `rows`, `cols`, `avgType`/`avgN`, `fps`, `invert`, `showFrame`/`showLabels` |
| `dnx.wfpro.state.v3` | `waterfall_pro.js` | Globaler + profilbezogener Wasserfall-Pegel (`__dnxPegelProfile`, bis `200`/`300` Profile) |
| `dnx_user`, `dnx_runtime_sources`, `dnx_remote_btn`, `dnx_admin` | `DNX-Remote-VIEW` | Benutzername, eigene Workspace-Quellen, Button-Position & Admin-Modus |

---

## 2. `TOOL_DEFS`-Werkzeugschalter (`t_*`) & Live-Masterleiste (`#dnx-master-tool-row`)

* **Audio & Dekoder:** `t_af` (Audio-Filter), `t_eq` (10-Band Grafik-EQ), `t_sounds` (FX/Pip-Töne), `t_dmr` (DMR-Slots), `t_oslot` (Original-Slots)
* **Anzeigen & Achsen:** `t_wf` (Wasserfall), `t_fft` (Spektrum), `t_ansicht` (3D-Ansicht), `t_tool3d` (3D-Tool-Popup), `t_pegel` (Pegel-Leiste), `t_zeitachse` (Zeitachse), `t_smeter` (S-Meter Nadel), `t_gelb` (Gelb Hover), `t_gruen` (Grün Tuning), `t_status` (DNX Status)
* **Funkgeräte & Zusatzmodule:** `t_funkgeraet1`, `t_funkgeraet2`, `t_funkgeraet3`, `t_dx` (DX-Cluster), `t_sonne` (Solar/HF), `t_wetter` (Wetter 2D/3D), `t_adsb` (ADS-B), `t_ais` (AIS), `t_iss` (ISS), `t_magnet` (Magnetfeld), `t_favoriten` (Scanner/Favoriten), `t_novnc` (noVNC/Foto), `t_remote` (Remote VIEW), `t_wfglaettung` (WF-Glättung)

---

## 3. Window-Bridges & CustomEvents

* **`window.dnxPalDaten()`** — liefert `{ wf, dnx, orig, msdr }` für Spektrum-Palette, Spektrum-Hintergrund, 2D-Wasserfall, 3D-Farbkarte und 3D-Hintergrund.
* **`window.dnx3dApi` & `Plugins.dnx_3dtool.configure()`** — setzt 3D-Ansicht, `colormap` und `bg` aus dem Styler heraus; geschützt durch `window.__dnx3dHgWache` (`700 ms`) und Ereignis `CustomEvent("dnx3d:hintergrund")`.
* **`window.__dnxPegelProfile` / `__dnxPegelProfileSet` / `__dnxPegelMerken()`** — Austausch des Pegelsatzes je SDR-Profil zwischen `waterfall_pro.js` und Styler (`#dnx-blk-pegel`).
* **`window.__dnxWeissSchutz`** — Schutz-Bridge für den `RF-GAIN`-Knopf (`dnx_rf_gain.js`) innerhalb von `waterfall_pro.js`.
* **`CustomEvent("dnx:basis")`** — meldet Basis-Änderungen an verknüpfte Overlays (z. B. `dnx_styler_basis`, `dnx_smeter`).
* **`window.DNXReceiverRights.can(key)`** — live aus `:8095/api/me` (`32` Rechte, z. B. `styler`, `waterfall3d`, `tool3d`, `profile_switch`, `scanner`, `remote`, `equalizer`, `fx`, `yellow_hover`, `green_tuning`, `timeline`, `dnx_status`, `novnc`, `administration`); bei API-Timeout (`6 s`) durch `dnx_rechte_puffer.js` bis `12 h` zwischengespeichert.
