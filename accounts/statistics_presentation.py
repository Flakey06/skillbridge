"""Server-rendered member charts and filters."""
from collections import Counter
from datetime import date
from math import ceil


COLOURS = ("#3fb4c5", "#7357c8", "#70b98b", "#e28a42", "#ce6681", "#4e8ed0")


def member_charts(records, params):
    role = params.get("stat_role", "all")
    if role not in {"candidate", "recruiter", "all"}:
        role = "all"
    def valid_date(value):
        try:
            return date.fromisoformat(value).isoformat()
        except (ValueError, TypeError):
            return ""
    start, end = valid_date(params.get("from")), valid_date(params.get("to"))
    records = [r for r in records if (role == "all" or r["role"] == role) and (not start or r["joined"] >= start) and (not end or r["joined"] <= end)]
    counts = Counter(r["category"] for r in records)
    total = len(records)
    stops, categories, position = [], [], 0
    for i, (name, count) in enumerate(counts.most_common()):
        finish = position + count * 100 / total
        colour = COLOURS[i % len(COLOURS)]
        stops.append(f"{colour} {position:.3f}% {finish:.3f}%")
        categories.append({"name": name, "count": count, "percent": round(count * 100 / total), "colour": colour})
        position = finish
    selected = params.get("category", "")
    growth_records = [r for r in records if not selected or r["category"] == selected]
    growth, running = [], 0
    for day, count in sorted(Counter(r["joined"] for r in growth_records).items()):
        running += count
        growth.append({"day": day, "count": running, "new": count, "label": date.fromisoformat(day).strftime("%d %b %Y")})
    points = []
    step = max(1, ceil(max(running, 1) / 4))
    ceiling = step * 4
    ticks = [{"value": value, "y": 300 - 250 * value / ceiling} for value in range(0, ceiling + 1, step)]
    for i, row in enumerate(growth):
        span = (date.fromisoformat(growth[-1]["day"]) - date.fromisoformat(growth[0]["day"])).days
        elapsed = (date.fromisoformat(row["day"]) - date.fromisoformat(growth[0]["day"])).days
        x = 50 + (650 * elapsed / span if span else 325)
        y = 300 - (250 * row["count"] / ceiling)
        row.update(x=round(x, 2), y=round(y, 2), tooltip_x=round(min(max(x - 110, 50), 490), 2), tooltip_y=round(max(5, y - 94), 2))
        points.append(f"{x:.2f},{y:.2f}")
    return {"total": total, "categories": categories, "growth": growth, "points": " ".join(points),
            "gradient": "conic-gradient(" + ",".join(stops) + ")" if stops else "#edf0f4",
            "ticks": ticks, "role": role, "from": start, "to": end, "selected": selected}
