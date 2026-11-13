"""Server-rendered member charts and filters."""
from collections import Counter
from datetime import date


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
        growth.append({"day": day, "count": running})
    points = []
    for i, row in enumerate(growth):
        x = 50 + (650 * i / max(len(growth) - 1, 1))
        y = 300 - (250 * row["count"] / max(total, 1))
        row.update(x=round(x, 2), y=round(y, 2))
        points.append(f"{x:.2f},{y:.2f}")
    return {"total": total, "categories": categories, "growth": growth, "points": " ".join(points),
            "gradient": "conic-gradient(" + ",".join(stops) + ")" if stops else "#edf0f4",
            "role": role, "from": start, "to": end, "selected": selected}
