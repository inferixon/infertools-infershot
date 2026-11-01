"""Annotation history and contact-sheet geometry, independent of the GUI."""

import copy
import math


class AnnotationHistory:
    def __init__(self, limit=20):
        self.limit = limit
        self.undo_states = []
        self.redo_states = []

    def remember(self, annotations):
        self.undo_states.append(copy.deepcopy(annotations))
        del self.undo_states[:-self.limit]
        self.redo_states.clear()

    def undo(self, annotations):
        if not self.undo_states:
            return None
        self.redo_states.append(copy.deepcopy(annotations))
        return self.undo_states.pop()

    def redo(self, annotations):
        if not self.redo_states:
            return None
        self.undo_states.append(copy.deepcopy(annotations))
        del self.undo_states[:-self.limit]
        return self.redo_states.pop()


def sheet_layout(sizes, gap=24):
    """Pack ordered native-size images; adapted from INFERSCOPE sheetLayout."""
    if not sizes or any(w <= 0 or h <= 0 for w, h in sizes):
        raise ValueError("Choose at least one non-empty screenshot")
    best = None
    for columns in range(1, len(sizes) + 1):
        rows = [sizes[index:index + columns] for index in range(0, len(sizes), columns)]
        widths = [sum(w for w, _ in row) + gap * (len(row) - 1) for row in rows]
        heights = [max(h for _, h in row) for row in rows]
        width, height = max(widths) + gap * 2, sum(heights) + gap * (len(rows) + 1)
        occupied = sum(w * h for w, h in sizes)
        score = abs(math.log(width / height / (4 / 3))) + .35 * (1 - occupied / (width * height))
        if best is None or score < best[0]:
            cells, y = [], gap
            for row, row_width, row_height in zip(rows, widths, heights):
                x = (width - row_width) / 2
                for w, h in row:
                    cells.append((round(x), round(y + (row_height - h) / 2), w, h))
                    x += w + gap
                y += row_height + gap
            best = score, (width, height), cells
    return best[1], best[2]


# Crossed repair tools adapted from INFERSCOPE's own Fix this stamp.
REPAIR_POLYGONS = (
    ((12.38, 9.63), (21.89, 19.14), (19.78, 21.3), (10.27, 11.74)),
    ((17.5, 10.1), (16.36, 9.91), (4.97, 21.25), (2.86, 19.14),
     (10.27, 11.74), (8.5, 9.96), (7.78, 10.66), (6.33, 9.25),
     (6.33, 12.11), (5.63, 12.81), (2.11, 9.25), (2.81, 8.55),
     (5.62, 8.55), (4.22, 7.14), (7.78, 3.58), (9.89, 2.7),
     (12, 3.58), (9.89, 5.74), (11.3, 7.14), (10.59, 7.85),
     (12.38, 9.63), (14.2, 7.75), (14, 6.63), (14.3, 5.1),
     (15.5, 3.6), (17.5, 3.11), (19.08, 3.53), (16.41, 6.2),
     (17.91, 7.7), (20.58, 5.03), (21, 6.63), (20.6, 8.2), (19.2, 9.7)),
)


def repair_polygons(center, size):
    cx, cy = center
    return [[(cx + (x - 12) * size / 24, cy + (y - 12) * size / 24)
             for x, y in polygon] for polygon in REPAIR_POLYGONS]
