import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page scaffold", () => {
  it("renders the minimal placeholder page without pretending recruiting data is connected", () => {
    const markup = renderToStaticMarkup(HomePage());

    expect(markup).toContain("HomePage");
    expect(markup).not.toContain('data-slot="card"');
    expect(markup).not.toContain('data-slot="badge"');
    expect(markup).not.toContain("Frontend foundation");
    expect(markup).not.toContain("Candidate names");
  });
});
