# Experiment Summary

## execution_enabled

| Scenario | Hit Rate | Delta vs Baseline | Cost | Delta Cost | Cache Hit Tokens | Cache Miss Tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| execution_enabled / Baseline | 88.30% +/- 1.90% | +0.00% | $0.0190 +/- $0.0015 | $+0.0000 | 55,501 | 7,359 |
| execution_enabled / 2. Dynamic Tool Add/Remove | 75.29% +/- 2.94% | -13.01% | $0.0266 +/- $0.0016 | $+0.0077 | 47,488 | 15,585 |
| execution_enabled / 3. Unstable Tool Order | 77.96% +/- 2.89% | -10.34% | $0.0255 +/- $0.0016 | $+0.0065 | 49,587 | 14,011 |
| execution_enabled / 5. Non-Deterministic Serialization | 11.14% +/- 3.11% | -77.16% | $0.0636 +/- $0.0016 | $+0.0446 | 7,091 | 56,502 |

Key takeaway: **execution_enabled / 5. Non-Deterministic Serialization** shows the largest drop in this track.

## schema_only

| Scenario | Hit Rate | Delta vs Baseline | Cost | Delta Cost | Cache Hit Tokens | Cache Miss Tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| schema_only / Baseline | 95.59% +/- 1.56% | +0.00% | $0.0060 +/- $0.0016 | $+0.0000 | 4,864 | 204 |
| schema_only / 1. Timestamp in Static Section | 93.75% +/- 1.27% | -1.83% | $0.0055 +/- $0.0017 | $-0.0005 | 4,467 | 281 |
| schema_only / 4. Modify Message History | 19.21% +/- 2.92% | -76.38% | $0.0091 +/- $0.0019 | $+0.0031 | 960 | 4,147 |
| schema_only / 6. Model Switch Mid-Session | 76.65% +/- 11.63% | -18.93% | $0.0075 +/- $0.0021 | $+0.0015 | 3,635 | 1,122 |

Key takeaway: **schema_only / 4. Modify Message History** shows the largest drop in this track.

## Tool Observability

### execution_enabled / Baseline

- Tool executions: 5.00
- Tool success rate: 100.00%
- Max-round terminations: 0.00
- Pending tool calls after loop: 0.00
- Executed tools: `read_file` 5.00
- Error codes: none

### execution_enabled / 2. Dynamic Tool Add/Remove

- Tool executions: 5.00
- Tool success rate: 100.00%
- Max-round terminations: 0.00
- Pending tool calls after loop: 0.00
- Executed tools: `read_file` 5.00
- Error codes: none

### execution_enabled / 3. Unstable Tool Order

- Tool executions: 5.00
- Tool success rate: 100.00%
- Max-round terminations: 0.00
- Pending tool calls after loop: 0.00
- Executed tools: `read_file` 5.00
- Error codes: none

### execution_enabled / 5. Non-Deterministic Serialization

- Tool executions: 5.00
- Tool success rate: 100.00%
- Max-round terminations: 0.00
- Pending tool calls after loop: 0.00
- Executed tools: `read_file` 5.00
- Error codes: none

