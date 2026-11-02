# Continuing the authorized data work

Scope: expand and harmonize monetary/fiscal data for
`cichons808-boop/sovereign-debt-transmission`. Work on the data branch, with
no changes to article estimation/results. Continue pending jobs and save
concrete progress. Use the actual latest code and checkpoint rather than
restarting the entire acquisition.

1. Use the existing checkout and lake if present. Otherwise fetch the data
   branch and restore the newest `monetary_fiscal_lake_checkpoint_*.tar.gz`
   data artifact. It excludes original Git-backed files. Reattach the frozen
   article sources with `import-existing` only if needed.
2. Inspect the last `reports/verification.json`, `reports/failures.json`, source
   coverage and queue. Stop duplicate runners with the filesystem lock. Do not
   reset running jobs while a live runner owns the lake lock.
3. Finish the high-value data families, provider-native units, labels and
   metadata. Discover additional official series, countries, vintages and
   dimensions when they address the listed research questions. Respect source
   restrictions and record unavailable or gated sources explicitly.
4. Run a bounded download/normalization batch. Use the available disk budget;
   retain at least 8 GiB free on a small environment. Completed partitions are
   atomic and raw responses are content-addressed. Large active jobs can finish
   after a batch's admission deadline.
   On the initial 8 GiB memory environment, prefer one worker and batches such
   as `run --workers 1 --hours 0.5 --max-jobs 30`. Check the actual filesystem
   runner lock and committed ledger after an interruption; a stale process
   identifier is not proof of a live acquisition process.
   Before claiming jobs, check required Python imports and make one short
   provider connection test. If dependency installation/provider access times
   out, preserve pending work rather than failing the whole queue repeatedly.
   Queue/catalog recovery and checkpoint commands can run without Polars.
5. Generate `report`, `build-panels`, `research-readiness` and `verify --hashes`.
   Update `run_summary.json` with measured counts and limitations. A failed
   provider or missing unit must not be described as integrated coverage.
6. If a Google Drive connector or configured rclone remote is actually
   authorized, use the supported upload operation and verify successful
   transfers. Do not claim the ChatGPT connection supplies server-side rclone
   credentials. Do not change sharing or buy storage.
7. Make a fresh consistent data checkpoint outside the lake with `snapshot`.
   Save the completed archive as a user-accessible file so a new session can
   recover it. Commit code/catalog/report improvements to the data branch.
   Keep bulky data out of the Git history.
   For connected Drive, retain the already verified base and save only a
   checksum-linked increment with `python3 -m datalake.checkpoint create
   --root ... --base previous.tar.gz --output new-increment.tar.gz`.
   Test the complete restore chain into a new empty directory before upload.
   Never delete, trash, prune, change sharing, or synchronize deletions on Drive.
8. Report material errors or required access promptly. Otherwise minimize
   notifications during the night and give a concrete final summary of actual
   sources, countries, observed values, files and remaining work.
