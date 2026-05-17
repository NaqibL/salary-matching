Debug the current match results for the loaded resume. Do the following:

1. Run the matcher and show top 20 results:
   ```bash
   uv run mcf match-jobs --top-k 20 --include-interacted
   ```

2. For each result show: rank, title, company, final score, and (if available) the recency factor contribution.

3. Diagnose the results:
   - Are the top results semantically relevant to the resume?
   - Are any very old jobs ranking unusually high (recency decay not working)?
   - Is Rocchio active? (Check if the user has liked/dismissed any jobs — if yes, a taste embedding should be influencing results.)
   - Is tier boost visible? (MNC/GOV roles ranked slightly higher than equivalent SME roles?)

4. Suggest one or two concrete tuning options if the results look off (e.g., adjust `RECENCY_DECAY`, `SEMANTIC_WEIGHT`, Rocchio α/β/γ).

Refer to `.claude/agents/matching-agent.md` for the full scoring pipeline before suggesting changes.
