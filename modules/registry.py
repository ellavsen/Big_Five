# modules/registry.py
from __future__ import annotations
from modules.role_vs_core import role_vs_core
from modules.energy_economy import energy_economy
from modules.team_mirror import team_mirror
from modules.compensation_patterns import compensation_patterns

MODULES = [
    role_vs_core,
    energy_economy,
    compensation_patterns,
    team_mirror,
]
