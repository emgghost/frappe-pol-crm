frappe.listview_settings["Customer"] = frappe.listview_settings["Customer"] || {};

if (!frappe.listview_settings["Customer"].add_fields) {
	frappe.listview_settings["Customer"].add_fields = [];
}
if (!frappe.listview_settings["Customer"].add_fields.includes("custom_rfm_segment")) {
	frappe.listview_settings["Customer"].add_fields.push("custom_rfm_segment", "custom_total_spent");
}

frappe.listview_settings["Customer"].get_indicator = function (doc) {
	if (doc.custom_rfm_segment) {
		const segment_colors = {
			CHAMPIONS: "green",
			LOYAL: "blue",
			POTENTIAL_LOYALIST: "cyan",
			NEW_CUSTOMERS: "blue",
			PROMISING: "orange",
			NEED_ATTENTION: "orange",
			ABOUT_TO_SLEEP: "yellow",
			AT_RISK: "red",
			CANT_LOSE: "purple",
			HIBERNATING: "gray",
			LOST: "darkgray",
		};
		const color = segment_colors[doc.custom_rfm_segment] || "gray";
		return [__(doc.custom_rfm_segment), color, "custom_rfm_segment,=," + doc.custom_rfm_segment];
	}
	return [__("Active"), "green", "disabled,=,0"];
};

function track_rfm_job_progress(listview, initial_job) {
	if (!frappe.realtime) return;

	let last_percent = initial_job ? initial_job.progress_percent : 0;
	frappe.show_alert({
		message: __("عملیات محاسبه RFM در صف پس‌زمینه در حال اجراست... ({0}%)", [last_percent]),
		indicator: "blue",
	}, 7);

	frappe.realtime.off("pol_rfm_job_status");
	frappe.realtime.on("pol_rfm_job_status", function (data) {
		if (!data) return;

		if (data.status === "IN_PROGRESS") {
			frappe.show_alert({
				message: __("محاسبه RFM در پس‌زمینه: {0}% ({1} از {2})", [
					data.progress_percent || 0,
					data.processed_records || 0,
					data.total_records || 0,
				]),
				indicator: "blue",
			}, 4);
		} else if (data.status === "SUCCESS") {
			frappe.msgprint({
				title: __("محاسبه RFM با موفقیت کامل شد"),
				message: __("امتیازات {0} مشتری از مجموع {1} رکورد با موفقیت به‌روزرسانی شد.", [
					data.scored_customers || 0,
					data.total_records || 0,
				]),
				indicator: "green",
			});
			if (listview && listview.refresh) {
				listview.refresh();
			}
			frappe.realtime.off("pol_rfm_job_status");
		} else if (data.status === "FAILED") {
			frappe.msgprint({
				title: __("خطا در محاسبه RFM"),
				message: __("عملیات با خطا مواجه شد: {0}", [data.error_message || __("خطای نامشخص")]),
				indicator: "red",
			});
			frappe.realtime.off("pol_rfm_job_status");
		}
	});
}

const original_onload = frappe.listview_settings["Customer"].onload;
frappe.listview_settings["Customer"].onload = function (listview) {
	if (original_onload) {
		original_onload(listview);
	}

	// Recover running job state after page refresh or navigation
	frappe.call({
		method: "pol_crm.rfm.rfm_calculator.get_rfm_job_status",
		callback: function (r) {
			if (r && r.message && (r.message.status === "IN_PROGRESS" || r.message.status === "QUEUED")) {
				track_rfm_job_progress(listview, r.message);
			}
		},
	});

	// Only System Manager or authorized users should see Global Recalculation
	if (frappe.user_roles.includes("System Manager") || frappe.session.user === "Administrator") {
		listview.page.add_menu_item(__("محاسبه مجدد RFM همه مشتریان (پس‌زمینه)"), function () {
			frappe.confirm(
				__("آیا می‌خواهید محاسبه مجدد RFM برای تمامی مشتریان در صف پس‌زمینه اجرا شود؟<br><small class='text-muted'>این عملیات سیستم را قفل نخواهد کرد و می‌توانید به کار خود ادامه دهید.</small>"),
				function () {
					frappe.call({
						method: "pol_crm.rfm.rfm_calculator.recalculate_all_customers_rfm",
						args: { async_run: true },
						callback: function (r) {
							if (r && r.message) {
								if (r.message.status === "already_running") {
									frappe.msgprint({
										title: __("عملیات در حال اجراست"),
										message: __("یک عملیات محاسبه مجدد دیگر هم‌اکنون در پس‌زمینه فعال است."),
										indicator: "orange",
									});
									track_rfm_job_progress(listview, r.message.job);
								} else if (r.message.status === "queued") {
									frappe.show_alert({
										message: __("عملیات در صف پس‌زمینه با شناسه {0} ثبت شد.", [r.message.job_id]),
										indicator: "green",
									});
									track_rfm_job_progress(listview, r.message.job);
								}
							}
						},
					});
				}
			);
		});
	}

	// Bulk Action Item for selected records
	listview.page.add_action_item(__("محاسبه مجدد RFM ردیف‌های انتخابی"), function () {
		const selected = listview.get_checked_items();
		if (!selected.length) return;

		frappe.confirm(
			__("آیا از محاسبه مجدد امتیازات RFM برای {0} مشتری اطمینان دارید؟", [selected.length]),
			function () {
				const customer_names = selected.map(function (item) { return item.name; });
				const is_large_batch = customer_names.length > 20;

				frappe.call({
					method: "pol_crm.rfm.rfm_calculator.calculate_rfm_for_customer",
					args: {
						customer_names: customer_names,
						async_run: is_large_batch,
					},
					freeze: !is_large_batch,
					freeze_message: is_large_batch ? null : __("در حال محاسبه RFM..."),
					callback: function (r) {
						if (is_large_batch && r && r.message && r.message.status === "queued") {
							frappe.show_alert({
								message: __("محاسبه گروهی {0} مشتری به صف پس‌زمینه منتقل شد.", [customer_names.length]),
								indicator: "blue",
							});
							track_rfm_job_progress(listview, r.message.job);
						} else {
							frappe.show_alert({
								message: __("امتیازات RFM با موفقیت به‌روزرسانی شد."),
								indicator: "green",
							});
							listview.refresh();
						}
					},
				});
			}
		);
	});
};
