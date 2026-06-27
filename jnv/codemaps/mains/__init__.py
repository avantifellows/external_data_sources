from .y2021 import CODEMAP as codemap_2021
from .y2022 import CODEMAP as codemap_2022
from .y2023 import CODEMAP as codemap_2023
from .y2024 import CODEMAP as codemap_2024
from .y2025 import CODEMAP as codemap_2025
from .y2026_eligible import CODEMAP as codemap_2026_eligible
from .y2026_ineligible import CODEMAP as codemap_2026_ineligible

# To add a new year: create codemap_YYYY.py and add it here.
ALL_CODEMAPS = [
    codemap_2021,
    codemap_2022,
    codemap_2023,
    codemap_2024,
    codemap_2025,
    codemap_2026_eligible,
    codemap_2026_ineligible,
]
