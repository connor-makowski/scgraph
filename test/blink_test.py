from scx.optimize import Model
import type_enforced

@type_enforced.Enforcer
class Location:
    def __init__(self, name:str):
        self.name = name

@type_enforced.Enforcer
class Region(Location):
    def __init__(self, demand:[float, int], **kwargs):
        super().__init__(**kwargs)
        self.demand = demand

@type_enforced.Enforcer
class Plant(Location):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@type_enforced.Enforcer
class Route:
    def __init__(self, cost_per_mile:[float, int], distance:[float, int], source:Plant, destination:Region):
        self.source = source
        self.destination = destination
        self.distance = distance
        self.source = source,
        self.destination = destination
        self.cost = cost_per_mile * distance
        self.amt = Model.variable(name=f"{source.name}__to__{destination.name}__amt", lowBound=0)


## Data
regions = {
    'R1': Region(name='R1', demand=2500),
    'R2': Region(name='R2', demand=4350),
    'R3': Region(name='R3', demand=3296),
}

plants = {
    'P1': Plant(name='P1'),
    'P2': Plant(name='P2'),
}

routes = [
    Route(
        source=plants['P1'], 
        destination=regions['R1'], 
        distance=105, 
        cost_per_mile=0.12
    ),
    Route(
        source=plants['P1'],
        destination=regions['R2'],
        distance=256,
        cost_per_mile=0.12
    ),
    Route(
        source=plants['P1'],
        destination=regions['R3'],
        distance=86,
        cost_per_mile=0.12
    ),
    Route(
        source=plants['P2'],
        destination=regions['R1'],
        distance=240,
        cost_per_mile=0.12
    ),
    Route(
        source=plants['P2'],
        destination=regions['R2'],
        distance=136,
        cost_per_mile=0.12
    ),
    Route(
        source=plants['P2'],
        destination=regions['R3'],
        distance=198,
        cost_per_mile=0.12
    ),
]

## Model
# Initialize the model
my_model = Model(name="Blinky22", sense='minimize')


# Add the Objective Fn
my_model.add_objective(
    fn=Model.sum([rt.amt*rt.cost for rt in routes])
)

# Add Constraints
## Demand Constraint
for r in regions.values():
    my_model.add_constraint(
        name=f"{r.name}__demand",
        fn=Model.sum([rt.amt for rt in routes if rt.destination==r]) >= r.demand,
    )

# Solve the model
my_model.solve()

my_model.show_outputs()



