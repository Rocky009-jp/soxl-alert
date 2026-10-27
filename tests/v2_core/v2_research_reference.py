"""TEST-SIDE port of the research signals() (37a14c0 engine.mjs), used only as an independent reference.

It keeps the research behaviour on purpose (initialArmed=true, a missing F&G resets the streak and leaves
armed unchanged). It is NOT the product state machine and is not imported by v2_core.
"""


def research_signals(rows, delay=0, initial_armed=True):
    armed, streak, prev_normal = initial_armed, 0, False
    out = []
    for i, r in enumerate(rows):
        f = rows[i - delay]["fg"] if i >= delay else None
        ex = False
        if f is None:
            streak = 0
        else:
            streak = streak + 1 if f >= 30 else 0
            if streak >= 3:
                armed = True
            if f < 25 and armed:
                ex = True
                armed = False
        normal_raw = (f is not None and 25 <= f < 30 and r["soxx"] > r["sma"] and r["rsi"] is not None
                      and r["rsi"] <= 55 and r["shd"] is not None and r["shd"] < 0)
        normal = normal_raw and not prev_normal and armed and not ex
        re_candidate = (f is not None and f >= 30 and r["sma"] is not None and r["soxx"] > r["sma"] and i > 0
                        and rows[i - 1]["rsi"] is not None and rows[i - 1]["rsi"] <= 55
                        and r["rsi"] is not None and r["rsi"] > 55)
        prev_normal = normal_raw
        out.append({"date": r["date"], "fg_used": f, "armed": armed, "streak": streak, "ex": ex,
                    "normal": bool(normal), "normal_raw": bool(normal_raw), "reCandidate": bool(re_candidate)})
    return out
