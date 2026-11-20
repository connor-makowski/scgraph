"""The functions of the steps of a build, one module for each step.

- `osm_ways` reads the ways of an OpenStreetMap file and cuts them into pieces.
  `osm_planet_reader` reads the planet file by HTTP byte ranges for it.
- `hub_connectors` joins the networks of several modes at hubs, with the land and
  the water of `land_mask`.
- `network_arrays` assembles the arrays of the network file.
- `validation_cases` checks a built network against known routes.
"""
