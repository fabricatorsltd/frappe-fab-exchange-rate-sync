frappe.ui.form.on("Exchange Rate Sync Settings", {
	refresh(frm) {
		frm.set_intro(
			__(
				"1. Open the seeded provider records and set API keys. 2. Add the currency pairs you want. 3. Click Sync Now for a manual fetch. Enable Automatic Sync only controls scheduled runs."
			),
			"blue"
		);

		frm.dashboard.clear_headline();
		if (!(frm.doc.currency_pairs || []).some((row) => !!row.enabled)) {
			frm.dashboard.add_indicator(__("No currency pairs configured"), "orange");
		}
		if (frm.doc.last_successful_sync_at) {
			frm.dashboard.add_indicator(
				__("Last success: {0}", [frappe.datetime.str_to_user(frm.doc.last_successful_sync_at)]),
				"green"
			);
		}
		if (frm.doc.last_attempted_sync_at) {
			frm.dashboard.add_indicator(
				__("Last attempt: {0}", [frappe.datetime.str_to_user(frm.doc.last_attempted_sync_at)]),
				"blue"
			);
		}
		if (frm.doc.last_error) {
			frm.dashboard.add_indicator(__("Last run failed"), "red");
		}

		frm.add_custom_button(__("Open Providers"), () => {
			frappe.set_route("List", "Exchange Rate Provider");
		});

		if (frm.doc.primary_provider) {
			frm.add_custom_button(__("Open Primary Provider"), () => {
				frappe.set_route("Form", "Exchange Rate Provider", frm.doc.primary_provider);
			});
		}

		frm.add_custom_button(__("Sync Now"), async () => {
			const response = await frappe.call({
				method: "fab_exchange_rate_sync.sync.sync_now",
				freeze: true,
				freeze_message: __("Syncing exchange rates..."),
			});
			const summary = response.message || {};
			if (summary.status === "success") {
				frappe.show_alert({
					message: __("Exchange rate sync complete: {0} inserted, {1} updated.", [
						summary.inserted || 0,
						summary.updated || 0,
					]),
					indicator: "green",
				});
			} else {
				frappe.msgprint({
					title: __("Sync not run"),
					indicator: "orange",
					message: summary.message || __("No exchange rates were updated."),
				});
			}
			await frm.reload_doc();
		});
	},
});
