# RC1 Release Checklist

- [x] Automated: clean project creation/reopen, schema migration, backup validation/restore, job recovery, settings sanitation, full regression suite.
- [x] Automated: document/claim/evidence/timeline/nexus/DBQ/strategy/optimizer/submission persistence from existing increment tests.
- [ ] Manual: exercise all workspaces with a synthetic large project and inspect accessibility labels/focus order.
- [ ] Manual: cancel each long job and close during work on a packaged build.
- [ ] Host build: create and smoke-test the macOS bundle and portable archive.
- [ ] Not verifiable on macOS: Windows and Linux executable/installer behavior.
- [ ] Before promotion: verify checksums, review known limitations, test restore on a copy, confirm no credentials or real medical data in artifacts.
