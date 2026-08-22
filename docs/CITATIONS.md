# WORKFACE — Registry citation trail
### Every threshold in `data/trade_windows.json`, and where it came from · compiled 20 Aug 2026 by T3

Open any `source_url` and you will find the number. That is the standard this project holds itself
to — `WORKFACE_REPO_GUIDE.md`'s definition of done for a registry row is *"a citation a human could
go and check."*

| # | Trade | Key threshold(s) | Source | Status |
|---|---|---|---|---|
| 1 | Concrete — hot weather | Concrete ≤ 95 °F (35 °C) at discharge; evaporation rate ≤ 0.2 lb/ft²/hr (0.1 low-bleed) | [ACI FAQ — max temperature limits](https://www.concrete.org/frequentlyaskedquestions.aspx?faqid=15) · sections 3.2/3.3 via [NIH ORF bulletin](https://orf.od.nih.gov/TechnicalResources/Documents/Technical%20Bulletins/16TB/Concrete%20Construction%20Precautions%20during%20Cold%20Weather%20February%202016%20Technical%20Bulletin_508.pdf) · thresholds cross-checked at [FHWA](https://www.fhwa.dot.gov/publications/research/infrastructure/pavements/pccp/05038/005.cfm) (1.0 / 0.5 kg/m²/h) · [NJDOT MP 29-08](https://www.nj.gov/transportation/eng/construction/pdf/Material/MP_29_08.pdf) (0.15 cessation) | primary |
| 2 | Concrete — cold weather | Cold weather = air fallen to / expected below 40 °F (4 °C) during the protection period | [ACI 306R-16 preview](https://www.concrete.org/Portals/0/Files/PDF/Previews/306R-16_preview.pdf) §1.1, §2.2 | **partial** — 72 h / 10 °C protection values are ours; ACI Table 5.1 paywalled |
| 3 | Structural steel epoxy coating | Air 35–120 °F · surface 35–250 °F · **≥ 5 °F (2.8 °C) above dew point** · RH ≤ 85 % · cure-to-service 10 d @ 35 °F, 7 d @ 77 °F, 4 d @ 100 °F | [Macropoxy 646 PDS](https://kta.com/wp-content/uploads/2020/09/SW-PDS.pdf) (rev. 21 May 2020) · [SSPC-PA 1 §6.2](https://relisleeve.com/wp-content/uploads/2021/12/sspc_pa_1.pdf) | primary |
| 4 | SFRM fireproofing | Substrate **and** ambient ≥ 40 °F maintained prior to, during, and **≥ 24 h after** application; ≥ 4 air changes/hour | [Isolatek CAFCO 300 TDS](https://www.isolatek.com/wp-content/uploads/2020/05/CAFCO-300_C-TDS_05-20.pdf) §1.7.1, §1.7.2.1 | primary |
| 5 | Adhesive anchors | Base material −5 to +40 °C; working time **120 min at 0 °C → 10 min at 40 °C**; cure 168 h → 4 h; ×2 in wet holes | [Hilti HIT-RE 500 V3 technical data](https://files-ask.hilti.com/original/2u/2urtfhut9a.pdf) | primary |
| 6 | HMA paving | Air ≥ 40 °F and rising; compaction minutes = f(base surface temp, lift thickness) — 3 in mat 26–34 min at 20–50 °F base, 1 in mat 5–7 min | [TxDOT Research Report 214-11](https://rosap.ntl.bts.gov/view/dot/85341/dot_85341_DS1.pdf) Tables 2–4 · [Graniterock](https://www.graniterock.com/technical_reports/cold-weather-asphaltic-concrete-compacti?category_id=90) hot-base row | **partial** — intermediate rows interpolated |
| 7 | Masonry — hot weather | Procedures above 100 °F, **or above 90 °F with wind > 8 mph**; enhanced above 115 °F or 105 °F with wind | [BIA Technical Note 1 / CMHA TEK 03-01C](https://www.jandsmasonry.com/wp-content/uploads/2019/03/1-TEK-03-1C-All-Weather-Construction.pdf) reproducing TMS 602 Tables 2a/2b | secondary — TMS 602 paywalled |
| 8 | Masonry — cold weather | Do not lay units below 20 °F; maintain masonry above 32 °F for 24 h (48 h grouted) | same source, Tables 1a/1b | secondary |
| 9 | Silicone weatherseal | Substrate −20 °F to 122 °F; do not apply on frost-laden or wet surfaces; below dew/frost point surfaces must be clean, dry and frost-free | [DOWSIL 795 TDS](https://www.valtec.ca/uploads/userfiles/files/Section%20''Document''.Fiches%20Tech/795%20FT_2017_EN.pdf) (Form 61-885-01 S) · [Dow cold-weather guide](https://www.dow.com/documents/63/63-6171-01-installation-building-sealants-cold-weather.pdf) · ASTM C1193 as `standard_ref` only | primary |
| 10 | Waterborne marking | 55 °F **and rising** min air and surface; never below 45 °F; MoDOT 50 °F minor / 60 °F major roads | Sherwin-Williams Sher-Flight PDS (06/18) · [MoDOT EPG 620.11](https://epg.modot.org/index.php/620.11_Guidelines_for_Using_Water-Borne_Traffic_Paint) | **partial** — the 1.7 °C dew-point offset is ours, not published |
| 11 | Structural welding | Prequalified preheat, Category B: ≤ ¾″ → 32 °F · ¾–1½″ → 50 °F · 1½–2½″ → 150 °F · > 2½″ → 225 °F | [UFC 3-320-01A Table 3-1](https://buildingcriteria1.tpub.com/ufc_3_320_01a/ufc_3_320_01a0151.htm) reproducing AWS D1.1 | secondary — AWS D1.1 paywalled; **table number differs by edition, don't cite one** |
| 12 | Crew heat exposure | Initial trigger HI 80 °F; high-heat trigger HI 90 °F → **15 min break every 2 h** | [OSHA rulemaking fact sheet](https://www.osha.gov/sites/default/files/publications/heat-rulemaking-factsheet.pdf) · [WBGT equation, OTM III:4](https://www.osha.gov/otm/section-3-health-hazards/chapter-4) · [status](https://www.osha.gov/heat-exposure/rulemaking/) | **partial** — WBGT→work/rest bands are ours; ACGIH table is copyrighted |

---

## Three facts worth saying out loud

**1. The rule is not final, and saying so accurately is a credibility win.**
OSHA's heat NPRM published 30 Aug 2024; the informal hearing closed 2 Jul 2025 and the post-hearing
comment period closed 30 Oct 2025, with **no target date announced for a final rule** as of mid-2026.
In the interim OSHA enforces heat under the General Duty Clause §5(a)(1), and **renewed its Heat
National Emphasis Program on 10 April 2026 for five further years, through 2031.** Seven states
(CA, CO, MD, MN, NV, OR, WA) enforce their own heat rules. Stating this correctly shows the team
checked rather than assumed.

**2. ACI 305 does not define hot weather as a temperature.** It defines it as *"any combination of
high air temperature, low relative humidity, wind, and solar radiation."* Two evaporation-rate
numbers prove it:

| | Tc | Ta | RH | Wind | E (lb/ft²/hr) | |
|---|---|---|---|---|---|---|
| Cool windy morning | 75 °F | 75 °F | 15 % | 15 mph | **0.290** | precautions mandatory |
| Hot calm afternoon | 90 °F | 95 °F | 50 % | 2 mph | **0.059** | not anticipated |

Every `if temp > X` competitor is wrong about this by construction. Put both rows on one slide.

**3. One trade's red is another trade's green.** Hot weather *helps* asphalt compaction — the
available compaction window runs 4 min at a 13 mm lift with a cold base and 15+ min with a base above
90 °F — and hurts everything else, on the same tile in the same hour. Cheapest possible proof that
WORKFACE is not a heat alarm.

---

## Surface-twin coefficients (Day 4.5 — `scripts/make_thermal_fixtures.py`)

The per-work-face surface temperature is a first-order energy balance
(WORKFACE_TECH_SPEC.md §6.2), `t_surf = t_air + (α·GHI − ε·Q_lw·(1−cloud/8))·ψ / (h_c(V)+h_r)`.
Its coefficients are published ranges, not measurements — the model is labelled
"model, not measurement" and does not replace the surface thermometer the standards require.

| Coefficient | Value(s) | Source |
|---|---|---|
| Solar absorptivity α | asphalt 0.90 · bare concrete 0.60 · CMU 0.55 · coated steel 0.45 · **galvanised steel 0.30** | WORKFACE_TECH_SPEC §6.2; ASHRAE *Fundamentals* ch. 26 surface-property tables. Bright galvanised is a **low** absorber — it runs hot from near-zero thermal mass, not high absorption. |
| Thermal emissivity ε | asphalt 0.93 · concrete/CMU 0.90 · coated steel 0.88 · **weathered galvanised steel 0.85** | ASHRAE *Fundamentals* ch. 26; Engineering Toolbox emissivity tables. Erected/weathered galvanising oxidises to a high-emissivity surface — the physical basis for the open deck's night radiative cooling. |
| Convective/radiative coefficients | `h_c(V)=5.7+3.8·V` (V m/s), `h_r=5 W/m²K` | WORKFACE_TECH_SPEC §6.2 (McAdams-form flat-plate convection; linearised longwave). |
| Clear-sky net longwave loss `Q_lw` | **130 W/m²** | Arid-climate radiative-cooling literature reports ~90–150 W/m² net longwave from high-ε horizontal surfaces under clear, dry skies. **The hero dawn closure sits on the upper half of this range and is fragile — see the Day-4.5 report's sensitivity note.** A humid monsoon dawn raises sky emissivity and *suppresses* this term, so 130 is generous, not conservative. |
| Substrate thermal-mass damping | steel 1.0 · asphalt 0.70 · concrete/CMU 0.65 | Amplitude proxy for thermal lag: thin steel tracks its surface, a massive slab is buffered toward air. Stated as a simplification, not a lag model. |

## Rule for the deck

Cite the **document you actually read**, not the standard behind it. Say *"BIA Technical Note 1,
reproducing TMS 602"* rather than *"TMS 602 Article 1.8 C"*, and say *"the AWS D1.1 prequalified
preheat table"* rather than *"AWS D1.1 Table 3.2"* — the table number moved between editions. A judge
who owns the standard will check, and being one layer more careful than necessary reads as rigour.

*All outputs are advisory and contractual. WORKFACE plans the work and produces the record; it does
not certify, and it does not replace the field measurement the referenced standards require.*
