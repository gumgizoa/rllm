"""The milestone-1 scoring of aidlc_v4, kept to compare with earlier evaluations; this verifier's own score
is ``reward/`` (``aidlc/score``).

    rubric/         the offline adherence rubric, vendored byte-identical from aidlc_v4 (commit 4c3ee52c)
    episode.py      rLLM Episode -> rubric Run (vendored byte-identical)
    compliance.py   the six compliance signals (order_v6, s1..s5) and their mean, with this verifier's
                    readings of test runs and stage bands (``reward/read.py``)

Nothing in ``reward/`` imports from here.
"""
