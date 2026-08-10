---
title: Trading the Gap: How We Built a 91% Win-Rate Basis Bot After a 217% Buy-and-Hold Reality Check
published: true
tags: python
canonical_url: https://github.com/tatsuyawwp/ai-trading-bot-experiment/blob/master/posts/02-trading-the-gap-how-we-built-a-91-win-rate-basis-bot-after-a.md
devto_url: https://dev.to/tatsuyawwp/trading-the-gap-how-we-built-a-91-win-rate-basis-bot-after-a-217-buy-and-hold-reality-check-1idl
devto_id: 4355694
---

After months of letting the agent build technical indicator bots, we finally asked it to run the simplest test possible: what if we just bought BTC/JPY eight years ago and did absolutely nothing?

The result was a +217.1% return. Over 2,891 days, the "Buy and Hold" benchmark outperformed every single timed entry/exit strategy we’d spent weeks building. The closest runner-up (C5) only managed a fraction of that gain (~7.9M JPY vs the benchmark's ~21.7M JPY). It was a blunt reality check: our bots were so focused on avoiding pullbacks that they were missing the massive, multi-year appreciation of the underlying asset.

The flip side, of course, was the pain. The buy-and-hold strategy suffered a maximum drawdown of 54.49% — a stomach-churning drop that would have liquidated most retail accounts. Our bots, meanwhile, kept drawdowns in the 13–17% range. This reframed the entire experiment. The goal wasn't just to "beat" the market; it was to find a way to capture that upside without the 50% wipeout risk.

## Trying to build a "Free Lunch" via Portfolio Blending

The agent's next move was to stop looking for one perfect bot and start looking for a portfolio. We tested three different blends:

- **The 6-leg blend** (Buy-and-hold + C3 through C7): This produced a +65.4% return with a 22.7% drawdown. 
- **The 3-leg blend** (Buy-and-hold + the two "survivor" bots, C3 and C7): This hit a +99.5% return, but the drawdown spiked to 31.8%.
- **The 5-leg "Optimized" blend**: By removing a known-loser (C4), the return jumped to +84.8%, but the drawdown actually *rose* to 23.6%. 

We found a counterintuitive reality: even the losing bot (C4) was providing diversification because its failures didn't correlate with the others. Removing it made the equity curve "cleaner" but more fragile. It was a reminder that in a portfolio, "bad" strategies can sometimes act as insurance for "good" ones.

## The 91% Win-Rate Basis Trade

When I told the agent that even doubling the money felt "too low" for the complexity of automated trading, it suggested something structurally different: a market-neutral basis-fade. This involves betting on the price gap between GMO’s BTC_JPY leverage product and its BTC spot product.

The results looked like a different sport:
- **Win Rate**: 91.3% (63 wins, 6 losses).
- **Max Drawdown**: 0.39%. 
- **Profit Factor**: 45.06.

But even here, the agent found real problems. First, it caught its own "phantom loss" bug: it was double-counting the entry cost of the spot leg, which initially made a high-win-rate strategy look like it was losing 33% instantly. Then it found a "silent zero" bug where financing fees weren't being attributed to trades at all.

Most importantly, the agent pointed out a structural decay: the strategy's trade frequency dropped from 55 trades in the first four years to just 14 in the most recent four. The "edge" wasn't a constant; it was a symptom of early-market volatility that is slowly being squeezed out as the market matures.

## The Grave of Rejected Hypotheses (C8 and C9)

We didn't stop at the winners. We put classic Japanese technical analysis through the same "gate" (Profit Factor > 1.2):

- **C8 (Ichimoku Strategy)**: Classic triple-confirmation cloud trading. It failed the gate with a PF of 1.19. Interestingly, its buy-side was profitable (PF 1.33) while its sell-side was a loser (PF 1.03), providing our third independent confirmation of a structural long-side bias in crypto.
- **C9 (RCI Multi-Timeframe)**: A total failure with a PF of 0.78. The agent traced the failure not to a logic bug, but to the circuit breaker tripping early during high-volatility periods, effectively "truncating" its own recovery.

We also tested timeframe shifts. Day trading (30-minute bars) was a decisive loser (PF 0.65). Weekly trading (1-day bars) had an incredible PF of 2.74, but it only generated 17 trades in 8 years. Mathematically, it’s a strategy you can’t trust because you’ll be dead before you have a statistically significant sample size.

## What we learned about the Agent

The agent has now built and backtested nine distinct candidates. Only two (C3 and C7) have survived every stress test we’ve thrown at them. 

The takeaway isn't that the AI is a "genius" trader. It’s that the AI is a world-class skeptic. It was happy to build a 91% win-rate bot, but it was just as happy to find the math error that made that win rate look better than it was. It didn't get "attached" to the Ichimoku strategy just because the code was elegant; it rejected it the moment the Profit Factor hit 1.19.

We are currently left with a choice: take the high-yield/high-pain path of the benchmark, or the slow, managed grind of the portfolio blends. 

The code, the full backtest engine, and the logs of every rejected strategy are public here: [github.com/tatsuyawwp/ai-trading-bot-experiment](https://github.com/tatsuyawwp/ai-trading-bot-experiment). This remains a paper-trading experiment—no real money was used, and nothing here is financial advice.
