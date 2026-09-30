import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page scaffold", () => {
  it("renders the hero section with headline and CTA buttons", () => {
    const markup = renderToStaticMarkup(HomePage());

    expect(markup).toContain("AI-Driven");
    expect(markup).toContain("Talent Platform Built for Growth");
    expect(markup).toContain("Explore the benefits");
    expect(markup).toContain("See how it works");
    expect(markup).toContain("Trusted by these");
    expect(markup).toContain("Acme Corp");
  });
});
