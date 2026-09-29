"""Candidate policies, each a single registered change on top of a frozen baseline.

Nothing here modifies the frozen baselines: a candidate reuses their code by import, and its own
source identity (``miaosuan_agent.evaluation.identity``) covers the frozen sources plus its own
files, named individually.
"""
