import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

describe("shadcn UI primitives", () => {
  it("merges caller utility classes without conflicting duplicates", () => {
    const classes = cn("px-2 py-1", "px-4");

    expect(classes).toContain("px-4");
    expect(classes).not.toContain("px-2");
    expect(classes).toContain("py-1");
  });

  it("renders button variants and preserves native disabled behavior", () => {
    const markup = renderToStaticMarkup(
      createElement(
        Button,
        { disabled: true, size: "sm", variant: "outline" },
        "Save changes",
      ),
    );

    expect(markup).toContain('data-slot="button"');
    expect(markup).toContain('data-variant="outline"');
    expect(markup).toContain('data-size="sm"');
    expect(markup).toContain('disabled=""');
    expect(markup).toContain("Save changes");
  });

  it("renders status badges and composable cards with semantic slots", () => {
    const markup = renderToStaticMarkup(
      createElement(
        Card,
        null,
        createElement(CardTitle, null, "Requisition status"),
        createElement(
          CardContent,
          null,
          createElement(Badge, { variant: "secondary" }, "Open"),
        ),
      ),
    );

    expect(markup).toContain('data-slot="card"');
    expect(markup).toContain('data-slot="card-title"');
    expect(markup).toContain('data-slot="card-content"');
    expect(markup).toContain('data-slot="badge"');
    expect(markup).toContain("Open");
  });

  it("connects a label to an input and exposes invalid state", () => {
    const markup = renderToStaticMarkup(
      createElement(
        "div",
        null,
        createElement(Label, { htmlFor: "work-email" }, "Work email"),
        createElement(Input, {
          "aria-invalid": true,
          id: "work-email",
          name: "email",
          type: "email",
        }),
      ),
    );

    expect(markup).toContain('for="work-email"');
    expect(markup).toContain('id="work-email"');
    expect(markup).toContain('data-slot="input"');
    expect(markup).toContain('aria-invalid="true"');
  });
});
