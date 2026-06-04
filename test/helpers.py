from scgraph.utils import hard_round


def assert_result(realized, expected):
    if isinstance(realized, dict) and "length" in realized:
        realized = {**realized, "length": hard_round(3, realized["length"])}
    if isinstance(expected, dict) and "length" in expected:
        expected = {**expected, "length": hard_round(3, expected["length"])}
    assert realized == expected
