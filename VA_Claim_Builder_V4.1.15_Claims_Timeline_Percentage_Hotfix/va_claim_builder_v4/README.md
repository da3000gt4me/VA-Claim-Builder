# VA Claim Builder 4.0 Stable — Multi-Agent AI Evidence Intelligence

A local-first Streamlit application for organizing VA claim evidence, OCR review, semantic evidence extraction, claim-element analysis, timelines, contradiction review, drafting, rating screening, DBQ/C&P parsing, literature review packets, possible additional-condition discovery, and final binder assembly.

## Install

### Windows
Run `scripts/install_windows.bat`, then `scripts/run_windows.bat`.

### macOS/Linux
Run `bash scripts/install_mac_linux.sh`, then `bash scripts/run_mac_linux.sh`.

## AI configuration

Copy `.env.example` to `.env`. Configure `OPENAI_API_KEY` and/or `XAI_API_KEY`. Multi-agent mode can call both providers concurrently and compare results. Consumer ChatGPT/Grok logins are not used directly; API access is separate.

## Safety

All AI findings require source citations and human approval. The program does not provide legal representation, create a clinician's medical opinion, or guarantee a VA outcome. Literature supports clinician review but does not establish veteran-specific causation by itself.

See `docs/USER_GUIDE.md`, `docs/SECURITY.md`, and `docs/RELEASE_VALIDATION_REPORT.md`.

## Version 4.0.1 additions
- Legal-authority research and validation for statutes, regulations, precedential Federal Circuit/CAVC opinions, VA General Counsel precedent opinions, and nonprecedential fact-pattern research.
- Mandatory source verification, binding-status labels, negative-treatment field, and human legal review.
- Provider-ready DOCX nexus templates using neutral professional formatting or provider-supplied/authorized branding only.
- The software does not scrape and imitate clinic letterhead or imply that an unsigned draft was issued by a provider.


## Version 4.1.11 upload-first automation
- Upload documents before creating claims.
- Form 20-0995 issue fields automatically populate the claim list.
- OCR/retrieval and Semantic Evidence Review each provide a Run All action across the complete project.
- Manual claim entry and single-claim retrieval remain available only for correction and diagnostics.


## Version 4.1.15 Section 21A claim extraction and editing

- Reads page 5, Section 21A of VA Form 20-0995 as the authoritative claim list.
- Separates each numbered Section 21A row into its own claim.
- Stops before Section 21B decision dates.
- Provides extraction diagnostics and a Section 21A text preview.
- Allows every claim to be renamed, assigned a theory/status, or deleted.


## Version 4.1.15 changes
- Isolates each uploaded Form 20-0995 and extracts no more than the nine numbered Section 21A rows per form.
- Adds bulk selection and deletion for claims.
- Corrects Historical Timeline category matching and retains useful undated medical/military events as editable proposals.
- Auto-populates timeline proposals during Run All OCR & Retrieval.
- Displays Semantic Evidence Review thresholds and relevance scores as percentages.
