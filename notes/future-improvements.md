# Future improvements

Working notes, not part of the report or the website.

## A decision layer in the solver

Added on 4 November 2026. Not started.

The solver reports distances, costs and distance from the optimum. A service manager asks other
questions, so this layer would turn those results into operational terms:

- How many postmen or vehicles are needed?
- How long does each shift last, and does it fit a working day?
- How much does the service cost, and how much would it save against the current route?
- Where should the depot be?

Likely inputs are speed, cost per hour and length of the working day. Likely outputs are hours,
cost and postmen needed. A worked real case, such as a district of Vilanova, could show the problem,
the options and the recommended decision from start to finish.

The algorithms and published results would not change. Any new figures would need to be labelled as
estimates from the user's inputs, and kept apart from the proved and measured results.
