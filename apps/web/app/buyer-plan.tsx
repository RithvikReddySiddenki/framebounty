"use client";
import { useState } from "react";
import { request } from "./api";
import type { PlanProposal } from "./agent-pane";
import Funding from "./funding";

export default function BuyerPlan({
  token,
  initialPlan,
}: {
  token?: string;
  initialPlan?: PlanProposal;
}) {
  const chainMode = process.env.NEXT_PUBLIC_ENABLE_CHAIN_FUNDING === "true";
  const [total, setTotal] = useState(initialPlan?.total || 20);
  const [large, setLarge] = useState(
    initialPlan?.requirements.find((r) => r.key === "large_towel")?.minimum ||
      5,
  );
  const [dark, setDark] = useState(
    initialPlan?.requirements.find((r) => r.key === "dark_surface")?.minimum ||
      5,
  );
  const [hours, setHours] = useState(initialPlan?.review_hours || 72);
  const [largeDescription, setLargeDescription] = useState(
    initialPlan?.requirements.find((r) => r.key === "large_towel")
      ?.description ||
      "A large bath towel matching the buyer-approved reference example.",
  );
  const [darkDescription, setDarkDescription] = useState(
    initialPlan?.requirements.find((r) => r.key === "dark_surface")
      ?.description ||
      "A dark tabletop matching the buyer-approved reference example.",
  );
  const [rights, setRights] = useState(initialPlan?.rights_declaration || "");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [planHash, setPlanHash] = useState("");
  const [published, setPublished] = useState(false);
  const [fixtureConfirmed, setFixtureConfirmed] = useState(false);
  async function publishFixture() {
    if (!token || !fixtureConfirmed) return;
    setBusy(true);
    setError("");
    try {
      await request(`/jobs/${saved}/fixture-publish`, token, {
        plan_hash: planHash,
        confirmed: true,
      });
      setPublished(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Fixture publication failed",
      );
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!token) {
      setError("Connect and sign in before saving your plan.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await request<{ id: string; plan_hash: string }>(
        "/jobs",
        token,
        {
          version: 1,
          title: initialPlan?.title || "Towel-folding demonstrations",
          total,
          budget_atomic: total * 1000000,
          reward_atomic: 1000000,
          min_seconds: 10,
          max_seconds: 30,
          review_hours: hours,
          rights_declaration: rights,
          requirements: [
            {
              key: "large_towel",
              minimum: large,
              description: largeDescription,
            },
            {
              key: "dark_surface",
              minimum: dark,
              description: darkDescription,
            },
          ],
        },
      );
      setSaved(result.id);
      setPlanHash(result.plan_hash);
      setPublished(false);
      setFixtureConfirmed(false);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="buyer-edit">
      <h2>Make the terms yours</h2>
      <p className="muted">
        Each accepted clip earns 1 test USDC, with a maximum reward budget of 20
        test USDC. Gas and inference are separate. Category requirements may
        overlap.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
        onChange={() => {
          setConfirmed(false);
          setSaved("");
          setPublished(false);
          setFixtureConfirmed(false);
        }}
      >
        <div className="metrics">
          <div>
            <label htmlFor="clip-count">Total clips</label>
            <input
              id="clip-count"
              type="number"
              min={1}
              max={20}
              required
              value={total}
              onChange={(e) => setTotal(Number(e.target.value))}
            />
          </div>
          <div>
            <label htmlFor="large-count">Large-towel minimum</label>
            <input
              id="large-count"
              type="number"
              min={1}
              max={total}
              required
              value={large}
              onChange={(e) => setLarge(Number(e.target.value))}
            />
          </div>
          <div>
            <label htmlFor="dark-count">Dark-surface minimum</label>
            <input
              id="dark-count"
              type="number"
              min={1}
              max={total}
              required
              value={dark}
              onChange={(e) => setDark(Number(e.target.value))}
            />
          </div>
          <div>
            <label htmlFor="review-hours">Review window (hours)</label>
            <input
              id="review-hours"
              type="number"
              min={1}
              max={168}
              required
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            />
          </div>
        </div>
        <label htmlFor="large-description">Large-towel definition</label>
        <textarea
          id="large-description"
          required
          minLength={8}
          maxLength={1000}
          rows={2}
          value={largeDescription}
          onChange={(e) => setLargeDescription(e.target.value)}
        />
        <label htmlFor="dark-description">Dark-surface definition</label>
        <textarea
          id="dark-description"
          required
          minLength={8}
          maxLength={1000}
          rows={2}
          value={darkDescription}
          onChange={(e) => setDarkDescription(e.target.value)}
        />
        <label htmlFor="rights">
          Requested usage rights (contributors must acknowledge these before
          submitting)
        </label>
        <textarea
          id="rights"
          required
          minLength={10}
          maxLength={2000}
          rows={3}
          value={rights}
          onChange={(e) => setRights(e.target.value)}
          placeholder="Describe the intended dataset usage and requested license."
        />
        <p className="muted">
          Task completion must be human-reviewed. Your authenticated wallet will
          be the reviewer. If review is abandoned, the timeout releases funds
          rather than automatically paying the contributor. Reference-image
          attachment is still being implemented.
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => {
              e.stopPropagation();
              setConfirmed(e.target.checked);
            }}
          />
          I confirm these version 1 draft terms and the {total} test USDC reward
          budget.
        </label>
        <button className="primary" disabled={!confirmed || busy || !!saved}>
          {busy ? "Saving…" : saved ? "Draft saved" : "Confirm & save draft"}
        </button>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {saved && (
        <div className="notice" role="status">
          <p>
            Draft {saved} saved.{" "}
            {published
              ? "Two or fewer initial fixture slots are published. No blockchain transaction occurred."
              : chainMode
                ? "Follow the Arc testnet funding steps below. Listings wait for verified funding."
                : "This draft has not been published through fixture funding."}
          </p>
          {!published && !chainMode && (
            <>
              <label className="check">
                <input
                  type="checkbox"
                  checked={fixtureConfirmed}
                  onChange={(e) => setFixtureConfirmed(e.target.checked)}
                />
                For local testing, simulate this budget and publish a small
                fixture batch. These funds and rewards have no monetary value.
              </label>
              <button
                disabled={!fixtureConfirmed || busy}
                onClick={() => void publishFixture()}
              >
                Simulate funding & publish fixture tasks
              </button>
            </>
          )}
          {!published && token && chainMode && (
            <Funding
              key={saved}
              token={token}
              jobId={saved}
              planHash={planHash}
            />
          )}
        </div>
      )}
    </section>
  );
}
