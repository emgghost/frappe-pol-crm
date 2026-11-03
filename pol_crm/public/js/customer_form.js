frappe.ui.form.on("Customer", {
	refresh: function (frm) {
		render_customer_360_header(frm);
		load_customer_offers_and_messages(frm);
	},
});

function render_customer_360_header(frm) {
	if (!frm.doc || frm.is_new()) return;

	// Remove previous header if exists
	frm.dashboard.clear_headline();
	frm.page.wrapper.find(".pol-crm-360-header").remove();

	const segment = frm.doc.custom_rfm_segment || "UNSCORED";
	const segment_config = {
		CHAMPIONS: { label: "قهرمانان (Champions)", color: "#16a34a", bg: "#dcfce7", desc: "بهترین مشتریان: خرید منظم، مبلغ بالا و به تازگی" },
		LOYAL: { label: "وفادار (Loyal)", color: "#2563eb", bg: "#dbeafe", desc: "مشتریان پایدار و با تکرار خرید بالا" },
		POTENTIAL_LOYALIST: { label: "مستعد وفاداری", color: "#0891b2", bg: "#cffafe", desc: "خریدهای اخیر با مبالغ خوب، پتانسیل تبدیل به مشتری وفادار" },
		NEW_CUSTOMERS: { label: "مشتری جدید", color: "#0284c7", bg: "#e0f2fe", desc: "اولین خرید به تازگی انجام شده است" },
		PROMISING: { label: "امیدبخش", color: "#ea580c", bg: "#ffedd5", desc: "خریدار تازه‌کار با مبلغ بالاتر از میانگین" },
		NEED_ATTENTION: { label: "نیازمند توجه", color: "#d97706", bg: "#fef3c7", desc: "خریدارهای باسابقه که مدت بیشتری از خرید قبلی گذشته" },
		ABOUT_TO_SLEEP: { label: "در آستانه خواب", color: "#ca8a04", bg: "#fef9c3", desc: "فاصله زمانی طولانی از آخرین تعامل، خطر ورود به ریزش" },
		AT_RISK: { label: "در خطر ریزش (At Risk)", color: "#dc2626", bg: "#fee2e2", desc: "مشتری قدیمی با مبالغ خرید بالا که مدت‌هاست خرید نکرده است!" },
		CANT_LOSE: { label: "نباید از دست برود", color: "#9333ea", bg: "#f3e8ff", desc: "مشتری باارزش تاریخی بسیار بالا و عدم فعالیت نگران‌کننده!" },
		HIBERNATING: { label: "راکد (Hibernating)", color: "#6b7280", bg: "#f3f4f6", desc: "عدم خرید در بازه طولانی و تعداد سفارشات کم" },
		LOST: { label: "از دست رفته (Lost)", color: "#374151", bg: "#e5e7eb", desc: "عدم فعالیت کامل در دوره‌های متوالی" },
		UNSCORED: { label: "ارزیابی‌نشده", color: "#6b7280", bg: "#f9fafb", desc: "تراکنش ثبتی کافی جهت محاسبه امتیاز موجود نیست" },
	};

	const conf = segment_config[segment] || segment_config["UNSCORED"];
	const composite = frm.doc.custom_rfm_composite_score || "---";
	const days = frm.doc.custom_days_since_last_purchase != null ? frm.doc.custom_days_since_last_purchase : "—";
	const orders_count = frm.doc.custom_paid_invoices_count || 0;
	const total_spent = frm.doc.custom_total_spent ? format_currency(frm.doc.custom_total_spent, frm.doc.billing_currency || "IRR") : "۰";

	let alert_html = "";
	if (["AT_RISK", "CANT_LOSE"].includes(segment)) {
		alert_html = `
			<div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 6px 12px; margin-top: 8px; font-size: 12px; color: #991b1b; display: flex; align-items: center; justify-content: space-between;">
				<span>⚠️ <strong>هشدار ریزش مشتری:</strong> این مشتری در خطر خروج از چرخه خرید است. ارائه آفر یا تماس پیگیری توصیه می‌شود.</span>
				<button class="btn btn-xs btn-danger btn-quick-offer" style="margin-right: 8px;">اعطای آفر تخفیف</button>
			</div>
		`;
	}

	const header_html = `
		<div class="pol-crm-360-header" style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px 16px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
			<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
				<div style="display: flex; align-items: center; gap: 12px;">
					<span style="background: ${conf.bg}; color: ${conf.color}; border: 1px solid ${conf.color}40; padding: 4px 10px; border-radius: 16px; font-weight: 600; font-size: 13px;">
						● ${conf.label}
					</span>
					<span style="font-size: 12px; color: #6b7280;">امتیاز ترکیبی: <strong style="color: #111827;">${composite}</strong></span>
					<span style="color: #d1d5db;">|</span>
					<span style="font-size: 12px; color: #6b7280;">آخرین خرید: <strong style="color: #111827;">${days} روز پیش</strong></span>
					<span style="color: #d1d5db;">|</span>
					<span style="font-size: 12px; color: #6b7280;">تعداد خریدها: <strong style="color: #111827;">${orders_count}</strong></span>
					<span style="color: #d1d5db;">|</span>
					<span style="font-size: 12px; color: #6b7280;">مجموع پرداخت: <strong style="color: #111827;">${total_spent}</strong></span>
				</div>
				<div style="display: flex; gap: 8px;">
					<button class="btn btn-default btn-xs btn-refresh-rfm" title="محاسبه مجدد امتیازات بر اساس فاکتورها">
						<i class="fa fa-refresh"></i> محاسبه مجدد RFM
					</button>
					<button class="btn btn-default btn-xs btn-open-offers" title="مشاهده یا ثبت آفر">
						<i class="fa fa-gift"></i> آفرهای مشتری
					</button>
					<button class="btn btn-default btn-xs btn-send-quick-msg" title="ارسال پیامک یا تلگرام">
						<i class="fa fa-paper-plane"></i> ارسال پیام
					</button>
				</div>
			</div>
			${alert_html}
		</div>
	`;

	const $dashboard = $(frm.fields_dict["customer_name"].wrapper).closest(".form-layout");
	$(header_html).insertBefore($dashboard);

	// Event Handlers
	frm.page.wrapper.find(".btn-refresh-rfm").on("click", function () {
		frappe.call({
			method: "pol_crm.rfm.rfm_calculator.calculate_rfm_for_customer",
			args: { customer_name: frm.doc.name },
			freeze: true,
			freeze_message: __("در حال محاسبه مجدد امتیازات RFM مشتری..."),
			callback: function (r) {
				frappe.show_alert({ message: __("امتیازات RFM به‌روزرسانی شد."), indicator: "green" });
				frm.reload_doc();
			},
		});
	});

	frm.page.wrapper.find(".btn-quick-offer, .btn-open-offers").on("click", function () {
		frappe.new_doc("Loyalty Offer", { customer: frm.doc.name });
	});

	frm.page.wrapper.find(".btn-send-quick-msg").on("click", function () {
		const d = new frappe.ui.Dialog({
			title: __("ارسال پیام به مشتری"),
			fields: [
				{
					fieldname: "channel",
					fieldtype: "Select",
					label: __("کانال ارتباطی"),
					options: "SMS\nTELEGRAM",
					default: frm.doc.custom_mkt_preferred_channel || "SMS",
				},
				{
					fieldname: "recipient",
					fieldtype: "Data",
					label: __("گیرنده (شماره موبایل یا شناسه چت)"),
					default: frm.doc.mobile_no || frm.doc.phone || frm.doc.custom_telegram_chat_id || "",
					reqd: 1,
				},
				{
					fieldname: "message",
					fieldtype: "Small Text",
					label: __("متن پیام"),
					reqd: 1,
				},
			],
			primary_action_label: __("ارسال"),
			primary_action: function (values) {
				frappe.call({
					method: "pol_crm.messaging.policy.send_marketing_message",
					args: {
						customer: frm.doc.name,
						phone: values.channel === "SMS" ? values.recipient : null,
						telegram_chat_id: values.channel === "TELEGRAM" ? values.recipient : null,
						text: values.message,
						channel: values.channel,
						urgent: true,
					},
					freeze: true,
					freeze_message: __("در حال ارسال پیام..."),
					callback: function (res) {
						d.hide();
						if (res && res.message && res.message.status === "SENT") {
							frappe.show_alert({ message: __("پیام با موفقیت ارسال شد."), indicator: "green" });
						} else {
							frappe.msgprint({
								title: __("نتیجه ارسال"),
								message: __("وضعیت: {0} ({1})", [
									res.message.status,
									res.message.reason || res.message.error || __("ارسال نشد"),
								]),
								indicator: res.message.status === "POSTPONED" ? "orange" : "red",
							});
						}
					},
				});
			},
		});
		d.show();
	});
}

function load_customer_offers_and_messages(frm) {
	if (!frm.doc || frm.is_new()) return;
	// Load active offers count for badge
	frappe.db.count("Loyalty Offer", { customer: frm.doc.name, status: "ACTIVE" }).then((count) => {
		if (count > 0) {
			frm.dashboard.add_badge(__("{0} آفر فعال", [count]), "blue");
		}
	});
}
