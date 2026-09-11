import { getCurrentUser, identifyUser, loginAdmin } from "../lib/api";

const page = document.querySelector<HTMLElement>("[data-identity-page]");

if (page) {
	const nameForm = page.querySelector<HTMLFormElement>("[data-name-form]");
	const passwordForm = page.querySelector<HTMLFormElement>("[data-password-form]");
	const nameInput = page.querySelector<HTMLInputElement>("#identity-name");
	const passwordInput = page.querySelector<HTMLInputElement>("#admin-password");
	const nameError = page.querySelector<HTMLElement>("[data-name-error]");
	const passwordError = page.querySelector<HTMLElement>("[data-password-error]");
	const heading = page.querySelector<HTMLElement>("[data-welcome-heading]");
	const welcomeCopy = page.querySelector<HTMLElement>("[data-welcome-copy]");
	let pendingAdminName = "";

	const getReturnPath = (): string => {
		const value = new URLSearchParams(window.location.search).get("returnTo");
		return value?.startsWith("/") && !value.startsWith("//") && !value.startsWith("/signin")
			? value
			: "/";
	};

	const redirectToApplication = (): void => window.location.replace(getReturnPath());

	const showError = (element: HTMLElement | null, message: string): void => {
		if (!element) return;
		element.textContent = message;
		element.hidden = false;
	};

	const clearError = (element: HTMLElement | null): void => {
		if (!element) return;
		element.textContent = "";
		element.hidden = true;
	};

	const verifySessionAndRedirect = async (): Promise<void> => {
		const user = await getCurrentUser();
		if (!user) {
			throw new Error("The browser did not accept the session cookie.");
		}
		redirectToApplication();
	};

	nameForm?.addEventListener("submit", async (event) => {
		event.preventDefault();
		clearError(nameError);
		const name = nameInput?.value.trim() ?? "";
		if (!name) {
			showError(nameError, "Enter your name to continue.");
			return;
		}

		const submitButton = nameForm.querySelector<HTMLButtonElement>('button[type="submit"]');
		if (submitButton) submitButton.disabled = true;
		try {
			const result = await identifyUser(name);
			if (!result.requires_password) {
				await verifySessionAndRedirect();
				return;
			}

			pendingAdminName = name;
			nameForm.hidden = true;
			if (passwordForm) passwordForm.hidden = false;
			if (heading) heading.textContent = "Welcome back, Kenek";
			if (welcomeCopy) welcomeCopy.textContent = "Enter your password to continue.";
			passwordInput?.focus();
		} catch (error: unknown) {
			const message = error instanceof Error && error.message.includes("session cookie")
				? "The session cookie was not accepted. HTTPS is required for cross-site cookies."
				: "Unable to connect to MCPanel. Try again.";
			showError(nameError, message);
		} finally {
			if (submitButton) submitButton.disabled = false;
		}
	});

	passwordForm?.addEventListener("submit", async (event) => {
		event.preventDefault();
		clearError(passwordError);
		const password = passwordInput?.value ?? "";
		if (!password) {
			showError(passwordError, "Enter your password.");
			return;
		}

		const submitButton = passwordForm.querySelector<HTMLButtonElement>('button[type="submit"]');
		if (submitButton) submitButton.disabled = true;
		try {
			await loginAdmin(pendingAdminName, password);
			await verifySessionAndRedirect();
		} catch {
			showError(passwordError, "Invalid credentials.");
			if (passwordInput) {
				passwordInput.value = "";
				passwordInput.focus();
			}
		} finally {
			if (submitButton) submitButton.disabled = false;
		}
	});

	page.querySelector<HTMLButtonElement>("[data-use-another-name]")?.addEventListener("click", () => {
		pendingAdminName = "";
		if (passwordInput) passwordInput.value = "";
		clearError(passwordError);
		if (passwordForm) passwordForm.hidden = true;
		if (nameForm) nameForm.hidden = false;
		if (heading) heading.textContent = "Welcome to the Homelab";
		if (welcomeCopy) welcomeCopy.textContent = "Enter your name to continue.";
		nameInput?.focus();
	});

	void getCurrentUser().then((user) => {
		if (user) redirectToApplication();
	}).catch(() => undefined);
}
