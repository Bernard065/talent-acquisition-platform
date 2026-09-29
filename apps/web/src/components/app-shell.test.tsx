import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppShell } from "./app-shell";

describe("AppShell", () => {
  it("provides a skip link, navigation, and a single main landmark", () => {
    const markup = renderToStaticMarkup(
      createElement(
        AppShell,
        null,
        createElement("h1", null, "Frontend foundation"),
      ),
    );

    expect(markup).toContain('href="#main-content"');
    expect(markup).toContain('aria-label="Main navigation"');
    expect(markup).toContain('aria-current="page"');
    expect(markup.match(/<main\b/g)).toHaveLength(1);
    expect(markup).toContain('id="main-content"');
  });

  it("marks unfinished areas and sign-in as unavailable rather than interactive", () => {
    const markup = renderToStaticMarkup(createElement(AppShell));

    expect(markup).toContain('aria-disabled="true"');
    expect(markup).toContain('disabled=""');
    expect(markup).toContain("API not connected");
    expect(markup).toContain("Sign-in not configured");
    expect(markup).toContain("No recruiting data loaded");
  });
});
