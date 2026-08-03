---
title: Improve interval boundary detection
status: draft
release: v3
---

## Problem / Context

I have seen the detection of intervals being slightly off (i.e. not the whole interval is covered). A few seconds are missing.

Context: Probably the 20s averaging window used for interval detection takes a longer time to raise above the threshold / drop below the threshold.

Potential solutions: Adapt the boundary of the interval through a different criterion (e.g. when the unfiltered version of the signal first crosses a threshold close to the current detection).

## Acceptance Criteria

<!-- Checklist of concrete, verifiable outcomes. -->

- [ ]

## Technical Decisions

<!-- Code-related decisions made during drafting, with rationale. -->

## Test Plan

<!-- How to verify the implementation once done: manual steps and/or
     specific automated tests to add/run. -->

## Out of Scope

Do not completely re-open the algorithms used for interval detection unless absolutely necessary.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->
