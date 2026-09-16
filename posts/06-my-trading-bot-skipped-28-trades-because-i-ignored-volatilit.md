---
title: My Trading Bot Skipped 28 Trades Because I Ignored Volatility on a Tiny Real-Money Budget
published: true
tags: trading, python, ai
canonical_url: https://github.com/tatsuyawwp/ai-trading-bot-experiment/blob/master/posts/06-my-trading-bot-skipped-28-trades-because-i-ignored-volatilit.md
devto_url: https://dev.to/tatsuyawwp/my-trading-bot-skipped-28-trades-because-i-ignored-volatility-on-a-tiny-real-money-budget-4mmd
devto_id: 4662834
---

I built a custom monitoring script, `daily_check.py`, to watch my bots while I slept. I wanted to see if they were actually following the rules I set or if they were just hallucinating success in the logs.

The script didn't find a catastrophic market crash. Instead, it found that my equities bot was paralyzed. In a single session, it had skipped 28 trades due to "budget constraints" while only successfully filling 8. It was sitting on its hands for 77% of its opportunities.

Full code for the monitoring setup and the bots is here: [github.com/tatsuyawwp/ai-trading-bot-experiment](https://github.com/tatsuyawwp/ai-trading-bot-experiment).

This post is about why a "perfectly working" bot can fail because of a tiny real-money budget and a lack of respect for volatility.

## The bug wasn't in the code, it was in the math

On paper, the logic was fine. The bot monitored four symbols: SPY, QQQ, TSLA, and NVDA. I had set a `PER_TRADE_NOTIONAL` of $20 and a `MAX_TOTAL_NOTIONAL` of $40. In my head, this meant the bot would always have two positions open.

The `daily_check.py` report showed the reality: the bot was trying to enter all four symbols at once because they are highly correlated. When SPY and QQQ signaled a buy, the $40 budget was gone. TSLA and NVDA - the high-volatility movers where the actual "alpha" usually lives - were getting skipped 28 times over because they were third or fourth in the execution queue.

I asked Gemini to review the design. It flagged three structural flaws I'd ignored:
1. **Correlation**: SPY, QQQ, TSLA, and NVDA move together. A "diversified" watchlist of four tech-heavy symbols is actually just one big trade split four ways.
2. **Risk Imbalance**: A $20 position in SPY (low volatility) has a completely different risk profile than a $20 position in NVDA (high volatility). Treating them as equal "slots" was mathematically lazy.
3. **The T+1 Trap**: In a real-money environment, selling a stock today doesn't give you the cash back instantly. By maxing out the budget every day, I was ensuring the bot would be unable to trade the following day while waiting for settlement.

## The Small-Budget Reality Check

The most embarrassing part of the audit came when I checked my actual liquidity. I had been building the bots assuming a $100 test budget on paper. When I sat down to actually think about funding a real account for this specific experiment, I realized I only wanted to commit a much smaller amount to it than that - nowhere near what the paper-trading logic had assumed.

That gap between the number the code was designed around and the number I actually wanted to risk was the real bug. Every position-sizing assumption downstream of it was wrong by the same proportion.

I had to rewrite the entire sizing logic to fit into a much smaller shoebox. We moved from flat per-symbol amounts to volatility-proportional sizing:
* **ETFs (SPY/QQQ)**: a smaller per-trade slice
* **Individual stocks (TSLA/NVDA)**: an even smaller per-trade slice, since they carry more volatility per dollar
* **A total cap with a real buffer set aside for fees and settlement gaps**

This wasn't about being "clever" with the AI; it was about the AI forcing me to be honest about the numbers before I lost real money to a settlement error.

## Automating the "Check," not the "Act"

While fixing the budget, the `daily_check.py` script caught another real bug. The crypto momentum bot's liquidation logic wasn't passing the `unrealized_plpc` (unrealized profit/loss percentage) value to the logger.

This caused `report.py` to attempt a `None + float` calculation, crashing the entire reporting suite. It was a simple fix, but it reinforced a hard rule I've adopted: **The "Check" phase is automated, but the "Act" phase is not.**

I had briefly considered letting the AI agent automatically deploy code fixes when it found bugs like the logger crash. I decided against it. An earlier session taught me that unattended code edits while a 5-minute scheduler is running is a recipe for broken state. Now, I have a "security gate" in `security_gate.py` and a manual review step.

If I want to change the code, I manually disable the Windows Task Scheduler, run the fix, verify it with `python-reviewer`, and then re-enable the task. It's slower, but it's the only way to ensure a small real-money account doesn't become a $0 account because of a typo in a docstring.

## Lessons from the logs

The AI agent is excellent at finding these "silent" failures - the skipped trades, the correlated risks, and the math errors that humans ignore because the "Live" light is green.

- **Infrastructure matters more than "Alpha"**: Most of my time is spent fixing `NoneType` errors in reports and working out currency-conversion buffers, not tuning RSI parameters.
- **The Budget is a Constraint, not a Suggestion**: If you ignore your budget in your logic, the exchange will enforce it for you by killing your best trades.
- **MCP is a distraction**: I looked into connecting Claude to financial data via MCP (Model Context Protocol), but realized it was useless for a headless bot. The bot needs a REST API in Python, not a chat tool. We skipped it.

The bots are back online with the smaller, real-money-sized constraints and the volatility-adjusted sizing. They are currently watching the markets, and more importantly, the `daily_check.py` script is watching them.

Full logs, the budget recalculations, and the updated `run.py` logic are available here: [github.com/tatsuyawwp/ai-trading-bot-experiment](https://github.com/tatsuyawwp/ai-trading-bot-experiment)

