"""Free interactive finance calculators: link magnets for people and quotable explainers for AI."""

from __future__ import annotations

from typing import Any

# Each tool: inputs (id, label, default, step, hint), a JS body that reads `v` (input values as
# numbers) and returns {rows: [[label, value], ...], note?: str, error?: str}, plus explainer copy.
TOOLS: list[dict[str, Any]] = [
    {
        "slug": "compound-interest-calculator",
        "match": ["compound", "invest", "saving", "wealth"],
        "title": "Compound Interest Calculator",
        "summary": "See how a lump sum plus monthly contributions grows with compound interest over time.",
        "inputs": [
            ("initial", "Starting amount", 1000, 100, ""),
            ("monthly", "Monthly contribution", 200, 10, ""),
            ("rate", "Expected annual return (%)", 6, 0.1, "Long-run averages are not guaranteed."),
            ("years", "Years", 20, 1, ""),
        ],
        "js": """
const i = v.rate / 100 / 12, m = Math.round(v.years * 12);
const grow = i === 0 ? v.initial + v.monthly * m
  : v.initial * Math.pow(1 + i, m) + v.monthly * (Math.pow(1 + i, m) - 1) / i;
const paid = v.initial + v.monthly * m;
const rows = [["Final balance", fmt(grow)], ["Total you put in", fmt(paid)], ["Growth from compounding", fmt(grow - paid)]];
const milestones = [5, 10, 20, 30].filter(y => y < v.years);
for (const y of milestones) {
  const k = y * 12;
  const b = i === 0 ? v.initial + v.monthly * k : v.initial * Math.pow(1 + i, k) + v.monthly * (Math.pow(1 + i, k) - 1) / i;
  rows.push([`Balance after ${y} years`, fmt(b)]);
}
return {rows};""",
        "explain": [
            ("What is compound interest?", "Compound interest means you earn returns on your original money and on the returns it has already earned. Over long periods this snowball effect usually matters more than the exact return rate, which is why starting early helps."),
            ("How this calculator works", "It assumes your contribution is added at the end of every month and returns compound monthly at a steady rate. Real investments rise and fall, so treat the result as an illustration, not a forecast."),
        ],
        "faq": [
            ("How much does starting 10 years earlier change the result?", "Usually a lot: money invested earlier has more years to compound. Try changing only the 'Years' field to see the difference for your own numbers."),
            ("What return rate should I use?", "Use a conservative figure and test a range (for example 3%, 5% and 7%). Past market returns do not guarantee future ones, and fees and inflation reduce real growth."),
        ],
    },
    {
        "slug": "etf-dca-calculator",
        "match": ["etf", "index", "dca", "invest", "dividend"],
        "title": "ETF Dollar-Cost Averaging (DCA) & Fee Calculator",
        "summary": "Estimate what regular monthly ETF or index-fund investing could grow to, and how much fees cost you.",
        "inputs": [
            ("monthly", "Monthly investment", 300, 10, ""),
            ("years", "Years", 25, 1, ""),
            ("rate", "Expected annual return before fees (%)", 6, 0.1, ""),
            ("fee", "Annual fund fee / expense ratio (%)", 0.2, 0.01, "Compare a low-cost index ETF with a high-fee fund."),
        ],
        "js": """
const m = Math.round(v.years * 12);
const fv = r => { const i = r / 100 / 12; return i === 0 ? v.monthly * m : v.monthly * (Math.pow(1 + i, m) - 1) / i; };
const gross = fv(v.rate), net = fv(v.rate - v.fee), paid = v.monthly * m;
return {rows: [["Value after fees", fmt(net)], ["Total invested", fmt(paid)], ["Value if there were no fees", fmt(gross)],
               ["Lifetime cost of the fee", fmt(gross - net)]],
        note: "A difference of 1% a year in fees can add up to a large share of your final balance over decades."};""",
        "explain": [
            ("What is dollar-cost averaging?", "Dollar-cost averaging (DCA) means investing the same amount on a regular schedule, regardless of price. You buy more units when prices are low and fewer when they are high, and you avoid trying to time the market."),
            ("Why fees matter so much", "An ETF's expense ratio is charged every year on your whole balance, so its cost compounds just like returns do. Low-cost broad index ETFs are popular for this reason, but always compare the fund's total costs, tracking and platform fees yourself."),
        ],
        "faq": [
            ("Is DCA better than investing a lump sum?", "Historically a lump sum has often done better simply because money is invested sooner, but DCA reduces the risk of investing everything right before a fall and suits people investing from their monthly income."),
            ("Does this include taxes and platform fees?", "No. Add your broker or platform fee to the expense ratio field for a rough all-in estimate, and check the tax rules in your country."),
        ],
    },
    {
        "slug": "debt-payoff-calculator",
        "match": ["debt", "credit", "loan"],
        "title": "Debt Payoff Calculator",
        "summary": "Find out how long it takes to clear a credit card or loan, and how much interest you'll pay.",
        "inputs": [
            ("balance", "Current balance", 5000, 100, ""),
            ("apr", "Interest rate (APR %)", 18, 0.1, ""),
            ("payment", "Monthly payment", 200, 10, ""),
        ],
        "js": """
const i = v.apr / 100 / 12;
if (v.payment <= v.balance * i) return {error: "Your payment doesn't cover the monthly interest, so the balance would never go down. Increase the payment."};
let bal = v.balance, months = 0, interest = 0;
while (bal > 0 && months < 1200) { const c = bal * i; interest += c; bal = bal + c - v.payment; months++; }
const extra = v.payment * 1.25;
let b2 = v.balance, m2 = 0, int2 = 0;
while (b2 > 0 && m2 < 1200) { const c = b2 * i; int2 += c; b2 = b2 + c - extra; m2++; }
return {rows: [["Time to pay off", dur(months)], ["Total interest paid", fmt(interest)],
               ["Total paid", fmt(v.balance + interest)],
               [`If you paid ${fmt(extra)} a month instead`, `${dur(m2)}, interest ${fmt(int2)}`]]};""",
        "explain": [
            ("How debt interest works", "Each month interest is added to what you owe, and your payment covers that interest first. Only the part above the interest reduces the balance, which is why small payments on high-rate debt take so long to clear."),
            ("Avalanche vs snowball", "The avalanche method pays extra on the highest-rate debt first and usually costs the least interest. The snowball method clears the smallest balance first for quick wins. Both work if you stick with them."),
        ],
        "faq": [
            ("Should I invest or pay off debt first?", "High-interest debt such as credit cards is usually expensive enough that paying it down first is hard to beat, but keep a small emergency buffer so you don't borrow again."),
            ("Is this exact?", "It's an estimate that assumes a fixed rate and payment with no new spending or fees. Your lender's statement is the authority."),
        ],
    },
    {
        "slug": "emergency-fund-calculator",
        "match": ["emergency", "saving", "budget", "bank"],
        "title": "Emergency Fund Calculator",
        "summary": "Work out how big your emergency fund should be and how long it will take to build.",
        "inputs": [
            ("expenses", "Essential monthly expenses", 2000, 50, "Rent, food, bills, transport, minimum debt payments."),
            ("months", "Months of cover you want", 6, 1, "3–6 is a common rule of thumb; more if income is irregular."),
            ("saved", "Already saved", 1000, 50, ""),
            ("monthly", "Amount you can save per month", 300, 10, ""),
        ],
        "js": """
const target = v.expenses * v.months, gap = Math.max(0, target - v.saved);
const rows = [["Emergency fund target", fmt(target)], ["Still needed", fmt(gap)]];
if (gap === 0) rows.push(["Status", "You've reached your target 🎉"]);
else if (v.monthly <= 0) rows.push(["Time to reach target", "Add a monthly saving amount"]);
else { const m = Math.ceil(gap / v.monthly); rows.push(["Time to reach target", dur(m)]); }
rows.push(["Current cover", `${(v.saved / v.expenses).toFixed(1)} months of expenses`]);
return {rows};""",
        "explain": [
            ("What an emergency fund is for", "An emergency fund is cash set aside for real surprises: job loss, medical bills, urgent repairs. It stops a bad month from turning into high-interest debt."),
            ("Where to keep it", "Keep it somewhere safe and easy to reach, such as a separate savings account, rather than invested in assets whose value can fall when you need the money."),
        ],
        "faq": [
            ("Is 3 or 6 months better?", "Three months may be enough with a stable job and no dependants; six or more is safer with irregular income, a single income household or dependants."),
            ("Should I invest before my emergency fund is full?", "Many people build at least a starter fund first so that an emergency doesn't force them to sell investments at a bad time."),
        ],
    },
    {
        "slug": "fire-calculator",
        "match": ["retire", "fire", "independence", "wealth", "invest"],
        "title": "FIRE Calculator (Financial Independence)",
        "summary": "Estimate your financial-independence number and how many years it could take to reach it.",
        "inputs": [
            ("spend", "Annual spending in retirement", 30000, 500, ""),
            ("swr", "Withdrawal rate (%)", 4, 0.1, "The '4% rule' is a rule of thumb from historical US data, not a guarantee."),
            ("invested", "Currently invested", 20000, 500, ""),
            ("save", "Amount you invest per year", 12000, 500, ""),
            ("rate", "Expected real return after inflation (%)", 5, 0.1, ""),
        ],
        "js": """
const target = v.spend / (v.swr / 100), r = v.rate / 100;
let bal = v.invested, years = 0;
while (bal < target && years < 100) { bal = bal * (1 + r) + v.save; years++; }
return {rows: [["Your FIRE number", fmt(target)], ["Years to reach it", years >= 100 ? "100+ years" : plural(years, "year")],
               ["Projected balance then", fmt(bal)]],
        note: "Lower withdrawal rates (3–3.5%) are more conservative for early retirement or long horizons."};""",
        "explain": [
            ("What is the FIRE number?", "Your FIRE (Financial Independence, Retire Early) number is the invested amount whose yearly withdrawals could cover your spending. With a 4% withdrawal rate it equals 25 times your annual spending."),
            ("The biggest lever", "Your savings rate usually matters more than your return: spending less both raises what you can invest and lowers the target you need to reach."),
        ],
        "faq": [
            ("Is the 4% rule safe?", "It comes from studies of past US market returns over roughly 30-year retirements. Longer retirements, different markets or high fees may need a lower rate; treat it as a starting point."),
            ("Should I use real or nominal returns?", "Use a 'real' return (after inflation) so the result is in today's money."),
        ],
    },
]
