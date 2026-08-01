"""Pruebas de regresión de Fase 4: selector de layouts."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snapassist.config import LAYOUT_TEMPLATES, Rect
from snapassist.ui.layout_menu import LayoutMenu


def make_menu() -> LayoutMenu:
    menu = LayoutMenu.__new__(LayoutMenu)
    menu._templates = LAYOUT_TEMPLATES
    menu._absolute_rects = [
        [Rect(0, 0, 100, 100) for _zone in layout.zones]
        for layout in LAYOUT_TEMPLATES
    ]
    menu._disabled_layouts = [False] * len(LAYOUT_TEMPLATES)
    menu._active_layout_idx = 0
    menu._active_zone_idx = 0
    menu._stage = "layout"
    menu._update_hover = lambda: None
    return menu


def test_layout_navigation_reaches_1_1_1():
    menu = make_menu()
    for _ in range(len(LAYOUT_TEMPLATES) - 1):
        menu._move(1)
    assert menu._active_layout_idx == len(LAYOUT_TEMPLATES) - 1
    assert menu._templates[menu._active_layout_idx].name == "1:1:1"


def test_disabled_layout_is_skipped_by_keyboard_navigation():
    menu = make_menu()
    menu._disabled_layouts[1] = True
    menu._move(1)
    assert menu._active_layout_idx == 2


def run_all_tests():
    for test in (
        test_layout_navigation_reaches_1_1_1,
        test_disabled_layout_is_skipped_by_keyboard_navigation,
    ):
        test()
        print(f"  ✓ {test.__name__}")


if __name__ == "__main__":
    run_all_tests()
