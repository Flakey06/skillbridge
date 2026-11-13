(() => {
    const workspace = document.querySelector("[data-admin-workspace]");
    if (!workspace) return;
    const links = [...workspace.querySelectorAll("[data-admin-nav]")];
    const panels = [...workspace.querySelectorAll("[data-admin-section]")];
    const valid = new Set(links.map((link) => link.dataset.adminNav));

    function activate(name, updateHistory = false) {
        const section = valid.has(name) ? name : "overview";
        panels.forEach((panel) => {
            const active = panel.dataset.adminSection === section;
            panel.hidden = !active;
            panel.setAttribute("aria-hidden", String(!active));
        });
        links.forEach((link) => {
            const active = link.dataset.adminNav === section;
            link.classList.toggle("active", active);
            if (active) link.setAttribute("aria-current", "page");
            else link.removeAttribute("aria-current");
        });
        if (updateHistory) history.pushState(null, "", `#${section}`);
        document.title = `${links.find((link) => link.dataset.adminNav === section)?.textContent.trim() || "Administration"} · SkillBridge`;
    }

    links.forEach((link) => link.addEventListener("click", (event) => {
        event.preventDefault();
        activate(link.dataset.adminNav, true);
        if (window.innerWidth < 850) workspace.scrollIntoView({behavior: "smooth", block: "start"});
    }));
    window.addEventListener("hashchange", () => activate(location.hash.slice(1)));
    window.addEventListener("popstate", () => activate(location.hash.slice(1)));
    activate(location.hash.slice(1));
})();
