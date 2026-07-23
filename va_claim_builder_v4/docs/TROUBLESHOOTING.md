# Troubleshooting

- If a project will not open, preserve it and run project validation on a copy or restore a verified backup.
- For missing files, reconnect the drive or restore the original source; repair never deletes evidence records.
- If a job was interrupted, reopen the project; active states are converted to interrupted/failed states with retry context.
- For PDF failures, verify the file is readable and not password protected.
- For permission or disk-space failures, select a writable local destination with adequate free space.
- Export a sanitized diagnostic bundle from the Project menu when reporting a defect.
- A Gatekeeper warning is expected for the unnotarized macOS RC; verify the checksum, then use Control-click > Open.
- Failed packaging retains logs under `dist/release/build-logs` without replacing the last valid release.
- If a build is missing, open the completed Actions run and inspect both platform jobs. Failed jobs intentionally upload no release artifact.
