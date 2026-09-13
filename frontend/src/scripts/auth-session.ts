import { getCurrentUser, logoutUser } from "../lib/api";

const protectedContent = document.querySelector<HTMLElement>("[data-protected-content]");

if (protectedContent) {
	const signInUrl = (): string => {
		const returnTo = `${window.location.pathname}${window.location.search}`;
		return `/signin?returnTo=${encodeURIComponent(returnTo)}`;
	};

	const checkSession = async (): Promise<void> => {
		try {
			const user = await getCurrentUser();
			if (!user) {
				window.location.replace(signInUrl());
				return;
			}

			for (const element of document.querySelectorAll<HTMLElement>("[data-current-user-name]")) {
				element.textContent = user.name;
			}
			for (const element of document.querySelectorAll<HTMLElement>("[data-current-user-access]")) {
				element.textContent = user.isAdmin ? "Administrator" : "Normal access";
			}
			protectedContent.hidden = false;
			window.dispatchEvent(new CustomEvent("mcpanel:session-ready", { detail: user }));
		} catch {
			window.location.replace(signInUrl());
		}
	};

	for (const button of document.querySelectorAll<HTMLButtonElement>("[data-sign-out]")) {
		button.addEventListener("click", async () => {
			button.disabled = true;
			try {
				await logoutUser();
			} finally {
				window.location.replace("/signin");
			}
		});
	}

	void checkSession();
}
