# Scientific revision of Sprint 1

The previous executed notebook remains available in Git at commit
`ffeba64ab3fea83f163979760deb0b39ba77c419`, path `lab01_calculations.ipynb`,
blob `ea1112e8a9bd0b39de4de3d73788fc2ab503d27f`.
No historical commit is rewritten and no second large notebook copy is needed.

The builder writes `design/sprint1_calculations.ipynb`; the complete report
builder can append Sprint 2 without losing a reproducible Sprint 1 artifact.

This revision changes scientific code and interpretation following the user's
authorization on 2026-11-13. It is not presented as unchanged author calculations.
`ASE10.csv` remains unchanged; its hash and the changed/inserted cell IDs are
recorded by `research_revision_manifest.json`.

Changes include all repeated empirical modes (or no distinguished mode), exact
ECDFs, min–max labels, finite-data sampling conclusions, candidate distribution
parameters/AIC, iid qualifications of normality tests, all three channel pairs,
Location and hourly dependence diagnostics, and documented physical units.

The association target is an explicitly finite empirical joint distribution on
complete hours, not a claim of causal or predictive validity for future hours.
No new inferential p-values for time-series correlation are introduced.

Rebuild and execute with the same Python environment used for the report:

```
python design/research_revision.py --execute
python -m unittest design.research_tests -v
```

Execution requires access to the local Jupyter kernel. The builder uses the
current Python executable explicitly and preserves the immutable Git source.
The old `design/build_report.py` reconstructs the earlier presentation and must
not be used to overwrite this scientific revision.
