"""The milestone-1 scoring, kept to compare with earlier evaluations; this verifier's own score is ``reward/``
(``aidlc/score``).

    rubric/         the offline adherence rubric as aidlc_v4_eval/legacy vendors it from aidlc_v4 (commit
                    4c3ee52c), with the v5 scorer edit of commit 60ddc546: ``facts.py`` adds
                    ``diff_test_files_modified`` (test files whose existing lines the patch changes or
                    removes) and ``score.py`` keys the hygiene penalty on it
    episode.py      rLLM Episode -> rubric Run (vendored byte-identical)
    compliance.py   the six compliance signals (order_v6, s1..s5) and their mean, with this verifier's
                    readings of test runs and stage bands (``reward/read.py``), as in aidlc_v4_eval/legacy

Nothing in ``reward/`` imports from here.
"""
