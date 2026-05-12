"""Domain plugins for ReviewStem.

A domain is a (skill catalog, fitness function, benchmark suite) triple that
plugs into the existing stem-cell pipeline. The default `code_review` domain
lives in the top-level `reviewstem/` package; alternative domains live here.

Adding a new domain proves the pipeline generalizes: the brief asks "for a
different class of tasks, you'd start a new stem agent," and this directory
is where those alternatives land.
"""
