---
title: Replace half-split decoupling with a fitted HR–power drift model
status: draft   # see tasks/WORKFLOW.md for the lifecycle
release:        # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

### Abbreviations

#### Training / physiology

| Symbol | Name | Meaning |
| --- | --- | --- |
| HR | heart rate | bpm |
| bpm | beats per minute | unit of HR |
| HR₀ | baseline heart rate | intercept of the HR–power line; HR extrapolated to zero watts. Not measured resting HR |
| HRmax | maximum heart rate | bounds the range where the affine model holds (~85% HRmax) |
| P | power | mechanical power at the crank, watts |
| P̄ | mean power | arithmetic average over the window |
| P̃ | lagged power | power passed through a first-order lag, `dP̃/dt = (P − P̃)/τ`, τ ≈ 30–45 s, to match HR's response dynamics |
| NP | normalized power | 30 s-smoothed, 4th-power-weighted average of power. Used by the old metric; **not** used here |
| VI | variability index | NP / P̄; 1.0 = perfectly steady |
| EF | efficiency factor | NP / HR; the old metric's building block |
| EF* | HR-reserve efficiency factor | P̄ / (HR − HR₀); the story-01 interim fix |
| Pw:Hr | power-to-HR decoupling | relative change in EF between ride halves, %; the metric being replaced |
| k | HR–power slope | bpm per watt; marginal cardiac cost of a watt |
| FTP | functional threshold power | ~1 h sustainable power; anchor for zones. Currently 335 W |
| Z2 / tempo | zone 2 / tempo | endurance (~55–75% FTP) and the zone above it (~75–90% FTP) |
| cardiac drift | — | HR rises over time at constant power (thermoregulation, plasma volume loss). Shows up as **intercept shift** |
| efficiency loss | — | more beats per watt (substrate shift, fatigue, fibre recruitment). Shows up as **slope change** |

#### Statistics / modelling

| Symbol | Name | Meaning |
| --- | --- | --- |
| β₀…β₃ | regression coefficients | see model below |
| ε | residual | unexplained variation |
| t, tc | time, centered time | tc = t − T/2, in hours |
| P̃c | centered lagged power | P̃ − median(P̃) |
| g(t) | drift basis function | the assumed *shape* of drift over time (step, linear, saturating, spline) |
| h | half indicator | 1 in the second half of the ride, 0 in the first |
| OLS | ordinary least squares | standard linear regression |
| errors-in-variables | — | regression where the *predictor* is noisy, which biases the slope toward zero |
| attenuation | regression dilution | that bias: slope shrinks by σ²_signal/(σ²_signal + σ²_noise) |
| Deming regression | — | a fit that accounts for noise in both variables |
| n_eff | effective sample size | how many *independent* observations the data is worth; far below n when samples are autocorrelated |
| AR(1) | first-order autoregressive | error model where each residual correlates with the previous one |
| HAC | heteroskedasticity- and autocorrelation-consistent | standard errors robust to both |
| VIF | variance inflation factor | how much a coefficient's variance is inflated by correlation among predictors; >5–10 signals a problem |
| CI | confidence interval | — |
| partial pooling | hierarchical / mixed model | estimating per-ride parameters while borrowing strength from ride history |

### Description

Depends on `0011-decoupling-hr-reserve-ef`, which documents the full diagnosis of
why the classic Pw:Hr metric produces false positives. Summary of that
diagnosis: EF = NP/HR is a ratio evaluated at two different operating points,
so it responds to the *power profile* rather than to physiology. Its elasticity
with respect to power is HR₀/HR ≈ 0.36, so a 10% power fade between halves
fabricates ~3.6% decoupling; NP in the numerator adds an independent VI-driven
artifact that can run opposite in sign; and stopped samples (EF → 0 at nonzero
HR) are the limiting case.

Story 01 fixes the intercept and VI artifacts cheaply. It does **not** address
three remaining structural problems:

**1. The half-split is a spreadsheet-era hack, and its output scales with ride
duration.** It discards the ordering information within each half and collapses
each to a single mean (wasteful of variance). Worse, it reports a total rather
than a rate. If drift is linear at γ bpm/hr, the half means sit at t = T/4 and
t = 3T/4, so with power held constant

    Pw:Hr ≈ γ·T / (2·HR)

The reported number is proportional to ride duration, which makes the fixed 5%
threshold a *different physiological criterion at every duration*. At HR 140,
5% implies ΔHR ≈ 7 bpm between half means, i.e. γ ≈ 9.3 bpm/hr on a 1.5 h ride,
4.7 on a 3 h ride, 2.3 on a 6 h ride — a fourfold range of drift rates all
receiving the identical flag, with the physiologically most impressive ride
treated worst.

This also corrupts the common coaching practice of tracking decoupling across a
season, because ride duration correlates with training phase (long steady base
blocks, shorter harder build blocks). Reported decoupling then falls on moving
from base to build for purely arithmetic reasons, precisely when a coach is
looking for evidence that the base work succeeded. Seasonal temperature is a
second confound pointing the same way. β₂ removes the duration one entirely.

Note also that duration governs *precision*: SE(β₂) ≈ σ_ε / (√n_eff · SD(t)),
and since n_eff grows roughly linearly with T while SD(t) = T/√12, SE(β₂)
scales like T^(−3/2). A 6 h ride estimates β₂ roughly eight times more
precisely than a 90 min one. This is a better-founded version of the
TrainingPeaks heuristic that efforts under 20 minutes are not valid: rather
than a duration cutoff, report β₂ with its confidence interval and let short
rides come back wide. "Drift 2.1 ± 4.8 bpm/hr" is honest where "3.2%
decoupling" from the same ride is false precision.

**2. A scalar cannot separate the two mechanisms.** Cardiac drift and
efficiency loss are physiologically distinct and warrant different responses,
but every scalar decoupling metric averages them into one number.

**3. It cannot say "I don't know."** Story 01's gate is a heuristic on Δln P̄
and ΔVI; a fitted model gives identifiability diagnostics directly.

**Empirical motivation.** On a flagged ride, the intervals.icu P/HR-vs-time
panel shows the trend line collapsing ~1.55 → ~0.85 (≈45%), while the
HR-vs-power scatter for the same ride shows first- and second-half point clouds
and fitted lines that are near-coincident. The scatter is the better
representation because it compares *parameters of the HR–power relationship*
rather than a ratio of means at two operating points, and is therefore
invariant to how power was distributed within the ride. The affine model is
built into it by construction. It also decomposes drift into two readable
components:

- **intercept shift ΔHR₀** (line translates up): same cost per watt, higher
  baseline → thermoregulatory drift, plasma volume loss, reduced stroke volume
  compensated by rate;
- **slope change Δk** (line rotates): the marginal cost of a watt changed →
  substrate shift, recruitment of less efficient fibres, mechanical efficiency
  loss.

"At the same power my HR was 4 bpm higher" is a substantially more useful coach
output than "your decoupling was 8%".

### Proposed model

Fit per activity, on centered variables, using lagged power P̃ rather than raw
power (raw power traces a hysteresis loop against HR: below the line on rising
power, above it on falling):

    HR = β₀ + β₁·(P̃ − P_ref) + β₂·(t − t_ref) + β₃·(t − t_ref)(P̃ − P_ref) + ε

with t in hours. Centering does not change the fit but is essential to
interpretation: uncentered, β₂ would be the drift rate *at zero watts*, an
extrapolation to a point never occupied. Centered:

- β₀ = HR at P_ref, at t_ref
- β₁ = k, marginal cardiac cost, bpm/W
- **β₂ = drift at P_ref, bpm/hr** ← the headline coach output
- β₃ = change in marginal cost, bpm/W/hr

**The reference point must be global, not per-ride.** An earlier draft of this
story specified P_ref = median(P̃) of the ride and t_ref = T/2. That is correct
for interpreting β₂ *within* a single ride, but it silently destroys
cross-ride comparability: each ride's β₀ then sits at that ride's own median
power and its own midpoint, so β₀ values cannot be compared across rides or
tracked over a season. Fix P_ref and t_ref once per athlete (e.g. P_ref =
200 W, t_ref = 1 h) and hold them constant across the whole history.

This is what makes a **standardized EF** possible — the fitted surface
evaluated at (P_ref, t_ref), rather than an average over whatever the ride
happened to be. Duration, power level and VI all drop out, because the output
is a point on a fitted relationship instead of a mean over the observed
distribution. That is the longitudinal payoff: current practice can only
compare EF between deliberately matched benchmark rides (same duration, same
terrain, same intensity, ideally indoors), which discards nearly every ride an
athlete actually does. This recovers a comparable number from ordinary rides.

Caveat: standardizing to a fixed P_ref means extrapolating on rides whose power
range does not cover it, using a slope attenuated by errors-in-variables (see
below). The bias grows with distance from the ride's own power centroid. Gate
the standardized EF on P_ref lying inside the ride's sampled power range. This
is still a restriction, but a far weaker one than matched benchmark rides.

Reporting both β₂ at the global P_ref and at the ride's own median may be
worthwhile: the former for tracking, the latter for "what happened on this
ride".

This is one member of a family sharing a drift basis g(t):

    HR = β₀ + β₁P̃ + β₂·g(t) + β₃·(g(t)·P̃)

with g(t) = 1{t > T/2} the half-split, g(t) = t the linear form above,
g(t) = 1 − e^(−t/T_c) a saturating form (closer to the true shape of
thermoregulatory drift), or a spline basis. Linear should be the default; the
step version is worth retaining as a **specification check** rather than as a
reported metric, since it is the one form that makes no assumption about drift
*shape*. Material disagreement between step and linear estimates indicates the
shape is wrong. On 5+ hour rides the saturating basis is expected to fit
noticeably better than linear.

One caveat on duration-invariance. β₂ is invariant to T *under linearity*, by
algebra. If drift actually saturates, a long ride samples more of the plateau
and returns a lower β₂ — so β₂ becomes a duration-weighted average and is not
strictly comparable between a 90 min Z2 ride and a 6 h event simulation. That
residual dependence is real physiology, not an artifact, but it is the actual
argument for the saturating basis: its asymptote and time constant T_c are
duration-free where a slope is not.

### Known complications to address during design

- **Identifiability of β₂ against β₁.** On rides where power declines with
  time, corr(t, P̃) < 0 — the same correlation that broke the ratio metric. The
  regression handles it correctly but not for free; it costs variance, and in
  the limit of monotone power decline with no other variation the two are
  perfectly confounded. What rescues it is *within-ride power variation at all
  points in time*, which the local terrain supplies naturally. Compute VIF and
  gate on it: VIF > 5–10 → report "drift not identifiable on this ride
  profile."
- **Errors-in-variables attenuation.** OLS of HR on power is attenuated by
  power measurement noise (relevant with a left-crank-only meter whose
  asymmetry drifts with fatigue). The attenuation depends on the *power
  variance in the window*, so a half with narrower power range is biased down
  more — fabricating a spurious Δk. This is a new artifact the ratio method did
  not have. Mitigations: Deming regression with an assumed noise ratio, or
  binning power and regressing on bin means.
- **Autocorrelation.** ~300 samples per half may be worth n_eff ≈ 30–60
  independent observations. Naive OLS standard errors will be badly
  overconfident. Use AR(1) errors, HAC standard errors, or a block bootstrap.
- **Is β₃ needed at all?** The interaction is the weakest-identified term,
  requiring joint variation in both time and power. Fit nested models and
  compare using n_eff. Prior expectation: intercept drift dominates on most
  rides and β₃ is often indistinguishable from zero.
- **Range restriction.** Fit below ~85% HRmax, where the affine model holds
  (above it the HR–power relationship flattens). When comparing halves,
  restrict to the power range both halves actually sampled — outside it one is
  differencing extrapolations.
- **Sample filtering.** Drop samples with P̃ below ~30% of the ride median
  (stops, coasting) and the ~60 s following any resumption of pedalling (lag
  transients). Residual *sign* identifies the mechanism and is worth logging
  separately: above the line at P ≈ 0 = pushing the bike (metabolically loaded,
  mechanically zero); below the line = HR lag on a power surge, which should
  largely disappear once P̃ replaces P.
- **Partial pooling across rides.** β₀ and β₁ are near-person-level parameters
  that move slowly with fitness, while drift is genuinely ride-specific. A
  mixed model with random slopes on the drift terms and tight priors on β₀/β₁
  from ride history would stabilize per-ride drift estimates considerably,
  especially on short or low-variation rides. No existing platform offers this.

### Interface note

Compute all of this deterministically in application code and hand the coach a
structured verdict — `{drift_bpm_per_hr, slope_change, validity, confounders,
ci}` — rather than raw values to interpret. An LLM given two EF numbers will
pattern-match to the 5% heuristic every time, which is the original failure
mode.

### Prerequisite

**Do not implement this until the offline validation study has shown β₂ to be
recoverable and reliable.** The study is deliberately outside application
development; see the separate handover brief. The specific risk is not bias but
*reliability*: the SportRxiv variance decomposition attributes the collapse in
dimensionality of field durability indices to the dominance of day-to-day
variation. If the intraclass correlation of β₂ is low, per-ride β₂ is useless
for tracking however well specified it is, only multi-ride aggregates carry
signal, and the partial-pooling layer becomes mandatory rather than optional.
That would not vindicate Pw:Hr — it fares worse on the same test — but it
changes what the app should display, so it must be settled before the UI is
designed around a per-ride number.

Caveat to carry forward: this removes terrain and pacing as confounders. It
does not separate thermoregulatory, plasma-volume and glycogen mechanisms —
β₂ remains a phenomenological drift rate. Separating those would need at
minimum ambient temperature and sweat rate, ideally core temperature.

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
