# AI-Agent-Built Trading Bot Experiment

> ## ⚠️ Disclaimer — read this before anything else
>
> - **This is not financial advice.** Nothing in this repository, its code,
>   comments, or documentation is a recommendation to buy, sell, or hold any
>   security, cryptocurrency, or derivative.
> - **This is an educational / research project**, published to document how
>   an AI coding agent designed, built, and iterated on a set of trading bots
>   — including its mistakes.
> - **Paper trading only.** Every bot here trades against Alpaca's simulated
>   ("paper") accounts with fake money. None of this code has ever placed a
>   real order with real capital, and none of the results below reflect real
>   money.
> - **There is no track record of profitability.** Sample sizes are tiny
>   (single digits to low double digits of closed trades per bot) and the
>   logged periods are short (days, not months). Nothing here has been shown
>   to work.
> - **The equities bot's original strategy tested with negative expectancy.**
>   Over its first logged period it lost more on losing trades than it made
>   on winning trades (expectancy: -0.46% per trade, profit factor: 0.02,
>   4 closed trades). See
>   [`trading-bot-equities/README.md`](trading-bot-equities/README.md) for
>   the honest numbers and what was changed in response. This repo keeps
>   that result visible on purpose instead of hiding it.
> - If you run this code with your own Alpaca keys, run it against a paper
>   account, understand every line of it first, and take full responsibility
>   for anything you do with it. The author(s) and contributors accept no
>   liability for any use of this code, paper or live.

## What this is

Three small, independent paper-trading bots, each built and iterated on by
an AI coding agent (Claude) against the [Alpaca](https://alpaca.markets)
paper trading API:

| Bot | Market | Strategy |
|---|---|---|
| [`trading-bot`](trading-bot/) | Crypto (BTC/ETH/DOGE/SOL) | Momentum/deviation |
| [`trading-bot-equities`](trading-bot-equities/) | Equities/ETFs | Mean-reversion (long) + momentum (short, dormant by default) |
| [`trading-bot-options`](trading-bot-options/) | Options (buy-only calls/puts) | 4-hour deviation signal, ATM contract, 30-45 DTE |

Each bot is a standalone Python project with its own `.env.example`,
`requirements.txt`, and README. They share the same basic shape: a thin
Alpaca client wrapper, a strategy module, a `run.py` entry point meant to be
invoked on a schedule (cron / Task Scheduler / etc.), a decision logger that
records *every* evaluation (not just fills) to `logs/trades.jsonl`, and a
read-only `report.py` for after-the-fact analysis (win rate, expectancy,
profit factor, MFE/MAE, equity drawdown).

`logs/` directories and `.env` files are intentionally not included in this
repository — they would contain your own paper-account trade history and
credentials once you run the bots yourself.

## Why this exists

This is a public writeup of a real experiment: can an AI agent design a
trading strategy, implement it, catch its own bugs, and honestly report the
result — including when the result is "this doesn't work yet"? The per-bot
READMEs document specific real bugs (a stale-data bug that fed fake bars to
the crypto bot, a stop-loss slippage bug in the options bot) alongside the
fixes, because those are as much the point of this project as the strategies
themselves.

## Posts

- [I had an AI agent build 3 trading bots. It was losing to HFT before it even started.](posts/01-hft-losing-before-we-started.md) ([also on dev.to](https://dev.to/tatsuyawwp/i-had-an-ai-agent-build-3-trading-bots-it-was-losing-to-hft-before-it-even-started-1kia))

## Getting started

Each bot folder has its own setup instructions. In short, for any of them:

```bash
cd trading-bot            # or trading-bot-equities / trading-bot-options
cp .env.example .env      # fill in your own Alpaca PAPER trading keys
pip install -r requirements.txt
python run.py
```

Get free paper trading API keys at https://app.alpaca.markets — no KYC
required to start paper trading. **Never put live-trading keys in `.env`**
while working through this code.

## License

MIT — see [LICENSE](LICENSE).
