# Architecture

Ingestion/OCR -> page chunks -> private project index -> claim-specific retrieval -> redaction -> AI router -> schema validation -> human review -> approved evidence store -> document generators -> final QC/package.

Cloud providers never receive the entire project by default. Requests should contain only the minimum relevant chunks. Every generated assertion must be linked to source filename and page.
