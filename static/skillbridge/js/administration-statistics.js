(() => {
    const board = document.querySelector("[data-statistics-board]");
    const source = document.getElementById("member-statistics-data");
    if (!board || !source) return;

    const records = JSON.parse(source.textContent || "[]")
        .filter((item) => item.joined && item.role && item.category)
        .sort((a, b) => a.joined.localeCompare(b.joined));
    const role = board.querySelector("[data-stat-role]");
    const from = board.querySelector("[data-stat-from]");
    const to = board.querySelector("[data-stat-to]");
    const donut = board.querySelector("[data-donut-chart]");
    const total = board.querySelector("[data-donut-total]");
    const legend = board.querySelector("[data-chart-legend]");
    const svg = board.querySelector("[data-growth-chart]");
    const tooltip = board.querySelector("[data-chart-tooltip]");
    const empty = board.querySelector("[data-stat-empty]");
    const breakdownCaption = board.querySelector("[data-breakdown-caption]");
    const growthCaption = board.querySelector("[data-growth-caption]");
    const colours = ["#3fb4c5", "#7357c8", "#70b98b", "#e28a42", "#ce6681", "#4e8ed0", "#a96dcc", "#d6b348", "#5da69e", "#8b96a8"];
    let selectedCategory = "";

    if (records.length) {
        from.min = to.min = records[0].joined;
        from.max = to.max = records[records.length - 1].joined;
    }

    const prettyDate = (value, options = {day: "numeric", month: "short", year: "numeric"}) =>
        new Intl.DateTimeFormat("en-SG", options).format(new Date(`${value}T00:00:00`));
    const escapeText = (value) => String(value).replace(/[&<>"']/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));

    function filteredRecords(includeCategory = true) {
        return records.filter((item) =>
            (role.value === "all" || item.role === role.value) &&
            (!from.value || item.joined >= from.value) &&
            (!to.value || item.joined <= to.value) &&
            (!includeCategory || !selectedCategory || item.category === selectedCategory)
        );
    }

    function renderDonut(baseRecords) {
        const counts = new Map();
        baseRecords.forEach((item) => counts.set(item.category, (counts.get(item.category) || 0) + 1));
        const entries = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
        const count = baseRecords.length;
        total.textContent = count;
        breakdownCaption.textContent = `${entries.length} categor${entries.length === 1 ? "y" : "ies"} across ${count} member${count === 1 ? "" : "s"}`;

        let position = 0;
        const stops = entries.map(([, value], index) => {
            const start = position;
            position += count ? value / count * 100 : 0;
            return `${colours[index % colours.length]} ${start}% ${position}%`;
        });
        donut.style.background = stops.length ? `conic-gradient(${stops.join(",")})` : "#edf0f4";
        legend.innerHTML = entries.map(([label, value], index) => {
            const active = selectedCategory === label;
            return `<button type="button" data-category="${escapeText(label)}" aria-pressed="${active}"><i style="background:${colours[index % colours.length]}"></i><span title="${escapeText(label)}">${escapeText(label)}</span><strong>${value} · ${Math.round(value / count * 100)}%</strong></button>`;
        }).join("") || '<span class="sub">No categories to display.</span>';
        legend.querySelectorAll("[data-category]").forEach((button) => button.addEventListener("click", () => {
            selectedCategory = selectedCategory === button.dataset.category ? "" : button.dataset.category;
            render();
        }));
    }

    function svgElement(name, attributes = {}, text = "") {
        const element = document.createElementNS("http://www.w3.org/2000/svg", name);
        Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
        if (text) element.textContent = text;
        return element;
    }

    function renderGrowth(items) {
        svg.replaceChildren();
        tooltip.hidden = true;
        const daily = new Map();
        items.forEach((item) => daily.set(item.joined, (daily.get(item.joined) || 0) + 1));
        let cumulative = 0;
        const points = [...daily.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([date, value]) => ({date, value: cumulative += value}));
        growthCaption.textContent = selectedCategory ? `${selectedCategory} registrations over time` : "Cumulative registrations over time";
        if (!points.length) return;

        const width = 760, height = 360, left = 52, right = 18, top = 28, bottom = 48;
        const plotWidth = width - left - right, plotHeight = height - top - bottom;
        const max = Math.max(points[points.length - 1].value, 1);
        const x = (index) => left + (points.length === 1 ? plotWidth / 2 : index / (points.length - 1) * plotWidth);
        const y = (value) => top + plotHeight - value / max * plotHeight;

        const defs = svgElement("defs");
        const gradient = svgElement("linearGradient", {id: "growth-gradient", x1: "0", y1: "0", x2: "0", y2: "1"});
        gradient.append(svgElement("stop", {offset: "0%", "stop-color": "#4e72b8", "stop-opacity": ".28"}), svgElement("stop", {offset: "100%", "stop-color": "#4e72b8", "stop-opacity": ".02"}));
        defs.append(gradient); svg.append(defs);
        for (let index = 0; index <= 4; index += 1) {
            const value = Math.round(max * index / 4);
            const gridY = y(value);
            svg.append(svgElement("line", {x1: left, y1: gridY, x2: width - right, y2: gridY, class: "grid-line"}));
            svg.append(svgElement("text", {x: left - 10, y: gridY + 4, "text-anchor": "end", class: "axis-label"}, value));
        }
        const linePoints = points.map((point, index) => `${x(index)},${y(point.value)}`).join(" ");
        const area = `M ${left} ${top + plotHeight} L ${linePoints.replaceAll(" ", " L ")} L ${x(points.length - 1)} ${top + plotHeight} Z`;
        svg.append(svgElement("path", {d: area, class: "growth-area"}));
        svg.append(svgElement("polyline", {points: linePoints, class: "growth-line"}));

        const labelIndexes = new Set([0, points.length - 1]);
        const step = Math.max(1, Math.ceil(points.length / 5));
        for (let index = 0; index < points.length; index += step) labelIndexes.add(index);
        [...labelIndexes].sort((a, b) => a - b).forEach((index) => {
            svg.append(svgElement("text", {x: x(index), y: height - 16, "text-anchor": index === 0 ? "start" : index === points.length - 1 ? "end" : "middle", class: "axis-label"}, prettyDate(points[index].date, {day: "numeric", month: "short"})));
        });
        points.forEach((point, index) => {
            const circle = svgElement("circle", {cx: x(index), cy: y(point.value), r: 5, class: "growth-point", tabindex: "0", "aria-label": `${point.value} members by ${prettyDate(point.date)}`});
            const show = () => {
                const rect = svg.getBoundingClientRect();
                tooltip.innerHTML = `<strong>${point.value} member${point.value === 1 ? "" : "s"}</strong><br>${prettyDate(point.date)}`;
                tooltip.style.left = `${x(index) / width * rect.width}px`;
                tooltip.style.top = `${y(point.value) / height * rect.height}px`;
                tooltip.hidden = false;
            };
            circle.addEventListener("mouseenter", show); circle.addEventListener("focus", show);
            circle.addEventListener("mouseleave", () => tooltip.hidden = true); circle.addEventListener("blur", () => tooltip.hidden = true);
            svg.append(circle);
        });
    }

    function render() {
        if (from.value && to.value && from.value > to.value) to.value = from.value;
        const base = filteredRecords(false);
        if (selectedCategory && !base.some((item) => item.category === selectedCategory)) selectedCategory = "";
        const filtered = filteredRecords(true);
        renderDonut(base);
        renderGrowth(filtered);
        empty.hidden = filtered.length > 0;
    }

    [role, from, to].forEach((control) => control.addEventListener("change", () => { selectedCategory = ""; render(); }));
    board.querySelector("[data-stat-reset]").addEventListener("click", () => { role.value = "all"; from.value = ""; to.value = ""; selectedCategory = ""; render(); });
    render();
})();
