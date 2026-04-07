FUTURE IMPROVEMENTS
===================

[ ] Revisit the 300-word description truncation in job embeddings
    File: src/mcf/lib/embeddings/job_text.py
    Lines: build_job_text_from_normalized() and build_job_text_from_dict()
    Context: BGE-base-en-v1.5 has a 512-token hard limit. The prefix lines
    (Job Title, Required Skills, Seniority, Role Type) consume ~40-60 tokens,
    leaving ~450 tokens for the description. 300 words ≈ 390 tokens, so there
    is ~60 tokens of headroom — could push to ~350 words safely.
    Also consider: does more description text actually help? The most signal-dense
    content is usually in the first 150-200 words (responsibilities, requirements).
    The tail is often boilerplate. Now that clean_description() strips boilerplate,
    the first 300 words are already denser than before. Measure before changing.
