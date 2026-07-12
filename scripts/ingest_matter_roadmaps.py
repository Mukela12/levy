#!/usr/bin/env python3
"""Litigation "next-step roadmaps" for the matters the 2026-07 field study found
real users (especially self-representing litigants) actually run but kept losing
the thread of ("anything else?", "what do I do next?").

Each roadmap is a where-you-are -> next-step -> what-to-file -> deadline guide for
one matter type, grounded in the governing Zambian law. Stored as
document_type='guide' (same as the civic guides): surfaces in search_corpus,
ignored by search_case_law. A title/purpose header is prepended before embedding
so short "how do I..." / "what's next" queries match. Re-runnable with --force.

ACCURACY DISCIPLINE (this is litigation): every roadmap names its governing law,
flags the time limits as things to CONFIRM against the current rules (limitation
periods here have been litigated and amended), and says when to get a lawyer.
Levy drafts the documents but the litigant/lawyer remains responsible for filing.
"""
import sys

REPO = "/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO + "/backend")
sys.path.insert(0, REPO + "/scripts")
import _dns_resilient  # noqa
from dotenv import load_dotenv
load_dotenv(REPO + "/backend/.env")
from app.db.supabase import get_db, insert_chunks
from app.services.embedder import get_embeddings
from ingest_civic_guides import chunk_text  # reuse the guides' paragraph chunker

CATEGORY = "litigation-roadmap"

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
        "law": "Affiliation and Maintenance of Children Act, Cap 64; the Juveniles Act, Cap 53; and, within a divorce, the Matrimonial Causes Act No. 20 of 2007",
        "body": """This is the path for a parent or guardian seeking custody of a child and/or a maintenance (upkeep) order. The court's overriding rule is the WELFARE OF THE CHILD: it is paramount and comes before either parent's wishes.

WHICH COURT / WHICH LAW:
- Maintenance (money for the child's upkeep): apply in the Subordinate Court under the Affiliation and Maintenance of Children Act. This is the common, accessible route and you do not need to be divorcing.
- Custody on its own (who the child lives with): can be sought under the Juveniles Act / the court's welfare jurisdiction.
- Custody and maintenance inside a divorce: dealt with by the High Court in the matrimonial proceedings under the Matrimonial Causes Act.

THE STAGES (maintenance / stand-alone custody):
1. Gather what shows the child's needs and each parent's means (school fees, medical, the child's living situation, incomes).
2. File the complaint / application in the appropriate court, stating what you seek (custody, care and control, access for the other parent, and a maintenance amount).
3. Serve the other parent (use substituted service if they evade you).
4. The other parent responds; the court may direct a welfare/social inquiry.
5. Hearing: the court weighs the child's welfare, stability, and each parent's circumstances, then makes an Order (custody, access, and/or a maintenance sum).

SAFETY NOTE: if there is a real risk to you or the child (violence, a firearm, threats, or a fear the child may be taken), tell the court, and you can ask for interim protective orders. Police and social welfare can also be involved. Do not delay if a child is at risk.

WHAT LEVY CAN DRAFT FOR YOU: the application / complaint, the Affidavit in Support, and a Draft Order. CONFIRM current court fees and the exact filing office locally, and consider the Legal Aid Board or a legal clinic if you cannot afford a lawyer.""",
    },
]


def main() -> int:
    force = "--force" in sys.argv
    db = get_db()
    # optional cleanup of prior roadmap guides
    existing = db.table("legal_documents").select("id,short_name").eq(
        "document_type", "guide").ilike("short_name", "Roadmap:%").execute().data or []
    if existing and force:
        for e in existing:
            db.table("legal_chunks").delete().eq("document_id", e["id"]).execute()
            db.table("legal_documents").delete().eq("id", e["id"]).execute()
        print(f"  cleared {len(existing)} existing roadmaps (--force)")
        existing = []
    have = {e["short_name"] for e in existing}

    done = 0
    for g in ROADMAPS:
        if g["short_name"] in have:
            print(f"  skip (exists): {g['short_name']}")
            continue
        doc = db.table("legal_documents").insert({
            "title": g["title"], "short_name": g["short_name"],
            "document_type": "guide", "year": 2026,
            "is_global": True, "owner_id": None,
        }).execute().data[0]
        # Prepend a title/purpose header so short "what do I do next" queries match,
        # then chunk the body the same way the rest of the corpus is chunked.
        header = (f"{g['title']}. This is a step-by-step Zambian litigation roadmap "
                  f"({g['short_name']}). Governing law: {g['law']}. It explains where "
                  f"you are in the case, the next step, what to file, and the deadline.\n\n")
        full = header + g["body"]
        chunks = chunk_text(full) or [full]
        embs = get_embeddings(chunks)
        rows = []
        for i, (c, e) in enumerate(zip(chunks, embs)):
            rows.append({
                "document_id": doc["id"], "content": c, "embedding": e,
                "metadata": {"act_name": g["short_name"], "document_type": "guide",
                             "category": CATEGORY, "governing_law": g["law"],
                             "is_header": i == 0},
                "chunk_index": i, "page_start": 1, "page_end": 1,
            })
        insert_chunks(rows)
        db.table("legal_documents").update({"total_chunks": len(rows)}).eq("id", doc["id"]).execute()
        print(f"  INGESTED roadmap: {g['short_name']} ({len(rows)} chunks)")
        done += 1
    print(f"\nDONE ingested={done} (of {len(ROADMAPS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
