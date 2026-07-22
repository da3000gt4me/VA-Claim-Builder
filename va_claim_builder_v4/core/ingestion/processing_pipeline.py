from __future__ import annotations
from pathlib import Path
from .text_extractor import TextExtractor

class ProcessingPipeline:
    def __init__(self, db, extractor: TextExtractor | None = None):
        self.db=db; self.extractor=extractor or TextExtractor()

    def process_document(self, project_id: str, document: dict) -> dict:
        pages=self.extractor.extract(document['original_path'])
        claim_ids=self.db.get_document_claim_ids(document['id'])
        for item in pages:
            page_id=self.db.upsert_document_page(project_id, document['id'], item.page, item.text, item.method,
                                                 item.confidence, item.needs_review, item.warnings)
            for claim_id in claim_ids: self.db.link_page_claim(page_id, claim_id)
        avg=sum(p.confidence for p in pages)/len(pages) if pages else 0.0
        low=sum(1 for p in pages if p.needs_review)
        self.db.update_document_processing(document['id'], 'complete', 'review_required' if low else 'complete', avg)
        return {'document_id':document['id'],'pages':len(pages),'average_confidence':avg,'low_confidence_pages':low}
