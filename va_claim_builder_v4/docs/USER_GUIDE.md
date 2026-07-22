# VA Claim Builder 4.0 Stable — User Guide

## AI setup

The application does not sign in to the consumer ChatGPT or Grok websites. Cloud analysis uses API credentials:

- `OPENAI_API_KEY` for OpenAI models
- `XAI_API_KEY` for Grok models

Consumer subscriptions and API billing are separate. Copy `.env.example` to `.env`, paste the keys, choose **Parallel multi-agent consensus**, and select both providers.

## How ensemble analysis works

1. The same redacted, page-labeled evidence packet is sent independently to each selected provider.
2. Calls run concurrently.
3. Findings are matched by proposition, claim element, polarity, filename, and page.
4. Findings agreed upon by multiple independent agents are marked corroborated or consensus.
5. One-agent findings remain in manual review.
6. An optional adjudicator reviews only disputed structured findings and source quotations.
7. No AI finding enters final drafting until approved by the user.

More agents do not automatically mean a stronger claim. Source evidence controls. The ensemble is intended to reduce omissions and expose disagreement, not manufacture support.
