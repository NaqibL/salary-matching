# Company names: duplicates and how they are resolved (SGSAL-032)

Source: the live company list on 22 Nov 2026 — **25,223 company names** (every name with an open ad, or 3+ ads ever) and the 2,140 cleaned-name aliases already recorded.

There are two different things that look like "duplicates". They are handled differently.

## 1. The same organisation spelled differently — merged automatically

**120 groups covering 241 names** (121 surplus names). These differ only in capital letters, the legal form ("Pte. Ltd.", "Limited", "LLP", "Co., Ltd.") or a trailing place qualifier ("(Singapore)", "(S)", "Singapore Branch", "Asia Pacific", "APAC").

How it is resolved: at the end of every crawl, `Storage.link_company_name_variants()` groups names by `mcf.lib.companies.names.name_key`, picks one display name per group (an already-cleaned name first, then the spelling with the most open ads) and writes it to `jobs.company_canonical`; the other spellings are recorded in `company_aliases`. No job row is deleted, and a second run changes nothing. New variants that appear later are merged by the next crawl.

- Preview without writing: `uv run python scripts/link_company_names.py`
- Apply now instead of waiting for the crawl: `uv run python scripts/link_company_names.py --apply`
- Undo a group: set `company_canonical` to NULL for its ads and delete its `company_aliases` rows.

What the rule deliberately does **not** do: drop words that tell sister companies apart ("Holdings", "Group", "Services", "International", "Trains" vs "Buses"); merge on a bare acronym plus a place ("AMT (Singapore)" and "AMT" stay separate); or treat a place that is part of the name as a qualifier ("Bank of Singapore").

The display name shown below is the one the rule would pick from spelling alone; in the database the spelling with the most open ads wins when no cleaned name exists.

| Shown as | Merged into it |
|---|---|
| A. Menarini | A. MENARINI ASIA-PACIFIC PTE. LTD. |
| ACCLAIM SYSTEMS PTE. LTD. | ACCLAIM SYSTEMS (ASIA) PTE. LTD. |
| ADDITIVE INN Limited Liability Partnership | ADDITIVE INN LIMITED LIABILITY PARTNERSHIP |
| Aetos Holdings | AETOS HOLDINGS PTE. LTD. |
| Alcon | ALCON PTE LTD |
| ALLIANZ TECHNOLOGY SE Singapore Branch | ALLIANZ TECHNOLOGY SE SINGAPORE BRANCH |
| Amgen | AMGEN ASIA PACIFIC PTE. LTD. |
| ANALOG DEVICES INTERNATIONAL, LLC Singapore Branch | ANALOG DEVICES INTERNATIONAL, LLC SINGAPORE BRANCH |
| Aramco | ARAMCO ASIA SINGAPORE PTE. LTD. |
| AstraZeneca | ASTRAZENECA SINGAPORE PTE LTD |
| AZQORE SA Singapore Branch | AZQORE SA SINGAPORE BRANCH |
| THE BALLET SCHOOL | THE BALLET SCHOOL (SINGAPORE) PTE. LTD. |
| Bank J. Safra Sarasin | BANK J. SAFRA SARASIN LTD, SINGAPORE BRANCH |
| Bank Julius Baer & Co. | BANK JULIUS BAER & CO. LTD. |
| BARINGA CONSULTING LIMITED (Singapore Branch) | BARINGA CONSULTING LIMITED (SINGAPORE BRANCH) |
| BARRINGTON JAMES LIMITED Singapore Branch | BARRINGTON JAMES LIMITED SINGAPORE BRANCH |
| BCD TRAVEL SINGAPORE PTE. LTD. | BCD TRAVEL ASIA PACIFIC PTE. LTD. |
| BDO UNIBANK, INC. (Singapore Branch) | BDO UNIBANK, INC. (SINGAPORE BRANCH) |
| BEIJING URBAN CONSTRUCTION GROUP CO., LTD. (Singapore Branch) | BEIJING URBAN CONSTRUCTION GROUP CO., LTD. (SINGAPORE BRANCH) |
| BlackRock | BLACKROCK (SINGAPORE) LIMITED |
| Canadian International School | CANADIAN INTERNATIONAL SCHOOL PTE LTD |
| Capgemini Singapore  PTE. LTD. | CAPGEMINI SINGAPORE  PTE. LTD. |
| CAPYSWIM | CAPYSWIM LLP |
| Ceva Logistics Solutions Singapore PTE. LTD. | CEVA LOGISTICS SOLUTIONS SINGAPORE PTE. LTD. |
| Chanel | Chanel Asia Pacific |
| Cheil Singapore PTE. LTD. | CHEIL SINGAPORE PTE. LTD. |
| China CITIC Bank International Singapore Branch | CHINA CITIC BANK INTERNATIONAL LIMITED SINGAPORE BRANCH |
| CHINA CIVIL ENGINEERING CONSTRUCTION CORPORATION Branch Office Singapore | CHINA CIVIL ENGINEERING CONSTRUCTION CORPORATION BRANCH OFFICE SINGAPORE |
| China Communications Construction Company (Singapore Branch) | CHINA COMMUNICATIONS CONSTRUCTION COMPANY LIMITED (SINGAPORE BRANCH) |
| CHINA ENERGY ENGINEERING GROUP SHANXI ELECTRIC POWER ENGINEERING CO., LTD. (Singapore Branch) | CHINA ENERGY ENGINEERING GROUP SHANXI ELECTRIC POWER ENGINEERING CO., LTD. (SINGAPORE BRANCH) |
| CHINA ENERGY ENGINEERING GROUP SHANXI NO.3 ELECTRIC POWER CONSTRUCTION CO., LTD. (Singapore Branch) | CHINA ENERGY ENGINEERING GROUP SHANXI NO.3 ELECTRIC POWER CONSTRUCTION CO., LTD. (SINGAPORE BRANCH) |
| CHINA HARBOUR ENGINEERING COMPANY LTD Singapore Branch | CHINA HARBOUR ENGINEERING COMPANY LTD SINGAPORE BRANCH |
| CHINA JINGYE ENGINEERING CORPORATION LIMITED (Singapore Branch) | CHINA JINGYE ENGINEERING CORPORATION LIMITED (SINGAPORE BRANCH) |
| CHINA RAILWAY 11 BUREAU GROUP CORPORATION (Singapore Branch) | CHINA RAILWAY 11 BUREAU GROUP CORPORATION (SINGAPORE BRANCH) |
| CHINA RAILWAY CONSTRUCTION GROUP CORPORATION LIMITED Singapore Branch | CHINA RAILWAY CONSTRUCTION GROUP CORPORATION LIMITED SINGAPORE BRANCH |
| CHINA RAILWAY FIRST GROUP CO., LTD. Singapore Branch | CHINA RAILWAY FIRST GROUP CO., LTD. SINGAPORE BRANCH |
| CHINA RAILWAY TUNNEL GROUP CO., LTD. (Singapore Branch) | CHINA RAILWAY TUNNEL GROUP CO., LTD. (SINGAPORE BRANCH) |
| CHINA-SINGAPORE SUZHOU INDUSTRIAL PARK DEVELOPMENT GROUP CO., LTD. (Singapore Branch) | CHINA-SINGAPORE SUZHOU INDUSTRIAL PARK DEVELOPMENT GROUP CO., LTD. (SINGAPORE BRANCH) |
| CHINA STATE CONSTRUCTION ENGINEERING CORPORATION LIMITED Singapore Branch | CHINA STATE CONSTRUCTION ENGINEERING CORPORATION LIMITED SINGAPORE BRANCH |
| Chubb Asia Pacific | CHUBB SINGAPORE PRIVATE LIMITED |
| Citibank | Citibank Singapore |
| CYBERBOT PTE. LTD. | CYBERBOT (S) PTE. LTD. |
| Delivery Hero APAC | DELIVERY HERO (SINGAPORE) PTE. LTD. |
| DONGAH GEOLOGICAL ENGINEERING CO., LTD, Singapore Branch | DONGAH GEOLOGICAL ENGINEERING CO., LTD, SINGAPORE BRANCH |
| Dyson | DYSON SINGAPORE PTE. LIMITED |
| EASMED PTE. LTD. | EASMED ASIA PTE. LTD. |
| EDEN LOFT PTE. LTD. | EDEN LOFT SG PTE. LTD. |
| EPG BUILDING SERVICES | EPG BUILDING SERVICES PTE. LTD. |
| EXENTEC SINGAPORE PTE. LTD. | EXENTEC SINGAPORE  PTE. LTD. |
| Fujifilm | FUJIFILM ASIA PACIFIC PTE. LTD. |
| Furama | FURAMA PTE. LTD. |
| FUTURE TECHNOLOGY DEVICES INTERNATIONAL LIMITED Singapore Branch | FUTURE TECHNOLOGY DEVICES INTERNATIONAL LIMITED SINGAPORE BRANCH |
| Geodis | GEODIS SINGAPORE PTE. LTD. |
| Hapag-Lloyd | HAPAG-LLOYD PTE. LTD. |
| HCL Singapore | HCL SINGAPORE PTE. LTD. |
| Hewlett-Packard Singapore | Hewlett-Packard Asia Pacific |
| Hitachi Plant Construction | HITACHI PLANT CONSTRUCTION, LTD. SINGAPORE BRANCH |
| ICBC Standard Bank | ICBC STANDARD BANK PLC SINGAPORE BRANCH |
| ILJIN ELECTRIC CO., LTD Singapore Branch | ILJIN ELECTRIC CO., LTD SINGAPORE BRANCH |
| Infosys | Infosys Singapore |
| Infosys BPM | INFOSYS BPM LIMITED SINGAPORE BRANCH |
| Kajima | KAJIMA CORPORATION |
| Keppel Management | KEPPEL MANAGEMENT LTD. |
| Kookmin Bank | KOOKMIN BANK CO., LTD. SINGAPORE BRANCH |
| KPMG Services | KPMG SERVICES PTE. LTD. |
| L&K ENGINEERING (SUZHOU) CO., LTD. Singapore Branch | L&K ENGINEERING (SUZHOU) CO., LTD. SINGAPORE BRANCH |
| Lapp | LAPP SINGAPORE PTE. LTD. |
| LASH PALACE PTE. LTD. | LASH PALACE SG PTE. LTD. |
| Leighton Contractors | LEIGHTON CONTRACTORS (ASIA) LIMITED (SINGAPORE BRANCH) |
| LG CNS | LG CNS CO., LTD. SINGAPORE BRANCH |
| Lotte Engineering & Construction | LOTTE ENGINEERING & CONSTRUCTION CO., LTD. SINGAPORE BRANCH |
| LT SAMBO CO., LTD. (Singapore Branch) | LT SAMBO CO., LTD. (SINGAPORE BRANCH) |
| LTM LIMITED Singapore Branch | LTM LIMITED SINGAPORE BRANCH |
| Marina Bay Sands | MARINA BAY SANDS  PTE. LTD. |
| MSD International | MSD INTERNATIONAL GMBH (SINGAPORE BRANCH) |
| MUFG Bank | MUFG BANK, LTD. SINGAPORE BRANCH |
| NESTE SINGAPORE PTE. LTD. | NESTE ASIA PACIFIC PTE. LTD. |
| New Hope Community Services | NEW HOPE COMMUNITY SERVICES LIMITED |
| NORGES BANK Singapore Branch | NORGES BANK SINGAPORE BRANCH |
| NUOVO PIGNONE INTERNATIONAL S.R.L. Singapore Branch | NUOVO PIGNONE INTERNATIONAL S.R.L. SINGAPORE BRANCH |
| OASIS PTE. LTD. | THE OASIS SG PTE. LTD. |
| Okumura | OKUMURA CORPORATION SINGAPORE BRANCH |
| PASSION E&C PTE. LTD. | PASSION E&C SG PTE. LTD. |
| PCF Sparkletots Preschool | PCF SPARKLETOTS PRESCHOOL LIMITED |
| Perennial Holdings | PERENNIAL HOLDINGS PRIVATE LIMITED |
| THE PIANO SOLUTION Limited Liability Partnership | THE PIANO SOLUTION LIMITED LIABILITY PARTNERSHIP |
| PT BANK RAKYAT INDONESIA (PERSERO) TBK Singapore Branch | PT BANK RAKYAT INDONESIA (PERSERO) TBK SINGAPORE BRANCH |
| RHQ RABBITHEADQUARTERS Limited Liability Partnership | RHQ RABBITHEADQUARTERS LIMITED LIABILITY PARTNERSHIP |
| Saint-Gobain (Singapore) PTE. LTD. | SAINT-GOBAIN (SINGAPORE) PTE. LTD. |
| Samsung | SAMSUNG ASIA PTE. LTD. |
| Sankyu | SANKYU (SINGAPORE) PTE LTD |
| SBM | SBM PTE. LTD. |
| SEAFOOD PARADISE SG PTE. LTD. | SEAFOOD PARADISE (S) PTE. LTD. |
| SHANGHAI TUNNEL ENGINEERING CO. LTD. | SHANGHAI TUNNEL ENGINEERING CO (SINGAPORE) PTE LTD |
| Shimadzu | SHIMADZU SINGAPORE PTE LTD |
| Singapore Veterinary Health PTE. LTD. | SINGAPORE VETERINARY HEALTH PTE. LTD. |
| Sinohydro Corporation | SINOHYDRO CORPORATION LIMITED (SINGAPORE BRANCH) |
| SMITH & NEPHEW PTE. LIMITED | SMITH & NEPHEW ASIA PACIFIC PTE. LIMITED |
| SNEAKSURF Limited Liability Partnership | SNEAKSURF LIMITED LIABILITY PARTNERSHIP |
| SOJITZ ASIA PTE. LTD. | SOJITZ CORPORATION SINGAPORE BRANCH |
| SPS UK&I LIMITED Singapore Branch | SPS UK&I LIMITED SINGAPORE BRANCH |
| Sumitomo Mitsui Banking Corporation | SUMITOMO MITSUI BANKING CORPORATION SINGAPORE BRANCH |
| Taipei Fubon Commercial Bank | TAIPEI FUBON COMMERCIAL BANK CO., LTD. SINGAPORE BRANCH |
| Tech Data | TECH DATA (SINGAPORE) PTE. LTD. |
| Tech Mahindra | TECH MAHINDRA (SINGAPORE) PTE. LIMITED · TECH MAHINDRA LIMITED (SINGAPORE BRANCH) |
| TECHCOM SOLUTIONS PTE. LTD. | TECHCOM SOLUTIONS (SINGAPORE) PTE. LTD. |
| TEX-STAR ENGINEERING PTE LTD | TEX-STAR ENGINEERING SINGAPORE PTE LTD |
| TMF SINGAPORE H PTE. LTD. | TMF SINGAPORE H  PTE. LTD. |
| Toppan Next Tech PTE. LTD. | TOPPAN NEXT TECH PTE. LTD. |
| TP ICAP Markets (Singapore) PTE. LTD. | TP ICAP MARKETS (SINGAPORE) PTE. LTD. |
| TRACX LOGIS LTD. | TRACX LOGIS PTE. LTD. |
| TRADITION SINGAPORE PTE. LTD. | TRADITION ASIA PACIFIC (PTE.) LTD. |
| TVS Motor Company | TVS MOTOR COMPANY LIMITED SINGAPORE BRANCH |
| United Microelectronics | UNITED MICROELECTRONICS CORPORATION (SINGAPORE BRANCH) |
| Vanguard Healthcare PTE. LTD. | VANGUARD HEALTHCARE PTE. LTD. |
| Vistra Corporate Services | VISTRA CORPORATE SERVICES (S) PTE. LTD. |
| Wipro | WIPRO LIMITED (SINGAPORE BRANCH) |
| WUHAN LINGYUN BUILDING TECHNOLOGY CO., LTD (Singapore Branch) | WUHAN LINGYUN BUILDING TECHNOLOGY CO., LTD (SINGAPORE BRANCH) |
| ZHEJIANG ETONE SPECIALIZED FOUNDATION ENGINEERING CO., LTD. Singapore Branch | ZHEJIANG ETONE SPECIALIZED FOUNDATION ENGINEERING CO., LTD. SINGAPORE BRANCH |
| Zurich Insurance | ZURICH INSURANCE COMPANY LTD (SINGAPORE BRANCH) |

## 2. Separate companies of one brand — not merged

These are different registered companies that share a brand (subsidiaries, business units, regional entities). They keep separate pages because their open roles and pay genuinely differ, and merging them by rule would also merge unrelated firms that happen to share a first word. The earlier clean-up (`scripts/canonicalize_companies.py`, which asks a language model to recognise well-known brands) is the tool for collapsing a family when that is wanted; it is not run automatically.

Families a job-seeker is most likely to notice:

- **deloitte** (8 names): DELOITTE & TOUCHE MANAGEMENT SERVICES PTE LTD · DELOITTE SINGAPORE ASSURANCE PTE. LTD. · DELOITTE SINGAPORE CORPORATE SERVICES PTE. LTD. · DELOITTE SINGAPORE SR&T PTE. LTD. · DELOITTE SINGAPORE T&T CYBER PTE. LTD. · DELOITTE SINGAPORE T&T PTE. LTD. · DELOITTE SINGAPORE TAX SERVICES PTE. LTD. · Deloitte & Touche
- **smrt** (4 names): SMRT BUSES LTD. · SMRT Corporation · SMRT Tel · SMRT Trains
- **hsbc** (3 names): HSBC · HSBC Global Asset Management · HSBC Life
- **ernst** (3 names): ERNST & YOUNG ADVISORY PTE. LTD. · ERNST ENGINEERING PTE. LTD. · Ernst & Young
- **natureland** (9 names): NATURELAND CARE PTE. LTD. · NATURELAND CLINIC PTE. LTD. · NATURELAND ENTERPRISE PTE. LTD. · NATURELAND GLOBAL PTE. LTD. · NATURELAND GROUP PTE. LTD. · NATURELAND INTERNATIONAL PTE. LTD. · NATURELAND PREMIUM PTE. LTD. · NATURELAND SINGAPORE PTE. LTD. · NATURELAND WELLNESS PTE. LTD.
- **keppel** (11 names): KEPPEL DHCS O&M PTE. LTD. · KEPPEL ENERGY PTE. LTD. · KEPPEL MANAGEMENT LTD. · KEPPEL SEGHERS ENGINEERING SINGAPORE PTE. LTD. · Keppel Capital International · Keppel Club · Keppel DC Services · Keppel DHCS · Keppel EAAS · Keppel Management · Keppel Technology Solutions
- **sembcorp** (10 names): SEMBCORP ARCHITECTS & ENGINEERS PTE. LTD. · SEMBCORP COGEN PTE LTD · SEMBCORP DEVELOPMENT LTD. · SEMBCORP GAS PTE LTD · SEMBCORP POWER PTE LTD · SEMBCORP SOLAR SINGAPORE PTE. LTD. · SEMBCORP SPECIALISED CONSTRUCTION PTE. LTD. · SEMBCORP UTILITIES PTE LTD · SEMBCORP UTILITIES SERVICES PTE. LTD. · Sembcorp Industries
- **capitaland** (2 names): CAPITALAND COMMERCIAL MANAGEMENT PTE. LTD. · CapitaLand Retail Management
- **ntuc** (8 names): NTUC Club · NTUC ENTERPRISE NEXUS CO-OPERATIVE LIMITED · NTUC FairPrice · NTUC First Campus · NTUC Foodfare · NTUC HEALTH CO-OPERATIVE LTD · NTUC LearningHub · NTUC My First Skool
- **surbana** (6 names): SURBANA JURONG PRIVATE LIMITED · SURBANA JURONG SERVICES PTE. LTD. · Surbana Jurong Consultants · Surbana Jurong Infrastructure · Surbana Site Supervisors · Surbana Technologies
- **grabtaxi** (2 names): GRABTAXI PTE. LTD. · GrabTaxi Holdings
- **allianz** (5 names): ALLIANZ GLOBAL CORPORATE & SPECIALTY SE Singapore Branch · ALLIANZ SE · ALLIANZ TECHNOLOGY SE SINGAPORE BRANCH · ALLIANZ TECHNOLOGY SE Singapore Branch · Allianz
- **hitachi** (10 names): HITACHI AQUA-TECH ENGINEERING PTE. LTD. · HITACHI ASIA LTD. · HITACHI PLANT CONSTRUCTION, LTD. SINGAPORE BRANCH · Hitachi Elevator Asia · Hitachi Energy Singapore · Hitachi High-Tech · Hitachi Plant Construction · Hitachi Plant Services · Hitachi Rail Singapore · Hitachi Vantara
- **mitsubishi** (10 names): MITSUBISHI CORPORATION RTM INTERNATIONAL PTE. LTD. · MITSUBISHI ELECTRIC ASIA PTE LTD · MITSUBISHI POWER ASIA PACIFIC PTE. LTD. · MITSUBISHI UFJ TRUST AND BANKING CORPORATION · Mitsubishi · Mitsubishi Chemical · Mitsubishi Elevator · Mitsubishi Heavy Industries · Mitsubishi Heavy Industries Engine System · Mitsubishi Logistics
- **sumitomo** (8 names): SUMITOMO (SHI) CYCLO DRIVE ASIA PACIFIC PTE. LTD. · SUMITOMO BAKELITE SINGAPORE PTE. LTD. · SUMITOMO MITSUI BANKING CORPORATION SINGAPORE BRANCH · SUMITOMO WAREHOUSE (SINGAPORE) PTE. LTD. · Sumitomo Corporation · Sumitomo Electric · Sumitomo Mitsui Banking Corporation · Sumitomo Mitsui Trust Bank
- **singhealth** (2 names): SINGHEALTH COMMUNITY HOSPITALS · SINGHEALTH POLYCLINICS
- **parkway** (3 names): PARKWAY LABORATORY SERVICES LTD. · PARKWAY SHENTON PTE LTD · Parkway Hospitals
- **comfortdelgro** (5 names): ComfortDelGro Bus · ComfortDelGro Driving Centre · ComfortDelGro Engineering · ComfortDelGro Insurance Brokers · ComfortDelGro Rent-a-Car

Also separate, by design: **National University Hospital**, **NATIONAL UNIVERSITY HEALTH SYSTEM PTE. LTD.** and **NATIONAL UNIVERSITY HEALTH SERVICES GROUP PTE. LTD.** (the hospital, the cluster head office, and the cluster's services group).

Why a shared first word is not enough: "Raffles" starts 28 unrelated companies (a concrete supplier, a gymnastics academy, a health insurer), "Recruit" 11 separate agencies, "Changi" and "Jurong" 8 each.

For reference, 914 first words are shared by 3 or more distinct companies in the list; most are coincidences ("Apex …", "Pacific …"), which is why first-word matching is not used.

## 3. Search covers the gap

The companies search matches every recorded spelling (`company_aliases`) and common short names (NUH, SGH, GovTech, MOE, PwC, …), so a merged or abbreviated name is still found.

