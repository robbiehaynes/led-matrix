"""
Defines the set of display modes and a small cycler for the physical button.
Kept separate from code.py so mode order/naming is a one-line change.
"""

MODES = ["planes", "football", "rugby"]


class ModeCycler:
    def __init__(self, modes=MODES, start=0):
        self._modes = modes
        self._index = start

    @property
    def current(self):
        return self._modes[self._index]

    def next(self):
        self._index = (self._index + 1) % len(self._modes)
        return self.current

    def previous(self):
        self._index = (self._index - 1) % len(self._modes)
        return self.current
