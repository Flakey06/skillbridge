document.addEventListener("DOMContentLoaded", () => {
    document.querySelector("[data-start-manual-resume]")?.addEventListener("click", () => {
        document.querySelector("[data-guided-resume-fields]")?.scrollIntoView({behavior: "smooth", block: "start"});
        document.querySelector("#id_name")?.focus({preventScroll: true});
    });
    const careerMapNode = document.querySelector("#onboarding-career-choice-map");
    const careerField = document.querySelector("#id_career");
    const specialisationField = document.querySelector("#id_specialisation");
    const interestsField = document.querySelector("#id_career_interests");
    if (careerMapNode && careerField && specialisationField && interestsField) {
        const careerMap = JSON.parse(careerMapNode.textContent);
        careerField.addEventListener("change", () => {
            const choices = careerMap[careerField.value];
            if (!choices) return;

            const selectedSpecialisation = specialisationField.value;
            specialisationField.replaceChildren(new Option("Choose an option", ""));
            choices.specialisations.forEach(([value, label]) => {
                specialisationField.add(new Option(label, value, false, value === selectedSpecialisation));
            });

            const selectedInterests = new Set(
                [...interestsField.querySelectorAll('input[type="checkbox"]:checked')].map(input => input.value)
            );
            interestsField.replaceChildren(...choices.interests.map(([value, label], index) => {
                const row = document.createElement("div");
                const labelElement = document.createElement("label");
                const input = document.createElement("input");
                input.type = "checkbox";
                input.name = "career_interests";
                input.value = value;
                input.id = `id_career_interests_${index}`;
                input.checked = selectedInterests.has(value);
                labelElement.htmlFor = input.id;
                labelElement.append(input, document.createTextNode(` ${label}`));
                row.append(labelElement);
                return row;
            }));
        });
    }
    const esc = (value) => {
        const node = document.createElement("div");
        node.textContent = value || "";
        return node.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    };
    const month = (value) => {
        if (!value) return "";
        const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(value);
        if (!match) return value;
        const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1));
        return new Intl.DateTimeFormat("en", {month: "short", year: "numeric", timeZone: "UTC"}).format(date);
    };
    const parse = (field, fallback) => { try { const data = JSON.parse(field.value || "[]"); return data.length ? data : [fallback]; } catch (_) { return [fallback]; } };
    const form = document.querySelector("[data-onboard-compose]");

    const livePreview = document.querySelector("[data-resume-preview]");
    const autosaveStatus = document.querySelector("[data-resume-autosave-status]");
    const fieldValue = (id) => document.querySelector(id)?.value.trim() || "";
    const selectedLabel = (id) => {
        const field = document.querySelector(id);
        return field?.selectedOptions?.[0]?.value ? field.selectedOptions[0].textContent.trim() : "";
    };
    const renderLivePreview = () => {
        if (!livePreview) return;
        const name = fieldValue("#id_name") || "Your name";
        const email = fieldValue("#id_email");
        const phone = [fieldValue("#id_phone_country_code"), fieldValue("#id_phone")].filter(Boolean).join(" ");
        const education = selectedLabel("#id_education");
        const institution = selectedLabel("#id_institution");
        const experience = fieldValue("#id_experience");
        const certifications = fieldValue("#id_certifications");
        const skills = fieldValue("#id_skills");
        const career = selectedLabel("#id_career");
        const specialisation = selectedLabel("#id_specialisation");
        const portfolio = fieldValue("#id_portfolio");
        const awards = fieldValue("#id_awards");
        const linkedin = fieldValue("#id_linkedin");
        const section = (title, value, extraClass = "") => value ? `<section class="live-resume-section ${extraClass}"><h3>${title}</h3><div class="resume-preview-copy">${esc(value).replace(/\n/g, "<br>")}</div></section>` : "";
        livePreview.innerHTML = `<p class="eyebrow">Live resume preview</p><header class="live-resume-header"><div><h2>${esc(name)}</h2><p>${esc([career, specialisation].filter(Boolean).join(" · "))}</p></div><div class="live-resume-contact">${esc([email, phone, linkedin].filter(Boolean).join("\n")).replace(/\n/g, "<br>")}</div></header>${section("Education", [education, institution].filter(Boolean).join("\n"))}${section("Experience", experience)}${section("Certifications", certifications)}${skills || portfolio || awards ? `<section class="live-resume-section live-resume-highlight"><h3>Skills, work and achievements</h3><div class="live-resume-grid">${section("Technical skills", skills, "live-resume-compact")}${section("Projects and portfolio", portfolio, "live-resume-compact")}</div>${section("Awards and achievements", awards, "live-resume-compact")}</section>` : ""}${!education && !experience && !skills && !portfolio && !awards ? '<p class="resume-preview-empty">Start completing the guided form. Your resume will appear here as you type.</p>' : ""}`;
    };

    let autosaveTimer;
    const queueAutosave = (event) => {
        if (event?.target?.type === "file" || !form?.dataset.autosaveUrl) return;
        renderLivePreview();
        window.clearTimeout(autosaveTimer);
        if (autosaveStatus) autosaveStatus.textContent = "Saving changes…";
        autosaveTimer = window.setTimeout(async () => {
            const data = new FormData(form);
            data.delete("resume");
            data.delete("action");
            try {
                const response = await fetch(form.dataset.autosaveUrl, {method: "POST", body: data, headers: {"X-Requested-With": "XMLHttpRequest"}});
                if (!response.ok) throw new Error("Draft could not be saved");
                if (autosaveStatus) autosaveStatus.textContent = "Draft saved automatically";
            } catch (_) {
                if (autosaveStatus) autosaveStatus.textContent = "Draft not saved—use Save resume & continue";
            }
        }, 800);
    };
    form?.addEventListener("input", queueAutosave);
    form?.addEventListener("change", queueAutosave);
    form?.addEventListener("submit", event => {
        if (event.submitter?.value === "extract_resume" && autosaveStatus) {
            autosaveStatus.textContent = "Scanning and validating resume…";
        }
    });
    form?.addEventListener("submit", async event => {
        if (event.submitter?.value !== "extract_resume" || !form.dataset.scanUrl) return;
        event.preventDefault();
        const upload = document.querySelector("#id_resume")?.files?.[0];
        if (!upload) {
            if (autosaveStatus) autosaveStatus.textContent = "Choose one resume before submitting.";
            return;
        }
        const data = new FormData();
        data.append("csrfmiddlewaretoken", form.querySelector('[name="csrfmiddlewaretoken"]').value);
        data.append("resume", upload);
        try {
            const response = await fetch(form.dataset.scanUrl, {method: "POST", body: data, headers: {"X-Requested-With": "XMLHttpRequest"}});
            const result = await response.json();
            if (!response.ok || !result.ok) throw new Error(result.error || "Resume could not be scanned.");
            const updates = result.updates || {};
            const ids = {name: "#id_name", email: "#id_email", phone: "#id_phone", education: "#id_education", institution: "#id_institution", career_stage: "#id_career_stage", skills: "#id_skills", portfolio: "#id_portfolio", awards: "#id_awards", linkedin: "#id_linkedin", visa: "#id_visa"};
            Object.entries(ids).forEach(([key, selector]) => { if (updates[key] !== undefined) document.querySelector(selector).value = updates[key]; });
            if (updates.career) {
                careerField.value = updates.career;
                careerField.dispatchEvent(new Event("change", {bubbles: true}));
            }
            if (updates.specialisation) specialisationField.value = updates.specialisation;
            if (updates.career_interests && interestsField) {
                const selected = new Set(updates.career_interests);
                interestsField.querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = selected.has(input.value); });
            }
            form.dispatchEvent(new CustomEvent("resume-autofilled", {detail: updates}));
            const resumeInput = document.querySelector("#id_resume");
            resumeInput.value = "";
            resumeInput.disabled = true;
            const uploadControls = document.querySelector("[data-resume-upload-controls]");
            if (uploadControls) uploadControls.hidden = true;
            const current = document.querySelector("[data-current-resume]");
            if (current) {
                current.hidden = false;
                const currentName = current.querySelector("[data-current-resume-name]");
                if (currentName) currentName.textContent = result.filename;
            }
            if (autosaveStatus) autosaveStatus.textContent = "Resume scanned and fields auto-filled";
            renderLivePreview();
        } catch (error) {
            if (autosaveStatus) autosaveStatus.textContent = error.message;
        }
    });
    document.querySelector("[data-delete-resume]")?.addEventListener("click", async () => {
        if (!form.dataset.deleteResumeUrl) return;
        if (autosaveStatus) autosaveStatus.textContent = "Deleting current resume…";
        const data = new FormData();
        data.append("csrfmiddlewaretoken", form.querySelector('[name="csrfmiddlewaretoken"]').value);
        try {
            const response = await fetch(form.dataset.deleteResumeUrl, {method: "POST", body: data, headers: {"X-Requested-With": "XMLHttpRequest"}});
            if (!response.ok) throw new Error("Resume could not be deleted.");
            const current = document.querySelector("[data-current-resume]");
            const uploadControls = document.querySelector("[data-resume-upload-controls]");
            const resumeInput = document.querySelector("#id_resume");
            if (current) current.hidden = true;
            if (uploadControls) uploadControls.hidden = false;
            if (resumeInput) {
                resumeInput.value = "";
                resumeInput.disabled = false;
            }
            if (autosaveStatus) autosaveStatus.textContent = "Current document deleted. You can upload a new resume.";
        } catch (error) {
            if (autosaveStatus) autosaveStatus.textContent = error.message;
        }
    });

    const work = document.querySelector("[data-experience-builder]");
    if (work) {
        const list = work.querySelector("[data-experience-list]");
        const json = document.querySelector("#id_experience_entries");
        const summaryField = document.querySelector("#id_experience");
        const blank = {position: "", company: "", start_date: "", end_date: "", current: false, skills: "", achievements: ""};
        let items = parse(json, {...blank, achievements: summaryField?.value || ""});
        const sync = () => {
            items = [...list.querySelectorAll("[data-work]")].map(card => ({
                position: card.querySelector('[data-key="position"]').value.trim(), company: card.querySelector('[data-key="company"]').value.trim(),
                start_date: card.querySelector('[data-key="start_date"]').value, end_date: card.querySelector('[data-key="end_date"]').value,
                current: card.querySelector('[data-key="current"]').checked, skills: card.querySelector('[data-key="skills"]').value.trim(),
                achievements: card.querySelector('[data-key="achievements"]').value.trim()
            }));
            json.value = JSON.stringify(items);
            const text = items.map(item => {
                const lines = [[item.position, item.company].filter(Boolean).join(" — "), [month(item.start_date), item.current ? "Present" : month(item.end_date)].filter(Boolean).join(" – ")].filter(Boolean);
                if (item.skills) lines.push(`Skills: ${item.skills}`);
                item.achievements.split(/\r?\n/).map(line => line.trim().replace(/^(?:•|-|\*)\s*/, "")).filter(Boolean).forEach(line => lines.push(`• ${line}`));
                return lines.join("\n");
            }).filter(Boolean).join("\n\n");
            summaryField.value = text; work.querySelector("[data-experience-preview]").textContent = text || "Your formatted experience will appear here."; renderLivePreview();
        };
        const render = () => {
            list.innerHTML = items.map((item, index) => `<section class="experience-entry" data-work><div class="row between"><h4>Experience ${index + 1}</h4><button class="button small" type="button" data-remove-work="${index}">Remove</button></div><div class="form-grid experience-entry-grid"><label class="field">Position / role<input data-key="position" value="${esc(item.position)}"></label><label class="field">Company / placement<input data-key="company" value="${esc(item.company)}"></label><label class="field">Start date<input type="month" data-key="start_date" value="${esc(item.start_date)}"></label><label class="field">End date<input type="month" data-key="end_date" value="${esc(item.end_date)}" ${item.current ? "disabled" : ""}></label><label class="experience-current"><input type="checkbox" data-key="current" ${item.current ? "checked" : ""}> I currently work here</label><label class="field span2">Skills learned<input data-key="skills" value="${esc(item.skills)}"></label><label class="field span2"><span class="field-label-with-hint"><span>Achievements and responsibilities</span><small>Use point form for clarity—enter one point per line.</small></span><textarea rows="4" data-key="achievements" placeholder="e.g. Improved processing time by 20%\nCollaborated with a team of five">${esc(item.achievements)}</textarea></label></div></section>`).join(""); sync();
        };
        work.querySelector("[data-add-experience]").addEventListener("click", () => { sync(); items.push({...blank}); render(); });
        list.addEventListener("click", event => { const button = event.target.closest("[data-remove-work]"); if (button) { sync(); items.splice(+button.dataset.removeWork, 1); if (!items.length) items.push({...blank}); render(); } });
        list.addEventListener("input", sync); list.addEventListener("change", event => { if (event.target.dataset.key === "current") { const end = event.target.closest("[data-work]").querySelector('[data-key="end_date"]'); end.disabled = event.target.checked; if (end.disabled) end.value = ""; } sync(); });
        form.addEventListener("submit", sync); render();
        form.addEventListener("resume-autofilled", event => {
            if (!event.detail.experience_entries?.length) return;
            items = event.detail.experience_entries;
            render();
        });
    }

    const cert = document.querySelector("[data-certification-builder]");
    if (cert) {
        const list = cert.querySelector("[data-certification-list]"); const json = document.querySelector("#id_certification_entries"); const summaryField = document.querySelector("#id_certifications");
        const blank = {name: "", issuer: "", issue_date: "", expiry_date: "", no_expiry: false, credential_id: "", skills: ""};
        let items = parse(json, {...blank, name: summaryField?.value || ""});
        const sync = () => {
            items = [...list.querySelectorAll("[data-cert]")].map(card => ({name: card.querySelector('[data-key="name"]').value.trim(), issuer: card.querySelector('[data-key="issuer"]').value.trim(), issue_date: card.querySelector('[data-key="issue_date"]').value, expiry_date: card.querySelector('[data-key="expiry_date"]').value, no_expiry: card.querySelector('[data-key="no_expiry"]').checked, credential_id: card.querySelector('[data-key="credential_id"]').value.trim(), skills: card.querySelector('[data-key="certification_skills"]').value.trim()}));
            json.value = JSON.stringify(items);
            const text = items.map(item => { const lines = [[item.name, item.issuer].filter(Boolean).join(" — "), [month(item.issue_date), item.no_expiry ? "No expiry" : month(item.expiry_date)].filter(Boolean).join(" – ")].filter(Boolean); if (item.credential_id) lines.push(`Credential ID: ${item.credential_id}`); if (item.skills) lines.push(`Skills: ${item.skills}`); return lines.join("\n"); }).filter(Boolean).join("\n\n");
            summaryField.value = text; cert.querySelector("[data-certification-preview]").textContent = text || "Your formatted certifications will appear here."; renderLivePreview();
        };
        const render = () => { list.innerHTML = items.map((item, index) => `<section class="experience-entry" data-cert><div class="row between"><h4>Certification ${index + 1}</h4><button class="button small" type="button" data-remove-cert="${index}">Remove</button></div><div class="form-grid experience-entry-grid"><label class="field">Certification name<input data-key="name" value="${esc(item.name)}"></label><label class="field">Issuing organisation<input data-key="issuer" value="${esc(item.issuer)}"></label><label class="field">Issue date<input type="month" data-key="issue_date" value="${esc(item.issue_date)}"></label><label class="field">Expiry date<input type="month" data-key="expiry_date" value="${esc(item.expiry_date)}" ${item.no_expiry ? "disabled" : ""}></label><label class="experience-current"><input type="checkbox" data-key="no_expiry" ${item.no_expiry ? "checked" : ""}> Does not expire</label><label class="field">Credential ID<input data-key="credential_id" value="${esc(item.credential_id)}"></label><label class="field span2">Skills covered<input data-key="certification_skills" value="${esc(item.skills)}"></label></div></section>`).join(""); sync(); };
        cert.querySelector("[data-add-certification]").addEventListener("click", () => { sync(); items.push({...blank}); render(); });
        list.addEventListener("click", event => { const button = event.target.closest("[data-remove-cert]"); if (button) { sync(); items.splice(+button.dataset.removeCert, 1); if (!items.length) items.push({...blank}); render(); } });
        list.addEventListener("input", sync); list.addEventListener("change", event => { if (event.target.dataset.key === "no_expiry") { const expiry = event.target.closest("[data-cert]").querySelector('[data-key="expiry_date"]'); expiry.disabled = event.target.checked; if (expiry.disabled) expiry.value = ""; } sync(); });
        form.addEventListener("submit", sync); render();
    }
    renderLivePreview();
});
