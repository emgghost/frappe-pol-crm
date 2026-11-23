// Shared by the campaign and automation forms and lists: Persian names for the stored
// codes, and the gallery of ready-made templates.
frappe.provide("pol_crm.marketing");

pol_crm.marketing.labels = {
	segment: {
		CHAMPIONS: "قهرمان",
		LOYAL: "وفادار",
		POTENTIAL_LOYALIST: "وفادار بالقوه",
		NEW_CUSTOMERS: "تازه‌وارد",
		PROMISING: "امیدوارکننده",
		NEED_ATTENTION: "نیازمند توجه",
		ABOUT_TO_SLEEP: "در آستانه‌ی خواب",
		AT_RISK: "در خطر ریزش",
		CANT_LOSE: "نباید از دست برود",
		HIBERNATING: "خوابیده",
		LOST: "از دست رفته",
	},
	trigger_type: {
		INACTIVITY: "مدتی خرید نکرده",
		RFM_SEGMENT_CHANGE: "وارد یک گروه RFM شده",
		FIRST_ORDER: "اولین خرید را کرده",
		AFTER_PURCHASE: "خرید کرده (هر خرید)",
		PURCHASE_COUNT: "به خرید چندم رسیده",
		SPEND_THRESHOLD: "جمع خریدش به مبلغی رسیده",
		BIRTHDAY: "تولدش است",
	},
	last_purchase: {
		ANY_TIME: "مهم نیست",
		BOUGHT_WITHIN: "در این چند روز اخیر خرید کرده",
		NOT_BOUGHT_WITHIN: "در این چند روز اخیر خرید نکرده",
	},
	channel: { SMS: "پیامک", TELEGRAM: "تلگرام" },
	status: {
		Draft: ["پیش‌نویس", "gray"],
		Scheduled: ["زمان‌بندی‌شده", "blue"],
		Sending: ["در حال ارسال", "orange"],
		Sent: ["ارسال‌شده", "green"],
		Cancelled: ["لغوشده", "red"],
	},
};

pol_crm.marketing.options = function (name) {
	return Object.entries(pol_crm.marketing.labels[name]).map(([value, label]) => ({ value, label }));
};

pol_crm.marketing.set_options = function (frm, fieldname, labels) {
	frm.set_df_property(fieldname, "options", pol_crm.marketing.options(labels || fieldname));
};

pol_crm.marketing.show_templates = function (kind) {
	const doctype = kind === "campaign" ? "Mkt Campaign" : "Mkt Scenario";
	frappe.call("pol_crm.marketing_automation.templates.get_templates", { kind }).then((r) => {
		const cards = (r.message || [])
			.map(
				(t) => `
			<div class="pol-template" style="border:1px solid var(--border-color);border-radius:8px;padding:12px;margin-bottom:10px">
				<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
					<b>${frappe.utils.escape_html(t.title)}</b>
					<button class="btn btn-xs btn-primary" data-id="${t.id}">${__("استفاده")}</button>
				</div>
				<div class="text-muted small" style="margin-top:6px;line-height:1.9">
					<div>👥 <b>${__("چه کسی")}:</b> ${frappe.utils.escape_html(t.who)}</div>
					<div>✉️ <b>${__("چه پیامی")}:</b> ${frappe.utils.escape_html(t.what)}</div>
					<div>🕒 <b>${__("چه زمانی")}:</b> ${frappe.utils.escape_html(t.when)}</div>
					${t.needs ? `<div class="text-warning">⚠️ ${frappe.utils.escape_html(t.needs)}</div>` : ""}
				</div>
			</div>`
			)
			.join("");
		const d = new frappe.ui.Dialog({
			title: kind === "campaign" ? __("قالب‌های آماده‌ی کمپین") : __("قالب‌های آماده‌ی اتوماسیون"),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "list" }],
		});
		d.fields_dict.list.$wrapper.html(
			`<p class="text-muted">${
				kind === "campaign"
					? __("یک پیش‌نویس ساخته می‌شود؛ هر چیزی را خواستید تغییر دهید و بعد «ارسال» بزنید.")
					: __("خاموش ساخته می‌شود؛ بعد از بررسی، تیک «روشن» را بزنید.")
			}</p>${cards}`
		);
		d.fields_dict.list.$wrapper.on("click", "button[data-id]", function () {
			frappe
				.call("pol_crm.marketing_automation.templates.create_from_template", {
					kind,
					template_id: $(this).data("id"),
				})
				.then((res) => {
					d.hide();
					frappe.set_route("Form", doctype, res.message);
				});
		});
		d.show();
	});
};

pol_crm.marketing.test_send = function (frm) {
	const telegram = frm.doc.channel === "TELEGRAM";
	frappe.prompt(
		telegram
			? { fieldname: "chat_id", fieldtype: "Data", label: __("شناسه‌ی چت تلگرام شما"), reqd: 1 }
			: { fieldname: "mobile", fieldtype: "Data", label: __("شماره‌ی موبایل شما"), reqd: 1 },
		(values) =>
			frm.call("send_test", values).then((r) => {
				frappe.msgprint({
					title: __("پیام آزمایشی فرستاده شد"),
					message: `<div style="white-space:pre-wrap">${frappe.utils.escape_html(r.message || "")}</div>`,
					indicator: "green",
				});
			}),
		__("ارسال آزمایشی"),
		__("بفرست")
	);
};
