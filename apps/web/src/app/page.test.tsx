import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page scaffold", () => {
  it("renders the minimal placeholder page without pretending recruiting data is connected", () => {
    const markup = renderToStaticMarkup(HomePage());

    expect(markup).toContain("MindHire");
    expect(markup).toContain("Request a Demo");
    expect(markup).toContain("Learn More");
    expect(markup).not.toContain('data-slot="card"');
    expect(markup).not.toContain('data-slot="badge"');
  });
});
