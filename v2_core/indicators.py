"""Indicators with the research definitions (37a14c0 engine.mjs): Wilder RSI, running-sum SMA200, SHD.

These are not the 260-row ewm RSI of the interim candidate. They follow the research engine so the
same pre-history fixture gives the same values.
"""


def rsi_wilder(values, n=14):
    out = [None] * len(values)
    g = 0.0
    l = 0.0
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        up = max(0.0, delta)
        dn = max(0.0, -delta)
        if i <= n:
            g += up / n
            l += dn / n
        else:
            g = (g * (n - 1) + up) / n
            l = (l * (n - 1) + dn) / n
        if i >= n:
            if g == 0 and l == 0:
                out[i] = 50.0
            elif l == 0:
                out[i] = 100.0
            else:
                out[i] = 100 - 100 / (1 + g / l)
    return out


def sma_running(values, window=200):
    out = [None] * len(values)
    total = 0.0
    for i, x in enumerate(values):
        total += x
        if i >= window:
            total -= values[i - window]
        if i >= window - 1:
            out[i] = total / window
    return out


def shd_by_date(dates, spy, ief, market_dates, lookback=20):
    """SHD = 100 * (SPY 20-session change - IEF 20-session change).

    'common' sessions are the SOXX dates that also have a row in the market table (as in the research
    engine). A blank SPY/IEF value is treated as missing (None), not as 0.
    """
    common = [d for d in dates if d in market_dates]
    result = {}
    for i, d in enumerate(common):
        if i < lookback:
            result[d] = None
            continue
        base = common[i - lookback]
        s_now, s_base = spy.get(d), spy.get(base)
        i_now, i_base = ief.get(d), ief.get(base)
        if None in (s_now, s_base, i_now, i_base):
            result[d] = None
        else:
            result[d] = 100 * (s_now / s_base - i_now / i_base)
    return result
