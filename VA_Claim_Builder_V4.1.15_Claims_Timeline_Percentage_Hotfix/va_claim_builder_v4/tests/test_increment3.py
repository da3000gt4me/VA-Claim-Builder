from core.storage.project_db import ProjectDB
from core.retrieval.hybrid_search import ClaimRetriever
from core.analysis.contradiction_engine import ContradictionEngine
from core.analysis.readiness import ReadinessEngine

def test_page_retrieval_and_readiness(tmp_path):
    db=ProjectDB(tmp_path/'x.db'); p=db.create_project('x'); c=db.add_claim(p,'Migraine headaches','direct')
    d=db.add_document({'project_id':p,'category':'medical_records','original_name':'n.pdf','original_path':str(tmp_path/'n.pdf'),'sha256':'abc'})
    db.link_document_claims(d,[c]); pg=db.upsert_document_page(p,d,1,'Migraine diagnosis with prostrating attacks','native',.95,False,[]); db.link_page_claim(pg,c)
    got=ClaimRetriever(db).retrieve(p,c); assert got and got[0]['page']==1
    for element in ['diagnosis','in_service_event','nexus']:
        aid=db.add_annotation(p,{'claim_id':c,'document_id':d,'page':1,'claim_element':element,'polarity':'favorable','finding':element,'confidence':.9})
        db.review_annotation(aid,'approved')
    result=ReadinessEngine().assess(db.list_claims(p)[0],db.list_annotations(p),[],[])
    assert result['score']>=80 and not result['missing_elements']

def test_contradiction_detection():
    anns=[{'id':'a','claim_id':'c','claim_element':'diagnosis','polarity':'favorable'}, {'id':'b','claim_id':'c','claim_element':'diagnosis','polarity':'unfavorable'}]
    events=[{'id':'e1','claim_id':'c','event_type':'onset','event_date_start':'2003'}, {'id':'e2','claim_id':'c','event_type':'onset','event_date_start':'2015'}]
    found=ContradictionEngine().analyze(anns,events)
    assert len(found)>=2
