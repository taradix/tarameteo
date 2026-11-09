import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../i18n";
import LanguageToggle from "./LanguageToggle";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

describe("LanguageToggle", () => {
  it("switches between English and French", async () => {
    await i18n.changeLanguage("en");
    render(<LanguageToggle />);

    await userEvent.click(screen.getByRole("button", { name: "Passer en français" }));
    expect(i18n.language).toBe("fr");

    await userEvent.click(screen.getByRole("button", { name: "Switch to English" }));
    expect(i18n.language).toBe("en");
  });

  it("treats a regional English locale as English", async () => {
    await i18n.changeLanguage("en-US");
    render(<LanguageToggle />);

    await userEvent.click(screen.getByRole("button", { name: "Passer en français" }));
    expect(i18n.language).toBe("fr");
  });
});
