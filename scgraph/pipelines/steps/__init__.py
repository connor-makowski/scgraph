"""The functions of the steps of a build. The name of a module starts with the rank
of its step in a build.

- Step 1, read the sources. `step1_osm_ways` reads the ways of an OpenStreetMap file
  and cuts them into pieces. `step1_osm_planet_reader` reads the planet file by HTTP
  byte ranges for it.
- Step 2, join the networks. `step2_hub_connectors` joins the road, rail and sea
  networks at hubs, with the land and the water of `step2_land_mask`.
- Step 3, assemble the network. `step3_network_assembly` keeps the connected
  components, contracts the chains and orders the nodes.
- Step 4, validate. `step4_validation_cases` checks a built network against known
  routes.

`near_nodes` finds the nodes near a point. Steps 1 and 2 use it.
"""
