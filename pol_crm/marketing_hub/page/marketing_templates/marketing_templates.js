// Campaigns and Automations in one place: ready-made templates as cards, then what you already have.
frappe.pages["marketing-templates"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Marketing"), single_column: true });
	const esc = frappe.utils.escape_html;
	const state = { kind: frappe.get_route()[1] === "automation" ? "automation" : "campaign" };

	const COPY = {
		campaign: {
			title: __("Send once, on your schedule"),
			text: __("Pick who gets it with filters, up to 1,000 customers per send. WhatsApp, Instagram DM or Wafi App."),
			scratch: __("New campaign from scratch"),
			doctype: "Mkt Campaign",
			mine: __("Your campaigns"),
		},
		automation: {
			title: __("Set it once: it runs until you turn it off"),
			text: __("Messages go out automatically when something happens: a purchase, a birthday, a quiet customer."),
			scratch: __("New automation from scratch"),
			doctype: "Mkt Scenario",
			mine: __("Your automations"),
		},
	};

	$(`<style>
		.mt-tabs{display:flex;gap:8px;margin-bottom:16px}
		.mt-tab{padding:10px 18px;border-radius:10px;font-weight:700;cursor:pointer;border:1.5px solid var(--border-color);background:var(--card-bg)}
		.mt-tab.on.k-campaign{background:#FF8C00;border-color:#FF8C00;color:#fff}
		.mt-tab.on.k-automation{background:#7c3aed;border-color:#7c3aed;color:#fff}
		.mt-hero{border-radius:14px;padding:20px;color:#fff;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:18px}
		.mt-hero.k-campaign{background:linear-gradient(135deg,#FF8C00,#e07000)}
		.mt-hero.k-automation{background:linear-gradient(135deg,#7c3aed,#5b21b6)}
		.mt-hero-t{font-size:18px;font-weight:800;margin-bottom:4px}
		.mt-hero-d{font-size:13px;opacity:.92;max-width:640px}
		.mt-hero button{background:#ffffff25;border:0;color:#fff;font-weight:700;padding:9px 14px;border-radius:8px;white-space:nowrap}
		.mt-sec{font-size:14px;font-weight:700;margin:20px 0 4px}
		.mt-sec span{font-size:11px;font-weight:600;color:var(--text-muted);margin-inline-start:6px}
		.mt-sec-d{font-size:12px;color:var(--text-muted);margin-bottom:10px}
		.mt-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
		.mt-card{background:var(--card-bg);border:1.5px solid var(--border-color);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:8px}
		.mt-card.k-campaign:hover{border-color:#FF8C00}
		.mt-card.k-automation:hover{border-color:#7c3aed}
		.mt-card.locked{opacity:.7}
		.mt-top{display:flex;align-items:center;gap:8px}
		.mt-ic{font-size:22px}
		.mt-name{font-size:14px;font-weight:700}
		.mt-desc{font-size:12px;color:var(--text-muted);line-height:1.5}
		.mt-preset{font-size:11.5px;line-height:1.7;background:var(--subtle-fg);border-radius:8px;padding:8px 10px}
		.mt-msg{font-size:12px;border-inline-start:3px solid var(--border-color);padding-inline-start:8px;color:var(--text-color);white-space:pre-wrap}
		.mt-tag{display:inline-block;font-size:10.5px;font-weight:700;border-radius:20px;padding:2px 8px;background:#f3e8ff;color:#6b21a8}
		.mt-tag.free{background:#dcfce7;color:#166534}
		.mt-actions{display:flex;gap:8px;margin-top:auto}
		.mt-actions .btn{flex:1}
		.mt-row{display:flex;align-items:center;gap:14px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:12px;padding:12px 14px;margin-bottom:8px;cursor:pointer}
		.mt-row-info{flex:1;min-width:0}
		.mt-row-name{font-weight:700}
		.mt-row-desc{font-size:12px;color:var(--text-muted)}
		.mt-stat{text-align:center;font-size:11px;color:var(--text-muted);min-width:70px}
		.mt-stat b{display:block;font-size:14px;color:var(--text-color)}
	</style>`).appendTo(page.main);
	const $body = $('<div class="mt-body"></div>').appendTo(page.main);

	const stat = (value, label) => `<div class="mt-stat"><b>${value}</b>${label}</div>`;
	const iqd = pol_crm.marketing.iqd;

	const card = (t) => {
		const actions = t.locked
			? `<button class="btn btn-default btn-sm" data-act="club">${__("Needs the Club subscription")}</button>`
			: (t.needs_setup ? "" : `<button class="btn btn-primary btn-sm" data-act="run" data-id="${t.id}">▶ ${__("Run")}</button>`) +
			  `<button class="btn btn-default btn-sm" data-act="edit" data-id="${t.id}">✏️ ${t.needs_setup ? __("Set up") : __("Edit")}</button>`;
		return `<div class="mt-card k-${state.kind} ${t.locked ? "locked" : ""}">
			<div class="mt-top"><span class="mt-ic">${t.icon}</span><span class="mt-name">${esc(__(t.name))}</span></div>
			<div class="mt-desc">${esc(__(t.desc))}</div>
			<div class="mt-preset">${t.lines.map((l) => `<div>${esc(l)}</div>`).join("")}</div>
			${t.message ? `<div class="mt-msg">${esc(t.message)}</div>` : ""}
			<div>${t.club ? `<span class="mt-tag">🔒 ${__("Club")}</span>` : ""}${t.free ? ` <span class="mt-tag free">${__("Free: no messages")}</span>` : ""}</div>
			<div class="mt-actions">${actions}</div>
		</div>`;
	};

	const row = (r) => {
		if (state.kind === "campaign") {
			const sent = r.status === "Sent";
			return `<div class="mt-row" data-open="${r.name}">
				<div class="mt-ic">📣</div>
				<div class="mt-row-info"><div class="mt-row-name">${esc(r.title)}</div>
				<div class="mt-row-desc">${esc(__(r.detail))} · ${esc(__(r.channel))} · <span class="indicator-pill ${sent ? "green" : "gray"}">${esc(__(r.status))}</span></div></div>
				${sent ? stat(r.sent_count || 0, __("Sent")) + stat(r.purchases_after || 0, __("Bought")) + stat(iqd(r.revenue_after), __("Revenue")) : ""}
			</div>`;
		}
		return `<div class="mt-row" data-open="${r.name}">
			<div class="mt-ic">⚡</div>
			<div class="mt-row-info"><div class="mt-row-name">${esc(r.title)}</div>
			<div class="mt-row-desc">${esc(r.detail)} · ${esc(r.channel || "")} · <span class="indicator-pill ${r.enabled ? "green" : "gray"}">${r.enabled ? __("Running") : __("Stopped")}</span></div></div>
			${r.entered ? stat(r.entered, __("Reached (30d)")) + stat(r.converted, __("Bought")) + stat(iqd(r.revenue), __("Revenue")) : stat("—", __("No activity yet"))}
			<label class="switch" title="${__("On / Off")}"><input type="checkbox" data-toggle="${r.name}" ${r.enabled ? "checked" : ""}></label>
		</div>`;
	};

	const render = () => {
		const copy = COPY[state.kind];
		frappe.call("pol_crm.marketing_hub.templates.get_gallery", { kind: state.kind }).then((r) => {
			const data = r.message;
			const open = data.templates.filter((t) => !t.locked);
			const locked = data.templates.filter((t) => t.locked);
			$body.html(`
				<div class="mt-tabs">
					<div class="mt-tab k-campaign ${state.kind === "campaign" ? "on" : ""}" data-kind="campaign">📣 ${__("Campaigns")}</div>
					<div class="mt-tab k-automation ${state.kind === "automation" ? "on" : ""}" data-kind="automation">⚡ ${__("Automations")}</div>
				</div>
				<div class="mt-hero k-${state.kind}">
					<div><div class="mt-hero-t">${copy.title}</div><div class="mt-hero-d">${copy.text}</div></div>
					<button data-act="scratch">+ ${copy.scratch}</button>
				</div>
				<div class="mt-sec">${__("Templates")}<span>${open.length}</span></div>
				<div class="mt-sec-d">${__("Run it as is, or edit it: you can change the message, who gets it and when.")}</div>
				<div class="mt-grid">${open.map(card).join("")}</div>
				${locked.length ? `<div class="mt-sec">🔒 ${__("Needs the Club subscription")}<span>${locked.length}</span></div>
					<div class="mt-sec-d">${__("These use club tiers or points. Turn on the Club subscription in Marketing Hub Settings to unlock them.")}</div>
					<div class="mt-grid">${locked.map(card).join("")}</div>` : ""}
				<div class="mt-sec">${copy.mine}<span>${data.mine.length}</span></div>
				${data.mine.length ? data.mine.map(row).join("") : `<div class="mt-sec-d">${__("Nothing yet. Start from a template above.")}</div>`}
			`);
		});
	};

	const use = (id, run) => {
		const method = run ? "run_template" : "create_from_template";
		frappe.call(`pol_crm.marketing_hub.templates.${method}`, { template_id: id }).then((r) => {
			const out = r.message;
			if (!out.name) return frappe.new_doc(out.doctype, out.values);
			if (run) {
				frappe.show_alert({
					message: out.doctype === "Mkt Campaign" ? __("Sending to {0} customers.", [out.recipients]) : __("Automation is on."),
					indicator: "green",
				});
				return render();
			}
			frappe.set_route("Form", out.doctype, out.name);
		});
	};

	$body.on("click", "[data-kind]", function () {
		state.kind = $(this).data("kind");
		render();
	});
	$body.on("click", "[data-act]", function (e) {
		e.stopPropagation();
		const act = $(this).data("act");
		const id = $(this).data("id");
		if (act === "scratch") return frappe.new_doc(COPY[state.kind].doctype);
		if (act === "club") return frappe.set_route("Form", "Marketing Hub Settings");
		if (act === "edit") return use(id, false);
		const question =
			state.kind === "campaign"
				? __("Create this campaign and send it now to everyone it matches?")
				: __("Create this automation and turn it on now?");
		frappe.confirm(question, () => use(id, true));
	});
	$body.on("click", "[data-toggle]", function (e) {
		e.stopPropagation();
		frappe
			.call("pol_crm.marketing_hub.templates.set_automation", { scenario: $(this).data("toggle"), enabled: this.checked ? 1 : 0 })
			.then(render);
	});
	$body.on("click", "label.switch", (e) => e.stopPropagation());
	$body.on("click", "[data-open]", function () {
		frappe.set_route("Form", COPY[state.kind].doctype, $(this).data("open"));
	});

	wrapper.refresh_templates = render;
	render();
};

frappe.pages["marketing-templates"].on_page_show = function (wrapper) {
	wrapper.refresh_templates && wrapper.refresh_templates();
};
