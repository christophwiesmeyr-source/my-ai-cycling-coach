---
title: Fix decoupling false positives with HR-reserve EF and a validity gate
status: draft   # see tasks/WORKFLOW.md for the lifecycle
release:        # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

### Abbreviations

| Symbol | Name | Meaning |
| --- | --- | --- |
| HR | heart rate | bpm |
| bpm | beats per minute | unit of HR |
| HR₀ | baseline heart rate | intercept of the HR–power line; HR extrapolated to zero watts. Not the same as measured resting HR (see below) |
| HR reserve | — | HR − HR₀, the part of heart rate attributable to the effort |
| HRmax | maximum heart rate | used only to bound the range where the affine model holds |
| P | power | mechanical power at the crank, watts |
| P̄ | mean power | arithmetic average over the window |
| NP | normalized power | a 30 s-smoothed, 4th-power-weighted average of power, intended to reflect metabolic cost of variable efforts. Always ≥ P̄ |
| VI | variability index | NP / P̄. 1.0 = perfectly steady; ~1.02 steady climb, ~1.12 rolling terrain |
| EF | efficiency factor | NP / HR. "Watts per beat" |
| EF* | HR-reserve efficiency factor | P̄ / (HR − HR₀). The proposed replacement |
| Pw:Hr | power-to-HR decoupling | relative change in EF from the first to the second half of a ride, in %. The metric being fixed |
| k | HR–power slope | bpm per watt; the marginal cardiac cost of a watt |
| FTP | functional threshold power | roughly the highest power sustainable ~1 h; the anchor for training zones. Currently 335 W |
| Z2 | zone 2 | endurance intensity, roughly 55–75% of FTP |
| tempo | — | the zone above Z2, roughly 75–90% of FTP |
| Friel threshold | — | the convention that Pw:Hr above 5% indicates aerobic decoupling |

Physiological note on the two mechanisms that decoupling is meant to detect:
**cardiac drift** (HR rises over time at constant power, driven by
thermoregulation and plasma volume loss) and **efficiency loss** (more beats
per watt, driven by substrate depletion and fatigue). Both raise Pw:Hr.

### Description

The coach reports aerobic decoupling as Pw:Hr: efficiency factor `EF = NP / HR`
computed over the first and second half of an activity, compared as a relative
change, flagged against the 5% Friel threshold. This is what intervals.icu does
and what the app inherited.

The metric produces frequent false positives on real rides. Diagnosis:

**1. The intercept artifact (dominant).** Under the affine model
`HR = HR₀ + k·P`, the elasticity of EF with respect to power is

    d ln EF / d ln P = HR₀ / HR

i.e. the sensitivity of EF to power equals the fraction of heart rate that is
baseline — roughly 0.36 at typical endurance HR. A 10% difference in average
power between halves therefore shifts EF by ~3.6% with *zero* physiological
drift. Rides that fade in power (the common case here: climb early, easy roll
home) manufacture a threshold breach on their own. Negative-split rides
manufacture the opposite and *mask* real drift.

Worked example, no drift whatsoever: 230 W first half / 195 W second, HR₀ = 48,
k = 0.358 → Pw:Hr = +6.2%, flagged.

**2. Stops are the limiting case.** At P → 0, EF → 0 while HR remains at
90–120 bpm. Each stopped sample contributes a ratio of 0 to a mean that should
be ~1.7. Rides with stops or hike-a-bike sections in one half are destroyed.
(Open question: whether intervals.icu ingests these on moving or elapsed time.)

**3. The VI artifact (independent, can run opposite in sign).** EF's numerator
is NP (4th-power weighted) while HR integrates roughly linearly and so tracks
*mean* power. EF therefore scales directly with VI. Identical mean power in
both halves with VI 1.02 → 1.12 gives a fabricated Pw:Hr of about −10%.

On mixed terrain both artifacts fire simultaneously and can reach 10–15%. The
metric is not merely noisy there; it is uninformative.

**4. It inverts under deep fatigue.** Severe autonomic fatigue suppresses HR,
raising EF in the second half and driving decoupling negative while performance
is actually collapsing (observed on RACA day 4). The metric fails precisely in
the regime where durability matters most.

**Empirical confirmation.** On a flagged ride, the intervals.icu P/HR-vs-time
panel shows the trend line falling ~1.55 → ~0.85 (a ~45% collapse), while the
HR-vs-power scatter for the same ride shows the first- and second-half point
clouds and fitted lines as near-coincident. Both cannot describe the same
physiology. The reconciliation is that the ratio is being destroyed by the
power distribution, not by cardiac drift.

**Consequence.** The coach flags decoupling on most rides. Because the flag is
usually an artifact of the power profile, it carries no information and is
being ignored — which also means a genuine drift signal would go unnoticed.
The metric additionally conflates "no drift detected" with "cannot be
determined from this ride", in the wrong direction.

### Scope of this story

This is the cheap, high-value mitigation that works on existing data and can
ship well before the fitted model (story:
`0012-decoupling-fitted-drift-model`). Three changes:

**a. Replace EF with HR-reserve EF.** `EF* = P̄ / (HR − HR₀)`. Under the affine
model this equals 1/k exactly, independently of power level, so the intercept
artifact vanishes. The same 230/195 W example gives 2.795 vs 2.794 → 0.0%
drift. Cost is noise amplification of roughly HR/(HR − HR₀) ≈ 1.55, and a
dependence on HR₀ — but the HR₀ sensitivity largely cancels in the ratio, so a
5 bpm misestimate perturbs the reported drift by ~5% *of itself*, not by 5
percentage points.

**b. Use mean (or lag-filtered) power rather than NP in the numerator.** This
removes the VI artifact, which is the second-largest term on mixed terrain and
can run opposite in sign to the first.

**c. Add a validity gate.** Compute Δln P̄ and ΔVI between halves; above a
threshold, report "decoupling unreliable on this profile" instead of a number.
Distinguishing "no drift" from "cannot tell" is the point.

HR₀ should be treated as a **fitted nuisance parameter**, not measured resting
HR: regress HR on lagged power across a batch of Z2–tempo rides below ~85%
HRmax and take the intercept. It will land above true resting HR because
postural and cycling-baseline effects are absorbed into it, and that is
correct — the goal is the intercept that makes EF* invariant over the working
range, not a physiologically literal number. Refit periodically as fitness and
plasma volume change.

A diagnostic worth running once on ride history, which both confirms the
diagnosis and retro-corrects it: regress reported Pw:Hr on Δln P̄ across all
rides. A slope near 0.36 confirms the flags are power-profile artifacts; the
intercept is the artifact-corrected mean drift and the residuals give a
de-artifacted decoupling per historical ride.

Caveats to carry forward. EF* removes a *known* artifact; it does not make the
remaining signal clean, since thermoregulatory, plasma-volume and glycogen
mechanisms stay tangled. The correction is two-sided: rides previously clean
because they were negative-split may start flagging, correctly. And EF* still
inherits the arbitrary half-split and still cannot separate intercept drift
from slope change — those are what story 02 addresses.

## Acceptance Criteria

<!-- Checklist of concrete, verifiable outcomes. -->

- [ ]

## Technical Decisions

<!-- Code-related decisions made during drafting, with rationale. -->

## Test Plan

<!-- How to verify the implementation once done: manual steps and/or
     specific automated tests to add/run. -->

## Out of Scope

<!-- Explicit non-goals, to prevent scope creep during implementation. -->

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->
