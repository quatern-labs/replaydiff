"""ROS-free logic for the latched /plan republisher (validation/ci/latched_plan_node.py) and the SUT's
transient-local /plan option. A bag replay delivers /plan once, so a SUT that starts late (or a subscriber that joins
after the message) never sees it; a latched publisher keeps the newest non-empty plan for late joiners."""


def durability_name(transient_local):
    """QoS durability the /plan endpoint uses: a transient-local subscriber only gets the latched sample from a
    transient-local publisher, a volatile one gets nothing late either way."""
    return "TRANSIENT_LOCAL" if transient_local else "VOLATILE"


def is_plan(msg):
    """A usable plan has at least two poses (the SUT's controller ignores shorter ones)."""
    return len(getattr(msg, "poses", [])) >= 2


class PlanLatch:
    """Remembers the newest usable plan; an empty or one-pose plan (nav2 clears /plan at goal) does not replace it."""

    def __init__(self):
        self.latest = None
        self.seen = 0

    def update(self, msg):
        """Returns True when msg became the latched plan."""
        self.seen += 1
        if not is_plan(msg):
            return False
        self.latest = msg
        return True
