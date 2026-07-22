# Increment 2 Design Notes

## Upload categories

0. VA Denial Letters
1. VA Form 20-0995 submissions
2. Statements in Support of Claim
3. Medical Records
4. Draft Self-Nexus Letters
5. Draft Doctor Nexus Letters
6. Draft Buddy/Lay Letters
7. SMART Transcript
8. Military Records
9. DD-214
10. Personal Statements and Historical Timelines
99. Unclassified holding area

## Draft inheritance rule

Uploaded drafts are immutable source artifacts. A byte-for-byte working copy is created for revision. Revised documents must be built from the working copy, approved evidence annotations, and timeline facts. Conflicts are raised as questions rather than silently resolved.

## Evidence approval rule

Only annotations with `review_status = approved` may be used in generated doctor, veteran, or witness packets. The final inclusion flag remains separate from approval so draft or unsigned materials are not accidentally submitted.
