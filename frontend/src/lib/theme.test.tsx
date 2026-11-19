import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThemeMenu } from "@/components/ThemeMenu";
import { TooltipProvider } from "@/components/ui/tooltip";
import { resolveTheme, THEME_STORAGE_KEY, ThemeProvider } from "@/lib/theme";

describe("resolveTheme", () => {
  it("follows the OS for 'system' and obeys a manual choice", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
  });
});

describe("theme switch", () => {
  it("sets data-theme on <html> and remembers the choice", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <TooltipProvider>
          <ThemeMenu />
        </TooltipProvider>
      </ThemeProvider>,
    );
    expect(document.documentElement.dataset.theme).toBe("light"); // jsdom's matchMedia says "not dark"
    await user.click(screen.getByRole("button", { name: "Appearance" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    await user.click(screen.getByRole("button", { name: "Appearance" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Match my device" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });
});
