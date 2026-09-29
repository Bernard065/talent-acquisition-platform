import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page scaffold", () => {
  it("renders a minimal page without pretending recruiting data is connected", () => {
    const markup = renderToStaticMarkup(HomePage());

    expect(markup).toContain("<main>");
    expect(markup).toContain("Frontend foundation");
    expect(markup).toContain("The workspace interface is being built.");
    expect(markup).not.toContain("candidate");
  });
});
