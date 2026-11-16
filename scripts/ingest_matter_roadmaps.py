#!/usr/bin/env python3
"""Litigation "next-step roadmaps" for the matters the 2026-07 field study found
real users (especially self-representing litigants) actually run but kept losing
the thread of ("anything else?", "what do I do next?").

Each roadmap is a where-you-are -> next-step -> what-to-file -> deadline guide for
one matter type, grounded in the governing Zambian law. Stored as
document_type='guide' (same as the civic guides): surfaces in search_corpus,
ignored by search_case_law. A title/purpose header is prepended before embedding
so short "how do I..." / "what's next" queries match.

  backend/.venv/bin/python scripts/with_harvest_key.py scripts/ingest_matter_roadmaps.py [--update] [--dry-run]

Without flags, guides that are missing are added and existing ones are left
alone. --update rewrites existing guides IN PLACE: the document keeps its id
(saved chats cite it), the new chunks are inserted first and the old ones
deleted after, so a failed run never leaves a guide empty.

ACCURACY DISCIPLINE (this is litigation): every roadmap names its governing law,
flags the time limits as things to CONFIRM against the current rules (limitation
periods here have been litigated and amended), and says when to get a lawyer.
Levy drafts the documents but the litigant/lawyer remains responsible for filing.
Cite only sections read in the library's own copy of the Act, or quoted in a
judgment the library holds; never cite a repealed Act as the current law.
"""
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))
import _dns_resilient  # noqa: E402,F401
from dotenv import load_dotenv  # noqa: E402

# backend/.env lives only in the main checkout, never in a git worktree.
_common = Path(subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                              cwd=REPO, capture_output=True, text=True).stdout.strip())
load_dotenv(REPO / "backend" / ".env")
load_dotenv(_common.parent / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402
from app.services.embedder import get_embeddings  # noqa: E402
from ingest_civic_guides import chunk_text  # noqa: E402  reuse the guides' paragraph chunker

CATEGORY = "litigation-roadmap"
ROADMAP_HEADER = ("{title}. This is a step-by-step Zambian litigation roadmap ({short_name}). "
                  "Governing law: {law}. It explains where you are in the case, the next step, "
                  "what to file, and the deadline.\n\n")

ROADMAPS = [
    {
        "title": "Roadmap: an unfair-dismissal / employment complaint in the Industrial Relations Division (stage by stage)",
        "short_name": "Roadmap: Industrial Relations complaint",
        "law": "Industrial and Labour Relations Act, Cap 269; Employment Code Act No. 3 of 2019",
        "body": """This is the step-by-step path for an employee (including a self-representing complainant) bringing a complaint such as unfair or wrongful dismissal, unpaid dues, or a labour grievance in the Industrial Relations Division of the High Court (the former Industrial Relations Court).

WHERE THIS RUNS: the Industrial Relations Division of the High Court. Individual employment complaints (unfair dismissal, terminal benefits) are lodged here. Some collective or trade-dispute matters must first go through the Labour Commissioner / conciliation, so check whether your matter needs that step first.

TIME LIMIT, CONFIRM THIS FIRST: the period within which you must lodge a complaint is the single most important date, and it has been the subject of litigation and amendment in Zambia. Do NOT rely on a remembered number of days. Confirm the current limitation period for your type of claim before you do anything else, because filing late can end the case.

THE STAGES:
1. Exhaust internal remedies. Show you used the employer's grievance/appeal process, or that it was futile.
2. Lodge the originating process (the Notice of Complaint) in the Industrial Relations Division, setting out the parties, the facts, and the relief you want (reinstatement, damages, terminal benefits, etc.).
3. Serve the complaint on the respondent (the employer). If the employer is evasive, ask the court for substituted service (Levy has a separate roadmap for that).
4. The respondent files its Answer.
5. You file a Reply, usually with an Affidavit in support.
6. Both sides file skeleton arguments, bundles of documents, witness statements and a summary of facts and issues to the court's directions.
7. Hearing (evidence and cross-examination), then judgment.

WHAT LEVY CAN DRAFT FOR YOU: the Notice of Complaint, the Affidavit in support, the Reply to the respondent's Answer, Skeleton Arguments, and a Witness Summons. Ask and Levy will walk each one through with you.

GET A LAWYER IF: the sums are large, dismissal facts are disputed, or you are unsure about the time limit. The Legal Aid Board and university legal clinics assist those who cannot afford a private lawyer.""",
    },
    {
        "title": "Roadmap: applying to remove a caveat on land in Zambia (stage by stage)",
        "short_name": "Roadmap: removal of a caveat",
        "law": "Lands and Deeds Registry Act, Cap 185",
        "body": """This is the path when a caveat has been lodged against land you own or are buying, and it is blocking your transaction. A caveat is a statutory 'stop' on dealings with the title. It can be removed either through the Lands Registry or by the High Court.

FIRST, THE KEY QUESTION: does the caveator actually have a 'caveatable interest' (an interest in the land itself, such as a purchaser, mortgagee or beneficiary)? A mere debt owed to the caveator is generally NOT a caveatable interest, so a caveat lodged only to secure a debt is usually removable.

TWO ROUTES:
Route A, through the Registrar (often faster/cheaper): apply to the Registrar of Lands to serve notice on the caveator. The caveat lapses unless, within the notice period, the caveator obtains a court order to keep it in place.
Route B, through the High Court: file an Originating Summons with a supporting Affidavit asking the court to order removal of the caveat. Serve the caveator, who may oppose; the court hears it and, if the caveat has no proper basis, orders removal.

THE STAGES (court route):
1. Gather proof of your interest (deed of assignment, contract of sale, certificate of title) and of the caveator's lack of a caveatable interest.
2. File the Originating Summons + Affidavit in Support in the High Court.
3. Serve the caveator (use substituted service if they evade you).
4. Caveator files any opposing affidavit; you may file an affidavit in reply.
5. Hearing, then the court's Order.

WHAT LEVY CAN DRAFT FOR YOU: the Originating Summons, the Affidavit in Support, an Affidavit in Reply, and a Draft Order for removal.

CONFIRM: the exact notice period and the current Registry practice with the Ministry of Lands / Lands and Deeds Registry before you rely on a timeline.""",
    },
    {
        "title": "Roadmap: applying for an order for substituted service when the other side is evading you (stage by stage)",
        "short_name": "Roadmap: substituted service",
        "law": "High Court Rules and the Rules of the Supreme Court (White Book) as applied in Zambia; the Subordinate Court Rules for the Subordinate Court",
        "body": """Use this when you have to serve court documents on someone but they are dodging personal service (hiding, refusing to take documents, unreachable). The court can order 'substituted service', letting you serve by another means, for example by advertisement in a newspaper, by posting at their last known address, by leaving with a relative, or sometimes by email or WhatsApp.

YOU MUST SHOW YOU TRIED PROPERLY FIRST: the court only allows substituted service once you prove real, reasonable attempts at personal service failed. Keep dates, names, and what happened (for example: 'attended the address on 16 June, the respondent was there but refused to receive the documents and was abusive; then engaged court messengers who could not reach him').

THE STAGES:
1. Record every attempt at personal service and how it failed.
2. File an application (usually ex parte, meaning the other side is not present) by Summons or Notice of Motion, WITH an Affidavit in Support setting out the attempts and asking for a specific method of substituted service.
3. The court hears it and, if satisfied, makes an Order specifying exactly how you may serve (which newspaper, which address, how many times, etc.).
4. Carry out service exactly as the Order says.
5. File proof: an Affidavit of Service (attach the newspaper page or delivery proof).

WHAT LEVY CAN DRAFT FOR YOU: the ex parte Summons / Notice of Motion, the Affidavit in Support of substituted service, and a Draft Order. Levy can also draft the later Affidavit of Service.

TIP: propose a method the court will accept as genuinely likely to bring the documents to the person's attention; a bare 'advertise once' is often not enough on its own.""",
    },
    {
        "title": "Roadmap: applying for child custody and maintenance in Zambia (stage by stage)",
        "short_name": "Roadmap: child custody and maintenance",
        "law": "Children's Code Act No. 12 of 2022 (which repealed the Affiliation and Maintenance of Children Act and the Juveniles Act); within a divorce, the Matrimonial Causes Act No. 20 of 2007",
        "body": """This is the path for a parent or guardian seeking custody of a child and/or a maintenance (upkeep) order. The court decides by the BEST INTERESTS OF THE CHILD (Children's Code Act, 2022, s.144(2)(a)), which come before either parent's wishes.

THE LAW CHANGED IN 2022: the Children's Code Act, 2022 repealed the Affiliation and Maintenance of Children Act and the Juveniles Act. Older documents, and some people, still cite those Acts. Apply under the Children's Code.

MAINTENANCE (money for the child's upkeep):
- A guardian or custodial parent may apply to the court for an order that a named person make regular payments for the child's maintenance (s.138(1)). You do not need to be divorcing.
- The court can also order the provision of education, medical care, housing and clothing (s.139).
- A person aged 19 or over may, with the court's leave, apply for maintenance for themselves while in education or training, or because of disability or illness (s.138(2)).
- Where to apply: the Subordinate (magistrate's) Court. A Subordinate Court hearing a matter involving a child sits as the "juvenile court" under the Act. Ask the clerk of court which court handles children's matters in your district. The High Court makes these orders inside a divorce.

CUSTODY (who the child lives with) AND ACCESS:
- The court may make an order on custody and on each parent's right of access to the child (s.143(1)). The father, the mother, the Director of Social Welfare, or anyone with a sufficient interest in the child may apply (s.143(2)).
- Once you have applied for custody, nobody may take the child out of your custody without the court's leave and your consent (s.142(1)).
- The court may ask a child welfare inspector for a report (s.144(1)). It weighs the child's best interests and wishes, each parent's conduct, and whether the child has suffered or is likely to suffer harm (s.144(2)).
- Parents can agree custody between themselves, but the court will not enforce an agreement that is not in the child's best interests (s.148).
- When the court makes a custody order it can also make a maintenance order (s.149).

INSIDE A DIVORCE: custody and maintenance are decided by the High Court in the divorce proceedings (Matrimonial Causes Act). The High Court Rules, Order XXXI r.4(4) (as amended by SI No. 72 of 2018), refer custody and maintenance applications in matrimonial causes to mediation first. See Levy's "Roadmap: divorce".
CUSTOMARY MARRIAGE: the Local Court can order maintenance for a child under 18 (Local Courts Act, Cap. 29).

THE STAGES:
1. Gather what shows the child's needs and each parent's means (school fees, medical costs, the child's living situation, incomes).
2. File the application in the appropriate court, stating what you seek: custody, access for the other parent, and a maintenance amount.
3. Serve the other parent (use substituted service if they evade you).
4. The other parent responds; the court may ask for a welfare report (s.144(1)).
5. Hearing: the court weighs the child's best interests and makes an order on custody, access and/or maintenance.

SAFETY NOTE: if there is violence, threats, a firearm, or a fear that the child may be taken, tell the court; harm to the child is one of the things it must weigh (s.144(2)(g)). A protection order under the Anti-Gender-Based Violence Act can be extended to protect the children too (s.18). See "Roadmap: protection order (gender-based violence)". If the court refers the matter to mediation, tell the court about the violence. Police and social welfare can also be involved. Do not delay if a child is at risk.

WHAT LEVY CAN DRAFT FOR YOU: the application, the Affidavit in Support, and a Draft Order. CONFIRM current court fees and the exact filing office locally. If you cannot afford a lawyer, apply to the Legal Aid Board (Legal Aid Act, 2021, s.34).""",
    },
    {
        "title": "Roadmap: getting a protection order against an abusive spouse, partner or relative under the Anti-Gender-Based Violence Act (stage by stage)",
        "short_name": "Roadmap: protection order (gender-based violence)",
        "law": "Anti-Gender-Based Violence Act No. 1 of 2011 (the 2026 amendment, Act No. 28 of 2026, changes only the Committee)",
        "body": """This is the path for someone facing violence, threats or abuse from a spouse, partner or relative, and for family or friends helping them. It covers reporting to the police and getting a court order that stops the abuser and can make him leave the home. Physical, mental, social or economic abuse in a domestic relationship (married under any law or custom, living together, dating, sharing a child, or related) is gender-based violence under the Act (s.3).

SAFETY FIRST: if she is in danger now, call 999 or go to the nearest police station and ask for the Victim Support Unit. For counselling and help planning how to leave safely, call 933 (Lifeline Zambia, toll-free); for a child, 116 (Childline). Levy's guide "Getting help for gender-based violence" lists more places to go.

WHICH COURT: a subordinate (magistrate's) court. Under the Act, "court" means a subordinate court (s.3).

STAGE 1, REPORT TO THE POLICE (helpful, not required before applying to court):
- The victim may file a complaint with the police (s.6(1)). Any other person or institution with information can file it where that is in the victim's interest (s.6(3)). Family members can report.
- She can report where he lives, where she lives, where the violence happened, where she is staying if she has left home, or wherever is convenient for the person reporting (s.6(4)).
- Police must respond promptly and protect her, even when the person reporting is not the victim (s.7).
- Police must record the complaint, give her an extract on request, help her get medical treatment (by issuing a medical form), help her to a place of safety, protect her while she collects her belongings, and advise her on keeping evidence (s.8).
- Police may arrest without a warrant where they reasonably believe an offence under the Act has been committed, or an order under it is being broken (s.9).

STAGE 2, APPLY FOR A PROTECTION ORDER (s.10):
- She applies to the court for an order to stop him carrying out threats or further violence (s.10(1)). If she has no lawyer, the clerk of court must explain the remedies and how to apply (s.10(2)).
- If she cannot apply herself, any other person with information about the violence may assist her to apply (s.10(3)), with her written consent or, without it, the court's leave (s.10(5)).
- Where to file: where she lives, works or is staying temporarily after leaving home; where he lives or works; or where the violence happened (s.10(6)).
- If a criminal case about the violence is already in court, that court can make a protection order itself (s.10(8)).
- Applications are made "in the prescribed manner and form" (s.10(7)): ask the clerk of court for the form and CONFIRM any fee.

STAGE 3, URGENT PROTECTION (interim order, s.12): the court can issue an interim protection order on an urgent application made without notice to him. It considers the risk of harm if no order is made at once, whether she might be scared off pursuing the case, and whether he is evading service (s.12(1)-(2)). An interim order lasts three months and can be extended by up to three more (s.12(3)).

STAGE 4, THE HEARING: held in chambers, not in open court (s.11(1)). The court can keep him apart from her and her witnesses (s.11(2)). It must consider the application within 14 days of filing, and can call for medical evidence supported by a police report (s.11(3)).

WHAT THE ORDER CAN DO:
- Forbid him from committing or threatening violence against her, her relatives or friends (s.13).
- Forbid assault, confining her, cutting off food, shelter, money, rent or household necessities, forced sexual contact "whether married or not", and contacting her at work or by phone (s.14).
- Keep him away from places she or the children go, order counselling, and make him surrender firearms or weapons to the police (s.15).
- Extend protection to other people, such as her children or relatives (s.18).
- OCCUPATION ORDER (s.20): the court can require him to leave the matrimonial home, or any home they share, and keep paying rent, mortgage and maintenance to her (s.20(1)). It first considers a social enquiry report (s.20(2)) and, for a married couple, the effect on the family's health, education and development (s.20(3)). A landlord may not evict her just because the lease is in his name (s.20(4)).

HOW LONG IT LASTS: a final order lasts up to 12 months at first and can be extended for good cause (s.17). Either side can ask to change, cancel or discharge it (ss.16, 22). Appeals go to the High Court (s.21).

IF HE BREAKS IT: breaking an order is an offence punishable by up to two years' imprisonment (s.23(1)), and police can arrest without a warrant (s.9(e)). An order does not stop a criminal prosecution for assault under the Penal Code (s.19).

SHELTERS: the Minister responsible for social welfare must establish and run shelters for victims (s.24). An adult shelter must keep her safe, offer counselling, and care for a child she brings (s.28). Ask the Victim Support Unit, a One Stop Centre or Lifeline (933) for the nearest one.

DIVORCE IS SEPARATE: a protection order does not end the marriage and does not require a divorce. See "Roadmap: divorce".

WHAT LEVY CAN DRAFT FOR YOU: a clear statement of what happened (dates, injuries, threats, witnesses, any police or medical reports) to support the application, and an affidavit in support. If she cannot afford a lawyer, the Legal Aid Board gives free or low-cost help (Legal Aid Act, 2021, ss.34-35).""",
    },
    {
        "title": "Roadmap: divorce in Zambia for statutory (civil or church) and customary marriages, including leaving a violent spouse (stage by stage)",
        "short_name": "Roadmap: divorce",
        "law": "Matrimonial Causes Act No. 20 of 2007 (as amended by Act No. 6 of 2024); High Court Rules, Cap. 27 (as amended by SI No. 72 of 2018); Local Courts Act, Cap. 29",
        "body": """This is the path for ending a marriage in Zambia: which court, the grounds, what to file, and what happens to the children, maintenance and property. It also explains what happens when a spouse leaves because of violence.

NOTE ON SOURCES: Levy's library holds the Matrimonial Causes (Amendment) Act, 2024 and many High Court divorce judgments that quote the Matrimonial Causes Act, 2007, but not yet the 2007 Act itself. The section numbers below are those the judgments quote and apply.

STEP ONE, WHICH KIND OF MARRIAGE?
- STATUTORY MARRIAGE (married under the Marriage Act at a registry office or licensed church, with a marriage certificate): it can only be ended by the High Court on a divorce petition under the Matrimonial Causes Act. The judgments in Levy's library come from the High Court's Family and Children's Court Division.
- CUSTOMARY MARRIAGE (married under African customary law, without a Marriage Act certificate): dissolved by the Local Court, which hears matrimonial cases based on African customary law (Local Courts Act, Cap. 29). On dissolution the Local Court issues a divorce certificate. It can order maintenance for a divorced spouse for up to three years or until she remarries, whichever is earlier, maintenance for children under 18, and the return of property.

STATUTORY MARRIAGE, THE GROUND:
- The only ground is that the marriage has broken down irretrievably (s.8). The petitioner must prove one or more of the facts in s.9(1):
  (a) the respondent has committed adultery and the petitioner finds it intolerable to live with the respondent;
  (b) the respondent has behaved in such a way that the petitioner cannot reasonably be expected to live with the respondent (violence, threats and cruelty are pleaded here);
  (c) the respondent has deserted the petitioner for a continuous period of at least two years immediately before the petition;
  (d) the parties have lived apart for a continuous period of at least two years and the respondent consents to the divorce;
  (e) the parties have lived apart for a continuous period of at least five years.
- TIMING: no divorce petition can be filed within the first year of the marriage (s.6, as applied in the High Court judgments).
- RESIDENCE: the court checks that a party is domiciled in Zambia or has lived here for at least twelve months before the petition.

LEFT BECAUSE OF VIOLENCE? DESERTION IS NOT THE ROUTE:
- Desertion under s.9(1)(c) is about the RESPONDENT having deserted the petitioner, and it needs two years.
- A wife who leaves home because her husband is violent does not need to wait two years or rely on desertion. She can petition on his behaviour under s.9(1)(b), once the marriage is a year old.
- Keep a record of the violence: police reports, medical reports, any protection order, messages and witnesses. The judgments decide behaviour petitions on the particulars pleaded and proved.
- If he claims she deserted him, get legal advice.
- Her safety comes first: a protection order (and an order making him leave the home) does not need a divorce and can be quicker. See "Roadmap: protection order (gender-based violence)".

THE STAGES (statutory marriage):
1. Gather: the marriage certificate, the children's details, evidence of the fact relied on (for behaviour: police and medical reports, protection orders, witnesses), and details of property and income.
2. File the divorce petition in the High Court, stating the ground (s.8), the fact (for example s.9(1)(b)) with particulars, and what else is asked for (custody, maintenance, property).
3. Serve the petition on the respondent. If he evades service, ask for substituted service (Levy has a roadmap for that).
4. He may answer, consent, or not respond. Uncontested petitions in the judgments were often decided on the documents.
5. Decree nisi: the judgments say it becomes absolute after six weeks unless cause is shown why it should not. The marriage ends when the decree is made absolute.
6. Children, maintenance and property: under the High Court Rules, Order XXXI r.4(4) (as amended by SI No. 72 of 2018), applications for maintenance, property settlement and custody in matrimonial causes are referred to mediation. If there has been violence, tell the court and the mediation officer, and ask not to mediate face to face with him; the rules let a judge treat a case as unsuitable for referral to mediation (Order XXXI r.4(1)).

CHILDREN: custody and maintenance follow the child's best interests (Children's Code Act, 2022). See "Roadmap: child custody and maintenance".

FREE LEGAL HELP: apply to the Legal Aid Board. Someone can apply on her behalf (Legal Aid Act, 2021, s.34(2)). The Director must decide within 30 days (s.35(1)) and grants aid to people who cannot afford a lawyer where it is in the interest of justice (s.35(2)). Consultation fees and contributions can be waived for people who cannot pay (ss.50(2), 51(2)). The National Legal Aid Clinic for Women and university law clinics also help.

WHAT LEVY CAN DRAFT FOR YOU: the divorce petition with particulars of behaviour, the supporting affidavit, a consent to divorce, and applications for custody and maintenance. CONFIRM current court fees at the registry.""",
    },
    {
        "title": "Getting help for gender-based violence in Zambia: emergency numbers, the police Victim Support Unit, One Stop Centres, shelters and free legal help",
        "short_name": "Getting help for gender-based violence",
        "law": "Anti-Gender-Based Violence Act No. 1 of 2011; Legal Aid Act No. 1 of 2021",
        "category": "safety",
        "header": ("{title}. This is a practical safety guide ({short_name}) for anyone being abused or "
                   "threatened by a spouse, partner or relative in Zambia, and for family or friends "
                   "helping them: who to call, where to go, and how to get free legal help. Domestic "
                   "violence, wife beating, threats. Governing law: {law}.\n\n"),
        "body": """Use this when someone is being abused or threatened by a spouse, partner or relative, or a family member wants to help them.

IN DANGER NOW:
- Call 999 (emergency) or go to any police station and ask for the Victim Support Unit (VSU), the police unit for violence against spouses, women, children and the elderly.
- Police must respond promptly and protect her even when the person reporting is not the victim (Anti-Gender-Based Violence Act, s.7). A relative can report for her (s.6(3)).
- The police toll-free line 991 has been reported as not always working. If it fails, call 999 or go in person.

TALK TO SOMEONE:
- 933: Lifeline Zambia, toll-free, for adults facing abuse. Counselling, help planning how to leave safely, and referrals.
- 116: Childline Zambia, toll-free, for children.
- CONFIRM: helpline numbers and hours change. If a number fails, go to the nearest police station or hospital.

MEDICAL CARE AND EVIDENCE:
- One Stop Centres bring medical care, police, counselling and legal advice into one place, many inside hospitals. The UK government's 2024 guide for victims in Zambia lists centres at University Teaching Hospital, Levy Mwanawasa Hospital and Mtendere Clinic (Lusaka), Ndola Central Hospital, Kitwe Central Hospital and Buchi Clinic (Kitwe), Livingstone General Hospital, Kabwe General Hospital and Mazabuka District Hospital. CONFIRM locally; more have opened since.
- Go as soon as possible after an assault. Police help with medical treatment by issuing a medical form (s.8). A medical report supported by a police report is evidence the court can call for (s.11(3)(b)).

A SAFE PLACE TO STAY:
- Police must help a victim get to a place of safety and protect her while she collects her belongings (s.8(1)(d)-(e)).
- The Government must establish shelters for victims (s.24). Ask the VSU, a One Stop Centre or 933 for the nearest shelter.

COURT PROTECTION: a protection order from the magistrate's court can stop him, and an occupation order can make him leave the home and keep paying rent and maintenance (ss.10, 12, 20). See "Roadmap: protection order (gender-based violence)".

FREE LEGAL HELP:
- The Legal Aid Board helps people who cannot afford a lawyer (Legal Aid Act, 2021). Apply to the Director; someone can apply on her behalf (s.34). Fees can be waived (s.50(2)).
- The National Legal Aid Clinic for Women (run by the Law Association of Zambia) and university law clinics also help.

DIVORCE: she does not need to rely on desertion. She can divorce on his behaviour (Matrimonial Causes Act, s.9(1)(b)) once the marriage is a year old, with no two-year wait. See "Roadmap: divorce".

PHONE AND PRIVACY SAFETY: if the abuser checks her phone, use a private (incognito) browser window, or let a trusted relative make the calls and searches. Levy can be used without signing in.""",
    },
]


def main() -> int:
    update = "--update" in sys.argv
    dry = "--dry-run" in sys.argv
    db = get_db()
    done = 0
    for g in ROADMAPS:
        header = g.get("header", ROADMAP_HEADER).format(**g)
        full = header + g["body"]
        chunks = chunk_text(full) or [full]
        existing = (db.table("legal_documents").select("id,title").eq("document_type", "guide")
                    .eq("short_name", g["short_name"]).execute().data or [])
        if len(existing) > 1:
            print(f"  REFUSING: {len(existing)} guides named {g['short_name']!r}; resolve by hand")
            return 1
        if existing and not update:
            print(f"  skip (exists): {g['short_name']}")
            continue
        if existing:
            # Unchanged text keeps its chunks, so citations to them stay valid.
            stored = [c["content"] for c in (db.table("legal_chunks").select("content,chunk_index")
                                             .eq("document_id", existing[0]["id"])
                                             .order("chunk_index").execute().data or [])]
            if stored == chunks and existing[0]["title"] == g["title"]:
                print(f"  unchanged: {g['short_name']}")
                continue
        print(f"  {'UPDATE' if existing else 'ADD'} {g['short_name']}: {len(chunks)} chunks, {len(full)} chars")
        if dry:
            continue
        # Embed before writing anything: a dead key must not leave an empty guide.
        embs = get_embeddings(chunks)
        if existing:
            doc_id = existing[0]["id"]
            old_ids = [c["id"] for c in (db.table("legal_chunks").select("id")
                                         .eq("document_id", doc_id).execute().data or [])]
            db.table("legal_documents").update({"title": g["title"]}).eq("id", doc_id).execute()
        else:
            doc_id = db.table("legal_documents").insert({
                "title": g["title"], "short_name": g["short_name"],
                "document_type": "guide", "year": 2026,
                "is_global": True, "owner_id": None,
            }).execute().data[0]["id"]
            old_ids = []
        rows = [{
            "document_id": doc_id, "content": c, "embedding": e,
            "metadata": {"act_name": g["short_name"], "document_type": "guide",
                         "category": g.get("category", CATEGORY), "governing_law": g["law"],
                         "is_header": i == 0},
            "chunk_index": i, "page_start": 1, "page_end": 1,
        } for i, (c, e) in enumerate(zip(chunks, embs))]
        # Five rows at a time: each carries a vector into an indexed column and
        # bigger inserts hit Supabase's statement timeout (57014).
        for k in range(0, len(rows), 5):
            for attempt in range(4):
                try:
                    db.table("legal_chunks").insert(rows[k:k + 5]).execute()
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 3 or "57014" not in str(e):
                        raise
                    time.sleep(2 * (attempt + 1))
        # Old chunks go only after the new ones are in.
        for k in range(0, len(old_ids), 20):
            db.table("legal_chunks").delete().in_("id", old_ids[k:k + 20]).execute()
        db.table("legal_documents").update({"total_chunks": len(rows)}).eq("id", doc_id).execute()
        print(f"    done: {doc_id} ({len(rows)} chunks, {len(old_ids)} old removed)")
        done += 1
    print(f"\nDONE {'updated/added' if update else 'added'}={done} (of {len(ROADMAPS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
