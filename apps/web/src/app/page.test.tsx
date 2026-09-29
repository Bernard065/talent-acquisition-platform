import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page scaffold", () => {
  it("renders a minimal page without pretending recruiting data is connected", () => {
    const markup = renderToStaticMarkup(HomePage());

    expect(markup).toContain('<section aria-labelledby="page-title"');
    expect(markup).toContain("Frontend foundation");
    expect(markup).toContain("Authentication, live recruiting data");
    expect(markup).not.toContain("Candidate names");
  });
});
