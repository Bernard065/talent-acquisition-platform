import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page scaffold", () => {
  it("renders the hero section with headline and CTA buttons", () => {
    const markup = renderToStaticMarkup(HomePage());

    // Hero Section
    expect(markup).toContain("AI-Driven");
    expect(markup).toContain("Talent Platform Built for Growth");
    expect(markup).toContain("Explore the benefits");
    expect(markup).toContain("See how it works");
    
    // Logos
    expect(markup).toContain("Trusted by these");
    expect(markup).toContain("Acme Corp");

    // Product Benefits Section
    expect(markup).toContain("Achieve more");
    expect(markup).toContain("with less effort");
    expect(markup).toContain("70");
    expect(markup).toContain("Reduction");
    expect(markup).toContain("97");
    expect(markup).toContain("50");
    expect(markup).toContain("Increase");
    expect(markup).toContain("Improve your time-to-hire");
    expect(markup).toContain("Reduce your admin work");
    expect(markup).toContain("Speed up your hiring");
  });
});
