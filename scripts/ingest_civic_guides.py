#!/usr/bin/env python3
"""Ingest curated Zambian e-government / civic PROCEDURE guides into the corpus.

Levy answers "what does the law say" well, but ~43% of real tool calls fell back
to the web because users kept asking "how do I actually DO this" — change car
ownership (RTSA), get a TPIN (ZRA), register a company (PACRA), apply for a
passport, NRC, permits, NAPSA/NHIMA, certificates, land title. That admin/e-gov
layer is not in the Acts. These guides fill it.

Each guide is stored as document_type='guide' so:
  - search_corpus surfaces it in live chat (it does NOT filter by type), and
  - search_case_law ignores it (it only keeps document_type=='judgment').

Content is grounded in official sources (rtsa.org.zm, zra.org.zm, pacra.org.zm,
zambiaimmigration.gov.zm, napsa.co.zm, nhima.co.zm, zamportal.gov.zm, DNRPC,
Ministry of Lands) as of 2026-07. Volatile figures (fees, tax bands, ceilings)
carry an explicit "confirm current" flag so Levy never states them as settled.

Idempotent: skips a guide whose title already exists as a guide. Safe to re-run.
Usage: .../python scripts/ingest_civic_guides.py
"""
from __future__ import annotations
import re, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))
import _dns_resilient  # noqa: E402,F401
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db, insert_chunks       # noqa: E402
from app.services.embedder import get_embeddings         # noqa: E402


def retry(fn, n=8, d=1.2):
    last = None
    for _ in range(n):
        try:
            return fn()
        except Exception as e:
            last = e; time.sleep(d)
    raise last


def chunk_text(text: str, target: int = 1200) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur, hard = [], "", int(target * 1.5)
    for p in paras:
        if len(cur) + len(p) <= hard:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks or [text]


# Each guide: title (the "how do I" phrasing), short_name (citation label the UI
# shows), authority, law, url (primary official source), body (the guide text).
GUIDES: list[dict] = [
    # ─────────────────────────── RTSA / VEHICLES ───────────────────────────
    {
        "title": "How to transfer vehicle ownership in Zambia (RTSA change of ownership)",
        "short_name": "RTSA guide: vehicle change of ownership",
        "authority": "Road Transport and Safety Agency (RTSA)",
        "law": "Road Traffic Act No. 11 of 2002",
        "url": "https://www.rtsa.org.zm/transport/registration/",
        "body": """You are only the legal owner of a vehicle once the **registration certificate (the "white book")** bears your exact names. Buying a car is not enough; you must transfer it at RTSA.

**Steps:**
1. Buyer and seller complete an original **Letter of Sale** (a donation letter if gifted; on signed, stamped headed paper if either party is a company).
2. Take the vehicle for a **physical inspection** at an RTSA centre (you get an inspection report and receipt).
3. The seller obtains a **ZRA tax clearance certificate for change of ownership** (needs a TPIN).
4. Obtain a **Police anti-theft clearance report** and swear a **General Affidavit** before a Commissioner for Oaths.
5. Complete **Form MVR 1**, signed by BOTH seller and buyer.
6. Submit the pack with the **original white book** and both parties' NRCs (or certificate of incorporation) to RTSA and pay. A new white book is issued in the buyer's name.
7. Separately, the seller should file the online **"Notification of Change of Ownership"** on the RTSA site — until this is done the seller stays liable and the vehicle can be impounded.

**Documents:** Letter of sale/donation; ZRA change-of-ownership tax clearance; NRC of buyer and seller; original white book; RTSA inspection report; Police anti-theft clearance; General Affidavit; Form MVR 1 (both signatures).

**Fees:** RTSA lists roughly **K476** for change of ownership plus about **K64** for the physical inspection. Fees are set in fee units under SI No. 25 of 2024 and change — **confirm the current fee with RTSA before quoting it.**

**Where:** In person at any RTSA office (the inspection is mandatory); the notification is online at rtsa.org.zm. ZRA tax clearance via ZRA.

**Notes:** The car must have valid road tax and a valid fitness certificate before transfer. **Insurance ends on change of ownership — the buyer must take out new cover.** Governing law: Road Traffic Act No. 11 of 2002. This is a practical procedure guide, not a statute.""",
    },
    {
        "title": "How to register an imported car in Zambia (first registration, RTSA and ZRA)",
        "short_name": "RTSA guide: first registration of a vehicle",
        "authority": "Road Transport and Safety Agency (RTSA)",
        "law": "Road Traffic Act No. 11 of 2002; Customs and Excise Act",
        "url": "https://www.rtsa.org.zm/transport/registration/",
        "body": """Registering a newly imported vehicle runs through ZRA (customs), the Police/Interpol, then RTSA.

**Steps (in order):**
1. **ZRA customs clearance** — clear the vehicle through ZRA (ASYCUDAWorld). Pay import duty (see below), VAT and the carbon emission surtax. You receive the Customs Clearance Certificate / e-Redbook, ZRA receipt, customs declaration (Form CE 20) and a Release Order.
2. **Interpol clearance** — get the Zambia Police / Interpol clearance certificate (screens for stolen vehicles).
3. **RTSA physical inspection** — present the vehicle (report + receipt).
4. **Insurance** — take out at least third-party cover.
5. **Submit registration to RTSA** with Form CNV1 and Form RL3 → RTSA issues the white book and number plate.
6. **Pay road tax** (motor vehicle licence) to be road-legal.

**Import duty (ZRA):** most used vehicles are charged **specific duty** — a fixed Kwacha amount by vehicle type, engine size and age that bundles customs duty, excise, VAT and fees — while vehicles under about two years old and hybrids may be charged on CIF value. A carbon emission surtax is added by engine size. **The exact duty depends on the specific make/model/year — always use ZRA's Motor Vehicle Tax Calculator; do not quote a figure from memory.** Note: Zambia does NOT charge an "Import Declaration Fee (IDF)" — it was scrapped in 1998; the import declaration form is for statistics only.

**Fees:** RTSA registration around **K238**, Interpol clearance around **K200**, inspection around **K64** — **confirm current RTSA fees**; import duty is separate and paid to ZRA.

**Where:** ZRA (customs, TPIN required) then RTSA (in-person inspection required); some steps are on ZamPortal. Governing law: Road Traffic Act No. 11 of 2002 (registration); Customs and Excise Act (duty).""",
    },
    {
        "title": "How to pay road tax (motor vehicle licence) in Zambia online",
        "short_name": "RTSA guide: road tax / motor vehicle licence",
        "authority": "Road Transport and Safety Agency (RTSA)",
        "law": "Road Traffic Act No. 11 of 2002; SI No. 25 of 2024",
        "url": "https://www.rtsa.org.zm/pay-online/",
        "body": """"Road tax" is the motor vehicle licence. It is separate from insurance and from the fitness certificate — you need all three.

**Steps (online):**
1. Register or log in to **ZamPass** using your NRC or driver's licence number plus your registered phone/email (you must already be on the RTSA system as an owner or licence holder).
2. On **ZamPortal**, choose "Motor Vehicle Licence (Road Tax)".
3. Pick the period — 1, 2, 3 or 4 quarters (each quarter is 25% of the annual fee; there is no quarterly surcharge).
4. Pay by mobile money or bank transfer. The licence disc is posted to you or collected at any RTSA office. The service runs 24/7 and needs no documents.

**Fees:** set by the vehicle's gross weight band under SI No. 25 of 2024 (not engine size). Amounts vary by band — **confirm the exact figure on the RTSA/ZamPortal licence screen for your vehicle.**

**Where:** Online via ZamPortal / ZamPass, mobile money, or any RTSA service centre; also rtsa.org.zm/pay-online.

**Notes:** Driving with expired road tax is an offence and the vehicle can be impounded; penalties can reach up to three times the annual tax. Under the 2022 amendment you cannot license a vehicle while you have outstanding traffic offences, and after several unlicensed years RTSA may cancel the registration. Governing law: Road Traffic Act No. 11 of 2002.""",
    },
    {
        "title": "How to get or renew a driver's licence in Zambia (RTSA)",
        "short_name": "RTSA guide: driver's licence",
        "authority": "Road Transport and Safety Agency (RTSA)",
        "law": "Road Traffic Act No. 11 of 2002",
        "url": "https://www.rtsa.org.zm/transport/driver-licencing/",
        "body": """**New licence (standard route):**
1. Get a medical certificate from an approved facility; you must be 18+ (16 for a rider's licence).
2. Sit and pass the computerised **theory test** at RTSA.
3. Pay for and receive a **Provisional Driving Licence**.
4. At least **7 days later**, sit the **practical driving test**.
5. On passing, pay for printing of the licence.

**Renewal / duplicate:** renew before or after expiry (a higher fee applies once expired); a lost licence needs a police report and a General Affidavit; a defaced licence is replaced on production of the old one.

**Documents:** NRC or passport; medical certificate (new/PSV); existing licence (renewal/duplicate); police report + affidavit (lost).

**Classes:** cover motorcycles, light and heavy vehicles, with PSV endorsements for passengers, taxi, goods and dangerous goods (the latter needs a HAZCHEM certificate). There are also provisional rider's, driving-instructor, foreign-licence conversion and international-permit categories.

**Fees:** each step (provisional, tests, printing, renewal, duplicate) is billed separately under SI No. 25 of 2024 — **confirm current RTSA fees.**

**Where:** the new-licence tests are in person at RTSA; renewals, duplicates, PSV renewal and test booking are available online on ZamPortal / ZamPass. Governing law: Road Traffic Act No. 11 of 2002.""",
    },
    {
        "title": "What insurance and fitness certificate a vehicle needs in Zambia",
        "short_name": "RTSA guide: motor insurance and fitness certificate",
        "authority": "Road Transport and Safety Agency (RTSA)",
        "law": "Road Traffic Act No. 11 of 2002",
        "url": "https://www.rtsa.org.zm/transport/examinations/",
        "body": """To be legal on the road a vehicle needs three separate things: **valid insurance, a valid Certificate of Fitness (roadworthiness), and paid road tax** — plus the white book in the owner's name.

**Insurance:** take out at least **third-party motor insurance** (compulsory by law) from a licensed Zambian insurer and keep the certificate or cover note. Insurance is bought from private insurers, not RTSA, and it ends when a vehicle changes ownership.

**Certificate of Fitness (roadworthiness):**
1. Make sure road tax is paid (it is a prerequisite).
2. Request the safety inspection (on ZamPortal you select it after paying road tax).
3. Present the vehicle for physical inspection at an RTSA or approved centre.
4. On passing you receive the Certificate of Fitness.

The inspection checks tyres, brakes, lights, steering, exhaust and emissions, plus fire equipment, a first-aid kit and two warning triangles.

**Documents:** the vehicle and its original white book, valid insurance, current road tax, examination receipt.

**Fees:** the private inspection / fitness test is around **K64** (about **K55** for a PSV Certificate of Fitness) — **confirm current RTSA fees.**

**Notes:** driving without a valid Certificate of Fitness is an offence; the exact validity period is best confirmed with RTSA. Governing law: Road Traffic Act No. 11 of 2002.""",
    },
    # ─────────────────────────── ZRA / TAX ───────────────────────────
    {
        "title": "How to get a TPIN (register with ZRA) in Zambia",
        "short_name": "ZRA guide: TPIN registration",
        "authority": "Zambia Revenue Authority (ZRA)",
        "law": "Income Tax Act, Cap. 323",
        "url": "https://www.zra.org.zm/business-registration-requirements/",
        "body": """A TPIN is your 10-digit Taxpayer Identification Number. It is now needed for everyday life — a bank account, employment, business, and motor-vehicle and land transactions — not only for people who owe tax.

**Steps (online, recommended):**
1. Go to the ZRA portal (portal.zra.org.zm) and choose Register / "Get a TPIN".
2. Select taxpayer type (individual, sole trader, partnership, company, NGO).
3. Enter your details (name, NRC or passport, address, contacts) and upload the required documents.
4. Submit. A TPIN is usually issued the same day. You can also register offline on Form TPIN-1 at any ZRA office.

**Companies registered with PACRA after 2020 are auto-issued a TPIN** through the PACRA–ZRA link — no separate ZRA application.

**Documents:** individual — NRC (or passport) and proof of address; company/business — PACRA certificate and directors'/partners' details and TPINs.

**Fees:** **TPIN registration is FREE.** Beware unofficial agents who charge for it.

**Where:** online at portal.zra.org.zm (or the TaxOnApp mobile app), or any ZRA office.

**Notes:** having a TPIN does not by itself mean you owe tax — many holders are below the tax threshold. Keep your contact details current or later steps (tax clearance, filing) fail. Governing law: Income Tax Act, Cap. 323.""",
    },
    {
        "title": "How PAYE income tax works in Zambia (tax bands and tax-free amount)",
        "short_name": "ZRA guide: PAYE income tax",
        "authority": "Zambia Revenue Authority (ZRA)",
        "law": "Income Tax Act, Cap. 323",
        "url": "https://www.zra.org.zm/paye-calculator/",
        "body": """PAYE (Pay As You Earn) is income tax your **employer deducts from your monthly pay and remits to ZRA**. It is progressive — each rate applies only to the income falling in that band.

**Monthly bands (published 2025 Budget rates, which carry into the 2026 charge year — these are set every year in the October Budget and must be re-confirmed each January, so always quote them with the year):**
- Up to K5,100: **0%** (tax-free threshold)
- K5,100.01 to K7,100: **20%**
- K7,100.01 to K9,200: **30%**
- Above K9,200: **37%**

So anyone earning K5,100 or less per month pays no PAYE.

**Mechanics:** the employer registers a PAYE tax type, files a monthly PAYE return and pays (commonly by the 10th of the following month — confirm the exact date with ZRA). Employees do not file PAYE themselves unless they have other income.

**Notes:** PAYE is separate from NAPSA (pensions) and NHIMA (health) — a payslip carries all three, but only PAYE is a ZRA tax. Do not confuse the monthly bands with their annual equivalents. **These figures change each Budget; verify the current bands on ZRA's PAYE calculator before relying on them.** Governing law: Income Tax Act, Cap. 323.""",
    },
    {
        "title": "How VAT registration works in Zambia (threshold and rate)",
        "short_name": "ZRA guide: VAT",
        "authority": "Zambia Revenue Authority (ZRA)",
        "law": "Value Added Tax Act, Cap. 331",
        "url": "https://www.zra.org.zm/",
        "body": """VAT is charged on taxable sales; a registered business charges output VAT, reclaims input VAT on purchases, and remits the difference to ZRA monthly.

**Key figures (current-published — re-confirm each Budget):**
- **Standard rate: 16%.** Some supplies are zero-rated (0%, e.g. exports — you can still reclaim input VAT) and some are exempt (no VAT, no input reclaim).
- **Registration threshold: K800,000** of annual taxable turnover.

**Important overlap:** the VAT threshold (K800,000) is much lower than the Turnover Tax ceiling (K5,000,000). A business turning over between those two figures can be on Turnover Tax and still be required to register for VAT if it makes taxable supplies. This confuses many people — flag it.

**Steps:** register the VAT tax type on the ZRA portal; charge VAT; file a monthly VAT return (commonly due by the 18th — confirm with ZRA). VAT-registered traders must issue invoices through ZRA's Smart Invoice electronic system.

**Documents:** active TPIN; PACRA/business registration; bank details; expected turnover.

**Notes:** voluntary registration below the threshold is possible; exempt is not the same as zero-rated. **Confirm the current rate and threshold with ZRA before quoting.** Governing law: Value Added Tax Act, Cap. 331.""",
    },
    {
        "title": "How small businesses are taxed in Zambia (Turnover Tax)",
        "short_name": "ZRA guide: Turnover Tax",
        "authority": "Zambia Revenue Authority (ZRA)",
        "law": "Income Tax Act, Cap. 323",
        "url": "https://www.zra.org.zm/",
        "body": """Turnover Tax is a simplified tax for small businesses and the self-employed. It is a flat percentage of **gross turnover** (not profit), with a simple monthly return, and it replaces normal business/corporate income tax for those who qualify.

**Key figures (effective 1 January 2025, carried into 2026 — verify each year):**
- **Threshold: annual turnover up to K5,000,000** (raised from K800,000 on 1 Jan 2025 — older guides citing K800,000 are stale).
- **Rate: 5%** on turnover (raised from 4%), with the first K12,000 a year (about K1,000/month) at 0%.
- Businesses above K5,000,000 move to standard **Corporate Income Tax (generally 30% on profits;** some sectors differ).

**Applies to:** small traders, gig/informal workers, minibus/taxi operators and similar small enterprises below K5m that are not required to register for VAT. Some regulated or professional-services activities are excluded — confirm eligibility with ZRA.

**Mechanics:** active TPIN and Turnover Tax registration; file and pay monthly on the ZRA portal or TaxOnApp (commonly due by the 14th — confirm).

**Notes:** because it is on gross turnover, it is owed even in a loss-making month. **The rate and threshold are Budget-set — re-verify annually.** Governing law: Income Tax Act, Cap. 323.""",
    },
    {
        "title": "How import duty is calculated in Zambia (customs, including on cars)",
        "short_name": "ZRA guide: import duty and customs",
        "authority": "Zambia Revenue Authority (ZRA)",
        "law": "Customs and Excise Act, Cap. 322",
        "url": "https://www.zra.org.zm/importation-of-goods/",
        "body": """Import duty is charged on the **Value for Duty Purposes (VDP)** — the Kwacha equivalent of the CIF value (Cost + Insurance + Freight), not the sticker price. ZRA's formula is: duty or tax = VDP × the rate.

**Who needs a clearing agent:** goods with a CIF up to US$2,000 can generally be self-declared; above US$2,000 you must declare on ASYCUDAWorld and use a licensed clearing agent. A traveller may bring in goods worth up to US$1,000 duty-free (personal, non-commercial).

**Components on a typical import:** customs duty 0%–40% by tariff (HS code); import VAT 16%; excise on selected goods.

**Motor vehicles:** newer vehicles (under about two years, and hybrids/EVs) are charged ad valorem on CIF (customs 25% + excise 30% + VAT 16%); older vehicles are charged a **specific duty** — a fixed Kwacha amount by body type and engine size that bundles customs, excise, VAT and fees. A one-off carbon emission surtax applies by engine size. **The exact amount depends on the specific vehicle — use ZRA's Motor Vehicle Tax Calculator; never quote a figure from memory.**

**Important:** Zambia does **NOT** charge an "Import Declaration Fee (IDF)" — it was discontinued in 1998; the import declaration form is for statistics only, at no fee. Do not tell users to pay an IDF.

**Documents:** commercial invoice, bill of lading/airway bill, packing list, permits for controlled goods, TPIN. Full duty is paid up front before release. Governing law: Customs and Excise Act, Cap. 322.""",
    },
    {
        "title": "Property Transfer Tax in Zambia (when you sell or transfer land or shares)",
        "short_name": "ZRA guide: Property Transfer Tax",
        "authority": "Zambia Revenue Authority (ZRA)",
        "law": "Property Transfer Tax Act, Cap. 340",
        "url": "https://www.zra.org.zm/",
        "body": """Property Transfer Tax (PTT) is charged when property is transferred and is paid by the **transferor (seller)**, on the **realised value** — the higher of the actual price or the open market value.

**Rates (effective 1 January 2025, carried into 2026 — confirm each Budget):**
- Land (including buildings), shares in a Zambian company, and intellectual property: **8%** (raised from 5% on 1 Jan 2025).
- Mining right under an exploration licence: 8%; under a mining licence, and mineral-processing licences: 10%.

It applies to land in Zambia, IP rights, mining rights and shares in a Zambian company, including certain indirect transfers.

**Mechanics:** assessed and paid via ZRA (needs the TPINs of both parties, the sale/transfer agreement and valuation). **PTT clearance is required before a land transfer is registered at Lands.** PTT is due within 14 days of ZRA's assessment.

**Notes:** the rise to 8% (from 5%) is recent — older material is outdated. ZRA can use the open market value even if the parties state a lower price, so under-declaring does not reduce PTT. **Confirm the current rate with ZRA before quoting.** Governing law: Property Transfer Tax Act, Cap. 340.""",
    },
    {
        "title": "How to get a Tax Clearance Certificate in Zambia (ZRA)",
        "short_name": "ZRA guide: Tax Clearance Certificate",
        "authority": "Zambia Revenue Authority (ZRA)",
        "law": "Administered under the tax Acts by ZRA",
        "url": "https://www.zra.org.zm/tax-information/tax-information-details/tax-clearance-certificate-2/",
        "body": """A Tax Clearance Certificate (TCC) confirms you are in good standing with ZRA — all returns filed and all liabilities settled — for the tax types it covers. You typically need one to bid for government tenders, renew licences, obtain work/residence permits, and for many bank loans.

**Steps (online):**
1. Make sure you are eligible: all returns filed (Income Tax, PAYE, VAT, Turnover Tax as applicable), all payments made, and an active TPIN with current details.
2. Log in to TaxOnline (portal.zra.org.zm) → e-Services → Tax Clearance Certificate application.
3. Select the tax types to include and complete the questionnaire; upload any requested documents; tick the declaration.
4. On approval, download the certificate.

**Validity:** one calendar year — renew before it expires.

**Documents:** active TPIN; up-to-date filed returns and payment proofs; financials if requested.

**Notes:** any single unfiled return or unpaid balance blocks issuance — the most common reason applications fail. File even a nil return to stay compliant. **Confirm whether any fee applies with ZRA.** Where: TaxOnline at portal.zra.org.zm.""",
    },
    # ─────────────────────────── PACRA / BUSINESS ───────────────────────────
    {
        "title": "How to register a business name (sole trader) in Zambia (PACRA)",
        "short_name": "PACRA guide: register a business name",
        "authority": "Patents and Companies Registration Agency (PACRA)",
        "law": "Registration of Business Names Act, Cap. 389",
        "url": "https://info.pacra.org.zm/what-do-i-do-first/",
        "body": """A business name (sole proprietorship or partnership) is a registered trading name for a person. It is **not a separate legal entity** — there is no limited liability, so the owner is personally liable for the debts.

**Steps:**
1. Create an account on the PACRA portal (portal.pacra.org.zm) or ZamPortal.
2. Apply for **name clearance** — propose up to 3 names (considered in order). An approved name is reserved for 30 days (extendable 90).
3. Complete **BN Form III** (Application to Register a Business Name), signed by the proprietor/partners.
4. Pay online; the Certificate of Registration is usually issued within about 24 hours.

**Documents:** BN Form III; NRC (or passport for non-Zambians); proposed name(s); business address; nature of business.

**Fees:** PACRA's current figures are about **K111 name clearance + K222 registration (≈ K334 total)** — **confirm the current fee with PACRA** (the older government eRegistry shows superseded fees). The binding schedule is SI No. 107 of 2022.

**Where:** online via the PACRA portal or ZamPortal, or in person at PACRA House, Lusaka.

**Notes:** registering a business name does not create a company or limited liability, and it does not give the bank-ready legal identity a company does. Sole traders are often eligible for Turnover Tax if turnover is within the threshold. Governing law: Registration of Business Names Act, Cap. 389.""",
    },
    {
        "title": "How to register (incorporate) a limited company in Zambia (PACRA)",
        "short_name": "PACRA guide: incorporate a company",
        "authority": "Patents and Companies Registration Agency (PACRA)",
        "law": "Companies Act No. 10 of 2017",
        "url": "https://info.pacra.org.zm/what-is-a-local-company/",
        "body": """A private company limited by shares is a **separate legal person** with limited liability and perpetual succession — it can own property and sign contracts in its own name.

**Steps:**
1. Create an account on the PACRA portal / ZamPortal.
2. **Name clearance** (up to 3 names; reserved 30 days, extendable 90).
3. Complete **Companies Form 3** (Application for Incorporation of a company limited by shares), signed by the directors and shareholders. File Articles of Association only if you want non-standard articles (otherwise the Act's standard articles apply).
4. File the beneficial-ownership declaration (Companies Form 21) at incorporation.
5. Pay online; the Certificate of Incorporation is targeted within about 24 hours.

**Minimum people:** at least **2 directors, of whom at least half must be resident in Zambia** (this catches foreign-owned startups), plus a company secretary and at least 2 shareholders.

**Share capital:** PACRA applies a minimum nominal share capital of **K20,000** for a private company (the incorporation fee is calculated against it).

**Fees:** PACRA's published all-in figure is about **K1,300–K1,420** (filing 2.5% of nominal capital with a K500 minimum, plus fixed certificates and name clearance) — **confirm the current fee with PACRA;** binding schedule SI No. 107 of 2022.

**Notes:** standard articles are free and fine for most SMEs. Incorporation carries ongoing duties (annual returns, beneficial ownership). Governing law: Companies Act No. 10 of 2017 (as amended by Act No. 12 of 2020).""",
    },
    {
        "title": "Business name or company in Zambia — which should I register?",
        "short_name": "PACRA guide: business name vs company",
        "authority": "Patents and Companies Registration Agency (PACRA)",
        "law": "Companies Act No. 10 of 2017; Registration of Business Names Act",
        "url": "https://info.pacra.org.zm/what-do-i-do-first/",
        "body": """This is one of the most common questions. The core difference is legal personality and liability.

**A registered business name** (sole proprietor / partnership): not a separate legal entity, so the owner has **unlimited personal liability**; ends on the owner's death; cannot own property or sue in its own name; cheap to set up (about K334); governed by the Registration of Business Names Act; typically taxed under Turnover Tax if turnover is within the threshold.

**A private company limited by shares:** a **separate legal person** with **limited liability** (you risk only unpaid amounts on your shares); has perpetual succession; can own property and contract in its own name; costs about K1,300–K1,420 to set up; governed by the Companies Act No. 10 of 2017; taxed under corporate income tax (generally 30%).

**Choose a business name** for a small, low-risk, single-owner or partnership trade where cost and simplicity matter. **Choose a company** when you need limited liability, plan to raise capital or bring in shareholders, want the business to outlive the founder, or expect to deal with banks, tenders or investors (who usually require an incorporated entity).

**Common myth:** a registered business name does NOT give limited liability. Converting a business name to a company later means a fresh incorporation, not an amendment. **Confirm current fees with PACRA.**""",
    },
    {
        "title": "How to file PACRA annual returns in Zambia (and the penalty for late filing)",
        "short_name": "PACRA guide: annual returns",
        "authority": "Patents and Companies Registration Agency (PACRA)",
        "law": "Companies Act No. 10 of 2017; Registration of Business Names Act",
        "url": "https://info.pacra.org.zm/how-do-i-file-annual-returns-to-pacra/",
        "body": """Every registered business must file an annual return with PACRA to stay active — it keeps the register's details current. The deadline runs from **your financial year-end, not the calendar year or your registration anniversary.**

**Business name:** file **BN Form XIV** within **3 months** after each financial year-end; the fee is about **K111 per year**; filed online in about 24 hours.

**Company:** file the company annual return within **90 days (3 months)** of the financial year-end (or within one month after the AGM where held). This refreshes the beneficial-ownership and director/shareholder particulars (Companies Act s. 270). **Confirm the exact company annual-return form and fee with PACRA — the public page details only the business-name return.**

**Penalty:** PACRA can **deregister/strike off** an entity that fails to file annual returns for **two consecutive years**, and late filing attracts penalty fees. Deregistration can freeze bank accounts and invalidate contracts; restoration is costly. PACRA sometimes runs amnesty/waiver campaigns for outstanding returns.

**Where:** online via the PACRA portal / ZamPortal. Governing law: Companies Act No. 10 of 2017 (companies); Registration of Business Names Act (business names).""",
    },
    {
        "title": "How to declare beneficial ownership of a company in Zambia (PACRA)",
        "short_name": "PACRA guide: beneficial ownership",
        "authority": "Patents and Companies Registration Agency (PACRA)",
        "law": "Companies Act No. 10 of 2017 (ss. 21, 123)",
        "url": "https://info.pacra.org.zm/who-is-a-beneficial-owner/",
        "body": """A beneficial owner is the **natural person** who ultimately owns, controls or substantially benefits from a company. PACRA keeps a Register of Beneficial Owners, and companies must keep it current. There are two distinct filings — keep them separate:

- **Initial declaration — Companies Form 21** ("Declaration of Beneficial Ownership"), filed **at incorporation** and thereafter within **30 days** of the company receiving a declaration from a beneficial owner (Companies Act s. 123).
- **Change of beneficial owner / shareholder — Companies Form 20**, filed within **14 days** of the change (Companies Act s. 21). Fee about **K266** — confirm current.

Widely reported thresholds are that a **5%+ shareholding is a "substantial interest"** and **over 25% is deemed control**, but confirm these against the Companies Act, as PACRA's public page does not state the percentages. Non-disclosure is reported to carry a fine (figures vary — confirm against the Act) and beneficial ownership is refreshed with every annual return, so it is not "file once and forget".

Companies limited by guarantee and foreign companies are excluded from the Form 20/21 regime. **Where:** PACRA portal / ZamPortal. Governing law: Companies Act No. 10 of 2017.""",
    },
    {
        "title": "What to do after registering a business in Zambia (TPIN, bank, licences)",
        "short_name": "Guide: after registering a business",
        "authority": "PACRA, ZRA, councils and sector regulators",
        "law": "Companies Act; Income Tax Act; sector statutes",
        "url": "https://www.zra.org.zm/business-registration-requirements/",
        "body": """PACRA registration alone does not make a business fully legal to operate. Complete this chain:

1. **TPIN from ZRA** — businesses registered with PACRA after 2020 usually receive a TPIN automatically within about a day; if not, register on the ZRA portal with the PACRA certificate.
2. **Open a corporate bank account** — banks require the PACRA certificate, TPIN, company/beneficial-ownership documents, directors' IDs and account-opening forms.
3. **Register the right taxes and social schemes** — VAT if turnover exceeds the threshold; register employees with NAPSA (pensions) and NHIMA (health), and WCFCB (workers' compensation) where applicable.
4. **Local council business levy / trading licence** — pay your local authority before trading; food businesses also need a health permit and any premises a fire-safety certificate.
5. **Sector-specific licences** — e.g. ZICTA (ICT), Bank of Zambia (financial services), ZAMRA (health/pharma), mines/energy regulators, tourism, etc., depending on activity.

Trading without the council levy or a required sector licence is an offence even with a valid PACRA certificate. Many of these are aggregated on the government eRegistry (businesslicenses.gov.zm) and ZamPortal (eservices.gov.zm). **Confirm current fees with each authority.**""",
    },
    # ─────────────────────── IDENTITY / IMMIGRATION ───────────────────────
    {
        "title": "How to apply for a Zambian passport (e-passport)",
        "short_name": "Guide: Zambian passport application",
        "authority": "Department of National Registration, Passport and Citizenship (DNRPC), Ministry of Home Affairs",
        "law": "Passport Act No. 28 of 2016",
        "url": "https://zamportal.gov.zm/",
        "body": """Since December 2025 you can apply for a Zambian passport online on **ZamPortal**, logged in with **ZamPass**, or still apply in person at a Passport / DNRPC office (or a Zambian mission abroad).

**Steps (online):**
1. Create or log in with a **ZamPass** account.
2. Complete the passport application and upload documents.
3. Pay online (card or mobile money).
4. Attend a passport office in person for **biometric enrolment** (fingerprints and photo) — this is required even when you start online.
5. Track and collect. New service timelines: about **14 days** for Lusaka, Ndola and Livingstone, and **21 days** for other provincial capitals.

**Documents:** **NRC (mandatory)**; full birth certificate; passport photos to spec (full face, both ears visible, no headgear/adornment unless religious); the application form with a recommender/deponent section signed by a person of standing who has known you 2+ years; a police report if a previous passport was lost.

**Fees:** the government service catalogue lists in-country fees for the ordinary 32-page and 48-page passport and higher "express" tiers, plus a small form fee; applications at missions abroad are commonly around US$100. **The exact Kwacha figures and the express turnaround are not consistently published — confirm the current fee and processing time on the portal before quoting them.**

**Notes:** you must appear in person for biometrics even if you start online, and no NRC means no passport. Passports are handled by DNRPC (not the Department of Immigration, which handles visas and permits). Governing law: Passport Act No. 28 of 2016.""",
    },
    {
        "title": "How to get or replace a National Registration Card (NRC) in Zambia",
        "short_name": "Guide: National Registration Card (NRC)",
        "authority": "Department of National Registration, Passport and Citizenship (DNRPC), Ministry of Home Affairs",
        "law": "National Registration Act, Cap. 126",
        "url": "https://www.mohais.gov.zm/",
        "body": """The green NRC is Zambia's national ID. It can only be obtained **in person, inside Zambia** — there is no embassy or fully online first-issue.

**First-time NRC:**
1. You must be **16 or older** with at least one parent who was a Zambian citizen at your birth.
2. Go to a DNRPC Registration Centre / District Registration Office, or attend a **mobile registration exercise** in your area.
3. Bring a **deponent** — a parent, blood relative or legal guardian — who must bring their **original NRC** (a copy is not enough).
4. Present proof of birth: a birth certificate, under-five card, record of birth, or a sworn affidavit.
5. Your photo is captured at the office (full face, both ears visible). The card is issued at the office.

**Replacing a lost or damaged NRC:** for a lost card get a **police report**; for a damaged one bring the damaged card. Complete the replacement form and pay the prescribed fee.

**Fees:** the **first NRC is FREE ("gratis")**. A replacement (lost/damaged) attracts a prescribed fee — **the amount is not officially published, so confirm it with DNRPC; do not quote a figure.**

**Where:** DNRPC District Registration Offices nationwide, or periodic mobile enrolment campaigns.

**Notes:** the deponent's original NRC is mandatory for a first issue; if you have no birth certificate, arrange an affidavit or under-five card before going. Governing law: National Registration Act, Cap. 126.""",
    },
    {
        "title": "Which Zambian immigration permit or visa a foreigner needs",
        "short_name": "Immigration guide: permits and visas",
        "authority": "Zambia Department of Immigration, Ministry of Home Affairs",
        "law": "Immigration and Deportation Act No. 18 of 2010",
        "url": "https://www.zambiaimmigration.gov.zm/permit-types/",
        "body": """Zambia's formal term is "Employment Permit" — there is no separate "work permit", and there is no official "self-employment permit" (a foreigner running their own business uses the Investor's Permit).

**Who needs which:**
- **Employment Permit** — a foreigner hired by a Zambian employer for a job over 6 months. The **employer, a practising lawyer, or a registered immigration consultant applies** — the employee cannot self-apply. Requires an employment contract, qualifications, a police clearance, newspaper adverts showing no qualified Zambian was available, and a succession plan to train a Zambian.
- **Temporary Employment Permit** — short-term business/technical work (30 days up to about 6 months).
- **Investor's Permit** — a foreigner (18+) investing in or joining a Zambian business. Investment thresholds apply: **US$250,000 for a new business, US$150,000 to join an existing one.**
- **Residence Permit** — permanent residence; qualifying routes include holding an Employment Permit 10+ years, an Investor's Permit 3+ years, or a Spouse Permit 5+ years.
- **Study Permit** — a foreign student (may not work for gain).
- **Spouse Permit** — spouse of a Zambian citizen/resident.
- **Visas** — single/double/multiple entry, KAZA UniVisa (Zambia + Zimbabwe), transit, day-tripper. Ordinary visitors get 90 days per 12 months; beyond that a Visiting Permit is needed.

**Fees:** the official schedule lists ZMW figures for permits and USD for visas, but the pages carry no effective date and differ between sections — **confirm the current fee at the portal before quoting.** Zambia has expanded visa-free entry for many nationalities — confirm a specific nationality's status on the e-Visa portal.

**Where:** the Department of Immigration e-Services portal (eservices.zambiaimmigration.gov.zm); permits also appear under ZamPortal "For Immigrants". Governing law: Immigration and Deportation Act No. 18 of 2010.""",
    },
    # ─────────────────────── SOCIAL SECURITY ───────────────────────
    {
        "title": "How NAPSA works in Zambia (registration, contributions, claiming your pension)",
        "short_name": "NAPSA guide: pensions",
        "authority": "National Pension Scheme Authority (NAPSA)",
        "law": "National Pension Scheme Act No. 40 of 1996",
        "url": "https://www.napsa.co.zm/self-service/contributions",
        "body": """NAPSA is the national pension scheme. It is compulsory for employees and voluntary for the self-employed.

**Registering:**
- **Employer:** must register with NAPSA within **one month** of employing the first employee, then register each employee, via the eNAPSA portal (enapsa.napsa.co.zm). Credentials are sent by SMS.
- **Employee:** your employer registers you and remits on your behalf; you can also use the member portal to check your statement (confirm the employer is actually remitting).

**Contributions:** **10% of gross earnings, split 5% employee + 5% employer**, each side capped by an earnings ceiling that is revised every January. The 2025 official maximum was about K1,708 per side (K3,416 total); 2026 figures are higher but **confirm the current ceiling on napsa.co.zm — the live site has at times shown a stale figure, so use the dated official notice.**

**Claiming benefits:** the key threshold is **180 months (15 years)** of contributions — below it you get a one-off lump sum, at or above it a monthly pension. Retirement is generally age 55–65 with 180+ months. There are also invalidity, survivors' and funeral benefits. Claim online via iCARE (icare.napsa.co.zm) or at a NAPSA office; benefits are typically settled within about 21–30 days if records are complete.

**Notes:** keep beneficiary/next-of-kin details up to date — missing details are the top cause of delayed survivors' and funeral payments. NAPSA is separate from NHIMA and PAYE. Governing law: National Pension Scheme Act No. 40 of 1996.""",
    },
    {
        "title": "How NHIMA (national health insurance) works in Zambia",
        "short_name": "NHIMA guide: national health insurance",
        "authority": "National Health Insurance Management Authority (NHIMA)",
        "law": "National Health Insurance Act No. 2 of 2018",
        "url": "https://www.nhima.co.zm/become-a-member/",
        "body": """NHIMA is Zambia's national health insurance scheme. Membership is compulsory for employees and open to the informal sector.

**Registering (all via enhima.nhima.co.zm):**
- **Employer:** create the employer account, then upload a schedule of employees; their registered dependants are covered too.
- **Formal employee:** registered by the employer.
- **Informal / self-employed:** register yourself with a copy of your NRC (front and back); an income assessment sets your premium.
- **Dependants:** a principal member can register a spouse and up to 5 children under 18.

**Contributions:** **2% of salary, split 1% employee + 1% employer**, with **no earnings cap** (unlike NAPSA), so high earners pay 1% on the full salary. The informal-sector amount is income-assessed — **there is no published flat figure, so direct users to NHIMA (hotline 8000) for their assessed premium; do not invent an amount.**

**Using it:** present your NHIMA membership card/number at an **accredited** facility; the scheme covers consultations, laboratory tests, medicines and inpatient/specialist services in the benefit package. For medicines, present a stamped prescription from an accredited facility to an accredited pharmacy. Care at a non-accredited provider is not covered.

**Notes:** confirm the exact benefit-package inclusions and any waiting period on nhima.co.zm, and confirm the current contribution base and deadline. Governing law: National Health Insurance Act No. 2 of 2018.""",
    },
    # ─────────────────────── VITAL RECORDS ───────────────────────
    {
        "title": "How to register a birth and get a birth certificate in Zambia",
        "short_name": "Guide: birth certificate",
        "authority": "Registrar-General / DNRPC, Ministry of Home Affairs",
        "law": "Births and Deaths Registration Act, Cap. 51",
        "url": "https://zamportal.gov.zm/citizens/",
        "body": """Birth registration is compulsory and the first certificate is **free**.

**Newborn:**
1. Notify the birth **within one month** (to the Registrar of the district where the child was born — in practice via the health facility, the district civil-registration/DNRPC office, or the council).
2. Complete **Form VIII** (Notice of Birth); if the birth was not at a health facility, also complete **Form IX** (Independent Witness).
3. Submit the original Record of Birth (under-five clinic card / hospital record) plus copies of the parents' NRCs.
4. Collect the certificate from the issuing office.

**Adult never registered (late registration):** a family member with knowledge of the birth swears a General Affidavit before a Commissioner for Oaths, attaching the hospital record or a baptismal certificate, and submits it to the Registrar-General requesting a late birth certificate.

**Fees:** first issue is **free**; a lost certificate is about **K310** and a replacement about **K220** — **confirm current fees.**

**Where:** district civil-registration / DNRPC offices, hospitals (for the notice) and councils; central office is the Registrar-General, Lusaka. It is listed on ZamPortal but the online apply-flow is not confirmed as fully live.

**Notes:** the one-month deadline matters — beyond it, it becomes late registration needing an affidavit. Governing law: Births and Deaths Registration Act, Cap. 51.""",
    },
    {
        "title": "How to register a death and get a death certificate and burial permit in Zambia",
        "short_name": "Guide: death certificate and burial permit",
        "authority": "Registrar-General / DNRPC, Ministry of Home Affairs",
        "law": "Births and Deaths Registration Act, Cap. 51",
        "url": "https://zamportal.gov.zm/citizens/",
        "body": """Two clocks apply: the medical certificate reaches the Registrar within **48 hours**, and the notice of death is given within **one month** (extendable to three).

**Steps:**
1. Get a **Medical Certificate of Cause of Death** from the attending medical practitioner; the practitioner delivers it to the district Registrar within 48 hours. A registrar cannot register a death without it.
2. **Give notice of death** to the district Registrar within one calendar month (up to three at the Registrar's discretion), completing the death-registration form.
3. On receiving the notice with the medical certificate, the Registrar **immediately issues the burial permit** — it is part of the notice process, not a separate application.
4. The death is registered and the certificate issued.

**Deaths outside a hospital / no medical certificate:** the Registrar notifies the nearest magistrate or police officer, who inquires into the cause; families commonly use the **police report** to obtain a burial order first, then complete registration.

**Documents:** medical certificate of cause of death (or police report for out-of-facility deaths); the death-registration form; the deceased's particulars; the informant's ID (the informant must be a relative present at the death or illness, the person in charge of the hospital, or the undertaker).

**Fees:** registration is free if notice is given within the statutory period; **confirm any fee for late registration or a certified copy.** Governing law: Births and Deaths Registration Act, Cap. 51.""",
    },
    {
        "title": "How to get married and obtain a marriage certificate in Zambia (civil marriage)",
        "short_name": "Guide: marriage certificate",
        "authority": "Council Marriage Registrar / Registrar-General",
        "law": "Marriage Act, Cap. 50",
        "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/Marriage%20Act.pdf",
        "body": """A civil (statutory) marriage under the Marriage Act is monogamous and produces the standard marriage certificate. It is separate from a customary marriage.

**Steps (civil marriage):**
1. Both parties attend the council civic centre / marriage registry in person and see the Marriage Registrar.
2. **Give notice of the intended marriage (Form 1).** A **21-day public notice period** must elapse before the marriage can be solemnised.
3. Provide the documents (NRCs, proof of single status / non-impediment, residence, age, witnesses) and pay the fees.
4. After the notice period, the Registrar solemnises the marriage before witnesses and completes the **marriage certificate (Form 5 or 6)**; within 7 days a counterpart goes to the Registrar-General.

**Documents:** valid NRCs; notice of marriage (Form 1); evidence of non-impediment / single status (e.g. an affidavit, or a divorce decree / death certificate of a prior spouse); proof of residence and age; witnesses; High Court or parental consent where a party is under age.

**Fees:** the statutory schedule (special licence, affidavit, certificate) totals a small amount, but the **real cost at councils is commonly a few hundred Kwacha depending on venue and day — confirm with your specific council; do not quote a single national figure.**

**Customary marriage** is valid and recognised but governed by customary law, is potentially polygamous, and is generally not centrally registered like a civil marriage — local courts handle customary-marriage matters. Governing law: Marriage Act, Cap. 50.""",
    },
    # ─────────────────────── COUNCIL / LAND ───────────────────────
    {
        "title": "How to get a business or trading licence from the council in Zambia",
        "short_name": "Council guide: business/trading licence",
        "authority": "Local authority (e.g. Lusaka City Council), Ministry of Local Government",
        "law": "Local Government Act No. 2 of 2019; Trades Licensing Act, Cap. 393",
        "url": "https://www.businesslicenses.gov.zm/",
        "body": """A council trading licence sits **on top of** PACRA registration and a ZRA TPIN — it does not replace them.

**Steps:**
1. First register the business with PACRA and get a ZRA TPIN.
2. Apply to your council (or via the national eRegistry, businesslicenses.gov.zm) for the trading authorisation. For most small traders this is the **Local Government Business Levy** ("business levy certificate"); larger or regulated trades are licensed under the Trades Licensing Act.
3. The council classifies the business (hawker/stall, retail, wholesale, manufacturer, filling station, etc.), which sets the fee.
4. Pay and obtain the certificate; renew **annually**.

**Sector add-ons (often prerequisites):** a **fire-safety certificate** for commercial premises, a **health/premises permit** (mandatory for any food business, with an inspection), and a **liquor licence** if selling alcohol.

**Documents:** NRC (or PACRA certificate for a company); PACRA registration; ZRA TPIN; premises details. Extra documents apply for liquor and health permits.

**Fees:** set by business class and re-gazetted every year, and they vary by council — **confirm the current fee on the eRegistry listing for your specific council; do not quote a single national figure.**

**Where:** the council civic centre or the national eRegistry (businesslicenses.gov.zm); some councils have online payment. Governing law: Local Government Act No. 2 of 2019; Trades Licensing Act, Cap. 393.""",
    },
    {
        "title": "Who pays property rates in Zambia and how to pay them",
        "short_name": "Council guide: property rates",
        "authority": "Local authority (e.g. Lusaka City Council)",
        "law": "Rating / property-valuation legislation",
        "url": "https://www.lcc.gov.zm/valuation-and-real-estate/",
        "body": """Property rates are a local tax on rateable property (land and buildings), levied on the **property owner** as listed in the council's valuation roll — and they are due **whether or not the council provides a specific service** to the property (a common misunderstanding).

**How it works:**
1. The council maintains a valuation roll prepared by a registered valuation surveyor; each entry carries a rateable value.
2. The rate charged is a proportion of that rateable value (rateable value × the rate the council sets) — it is not a flat fee.
3. The council issues a rates bill; the owner pays.
4. Pay online through the council's payment portal (for Lusaka, epay.lcc.gov.zm), a mobile channel, or in person at the civic centre — you look up the bill by property/account reference.

**Documents:** the property/rates account number or property description to locate the bill; proof of ownership if updating or contesting the roll entry.

**Fees:** the amount depends on the specific property's rateable value — **confirm it with the council's Valuation department or the online lookup; there is no single figure.**

**Notes:** liability attaches to the owner and persists regardless of services; arrears accrue and can be enforced. You can object to a valuation, but only within set windows. Confirm the exact governing Act with the council.""",
    },
    {
        "title": "How to check or obtain a land title (Certificate of Title) in Zambia",
        "short_name": "Lands guide: certificate of title",
        "authority": "Ministry of Lands and Natural Resources (Commissioner of Lands; Lands and Deeds Registry)",
        "law": "Lands Act, Cap. 184; Lands and Deeds Registry Act",
        "url": "https://www.mlnr.gov.zm/",
        "body": """All land in Zambia is held on leasehold from the State, and the Lands and Deeds Registry records ownership. The Ministry of Lands now runs a digital system (ZILAS) reached through ZamPortal / ZamPass.

**Checking a title (do this before paying any deposit):** carry out an official search / **Digital Clearance** at the Lands and Deeds Registry. Digital Clearance is the Ministry's digital confirmation of a title's details, including the **name of the registered holder**, and is the mandatory first step before any land transaction. Submit online via ZamPortal or in person. Confirm the holder's name matches the seller's ID exactly. Approval can take a few weeks even though submission is quick.

**Obtaining title on a purchase (existing titled land):** get **State Consent to assign** (see the consent-to-assign guide) → sign the Deed of Assignment → obtain **Property Transfer Tax clearance from ZRA** → lodge for registration at the Lands and Deeds Registry with the original Certificate of Title, the signed Assignment, the Consent and the PTT clearance → a new Certificate of Title is issued to the buyer.

**New state land:** apply to the Commissioner of Lands, receive an Invitation to Treat (pay within 90 days), get an Offer Letter, submit survey diagrams, sign the lease, and collect the Certificate of Title (with your NRC).

**Fees:** search, registration and lease charges are set under the Lands regulations (fee-unit based) — **confirm current amounts with the Registry / ZILAS.** Governing law: Lands Act, Cap. 184; Lands and Deeds Registry Act.""",
    },
    {
        "title": "What State consent to assign is and how to get it when transferring land in Zambia",
        "short_name": "Lands guide: State consent to assign",
        "authority": "Commissioner of Lands, Ministry of Lands and Natural Resources",
        "law": "Lands Act, Cap. 184",
        "url": "https://zamportal.gov.zm/how-to-pay-ground-rent-online/",
        "body": """Because land is held on leasehold from the State, **any transfer, sale, gift or lease of titled land needs the consent of the Commissioner of Lands ("State consent to assign"). Without it the transaction is void — no interest passes.** This is the single most important step in a land transfer.

**Steps:**
1. **Clear all outstanding ground rent** first — consent will not issue while ground rent is in arrears. Ground rent is paid online via ZamPortal/ZILAS (enter the Land Parcel ID, choose the years, pay, and get a Treasury Receipt).
2. Apply to the Commissioner of Lands using **Form CT19** (online via ZILAS/ZamPortal, or in person), with the property details and evidence that ground rent is paid up.
3. Pay the consent fees electronically.
4. Consent is issued (often within a few days if all conditions are met), then used for the Deed of Assignment, PTT clearance and registration.

**Documents:** Form CT19; the Certificate of Title / Land Parcel ID; evidence that ground rent is cleared; the parties' identification; the assignment particulars.

**Fees:** consent fees are paid through ZILAS — **confirm the current amount; note ground rent must be cleared first.**

**Notes:** skipping consent voids the deal; ground-rent arrears block consent and, if unpaid after notice, can lead to cancellation of the lease — reconcile ground rent early. Governing law: Lands Act, Cap. 184.""",
    },
    # ─────────────────────── E-GOV PORTAL ECOSYSTEM ───────────────────────
    {
        "title": "ZamPass, ZamPortal, ZamGov and Smart Zambia explained (Zambia's e-government)",
        "short_name": "Guide: Zambia e-government portals",
        "authority": "Smart Zambia Institute / Ministry of Finance",
        "law": "Government Gazette Notice No. 836 of 2016",
        "url": "https://zamportal.gov.zm/",
        "body": """These four are easy to confuse, so here is the mental model:

- **ZamPass** is your **login / digital identity**. You create **one** account and reuse it to sign in to every connected government service (single sign-on). It is not a service catalogue and holds no services — it only proves who you are. Register at pass.gsb.gov.zm/registration with an NRC (or passport/refugee ID), a phone number and an email. **An NRC + phone + email is enough to create a ZamPass account — you do not need a driving licence or RTSA record just to register** (that RTSA wording is RTSA's own matching, not a universal gate). A separate optional "verified" (KYC) step unlocks the Digital ID and e-signature.
- **ZamPortal** (zamportal.gov.zm) is the **website of services** — the one-stop shop where you browse government services, see the requirements and fees, then log in with ZamPass to apply and pay (via the ZamPay gateway).
- **ZamGov** (also called **ZamMobile**) is the **mobile app** — ZamPortal in your pocket, plus a wallet that can carry your Digital ID, driver's licence and vehicle registration, and sign PDFs. It uses the same ZamPass login.
- **Smart Zambia Institute** is the **operator** — the government division (in the Office of the President) that runs ZamPass and maintains ZamPortal. Citizens do not log into Smart Zambia.

**What is solidly live today via ZamPortal + ZamPass:** RTSA services (road tax, fitness test, driver's licence renewal/duplicate, vehicle registration), passports and travel documents (launched Dec 2025), some Lands services (ground rent), and NRC issuance. **Other things the portal lists as categories — NAPSA, NHIMA, ZRA tax, birth/marriage certificates, immigration — are either placeholders or still live on their own agency portals, so check rather than assume a full online flow.** Immigration keeps its own portal at eservices.zambiaimmigration.gov.zm; ZRA tax is on portal.zra.org.zm.""",
    },
    # ─────────────────── COUNCIL / SECTOR LICENCES (expansion) ───────────────────
    {
        "title": "How to get a fire safety certificate for business premises in Zambia",
        "short_name": "Council guide: fire safety certificate",
        "authority": "Local authority fire services (e.g. Lusaka City Council)",
        "law": "Local Government Act No. 2 of 2019; council fire by-laws",
        "url": "https://www.businesslicenses.gov.zm/license/id/468",
        "body": """Most commercial premises must hold a fire safety certificate before the council will issue or renew a trading licence. It certifies the premises meet fire standards and is risk-banded.

**Steps:**
1. Apply to the council fire services department (for Lusaka, Lusaka City Council).
2. The premises are inspected and assigned a risk band (low, medium, high, or extra-high risk) based on the activity and building.
3. Pay the risk-banded fee and receive the certificate.
4. Renew annually (it is checked when you renew your trading licence).

**Documents:** business/premises details; PACRA registration; access for the fire inspection.

**Fees:** set by risk band and re-gazetted annually, so they vary and change. **Confirm the current fee with your council; do not rely on an old figure.** Payable online at some councils.

**Notes:** you usually cannot get or keep a trading licence without the fire certificate, so plan for it alongside the business levy and (for food) the health permit. Governing law: Local Government Act No. 2 of 2019 and council fire by-laws.""",
    },
    {
        "title": "How to get a health permit for a food business in Zambia",
        "short_name": "Council guide: health / food premises permit",
        "authority": "Local authority public health department",
        "law": "Public Health Act; Local Government Act No. 2 of 2019",
        "url": "https://www.businesslicenses.gov.zm/",
        "body": """Any business that handles food (restaurant, takeaway, grocery, bakery, bar) needs a health/premises permit from the council in addition to its trading licence.

**Steps:**
1. Apply to the council public health department.
2. A health inspector visits and checks the premises (kitchen layout, ventilation, drainage, water, waste, storage and staff hygiene).
3. Address any issues raised, then pay the fee and receive the permit.
4. Food handlers may also need medical/food-handler certificates.
5. Renew as required (usually annually).

**Documents:** business/premises details; PACRA registration; access for the inspection; food-handler medical certificates for staff where required.

**Fees:** set per council and re-gazetted annually. **Confirm the current fee with your council.**

**Notes:** the health permit is separate from the business levy and the fire certificate, and a food business generally cannot operate legally without it. Governing law: Public Health Act; Local Government Act No. 2 of 2019.""",
    },
    {
        "title": "How to get a liquor licence in Zambia",
        "short_name": "Council guide: liquor licence",
        "authority": "Local authority liquor licensing committee",
        "law": "Liquor Licensing Act No. 20 of 2011; SI No. 99 of 2011",
        "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/Liquor%20Licensing%20Act.pdf",
        "body": """If your business sells alcohol (bar, bottle store, restaurant, grocery), you need a liquor licence from the council's liquor licensing committee, on top of your trading licence.

**Steps:**
1. Apply to the council liquor licensing committee for the class of licence that fits your business (on-consumption, off-consumption, etc.).
2. Provide the supporting documents (below) and give the required public notice.
3. The committee considers the application (objections may be raised).
4. On approval, pay the fee and receive the licence; renew as required.

**Documents:** NRC; PACRA registration; a police report; a health report; a Government Gazette notice; and confirmation of the premises, as required under the Liquor Licensing Act and SI No. 99 of 2011.

**Fees:** set per council and class of licence. **Confirm the current fee with your council.**

**Notes:** selling alcohol without a liquor licence is an offence. The licence is in addition to the business levy, fire certificate and (for food) health permit. Governing law: Liquor Licensing Act No. 20 of 2011.""",
    },
    {
        "title": "How to get a market stall or street vending permit in Zambia",
        "short_name": "Council guide: market stall / vending permit",
        "authority": "Local authority / market master",
        "law": "Markets and Bus Stations Act; Local Government Act No. 2 of 2019",
        "url": "https://www.businesslicenses.gov.zm/license/id/458",
        "body": """To trade in a council market you need a stall allocation and a trading permit from the council or the market master. Trading in undesignated street spots is generally not permitted; the lawful route is a designated market space.

**Steps:**
1. Apply to the council or the market office (market master) for a stall or trading-space allocation.
2. Pay the applicable market/stall levy (often daily or monthly) and get a receipt.
3. Food sellers may also need a health check.
4. Larger shops still need the council trading licence (business levy) plus fire and health clearances as applicable.

**Documents:** NRC; the stall/space application; a health check for food sellers.

**Fees:** market/stall levies are small and set locally; they change and vary by market. **Confirm the current daily/monthly levy with your council or market master; always get a receipt for any levy paid on site.**

**Notes:** government policy directs vendors to trade from designated markets, and directives on street-vending levies have shifted, so secure a designated space rather than a street pitch. Governing law: Markets and Bus Stations Act; Local Government Act No. 2 of 2019.""",
    },
    {
        "title": "Which sector licence a business needs in Zambia (regulators guide)",
        "short_name": "Guide: sector business licences (which regulator)",
        "authority": "Sector regulators (BoZ, ZICTA, ZAMRA, ERB, ZEMA, tourism, mines)",
        "law": "Sector-specific statutes",
        "url": "https://www.businesslicenses.gov.zm/",
        "body": """After PACRA registration and a council trading licence, many businesses also need a licence from the regulator for their sector. Registering with PACRA alone does not make a regulated business legal to operate.

**Which regulator for which activity:**
- **Financial services, banking, lending, forex, payment systems:** Bank of Zambia (BoZ). Insurance and pensions: Pensions and Insurance Authority (PIA). Securities: Securities and Exchange Commission (SEC).
- **Telecoms, internet, ICT, broadcasting equipment:** Zambia Information and Communications Technology Authority (ZICTA).
- **Medicines, pharmacies, health products:** Zambia Medicines Regulatory Authority (ZAMRA); health facilities and professionals: Health Professions Council (HPCZ).
- **Energy (fuel, electricity supply):** Energy Regulation Board (ERB).
- **Environment (projects with environmental impact, e.g. mining, manufacturing, large developments):** Zambia Environmental Management Agency (ZEMA), often a prerequisite (an EIA or project brief).
- **Mining:** Ministry of Mines and the mining-rights regime.
- **Tourism and hospitality:** Ministry of Tourism licensing.
- **Employees:** register with NAPSA (pensions), NHIMA (health) and WCFCB (workers' compensation).

**Steps:** identify your sector regulator (the national eRegistry at businesslicenses.gov.zm lists licences by activity), apply to that regulator with your PACRA certificate and TPIN, meet the sector requirements, and pay the licence fee.

**Fees and requirements:** vary by regulator and licence. **Confirm the current fee and exact requirements with the specific regulator; do not quote a single figure.**

**Notes:** trading in a regulated sector without the sector licence is an offence even with a valid PACRA certificate and council licence.""",
    },
    {
        "title": "How to register employees with WCFCB (workers' compensation) in Zambia",
        "short_name": "Guide: WCFCB workers' compensation registration",
        "authority": "Workers' Compensation Fund Control Board (WCFCB)",
        "law": "Workers' Compensation Act",
        "url": "https://www.workers.com.zm/",
        "body": """Employers must register with the Workers' Compensation Fund Control Board (WCFCB), which compensates workers for injuries, disability or death arising from work. It is separate from NAPSA (pensions) and NHIMA (health).

**Steps:**
1. Register the business as an employer with WCFCB (the WCFCB Employer Registration form is downloadable from Levy).
2. Declare your workers and their earnings.
3. Pay the assessed contribution (assessed on payroll and the risk class of the work).
4. Keep the registration and declarations current; claim on the fund if a worker suffers a work injury.

**Documents:** PACRA certificate; TPIN; employer and payroll details; the WCFCB Employer Registration form.

**Fees / contributions:** assessed by WCFCB on payroll and industry risk class. **Confirm the current assessment basis and rate with WCFCB.**

**Notes:** WCFCB cover is a legal obligation for employers and sits alongside NAPSA and NHIMA on the payroll compliance list. Governing law: Workers' Compensation Act.""",
    },
    {
        "title": "How to get an environmental approval or EIA for a project in Zambia (ZEMA)",
        "short_name": "Guide: environmental approval / EIA (ZEMA)",
        "authority": "Zambia Environmental Management Agency (ZEMA)",
        "law": "Environmental Management Act No. 12 of 2011",
        "url": "https://www.zema.org.zm/",
        "body": """Projects that can affect the environment (mining, manufacturing, large developments, some energy and agriculture projects) need environmental clearance from the Zambia Environmental Management Agency (ZEMA) before they proceed. It is often a prerequisite for a sector licence or land development.

**Steps:**
1. Determine the level of assessment your project needs: a project brief / Environmental Project Brief for lower-impact projects, or a full Environmental Impact Assessment (EIA) with an Environmental Impact Statement for higher-impact ones.
2. Engage a registered environmental consultant to prepare the study, including public consultation where required.
3. Submit to ZEMA with the fee; ZEMA reviews (and may hold public hearings for an EIA).
4. On approval, ZEMA issues a decision letter / environmental approval, usually with conditions you must comply with and monitor.

**Documents:** the project brief or Environmental Impact Statement; the developer's and consultant's details; site/land information; proof of the fee.

**Fees:** set by ZEMA and scaled to the project. **Confirm the current fee and the required assessment level with ZEMA.**

**Notes:** starting a project that needs clearance without ZEMA approval is an offence and can halt the project. Governing law: Environmental Management Act No. 12 of 2011.""",
    },
    {
        "title": "How foreign investors get incentives and register with the ZDA in Zambia",
        "short_name": "Guide: ZDA investment registration and incentives",
        "authority": "Zambia Development Agency (ZDA)",
        "law": "Zambia Development Agency Act",
        "url": "https://www.businesslicenses.gov.zm/",
        "body": """Investors, especially foreign investors and larger projects, can register with the Zambia Development Agency (ZDA) to access investment incentives and support. This is separate from PACRA company registration and does not replace sector licences.

**Steps:**
1. Incorporate the company with PACRA and get a TPIN first.
2. Apply to the ZDA for an investment certificate (the ZDA Investor Application form is downloadable from Levy), meeting the investment thresholds that apply to the incentives you seek.
3. ZDA assesses the application and, if approved, issues an investment certificate that can unlock incentives (which may include tax and customs incentives for qualifying investments in priority sectors).
4. Comply with the conditions and any reporting the certificate carries.

**Documents:** PACRA certificate of incorporation; TPIN; the ZDA Investor Application; business plan and proof of investment; details of the sector and location.

**Fees and thresholds:** set by ZDA and the incentive framework, and revised periodically. **Confirm the current thresholds, incentives and fees with the ZDA; incentives change with each Budget.**

**Notes:** a foreigner investing in their own business also needs an Investor's Permit from the Department of Immigration (US$250,000 for a new business, US$150,000 to join an existing one). Governing law: Zambia Development Agency Act.""",
    },
]


def main() -> int:
    force = "--force" in sys.argv
    db = get_db()
    if force:
        # delete every existing guide (doc + chunks) so we can re-ingest cleanly
        olds = retry(lambda: db.table("legal_documents").select("id")
                     .eq("document_type", "guide").limit(2000).execute().data) or []
        for o in olds:
            retry(lambda: db.table("legal_chunks").delete().eq("document_id", o["id"]).execute())
            retry(lambda: db.table("legal_documents").delete().eq("id", o["id"]).execute())
        print(f"--force: deleted {len(olds)} existing guides", flush=True)
    existing = {r["title"] for r in (retry(lambda: db.table("legal_documents")
                 .select("title").eq("document_type", "guide").limit(2000).execute().data) or [])}
    print(f"{len(GUIDES)} guides to ingest; {len(existing)} guides already present", flush=True)
    done = skipped = failed = 0
    for g in GUIDES:
        if g["title"] in existing:
            skipped += 1; continue
        try:
            doc = retry(lambda: db.table("legal_documents").insert({
                "title": g["title"], "short_name": g["short_name"],
                "document_type": "guide", "source_url": g["url"], "year": 2026,
                "is_global": True, "owner_id": None,
            }).execute().data)[0]
            did = doc["id"]
            # Prepend a tight title/purpose header so the first chunk's embedding
            # keys off what the guide is FOR — otherwise short "how do I X"
            # queries under-match a title-less body and statutes drown the guide.
            header = (f"{g['title']}\n\nZambian e-government / civic procedure guide "
                      f"from {g['authority']} ({g['law']}). Practical step-by-step on "
                      f"how to {g['title'][0].lower() + g['title'][1:]}.\n\n")
            pieces = chunk_text(header + g["body"])
            embs = retry(lambda: get_embeddings(pieces))
            recs = [{
                "document_id": did, "content": t, "embedding": e,
                "metadata": {"act_name": g["short_name"], "document_type": "guide",
                             "category": "e-government", "issuing_authority": g["authority"],
                             "governing_law": g["law"], "source_url": g["url"], "is_header": i == 0},
                "chunk_index": i, "page_start": 1, "page_end": 1,
            } for i, (t, e) in enumerate(zip(pieces, embs))]
            retry(lambda: insert_chunks(recs))
            retry(lambda: db.table("legal_documents").update({"total_chunks": len(recs)}).eq("id", did).execute())
            done += 1
            print(f"  [{done}] {len(recs)} chunks <- {g['short_name']}", flush=True)
        except Exception as e:
            print(f"  ! {g['short_name']}: {str(e)[:90]}", flush=True); failed += 1
    print(f"\nSUMMARY ingested={done} skipped={skipped} failed={failed}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
