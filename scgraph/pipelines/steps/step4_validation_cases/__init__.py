"""
This step checks a built network against known routes of the real world.

A case describes one known route. It gives the two ends of the route and a
reference value from a published source. Each case is one row of a CSV file in
`cases/`.

There is one CSV file for each kind of case. Each kind has its own rule, and its routes
are searched on the node modes of that kind only. The node mode of a node is the kind of
place where the node is, such as `road` or `port`. For example, a road distance is
measured on roads only, so a sea route cannot replace it. The two ends of a case snap to
the nodes of these node modes, whatever node modes the network names for its query
points (`node_addition_modes`).

    Kind (file name)  Node modes  The case passes when
    ----------------  ----------  -------------------------------------------------
    road_distances    road        The route is within 10 % of the driving distance
                                  (or within the tolerance of the case), in each
                                  direction. The two directions are within 5 % of
                                  each other.
    crossings         road        Each end is within 5 km of a road, and a road
                                  route joins the two ends.
    coverage          road        The city is within 5 km of a road, and a road
                                  route joins it to the main city of its landmass.
                                  Up to 1 % of the cities may fail.
    rail_corridors    rail        Each end is within 10 km of a track. The route is
                                  at most 10 % longer and at most 20 % shorter than
                                  the published length.
    sea_distances     port, sea   The water route is within 10 % of the published
                                  distance, or within 30 km of it.
    passages          sea         The route enters the passage (Suez, Panama) or
                                  avoids it (the Arctic), as the case says.
    river_ports       port, sea   The port has a node within 5 km. Its water route
                                  to the sea is at most 1.8 times the straight line.
    route_lengths     all         The route is within the tolerance of the case
                                  (5 % when the case gives none).
    hubs              all         A hub of the case's kind is within 5 km. For each
                                  network in `reference` (such as `road rail sea`),
                                  the route from the hub to that network takes the
                                  connector of the hub to it. For `air`, the route
                                  is a direct flight to the airport of the case.

Every file has the columns `id`, `origin_lat`, `origin_lon`, `destination_lat`,
`destination_lon`, `reference`, `source`, `tolerance` and `tolerance_reason`. `source`
says where the reference comes from. A kind adds the columns that its rule reads:
`reference_back` (road_distances), `landmass` (coverage), `passage` and the four
`box_` columns (passages), `hub_kind` (hubs). The other columns of a file describe the
case for a reader. A row is disabled when its id starts with `#`.

A pipeline lists the cases for its network in `VALIDATION = {"cases": [...]}`. An
entry of this list is one of:

- the id of a case;
- the name of a kind, which means all the cases of that kind;
- a dictionary that describes a case directly. It has the keys `id`, `kind`,
  `origin` and `destination` (each a `(latitude, longitude)` pair). It also has
  the fields that the rule of its kind reads, such as `reference`. `tolerance` is
  optional (a share such as 0.05).

A regional pipeline gives `{"cases": {region: [...]}}`, one such list for each region.
"""

from scgraph.pipelines.steps.step4_validation_cases.validation import (
    RULES as RULES,
    ValidationResult as ValidationResult,
    load_validation_cases as load_validation_cases,
    validate_network as validate_network,
)

__all__ = ["ValidationResult", "load_validation_cases", "validate_network"]
