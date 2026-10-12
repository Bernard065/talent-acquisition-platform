"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { useApplicationOffers, useCreateApplicationOffer } from "@/lib/api/hooks/offers";
import type { ApplicationStatus, OfferPayPeriod, OfferResponse, OfferStatus } from "@/types/api";

const ACTIVE_OFFER_STATUSES: ReadonlySet<OfferStatus> = new Set([
  "draft",
  "pending_approval",
  "approved",
  "sent",
]);

const OFFER_STATUS_LABELS: Record<OfferStatus, string> = {
  draft: "Draft",
  pending_approval: "Pending approval",
  approved: "Approved",
  sent: "Sent",
  accepted: "Accepted",
  declined: "Declined",
  expired: "Expired",
  cancelled: "Cancelled",
};

function formatMoney(amount: string | number, currency: string): string {
  return `${currency} ${Number(amount).toLocaleString("en", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatUtcDateTime(value: string): string {
  return `${new Date(value).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function OfferCard({ offer }: { offer: OfferResponse }) {
  return (
    <li className="rounded-lg border border-gray-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            {formatMoney(offer.base_salary, offer.currency)} {offer.pay_period === "annually" ? "per year" : "per month"}
          </h3>
          <p className="mt-1 text-sm text-gray-600">
            Proposed start date: {offer.proposed_start_date}
          </p>
        </div>
        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800">
          {OFFER_STATUS_LABELS[offer.status]}
        </span>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Expires</dt>
          <dd className="mt-1 text-gray-800">{formatUtcDateTime(offer.expires_at)}</dd>
        </div>
        {offer.bonus_amount !== null && (
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Bonus</dt>
            <dd className="mt-1 text-gray-800">{formatMoney(offer.bonus_amount, offer.currency)}</dd>
          </div>
        )}
        {offer.equity_summary && (
          <div className="sm:col-span-2">
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Equity</dt>
            <dd className="mt-1 whitespace-pre-wrap text-gray-800">{offer.equity_summary}</dd>
          </div>
        )}
      </dl>
    </li>
  );
}

function CreateOfferForm({
  applicationId,
  onError,
}: {
  applicationId: string;
  onError: (message: string | null) => void;
}) {
  const [currency, setCurrency] = useState("KES");
  const [baseSalary, setBaseSalary] = useState("");
  const [payPeriod, setPayPeriod] = useState<OfferPayPeriod>("monthly");
  const [bonusAmount, setBonusAmount] = useState("");
  const [equitySummary, setEquitySummary] = useState("");
  const [proposedStartDate, setProposedStartDate] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const mutation = useCreateApplicationOffer();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!baseSalary || !proposedStartDate || !expiresAt) return;
    const expiresAtDate = new Date(expiresAt);
    if (Number.isNaN(expiresAtDate.getTime()) || expiresAtDate.getTime() <= Date.now()) {
      onError("Choose an expiry date and time in the future.");
      return;
    }

    onError(null);
    mutation.mutate({
      applicationId,
      offer: {
        currency: currency.trim().toUpperCase(),
        base_salary: baseSalary,
        pay_period: payPeriod,
        bonus_amount: bonusAmount || null,
        equity_summary: equitySummary.trim() || null,
        proposed_start_date: proposedStartDate,
        expires_at: expiresAtDate.toISOString(),
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onError: () => onError("We couldn’t create the draft offer. Check the terms and try again."),
    });
  }

  return (
    <form className="mt-5 grid gap-4 border-t border-gray-100 pt-5 sm:grid-cols-2" onSubmit={submit}>
      <h3 className="text-sm font-semibold text-gray-900 sm:col-span-2">Create a draft offer</h3>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Currency</span>
        <input
          required
          minLength={3}
          maxLength={3}
          value={currency}
          onChange={(event) => setCurrency(event.target.value.replace(/[^a-z]/gi, "").toUpperCase())}
          className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm uppercase outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          aria-describedby="offer-currency-help"
        />
        <span id="offer-currency-help" className="mt-1 block text-xs text-gray-500">Three-letter currency code, for example KES or USD.</span>
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Base salary</span>
        <input
          required
          type="number"
          min="0.01"
          step="0.01"
          value={baseSalary}
          onChange={(event) => setBaseSalary(event.target.value)}
          className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
        />
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Pay period</span>
        <select
          value={payPeriod}
          onChange={(event) => setPayPeriod(event.target.value as OfferPayPeriod)}
          className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
        >
          <option value="monthly">Monthly</option>
          <option value="annually">Annually</option>
        </select>
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Bonus (optional)</span>
        <input
          type="number"
          min="0"
          step="0.01"
          value={bonusAmount}
          onChange={(event) => setBonusAmount(event.target.value)}
          className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
        />
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Proposed start date</span>
        <input
          required
          type="date"
          value={proposedStartDate}
          onChange={(event) => setProposedStartDate(event.target.value)}
          className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
        />
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Offer expiry</span>
        <input
          required
          type="datetime-local"
          value={expiresAt}
          onChange={(event) => setExpiresAt(event.target.value)}
          className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
        />
      </label>
      <label className="sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-gray-700">Equity summary (optional)</span>
        <textarea
          rows={3}
          maxLength={5000}
          value={equitySummary}
          onChange={(event) => setEquitySummary(event.target.value)}
          className="w-full rounded-lg border border-gray-200 p-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
        />
      </label>
      <div className="sm:col-span-2">
        <Button type="submit" disabled={mutation.isPending || currency.length !== 3 || !baseSalary || !proposedStartDate || !expiresAt}>
          {mutation.isPending ? "Creating offer…" : "Create draft offer"}
        </Button>
        {mutation.isSuccess && <p className="mt-2 text-sm text-green-800" role="status">Draft offer created.</p>}
      </div>
    </form>
  );
}

export function ApplicationOfferSection({
  applicationId,
  applicationStatus,
}: {
  applicationId: string;
  applicationStatus: ApplicationStatus;
}) {
  const offersQuery = useApplicationOffers(applicationId);
  const [formError, setFormError] = useState<string | null>(null);
  const offers = offersQuery.data?.items ?? [];
  const hasActiveOffer = offers.some((offer) => ACTIVE_OFFER_STATUSES.has(offer.status));

  return (
    <section aria-labelledby="application-offers-heading" className="rounded-xl border border-gray-200 bg-white p-6">
      <div>
        <h2 id="application-offers-heading" className="text-base font-semibold text-sr-text-blue">Offer</h2>
        <p className="mt-1 text-sm text-gray-600">Create and review compensation terms for this candidate.</p>
      </div>

      {offersQuery.isLoading ? (
        <p className="mt-4 text-sm text-gray-500" role="status">Loading offer details…</p>
      ) : offersQuery.isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-red-800">We couldn’t load offers for this application.</p>
          <Button type="button" variant="outline" onClick={() => void offersQuery.refetch()}>Try again</Button>
        </div>
      ) : (
        <>
          {offers.length ? (
            <ul className="mt-4 space-y-3">{offers.map((offer) => <OfferCard key={offer.id} offer={offer} />)}</ul>
          ) : (
            <p className="mt-4 text-sm text-gray-600">
              {applicationStatus === "offer"
                ? "No offer has been drafted for this application yet."
                : "Move the application to the Offer stage before creating an offer."}
            </p>
          )}

          {applicationStatus === "offer" && !hasActiveOffer && (
            <CreateOfferForm applicationId={applicationId} onError={setFormError} />
          )}
          {formError && <p className="mt-3 text-sm text-red-800" role="alert">{formError}</p>}
        </>
      )}
    </section>
  );
}
