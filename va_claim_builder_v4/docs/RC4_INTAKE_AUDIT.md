
# RC3-to-RC4 intake workflow audit

## RC3 findings

The import execution path ended in `DocumentImportWorker` after
`DocumentManager.import_files`. It copied, fingerprinted, deduplicated, and
cataloged files, then reported completion. It did not queue OCR or call any
analysis service.

The remaining stages existed as separate workspaces and workers:

- OCR/text extraction was manually started from OCR & Text.
- Evidence analysis was manually started per evidence record and failed by
  design in local-only mode.
- Timeline extraction was manually started and failed by design in local-only
  mode.
- Nexus, DBQ, rating strategy, optimizer, and submission generation were
  independent manual jobs.
- Job records persisted, but import did not create downstream jobs. Startup
  marked active jobs interrupted rather than resuming an intake plan.
- UI pages refreshed only their own completed worker. Import completion did not
  refresh claims, evidence, timeline, or later workspaces.
- No shared processing-state record tied stage/version/checksum/results to each
  document. Failures in manually invoked tools were therefore easy to miss.
- Cloud analyzers required configured credentials; no deterministic local path
  connected document text to reviewable claims/evidence/timeline data.

## RC4 execution path

`DocumentImportWorker` now passes newly created document IDs to
`AutomatedIntakeOrchestrator` when automatic analysis is enabled:

1. SHA-256 duplicate detection and persistent Imported/Queued state.
2. Cached text reuse or local PDF/DOCX/text/image extraction.
3. Conservative local classification and metadata/fact extraction.
4. Source-linked draft evidence creation and existing-claim matching.
5. Pending claim field drafts; confirmed claim text is never updated.
6. Draft timeline creation with document/evidence traceability.
7. Claim, relationship, metadata, evidence, timeline, contradiction, and gap
   review suggestions.
8. Persistent completion/failure/cancellation state and workspace-wide refresh.

Jobs and document state persist. Interrupted active stages become **Needs
reanalysis**; partial valid records remain and deterministic fingerprints prevent
duplicates. Accepted/rejected/deferred decisions survive reanalysis.

Core intake is local-only and makes no provider call. Optional cloud tools remain
separate and require explicit configuration. Logs and job messages contain stage
and file information, not extracted medical text.

## Current RC4 boundaries

RC4 does not create a medical nexus opinion, confirm a diagnosis, or infer a
presumptive theory without configured rules. Rating and optimizer jobs remain
opt-in settings because automatically presenting medical/legal strategy as fact
would exceed this functional-correction release. Accepted evidence and claims
are immediately visible to those downstream workspaces.
