import sys, re, io
REPO="/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO+"/scripts"); sys.path.insert(0, REPO+"/backend")
import _dns_resilient  # noqa
from dotenv import load_dotenv; load_dotenv(REPO+"/backend/.env")
from pathlib import Path
from app.db.supabase import get_db, insert_chunks
from app.services.embedder import get_embeddings
from app.services.form_ingester import ingest_form_pdf
from harvest_judgments_v2 import http, store, pages_of
db=get_db(); DL=Path("/tmp/forms3"); DL.mkdir(exist_ok=True)
DNRPC="Department of National Registration, Passport and Citizenship (DNRPC)"; PACRA="Patents and Companies Registration Agency (PACRA)"

def fetch(c,url,tries=4):
    for _ in range(tries):
        try:
            r=c.get(url)
            if r.status_code==200 and len(r.content)>3000: return r.content
        except Exception: pass
    return None

def docx_text(b):
    try:
        import docx
        d=docx.Document(io.BytesIO(b))
        return "\n".join(p.text for p in d.paragraphs if p.text.strip())
    except Exception: return ""

# 1) Passport Form A+N is a real PDF -> normal form ingest
with http() as c:
    b=fetch(c,"https://www.mofaic.gov.zm/diasporaportal/wp-content/uploads/2025/09/PASSPORT-FORM-A-WITH-FORM-N.pdf")
    if b and b[:4]==b"%PDF":
        key="Zambian_Passport_Application_Form.pdf"; (DL/key).write_bytes(b)
        res=ingest_form_pdf(str(DL/key), title="Zambian Passport Application Form (Form A and Form N)",
            short_name="Zambian Passport Application Form", document_type="form", category="identity",
            issuing_authority=DNRPC, description="The official fillable Zambian ordinary passport application (Form A with the Form N recommender declaration), for applicants over 16.",
            source_url="https://www.mofaic.gov.zm/diasporaportal/wp-content/uploads/2025/09/PASSPORT-FORM-A-WITH-FORM-N.pdf")
        if res.get("status")!="skipped":
            sp=store(b,key); db.table("legal_documents").update({"is_global":True,"owner_id":None,"pdf_storage_path":sp,"pdf_page_count":pages_of(b),"source_url":res["document"].get("source_url")}).eq("id",res["document"]["id"]).execute()
            print("  INGESTED [form] Zambian Passport Application Form (PDF)",flush=True)
        else: print("  skip: Passport form",flush=True)
    else: print("  ! passport fetch failed",flush=True)

    # 2) PACRA .docx/.doc forms -> real text (docx) or rich stub (doc); store file for download
    PF=[
     ("PACRA Companies Form 3 (Application for Incorporation)","company","Incorporate a private company limited by shares under the Companies Act No. 10 of 2017.","https://www.pacra.org.zm/files/forms/companies/CompaniesForm3.docx"),
     ("PACRA Companies Form 21 (Beneficial Ownership Declaration)","company","Declare a company's beneficial owners under s.123 of the Companies Act No. 10 of 2017, filed at incorporation.","https://www.pacra.org.zm/files/forms/companies/CompaniesForm21.docx"),
     ("PACRA Companies Form 20 (Change in Shareholding or Beneficial Owner)","company","Notify PACRA of a change in a company's shareholding or beneficial ownership within 14 days.","https://www.pacra.org.zm/files/forms/companies/CompaniesForm20.docx"),
     ("PACRA Companies Form 1 (Name Clearance)","company","Reserve or clear a proposed company name before incorporation.","https://www.pacra.org.zm/files/forms/companies/CompaniesForm1.docx"),
     ("PACRA Standard Articles of Association","company","The standard/model Articles of Association template for a private company limited by shares.","https://www.pacra.org.zm/files/forms/companies/STANDARD-ARTICLES-2017.docx"),
     ("PACRA BN Form XI (Change in Business Name Particulars)","business","Notify PACRA of a change to a registered business name's particulars.","https://www.pacra.org.zm/files/forms/business-name/BNFormXI.doc"),
     ("PACRA BN Form XIV (Cessation of Business)","business","Declare that a registered business name has ceased trading (also used for the annual return).","https://www.pacra.org.zm/files/forms/business-name/BNFormXIV.doc"),
    ]
    for title,cat,desc,url in PF:
        b=fetch(c,url)
        if not b: print(f"  ! fetch failed: {title}",flush=True); continue
        # dedupe by title
        if db.table("legal_documents").select("id").eq("document_type","form").eq("title",title).execute().data:
            print(f"  skip (exists): {title}",flush=True); continue
        ext=url.rsplit(".",1)[-1]
        key=re.sub(r"[^A-Za-z0-9._-]+","_",title).strip("_")[:76]+"."+ext
        txt=docx_text(b) if ext=="docx" else ""
        body=f"{title}. {desc} This is the official downloadable {PACRA} form; fill it in and file it with PACRA (portal.pacra.org.zm)."
        if len(txt)>200: body+="\n\nForm contents:\n"+txt[:3500]
        doc=db.table("legal_documents").insert({"title":title,"short_name":title,"document_type":"form","source_url":url,"year":2026,"is_global":True,"owner_id":None}).execute().data[0]
        emb=get_embeddings([body])
        insert_chunks([{"document_id":doc["id"],"content":body,"embedding":emb[0],
            "metadata":{"act_name":title,"document_type":"form","category":cat,"issuing_authority":PACRA,"is_header":True},
            "chunk_index":0,"page_start":1,"page_end":1}])
        sp=store(b,key)
        db.table("legal_documents").update({"pdf_storage_path":sp,"total_chunks":1}).eq("id",doc["id"]).execute()
        print(f"  INGESTED [form/{ext}] {title} ({len(b)//1024}KB, text={len(txt)})",flush=True)
print("DONE",flush=True)
