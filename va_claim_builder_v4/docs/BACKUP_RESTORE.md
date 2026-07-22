# Project Backup and Restore

Use **Project > Create Backup** to produce a validated `.vcbbackup.zip`. The archive includes a manifest and SHA-256 checksum for every member. Backups are local and include source documents by default. Restore validates format, checksums, and archive paths before extracting into a new location. A non-empty destination is never overwritten without explicit authorization; replacement restores preserve the former destination as a timestamped safety copy. Migration backups are automatic database-only snapshots in the application backup folder.
