import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../i18n";
import { stubFetch } from "../test/utils";
import { AlertsDialog } from "./AlertForm";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

describe("AlertsDialog", () => {
  it("opens the create form and closes on cancel", async () => {
    render(<AlertsDialog sensors={["garden"]} />);

    await userEvent.click(screen.getByRole("button", { name: /Set alert/ }));
    expect(screen.getByText("New weather alert")).toBeTruthy();
    expect(screen.getByRole("dialog").hasAttribute("open")).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("New weather alert")).toBeNull();
  });

  it("asks hours, not above or below, for an offline alert", async () => {
    const fetch = stubFetch({ "/api/alerts": { status: "confirmation_sent" } });
    render(<AlertsDialog sensors={["garden"]} />);

    await userEvent.click(screen.getByRole("button", { name: /Set alert/ }));
    await userEvent.selectOptions(screen.getByDisplayValue("Temperature"), "offline");
    expect(screen.queryByDisplayValue("below")).toBeNull();
    await userEvent.type(screen.getByRole("spinbutton", { name: "Hours" }), "6");
    await userEvent.type(screen.getByPlaceholderText("Email address"), "a@b.c");
    await userEvent.click(screen.getByRole("button", { name: "Create alert" }));

    expect(await screen.findByText("Check your email to confirm the alert.")).toBeTruthy();
    expect(fetch).toHaveBeenCalledWith("/api/alerts", expect.objectContaining({
      body: JSON.stringify({ email: "a@b.c", sensor: "garden", field: "offline", condition: "above", threshold: 6, language: "en" }),
    }));
  });

  it("asks for a link in the page's language", async () => {
    await i18n.changeLanguage("fr");
    const fetch = stubFetch({ "/api/alerts/manage": { status: "sent" } });
    render(<AlertsDialog sensors={[]} />);

    await userEvent.click(screen.getByRole("button", { name: /Créer une alerte/ }));
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
    render(<AlertsDialog sensors={[]} />);

    await userEvent.click(screen.getByRole("button", { name: /Set alert/ }));
    await userEvent.click(screen.getByRole("button", { name: "Manage my alerts" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Email address" }), "a@b.c");
    await userEvent.click(screen.getByRole("button", { name: "Email me a link" }));

    expect(await screen.findByText("Failed to send the link. Please try again.")).toBeTruthy();
  });
});
