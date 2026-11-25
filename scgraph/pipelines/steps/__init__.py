"""The functions of the steps of a build. The name of a module starts with the rank
of its step in a build.

- Step 1, read the sources. `step1_osm_ways` downloads an OpenStreetMap file, or reads
  it on its server. `step1_osm_range_streamer` downloads the byte ranges of the planet
  file for it. `scgraph.helpers.osm` reads the ways of the file and cuts them into
  pieces.
- Step 2, join the networks. `step2_hub_connectors` joins the road, rail and sea
  networks at hubs, with the land and the water of `step2_land_mask`.
- Step 3, assemble the network. `scgraph.network_assembly` keeps the connected
  components, contracts the chains and orders the nodes.
- Step 4, validate. `step4_validation_cases` checks a built network against known
  routes.

`scgraph.helpers.near_nodes` finds the nodes near a point. Steps 1 and 2 use it.
"""
