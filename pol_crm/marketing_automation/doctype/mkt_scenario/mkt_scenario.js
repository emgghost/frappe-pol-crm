frappe.ui.form.on("Mkt Scenario", {
	setup(frm) {
		pol_crm.marketing.set_options(frm, "trigger_type");
		pol_crm.marketing.set_options(frm, "target_rfm_segment", "segment");
		pol_crm.marketing.set_options(frm, "channel");
	},

	refresh(frm) {
		frm.page.set_indicator(frm.doc.enabled ? __("روشن") : __("خاموش"), frm.doc.enabled ? "green" : "gray");
		show_trigger_help(frm);
		if (frm.is_new()) return;
		frm.add_custom_button(__("پیش‌نمایش پیام"), () =>
			frm.call("preview").then((r) =>
				frappe.msgprint({
					title: __("پیش‌نمایش پیام"),
					message: `<div style="white-space:pre-wrap">${frappe.utils.escape_html(r.message.text)}</div>`,
				})
			)
		);
		frm.add_custom_button(__("ارسال آزمایشی"), () => pol_crm.marketing.test_send(frm));
	},

	trigger_type: show_trigger_help,
});

const TRIGGER_HELP = {
	INACTIVITY: "هر روز، به مشتریانی که دقیقاً همین تعداد روز از آخرین خریدشان گذشته.",
	RFM_SEGMENT_CHANGE: "وقتی محاسبه‌ی RFM مشتری را به این گروه ببرد؛ حداکثر یک بار در ماه برای هر مشتری.",
	FIRST_ORDER: "یک بار برای هر مشتری، چند روز بعد از اولین خریدش.",
	AFTER_PURCHASE: "چند روز بعد از هر خرید.",
	PURCHASE_COUNT: "همان لحظه که فاکتور خرید چندم ثبت شود؛ یک بار برای هر مشتری.",
	SPEND_THRESHOLD: "همان لحظه که جمع خرید مشتری از این مبلغ بگذرد؛ یک بار برای هر مشتری.",
	BIRTHDAY: "روز تولد مشتری، اگر در پرونده‌اش «تاریخ تولد» ثبت شده باشد.",
};

function show_trigger_help(frm) {
	const help = TRIGGER_HELP[frm.doc.trigger_type] || "";
	frm.fields_dict.trigger_help.$wrapper.html(help ? `<p class="text-muted small">${__(help)}</p>` : "");
}
