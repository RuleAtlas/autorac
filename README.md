# AutoRAC

AI-assisted RAC encoding infrastructure. Provides the feedback loop for automated statute encoding.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```python
from autorac import EncoderHarness, EncoderConfig
from pathlib import Path

config = EncoderConfig(
    rac_us_path=Path("../rac-us"),
    rac_path=Path("../rac"),
)

harness = EncoderHarness(config)
run, result = harness.encode_with_feedback(
    citation="26 USC 32(a)(1)",
    statute_text="...",
    output_path=Path("rac-us/statute/26/32/a/1.rac"),
)
```

## Eval suites and readiness gates

Use manifest-driven benchmark suites when you want an explicit readiness answer instead
of ad hoc spot checks.

```bash
autorac eval-suite benchmarks/uk_starter.yaml
autorac eval-suite benchmarks/uk_readiness.yaml
```

- `benchmarks/uk_starter.yaml` is the current runnable UK benchmark set.
- `benchmarks/uk_readiness.yaml` is the stricter go/no-go target for bulk UK work.

Each suite reports:
- success rate
- compile pass rate
- CI pass rate
- zero-ungrounded rate
- PolicyEngine pass rate on oracle-mappable cases
- mean estimated cost

The command exits `0` only when all readiness gates pass.

## Paper-ready model comparison

Use a fixed multi-runner manifest plus the report exporter when you want a
reproducible GPT-vs-Claude experiment you can cite in a paper.

```bash
autorac eval-suite benchmarks/uk_paper_head_to_head.yaml \
  --output /tmp/autorac-uk-paper-head-to-head \
  --json > /tmp/autorac-uk-paper-head-to-head/results.json

autorac eval-suite-report /tmp/autorac-uk-paper-head-to-head/results.json \
  --markdown-out /tmp/autorac-uk-paper-head-to-head/report.md \
  --csv-out /tmp/autorac-uk-paper-head-to-head/cases.csv
```

`benchmarks/uk_paper_head_to_head.yaml` freezes the case set and runner aliases,
while `eval-suite-report` emits:
- a Markdown summary table suitable for a paper appendix
- a case-level CSV for downstream analysis
- a JSON comparison object when run with `--json`
