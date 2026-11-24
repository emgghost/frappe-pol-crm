frappe.pages["marketing-templates"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("قالب‌های آماده"), single_column: true });
	const $body = $(`
		<div style="max-width:760px;margin:0 auto;padding:12px 0">
			<div class="btn-group" role="group" style="margin-bottom:16px">
				<button class="btn btn-default btn-sm" data-kind="campaign">${__("کمپین (ارسال یک‌باره)")}</button>
				<button class="btn btn-default btn-sm" data-kind="automation">${__("اتوماسیون (ارسال خودکار)")}</button>
			</div>
			<div class="pol-templates-list"></div>
		</div>`).appendTo(page.main);

	const show = (kind) => {
		$body.find("button[data-kind]").removeClass("btn-primary").addClass("btn-default");
		$body.find(`button[data-kind="${kind}"]`).removeClass("btn-default").addClass("btn-primary");
		pol_crm.marketing.render_templates($body.find(".pol-templates-list"), kind);
	};
	$body.on("click", "button[data-kind]", function () {
		show($(this).data("kind"));
	});
	show("campaign");
};
