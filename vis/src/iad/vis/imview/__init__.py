"""Interactive image viewing toolkit for notebooks (anywidget-based).

Exports :func:`imgrid` and :class:`ImageGrid`. See ``vis/IMVIEW.md`` for
architecture, parameters, and frontend module layout.
"""

from iad.vis.imview.api import ImageGrid, imgrid

__all__ = ['imgrid', 'ImageGrid']
