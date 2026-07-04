import sys, re
REPO="/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO+"/scripts"); sys.path.insert(0, REPO+"/backend")
import _dns_resilient  # noqa (falls back to public DNS for www.nhima.co.zm etc.)
from dotenv import load_dotenv; load_dotenv(REPO+"/backend/.env")
from pathlib import Path
from app.db.supabase import get_db
from app.services.form_ingester import ingest_form_pdf
from harvest_judgments_v2 import http, store, pages_of   # http() uses verify=False (RTSA cert)
db=get_db()
DL=Path("/tmp/forms2"); DL.mkdir(exist_ok=True)
RTSA="Road Transport and Safety Agency (RTSA)"; NHIMA="National Health Insurance Management Authority (NHIMA)"; ZP="ZamPortal (Smart Zambia)"
DOCS=[
 ("RTSA Medical Certificate Form","form","transport",RTSA,"RTSA medical fitness certificate form a doctor completes, required for a driving licence.","https://www.rtsa.org.zm/wp-content/uploads/2020/04/Medical-Certificate-Form-.pdf"),
 ("RTSA Motor Vehicle Registration Requirements","form","transport",RTSA,"RTSA checklist of documents and forms (including CNV1 and RL3) needed to first-register a motor vehicle or trailer.","https://www.rtsa.org.zm/wp-content/uploads/2019/09/REGISTRATION-REQUIREMENTS-edited.pdf"),
 ("RTSA Driving Licence Renewal Requirements","form","transport",RTSA,"RTSA checklist of what is needed to renew a driving licence.","https://www.rtsa.org.zm/wp-content/uploads/2019/09/DRIVING-LICENCE-renewals.pdf"),
 ("RTSA Replacement of Registration Certificate Requirements","form","transport",RTSA,"RTSA checklist of what to bring to replace a lost or damaged vehicle registration certificate (white book).","https://www.rtsa.org.zm/wp-content/uploads/2019/09/REQUIREMENTS-FOR-REPLACEMENT-OF-REGISTRATION-CERTIFICAT1.pdf"),
 ("RTSA Road Service Licence Application Form PSV 1","form","transport",RTSA,"RTSA Form PSV 1 to apply for a public service vehicle road service licence.","https://www.rtsa.org.zm/wp-content/uploads/2022/11/ROAD-SERVICE-LICENCE-APPLICATION-FORM-PSV-1-2022.pdf"),
 ("RTSA PSV Driving Licence Requirements","form","transport",RTSA,"RTSA checklist of requirements to get a Public Service Vehicle (PSV) driving licence.","https://www.rtsa.org.zm/wp-content/uploads/2019/09/PUBLIC-SERVICE-VEHICLE-DRIVING-LICENCE.pdf"),
 ("NHIMA Complaints Form","form","health",NHIMA,"NHIMA form to lodge a formal complaint with the National Health Insurance Management Authority.","https://www.nhima.co.zm/wp-content/uploads/2025/09/Complaints-form.pdf"),
 ("NHIMA Attestation Form","form","health",NHIMA,"NHIMA beneficiary/dependant attestation form.","https://www.nhima.co.zm/wp-content/uploads/2025/09/attestation-1.pdf"),
 ("NHIMA Membership Guide","reference","health",NHIMA,"NHIMA 'All You Need to Know' brochure: membership, contributions and benefits.","https://www.nhima.co.zm/wp-content/uploads/2025/09/All-you-need-to-know-Brochure-2025.pdf"),
 ("ZamPortal Guide: Register a ZamPass Account","reference","e-government",ZP,"Official ZamPortal quick guide to creating the ZamPass account needed for all Zambian government e-services.","https://zamportal.gov.zm/wp-content/uploads/2020/04/How-to-Register-New-ZamPass-Account-Quick-Guide.pdf"),
 ("ZamPortal Guide: Pay Government Fees Online","reference","e-government",ZP,"Official ZamPortal quick guide to paying government fees online.","https://zamportal.gov.zm/wp-content/uploads/2020/05/04-ZIGS-Quick-Guide-How-to-Pay-Online.pdf"),
]
with http() as c:
  for title,dtype,cat,auth,desc,url in DOCS:
    try:
      r=c.get(url)
      if not (r.status_code==200 and r.content[:4]==b"%PDF" and len(r.content)>3000):
        print(f"  ! bad fetch ({r.status_code}, {len(r.content)}b): {title}", flush=True); continue
      content=r.content
    except Exception as e:
      print(f"  ! fetch err {str(e)[:50]}: {title}", flush=True); continue
    key=re.sub(r"[^A-Za-z0-9._-]+","_",title).strip("_")[:80]+".pdf"
    (DL/key).write_bytes(content)
    try:
      res=ingest_form_pdf(str(DL/key), title=title, short_name=title, description=desc,
          document_type=dtype, category=cat, issuing_authority=auth, source_url=url)
    except Exception as e:
      print(f"  ! ingest err {str(e)[:60]}: {title}", flush=True); continue
    if res.get("status")=="skipped":
      print(f"  skip (exists): {title}", flush=True); continue
    sp=store(content,key)
    db.table("legal_documents").update({"is_global":True,"owner_id":None,"pdf_storage_path":sp,
        "pdf_page_count":pages_of(content),"source_url":url}).eq("id",res["document"]["id"]).execute()
    print(f"  INGESTED [{dtype}] {title} ({len(content)//1024}KB)", flush=True)
print("DONE", flush=True)
