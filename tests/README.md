Run `python -m unittest discover -s tests -p 'test_*.py'` to verify the Trakt and AniList adapter contracts against synthetic fixtures. SQL verification lives in `supabase/verification`.
The Trakt device authorization helper is exercised with fake HTTP and a fake GitHub CLI runner. Tests never contact Trakt or read real credentials.
The GitHub Actions enrollment and token bundle selection are also tested offline; no Trakt or GitHub secrets are used.
