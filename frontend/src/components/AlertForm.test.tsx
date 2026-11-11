import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../i18n";
import { stubFetch } from "../test/utils";
import { ManageAlerts } from "./AlertForm";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

describe("ManageAlerts", () => {
  it("asks for a link in the page's language", async () => {
    await i18n.changeLanguage("fr");
    const fetch = stubFetch({ "/api/alerts/manage": { status: "sent" } });
    render(<ManageAlerts />);

    await userEvent.click(screen.getByRole("button", { name: "Gérer mes alertes" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Adresse courriel" }), "a@b.c");
    await userEvent.click(screen.getByRole("button", { name: "M'envoyer un lien" }));

    expect(await screen.findByText(/un lien pour les gérer est en route/)).toBeTruthy();
    expect(fetch).toHaveBeenCalledWith("/api/alerts/manage", expect.objectContaining({
      body: JSON.stringify({ email: "a@b.c", language: "fr" }),
    }));
  });

  it("shows an error when sending fails", async () => {
    stubFetch({});
    render(<ManageAlerts />);

    await userEvent.click(screen.getByRole("button", { name: "Manage my alerts" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Email address" }), "a@b.c");
    await userEvent.click(screen.getByRole("button", { name: "Email me a link" }));

    expect(await screen.findByText("Failed to send the link. Please try again.")).toBeTruthy();
  });
});
