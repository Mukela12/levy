import sys, re
REPO="/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO+"/scripts"); sys.path.insert(0, REPO+"/backend")
import _dns_resilient  # noqa
from dotenv import load_dotenv; load_dotenv(REPO+"/backend/.env")
from pathlib import Path
from app.db.supabase import get_db
from app.services.form_ingester import ingest_form_pdf
from harvest_judgments_v2 import http, store, pages_of
db=get_db()
DL=Path("/tmp/rtsa"); DL.mkdir(exist_ok=True)
DOCS=[
 ("RTSA Change of Ownership Requirements","form","transport",
  "Official RTSA checklist of the documents and steps required to transfer motor vehicle ownership (change of ownership).",
  ["https://www.rtsa.org.zm/wp-content/uploads/2019/09/Change-of-Ownership-List-of-requirements-1.pdf",
   "https://41.175.8.225/wp-content/uploads/2019/09/Change-of-Ownership-List-of-requirements-1.pdf"]),
 ("Zambian Highway Code","reference","transport",
  "The Zambian Highway Code published by RTSA: road signs, rules of the road and safe-driving guidance for driver's licence learners.",
  ["https://www.rtsa.org.zm/wp-content/uploads/2019/09/Zambian-Highway-Code.pdf",
   "https://41.175.8.225/wp-content/uploads/2019/09/Zambian-Highway-Code.pdf"]),
]
with http() as c:
  for title,dtype,cat,desc,urls in DOCS:
    content=None; src=None
    for u in urls:
      try:
        r=c.get(u)
        if r.status_code==200 and r.content[:4]==b"%PDF" and len(r.content)>5000:
          content=r.content; src=u; break
      except Exception:
        pass
    if not content:
      print(f"  ! FETCH FAILED: {title}", flush=True); continue
    key=re.sub(r"[^A-Za-z0-9._-]+","_",title).strip("_")[:80]+".pdf"
    (DL/key).write_bytes(content)
    res=ingest_form_pdf(str(DL/key), title=title, short_name=title, description=desc,
        document_type=dtype, category=cat, issuing_authority="Road Transport and Safety Agency (RTSA)", source_url=src)
    if res.get("status")=="skipped":
      print(f"  skip (exists): {title}", flush=True); continue
    sp=store(content,key)
    db.table("legal_documents").update({"is_global":True,"owner_id":None,"pdf_storage_path":sp,
        "pdf_page_count":pages_of(content),"source_url":src}).eq("id",res["document"]["id"]).execute()
    print(f"  INGESTED [{dtype}] {title} ({len(content)//1024}KB, downloadable)", flush=True)
print("DONE", flush=True)
