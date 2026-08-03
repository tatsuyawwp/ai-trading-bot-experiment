# I had an AI agent build 3 trading bots. It was losing to HFT before it even started.

I run a one-person AI company. A few weeks ago I pointed Claude Code — an AI coding agent — at a simple brief: build a paper-trading bot, watch it run, tell me honestly whether it works.

It built three: crypto, equities, and options, each against [Alpaca](https://alpaca.markets)'s paper trading API. Full code is in this repo.

This post is about what happened when I asked it the one question that actually mattered, and made it answer honestly instead of just shipping something that looked done.

## The bots got built. That part was never the hard part.

Within a few sessions there were three working bots: entry/exit logic, stop-losses and take-profits, a circuit breaker that halts everything after a cumulative paper loss, email alerts, isolated paper accounts per asset class so one bot's drawdown couldn't false-trigger another's, and a decision logger that records *every* evaluation cycle — not just fills — so nothing could hide in a gap between logs.

The agent also found and fixed its own bugs along the way. Early on, the crypto bot's price feed was silently broken: a missing parameter meant the API was returning a fixed window from midnight instead of the most recent bars, so the bot had been making live trading decisions off a BTC price frozen at exactly the same number for over an hour. Later, the options bot's stop-loss slipped from -30% to -42% on a real (paper) fill, which turned out to be poll-interval gap plus thin-spread slippage on a real illiquid contract, not a logic bug. These are the kind of bugs that are easy to miss and expensive to leave in — the kind you actually want an agent that never gets bored re-checking for.

None of that is the interesting part of this post. Building working trading infrastructure is a solved problem. The interesting part is what happened when I stopped asking "does it run" and started asking "does it win."

## The question that mattered: can this actually compete?

I asked the agent, bluntly: does a retail bot like this have any realistic edge, or is this just an elaborate way to lose money slowly?

It didn't have an opinion of its own worth trusting on this — so it went and checked. The honest numbers that came back:

- **Speed**: colocated HFT infrastructure sits 10,000–100,000x closer to the exchange than a REST API call from a home machine. Not a rounding error — a different sport.
- **Cost**: at $20/trade with 5-minute polling, realistic round-trip cost (taker fees + real spread, not the optimistic best-case number) runs 0.65–1.08% per crypto symbol. A technical-indicator strategy trying to scalp small moves on that timescale is fighting a cost structure that eats the edge before it exists.

The blunt verdict, once we ran the actual numbers instead of assuming: a retail agent trying to out-trade HFT on speed has zero chance, full stop. The viable move isn't "tune the parameters harder" — it's stop competing on a timescale where the fee structure and the speed gap both work against you, and move to a timescale where they don't.

## So we tested it properly — and it kept failing

Once the frame was "prove it, don't assume it," the actual work was a strategy going through a real gate: propose a hypothesis, backtest it against real historical data, only ever adopt something that clears a pre-agreed bar (profit factor > 1.2), and — critically — reject it if it doesn't, instead of quietly lowering the bar.

Five hypotheses went through that gate for the crypto bot alone:

1. **The strategy already running live** (price-deviation + momentum): 469 trades, 26.9% win rate, profit factor 0.36. A real, statistically real loser — not bad luck on a small sample.
2. **Bollinger Band breakout** (an attempt at something structurally different): 6,712 trades, profit factor 0.06. The exit band was so tight the strategy was closing on every normal pullback before ever reaching its own stop-loss or take-profit.
3. **Same entry, fixed stop-loss/take-profit instead of the band exit**: 339 trades, profit factor 0.36 again — same ceiling, worse win rate.
4. **A 4-hour EMA crossover trend strategy**, tested on 1 year / 4 symbols: profit factor 1.23. This *looked* like a pass. It wasn't — 2 outlier trades accounted for almost the entire profit. Extended to 4 years / 10 symbols per the same discipline that flagged the first result as too small to trust: profit factor 0.42. Decisive rejection, and a good reminder that a strategy passing on a small sample is usually a coincidence wearing a lab coat.
5. **A liquidation-cascade mean-reversion catcher**: profit factor 0.68. An early version looked much better (1.36–1.44) until a more conservative cost assumption on some added symbols collapsed it — the "good" number turned out to be an unverified-cost artifact, not real edge.

Somewhere in there, the backtest tooling itself turned out to have a real bug: Alpaca's historical crypto data has genuine multi-hundred-day gaps for some symbols, and the lookup logic didn't detect them — it silently used a stale pre-gap price as "current," which manufactured one fake +672% trade that briefly made an early run look like it had a profit factor of 3.51. Found, fixed, re-verified. The whole point of building the gate was that it had to be trustworthy enough to actually kill bad ideas instead of just rubber-stamping whatever came out of the last backtest run.

## The sixth one passed

**Cross-sectional momentum rotation** — rank the watchlist by 7-day return, hold only whichever one is #1, rotate daily — cleared the bar: profit factor 1.55 on 116 trades, no small-sample red flags, and every individual trade traced back to a real, explainable market event (BTC's 2023 recovery, ETH's 2024–25 run, DOGE's 2024 spike) rather than a lucky fluke.

It's live now, on the real (paper) account, holding at most one position at a time. Rolling it out wasn't clean, either — minutes after the new code was saved, the unattended 5-minute scheduler ran it before a code review caught a bug where a still-forming daily candle got treated as a closed one, producing one real (paper) trade on partial data. Caught, fixed, re-verified, redeployed. The fix for *that* was procedural, not just technical: disable the scheduled task before editing a live bot's code, not after you find out it did something during the edit.

## What I actually take away from this

An AI agent turned out to be genuinely good at the parts of this that reward being tireless and honest: building real risk controls, catching its own stale-data and off-by-one bugs, running five backtests back to back without getting attached to any of them, and rejecting its own best-looking result when a bigger sample said otherwise.

It was not, on its own, a source of alpha. Nothing here found an edge because the agent was clever — it found one (maybe) because the process refused to accept "looks promising" as good enough, five times in a row, before something finally survived a harder test.

Code, real numbers (including the losing ones), and the honest per-bot writeups are in this repo. Paper money only — nothing in this post or the repo is a recommendation to trade anything.
