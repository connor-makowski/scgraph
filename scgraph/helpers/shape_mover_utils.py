# Note: ShapeMoverUtils is copied directly from fizgrid to avoid the dependency on fizgrid.
# See: https://github.com/connor-makowski/fizgrid
class ShapeMoverUtils:
    @staticmethod
    def moving_segment_overlap_intervals(
        seg_start: int | float,
        seg_end: int | float,
        t_start: int | float,
        t_end: int | float,
        shift: int | float,
    ):
        """
        Calculates the time intervals during which a moving 1D line segment overlaps with each unit-length
        integer-aligned range along the x-axis.

        Args:

        - seg_start (int|float): Initial position of the left end of the line segment.
        - seg_end (int|float): Initial position of the right end of the line segment.
        - t_start (int|float): Start time of the motion.
        - t_end (int|float): End time of the motion.
        - shift (int|float): Total distance the line segment moves along the x-axis during [t_start, t_end].

        Returns:

        - dict[int, tuplie(int|float,int|float)]: A dictionary mapping each integer `i` to the time interval [t_in, t_out]
                                during which any part of the line overlaps the range [i, i+1).
                                Only includes ranges with non-zero overlap duration.
        """
        duration = t_end - t_start
        velocity = shift / duration if duration != 0 else 0

        result = {}

        final_start = seg_start + shift
        final_end = seg_end + shift
        global_min = min(seg_start, final_start)
        global_max = max(seg_end, final_end)

        for i in range(int(global_min) - 1, int(global_max) + 2):
            if velocity == 0:
                if seg_end > i and seg_start < i + 1 and t_start < t_end:
                    result[i] = (t_start, t_end)
                continue
            # Solve for times when the line enters and exits overlap with [i, i+1)
            t1 = (i - seg_end) / velocity + t_start
            t2 = (i + 1 - seg_start) / velocity + t_start
            entry_time = max(min(t1, t2), t_start)
            exit_time = min(max(t1, t2), t_end)

            if exit_time > entry_time:
                result[i] = (entry_time, exit_time)

        return result

    @staticmethod
    def moving_rectangle_overlap_intervals(
        x_start: float | int,
        x_end: float | int,
        y_start: float | int,
        y_end: float | int,
        x_shift: float | int,
        y_shift: float | int,
        t_start: float | int,
        t_end: float | int,
    ):
        """
        Calculates the time intervals during which a moving rectangle overlaps with each unit-length
        integer-aligned range along the x and y axes.

        Args:

        - x_start (float|int): Initial position of the left end of the rectangle along the x-axis.
        - x_end (float|int): Initial position of the right end of the rectangle along the x-axis.
        - y_start (float|int): Initial position of the bottom end of the rectangle along the y-axis.
        - y_end (float|int): Initial position of the top end of the rectangle along the y-axis.
        - x_shift (float|int): Total distance the rectangle moves along the x-axis during [t_start, t_end].
        - y_shift (float|int): Total distance the rectangle moves along the y-axis during [t_start, t_end].
        - t_start (float|int): Start time of the motion.
        - t_end (float|int): End time of the motion.

        Returns:

        - dict[tuple(int,int),tuple(int|float,int|float)]: A dictionary mapping each integer (i,j) to the time interval [t_in, t_out]
            during which any part of the rectangle overlaps the range [i, i+1) x [j, j+1).
            Only includes ranges with non-zero overlap duration.

        """
        x_intervals = ShapeMoverUtils.moving_segment_overlap_intervals(
            seg_start=x_start,
            seg_end=x_end,
            t_start=t_start,
            t_end=t_end,
            shift=x_shift,
        )
        y_intervals = ShapeMoverUtils.moving_segment_overlap_intervals(
            seg_start=y_start,
            seg_end=y_end,
            t_start=t_start,
            t_end=t_end,
            shift=y_shift,
        )
        result = {}
        for x_key, x_interval in x_intervals.items():
            for y_key, y_interval in y_intervals.items():
                # Only add intervals with time overlap
                if (
                    x_interval[1] > y_interval[0]
                    and y_interval[1] > x_interval[0]
                ):
                    result[(x_key, y_key)] = (
                        max(x_interval[0], y_interval[0]),
                        min(x_interval[1], y_interval[1]),
                    )

        return result

    @staticmethod
    def argmin(lst):
        return min(enumerate(lst), key=lambda x: x[1])[0]

    @staticmethod
    def argmax(lst):
        return max(enumerate(lst), key=lambda x: x[1])[0]

    @staticmethod
    def find_extreme_orthogonal_vertices(
        points: list[tuple[int | float, int | float]], slope: float | int
    ):
        """
        Finds the points in a list that are the furthest apart in the direction
        orthogonal to the given slope. This is useful for finding the extreme
        points in a set of 2D coordinates that are orthogonal to a given line.

        Args:

        - points (list of tuples): A list of (x, y) coordinates.
        - slope (float): The slope of the line.

        Returns:

        - tuple: The points with the minimum and maximum projections.
        """
        # Compute orthogonal slope
        orthogonal = float("inf") if slope == 0 else -1 / slope
        # Define direction projections (a normalized direction vector, but without the linear algebra)
        # Handle vertical slope
        if orthogonal == float("inf"):
            x_proj = 0.0
            y_proj = 1.0
        else:
            # Note: Technically normalized length is (1**2 + orthogonal**2)**.5, but we avoid the extra square for performance
            length = (1 + orthogonal**2) ** 0.5
            x_proj = 1.0 / length
            y_proj = orthogonal / length
        # Compute projections
        projections = [x * x_proj + y * y_proj for x, y in points]
        # Return the min and max projections
        return (
            points[ShapeMoverUtils.argmin(projections)],
            points[ShapeMoverUtils.argmax(projections)],
        )

    @staticmethod
    def find_extreme_orthogonal_vertices_simplified(
        points: list[tuple[int | float, int | float]], slope: float | int
    ):
        """
        A simplified version of the function `find_extreme_orthogonal_vertices`
        that assumes the slope is never 0.

        Finds the points in a list that are the furthest apart in the direction
        orthogonal to the given slope. This is useful for finding the extreme
        points in a set of 2D coordinates that are orthogonal to a given line.

        Args:

        - points (list of tuples): A list of (x, y) coordinates.
        - slope (float): The slope of the line.
            - Note: This should never be 0 or infinite for this function.

        Returns:

        - tuple: The points with the minimum and maximum projections.
        """
        # Compute orthogonal slope
        orthogonal = -1 / slope
        # Define direction projections (a normalized direction vector, but without the linear algebra)
        # Note: Technically normalized length is (1**2 + orthogonal**2)**.5, but we avoid the extra square for performance
        length = (1 + orthogonal**2) ** 0.5
        projections = [
            x * 1.0 / length + y * orthogonal / length for x, y in points
        ]
        # Return the min and max verticies
        vertex_1 = points[ShapeMoverUtils.argmin(projections)]
        vertex_2 = points[ShapeMoverUtils.argmax(projections)]
        if slope < 0:
            return vertex_1, vertex_2
        else:
            return vertex_2, vertex_1

    @staticmethod
    def remove_untouched_intervals(
        intervals: dict[tuple[int, int], tuple[int | float, int | float]],
        slope: float | int,
        absolute_shape: list[tuple[int | float, int | float]],
    ):
        """
        Removes unnecessary intervals from the dictionary of intervals.

        Args:

        - intervals (dict[tuple(int,int),tuple(int|float,int|float)]): A dictionary mapping each integer (i,j) to the time interval [t_in, t_out]
            during which any part of the shape overlaps the range [i, i+1) x [j, j+1).
        - slope (float|int): The slope of the line.
        - absolute_shape (list(tuple[int|float, int|float])): A list of coordinates representing the shape's vertices relative to its center.

        Returns:

        - dict[tuple(int,int),tuple(int|float,int|float)]: A dictionary with unnecessary intervals removed.
        """
        (
            min_vertex,
            max_vertex,
        ) = ShapeMoverUtils.find_extreme_orthogonal_vertices_simplified(
            points=absolute_shape, slope=slope
        )
        shape_min_intercept = min_vertex[1] - slope * min_vertex[0]
        shape_max_intercept = max_vertex[1] - slope * max_vertex[0]

        # Given the slope, determine which cell vertex to use for the max and min intercepts
        # This is to ensure that the intervals are removed correctly
        ltx_increment = 1 if slope < 0 else 0
        gtx_increment = 0 if slope < 0 else 1

        remove_keys = []
        for x_cell, y_cell in intervals.keys():
            cell_min_intercept = y_cell - (slope * (x_cell + gtx_increment))
            cell_max_intercept = (y_cell + 1) - (
                slope * (x_cell + ltx_increment)
            )
            # If the intercept ranges do not overlap, remove the interval
            if not (
                cell_min_intercept < shape_max_intercept
                and shape_min_intercept < cell_max_intercept
            ):
                remove_keys.append((x_cell, y_cell))
        for key in remove_keys:
            del intervals[key]
        return intervals

    @staticmethod
    def moving_shape_overlap_intervals(
        x_coord: float | int,
        y_coord: float | int,
        x_shift: float | int,
        y_shift: float | int,
        t_start: float | int,
        t_end: float | int,
        shape: list[list[float | int]],
        cell_density: int = 1,
    ):
        """
        Calculates the time intervals during which a moving shape overlaps with each unit-length
        integer-aligned range along the x and y axes.

        Note: This converts each shape into a full bounding box rectangle and then uses the rectangle overlap function to calculate the intervals.

        Args:

        - x_coord (float|int): Initial x-coordinate of the shape's center.
        - y_coord (float|int): Initial y-coordinate of the shape's center.
        - x_shift (float|int): Total distance the shape moves along the x-axis during [t_start, t_end].
        - y_shift (float|int): Total distance the shape moves along the y-axis during [t_start, t_end].
        - t_start (float|int): Start time of the motion.
        - t_end (float|int): End time of the motion.
        - shape (list[list[float|int]]): List of coordinates representing the shape's vertices relative to its center.
        - cell_density (int): The number of cells per unit of length.


        Returns:

        - dict[tuple(int,int),tuple(int|float,int|float)]: A dictionary mapping each integer (i,j) to the time interval [t_in, t_out]
                                during which any part of the shape overlaps the range [i, i+1) x [j, j+1).
                                Only includes ranges with non-zero overlap duration.
        """
        # Get the overlap intervals for a rectangle that bounds the shape in cell space
        absolute_shape = [
            [
                (x_coord + coord[0]) * cell_density,
                (y_coord + coord[1]) * cell_density,
            ]
            for coord in shape
        ]
        # Get the shifts in cell space
        x_shift = x_shift * cell_density
        y_shift = y_shift * cell_density
        # Calculate the rectangle overlap intervals in cell space
        rectangle_overlap_intervals = (
            ShapeMoverUtils.moving_rectangle_overlap_intervals(
                x_start=min([coord[0] for coord in absolute_shape]),
                x_end=max([coord[0] for coord in absolute_shape]),
                y_start=min([coord[1] for coord in absolute_shape]),
                y_end=max([coord[1] for coord in absolute_shape]),
                x_shift=x_shift,
                y_shift=y_shift,
                t_start=t_start,
                t_end=t_end,
            )
        )
        # If the shape is only moving vertically or horizontally, we can just return the rectangle overlap intervals
        if x_shift == 0 or y_shift == 0:
            return rectangle_overlap_intervals
        # If the shape is moving diagonally, we should remove intervals that are never passed through by the shape
        return ShapeMoverUtils.remove_untouched_intervals(
            intervals=rectangle_overlap_intervals,
            slope=y_shift / x_shift,
            absolute_shape=absolute_shape,
        )
