# Read-only Crunchyroll history probe

This is a manual coverage and shape check, not an importer. It never connects to Supabase, calls AniList, writes to Crunchyroll, stores raw history, or prints session credentials, titles, account IDs or episode IDs. It prints aggregate counts, first/last `date_played`, and the names of available JSON fields. No schedule is active.

The endpoint and `etp_rt_cookie` authentication grant are unofficial and may change. The implementation is based on the public [CrunchyExporter history fetcher](https://github.com/ruflas/crunchyexporter-cli/blob/master/src/crunchyroll/history.py) and [cookie exchange](https://github.com/ruflas/crunchyexporter-cli/blob/master/src/crunchyroll/auth.py); it does not execute their code or their AniList matching. The public web-client ID in this probe can be overridden with `CRUNCHYROLL_PUBLIC_CLIENT_ID` if Crunchyroll rotates it.

## Manual GitHub Actions run

1. In a browser, sign into Crunchyroll and select **your intended profile**, then open **History**. The profile selection must happen before copying the session value.
2. In that browser's developer tools, under Application (or Storage) > Cookies > `https://www.crunchyroll.com`, copy the **value only** of the `etp_rt` cookie. Treat it as a login credential: never post it in chat, screenshots, issues, code or logs.
3. In `ddibara5/marquee` > Settings > Secrets and variables > Actions > **Secrets**, create the repository secret `CRUNCHYROLL_ETP_RT`. Paste the value there. This is the only secret the probe requires. If GitHub rejects or changes it, obtain a new browser cookie.
4. Dispatch **Crunchyroll history probe (manual, read-only)** once from Actions on `main`. Share only the run URL. The run may take several minutes for a long history; it fails if a page repeats, changes shape, or hits the page limit.

The public Actions log contains aggregate history dates, counts and field names. Do not add a raw-data artifact or paste a cookie into a workflow input. This probe cannot prove the selected profile merely from account response fields; compare the result with the profile's website history. A successful dry run does not authorize an import or a recurring scheduler. After inspection, remove the temporary `CRUNCHYROLL_ETP_RT` secret unless explicitly needed for a separately reviewed next step.

Offline check: `python3 -m unittest discover -s tests -p 'test_crunchyroll_probe.py'`. The fixture contains invented IDs and titles.
