# Contributing

```
git clone https://github.com/TahaKocpinar/hollowstar
cd hollowstar
python -m unittest discover -s tests -t . -v
```

No dependencies beyond the standard library, and it should stay that way. Tests never hit the network; `tests/helpers.py` builds fake API responses.

Most useful contributions:

- **A repo it got wrong.** Open a "wrong verdict" issue with the repo name, the score, and why you think it is wrong. Earned repos flagged as inflated matter most, because the output may end up in front of the author.
- **A new signal.** Add it to `evaluate()` in `hollowstar/signals.py`. It must return a severity between 0 and 1 and a sentence a person can check against public data. Add a test with a case that fires and one that must not.
- **A new campaign pattern for `sweep`.** Same rule: show the evidence, not just a label.

Please do not open issues or PRs that name a repo as fake without the numbers that support it.
