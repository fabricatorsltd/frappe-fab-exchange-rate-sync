frappe.ui.form.on("Exchange Rate Provider", {
	refresh(frm) {
		frm.set_intro(
			__(
				"These provider records are shipped by the app. Edit credentials and plan limits here, but new provider integrations must be added in code."
			),
			"blue"
		);
	},
});
