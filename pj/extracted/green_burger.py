from __future__ import annotations

import math

from cambc import Controller, Direction, EntityType, Environment, Position

INF = float("inf")
PASSABLE_COST = 1.0
BUILDABLE_COST = 2.0
UNKNOWN_COST = BUILDABLE_COST

ALL_DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class BugNavPlanner:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.costs = [[UNKNOWN_COST for _ in range(width)] for _ in range(height)]
        self._known_costs: list[list[float | None]] = [
            [None for _ in range(width)] for _ in range(height)
        ]
        self._goal: tuple[int, int] | None = None

        self._trace_mode = False
        self._follow_right = True
        self._last_step_dir: Direction | None = None
        self._trace_hit_distance = INF
        self._trace_best_distance = INF
        self._trace_start: tuple[int, int] | None = None
        self._trace_steps = 0
        self._trace_state_visits: dict[
            tuple[int, int, bool, Direction | None], int,
        ] = {}
        self._recent_positions: list[tuple[int, int]] = []

    def set_goal(self, goal: Position) -> None:
        goal_key = self._to_key(goal)
        if not self.in_bounds(goal):
            msg = "goal must be in bounds"
            raise ValueError(msg)
        self._goal = goal_key
        self._recent_positions.clear()
        self._reset_trace()

    def clear_goal(self) -> None:
        self._goal = None
        self._recent_positions.clear()
        self._reset_trace()

    def has_goal(self) -> bool:
        return self._goal is not None

    def goal(self) -> Position | None:
        if self._goal is None:
            return None
        return Position(self._goal[0], self._goal[1])

    def observe(self, ct: Controller) -> bool:
        if self._goal is None:
            return False

        changed = False
        for pos in ct.get_nearby_tiles():
            new_cost = self._visible_tile_cost(ct, pos)
            if self._set_known_cost(pos, new_cost):
                changed = True
        return changed

    def next_step(
        self, start: Position, ct: Controller | None = None,
    ) -> Position | None:
        if self._goal is None:
            return None
        if not self.in_bounds(start):
            return None

        start_key = self._to_key(start)
        self._remember_position(start_key)
        if start_key == self._goal:
            self._reset_trace()
            return None

        direct_move = self._best_direct_move(start_key, ct)
        if direct_move is not None and self._can_leave_trace(start_key):
            self._reset_trace()
            self._last_step_dir = direct_move[0]
            return Position(direct_move[1][0], direct_move[1][1])

        if not self._trace_mode:
            trace_move = self._enter_trace(start_key, ct)
        else:
            trace_move = self._continue_trace(start_key, ct)

        if trace_move is None:
            if direct_move is not None:
                self._reset_trace()
                self._last_step_dir = direct_move[0]
                return Position(direct_move[1][0], direct_move[1][1])
            self._reset_trace()
            return None

        direction, next_key = trace_move
        self._last_step_dir = direction
        self._trace_steps += 1
        self._trace_best_distance = min(
            self._trace_best_distance,
            self._heuristic(next_key, self._goal),
        )
        return Position(next_key[0], next_key[1])

    def next_direction(
        self,
        start: Position,
        ct: Controller | None = None,
    ) -> Direction | None:
        step = self.next_step(start, ct)
        if step is None:
            return None
        return start.direction_to(step)

    def is_known_blocked(self, pos: Position) -> bool:
        if not self.in_bounds(pos):
            return True
        return math.isinf(self.costs[pos.y][pos.x])

    def debug_known_cost(self, pos: Position) -> float:
        if not self.in_bounds(pos):
            return INF
        return self.costs[pos.y][pos.x]

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.x < self.width and 0 <= pos.y < self.height

    def _enter_trace(
        self,
        start_key: tuple[int, int],
        ct: Controller | None,
    ) -> tuple[Direction, tuple[int, int]] | None:
        assert self._goal is not None

        goal_dir = self._direction_toward(start_key, self._goal)
        if goal_dir is None:
            return None

        right_move = self._best_trace_move(start_key, goal_dir, True, ct)
        left_move = self._best_trace_move(start_key, goal_dir, False, ct)
        chosen_side, chosen_move = self._pick_trace_side(
            start_key,
            right_move,
            left_move,
        )
        if chosen_move is None:
            return None

        self._trace_mode = True
        self._follow_right = chosen_side
        self._last_step_dir = goal_dir
        self._trace_hit_distance = self._heuristic(start_key, self._goal)
        self._trace_best_distance = self._trace_hit_distance
        self._trace_start = start_key
        self._trace_steps = 0
        self._trace_state_visits.clear()
        return chosen_move

    def _continue_trace(
        self,
        start_key: tuple[int, int],
        ct: Controller | None,
    ) -> tuple[Direction, tuple[int, int]] | None:
        assert self._goal is not None

        if self._trace_start == start_key and self._trace_steps > 0:
            self._flip_trace_side(start_key)

        state_key = (
            start_key[0],
            start_key[1],
            self._follow_right,
            self._last_step_dir,
        )
        visits = self._trace_state_visits.get(state_key, 0) + 1
        self._trace_state_visits[state_key] = visits
        if visits >= 3:
            self._flip_trace_side(start_key)

        heading = self._last_step_dir
        if heading is None:
            heading = self._direction_toward(start_key, self._goal)
        if heading is None:
            return None

        return self._best_trace_move(start_key, heading, self._follow_right, ct)

    def _can_leave_trace(self, start_key: tuple[int, int]) -> bool:
        if not self._trace_mode:
            return True
        assert self._goal is not None

        current_distance = self._heuristic(start_key, self._goal)
        if current_distance < self._trace_hit_distance:
            return True
        return self._trace_steps >= 12 and current_distance <= self._trace_best_distance

    def _best_direct_move(
        self,
        start_key: tuple[int, int],
        ct: Controller | None,
    ) -> tuple[Direction, tuple[int, int]] | None:
        assert self._goal is not None

        start = Position(start_key[0], start_key[1])
        preferred = start.direction_to(Position(self._goal[0], self._goal[1]))
        current_distance = self._heuristic(start_key, self._goal)
        best: (
            tuple[tuple[float, float, int, int], Direction, tuple[int, int]] | None
        ) = None

        for direction, next_key in self._legal_moves(start_key, ct):
            next_distance = self._heuristic(next_key, self._goal)
            if next_distance >= current_distance:
                continue

            score = (
                next_distance,
                self._movement_cost(start_key, next_key),
                self._turn_distance(direction, preferred),
                self._recent_backtrack_penalty(next_key),
            )
            if best is None or score < best[0]:
                best = (score, direction, next_key)

        if best is None:
            return None
        return best[1], best[2]

    def _best_trace_move(
        self,
        start_key: tuple[int, int],
        heading: Direction,
        follow_right: bool,
        ct: Controller | None,
        allow_flip: bool = True,
    ) -> tuple[Direction, tuple[int, int]] | None:
        assert self._goal is not None

        legal = dict(self._legal_moves(start_key, ct))
        if not legal:
            return None

        best: (
            tuple[tuple[int, int, float, float], Direction, tuple[int, int]] | None
        ) = None
        for index, direction in enumerate(
            self._trace_scan_order(heading, follow_right),
        ):
            next_key = legal.get(direction)
            if next_key is None:
                continue

            score = (
                0
                if self._keeps_wall_contact(start_key, direction, follow_right)
                else 1,
                self._recent_backtrack_penalty(next_key),
                self._heuristic(next_key, self._goal),
                self._movement_cost(start_key, next_key),
            )
            ranked = (score[0], score[1], score[2], float(index) + score[3] / 10.0)
            if best is None or ranked < best[0]:
                best = (ranked, direction, next_key)

        if best is None:
            return None

        direction, next_key = best[1], best[2]
        previous = self._previous_position()
        if previous is not None and next_key == previous:
            alternate = self._best_trace_alternate(
                start_key,
                heading,
                follow_right,
                ct,
                blocked_key=previous,
            )
            if alternate is not None:
                return alternate
            if allow_flip and self._is_two_tile_loop(previous):
                self._flip_trace_side(start_key)
                return self._best_trace_move(
                    start_key,
                    heading,
                    self._follow_right,
                    ct,
                    allow_flip=False,
                )

        return direction, next_key

    def _best_trace_alternate(
        self,
        start_key: tuple[int, int],
        heading: Direction,
        follow_right: bool,
        ct: Controller | None,
        blocked_key: tuple[int, int],
    ) -> tuple[Direction, tuple[int, int]] | None:
        assert self._goal is not None

        legal = dict(self._legal_moves(start_key, ct))
        best: (
            tuple[tuple[int, int, float, float], Direction, tuple[int, int]] | None
        ) = None
        for index, direction in enumerate(
            self._trace_scan_order(heading, follow_right),
        ):
            next_key = legal.get(direction)
            if next_key is None or next_key == blocked_key:
                continue

            score = (
                0
                if self._keeps_wall_contact(start_key, direction, follow_right)
                else 1,
                self._recent_backtrack_penalty(next_key),
                self._heuristic(next_key, self._goal),
                self._movement_cost(start_key, next_key),
            )
            ranked = (score[0], score[1], score[2], float(index) + score[3] / 10.0)
            if best is None or ranked < best[0]:
                best = (ranked, direction, next_key)

        if best is None:
            return None
        return best[1], best[2]

    def _pick_trace_side(
        self,
        start_key: tuple[int, int],
        right_move: tuple[Direction, tuple[int, int]] | None,
        left_move: tuple[Direction, tuple[int, int]] | None,
    ) -> tuple[bool, tuple[Direction, tuple[int, int]] | None]:
        assert self._goal is not None

        if right_move is None:
            return False, left_move
        if left_move is None:
            return True, right_move

        right_score = self._trace_side_score(start_key, right_move)
        left_score = self._trace_side_score(start_key, left_move)
        if right_score <= left_score:
            return True, right_move
        return False, left_move

    def _trace_side_score(
        self,
        start_key: tuple[int, int],
        move: tuple[Direction, tuple[int, int]],
    ) -> tuple[float, float, int]:
        assert self._goal is not None

        direction, next_key = move
        return (
            self._heuristic(next_key, self._goal),
            self._movement_cost(start_key, next_key),
            self._recent_backtrack_penalty(next_key) + self._direction_bias(direction),
        )

    def _trace_scan_order(
        self, heading: Direction, follow_right: bool,
    ) -> list[Direction]:
        order: list[Direction] = []
        direction = heading.rotate_left() if follow_right else heading.rotate_right()
        for _ in range(8):
            order.append(direction)
            direction = (
                direction.rotate_right() if follow_right else direction.rotate_left()
            )
        return order

    def _keeps_wall_contact(
        self,
        start_key: tuple[int, int],
        move_dir: Direction,
        follow_right: bool,
    ) -> bool:
        current = Position(start_key[0], start_key[1])
        next_pos = current.add(move_dir)
        side_dir = move_dir.rotate_right() if follow_right else move_dir.rotate_left()
        side_pos = current.add(side_dir)
        next_side_pos = next_pos.add(side_dir)
        return self.is_known_blocked(side_pos) or self.is_known_blocked(next_side_pos)

    def _legal_moves(
        self,
        start_key: tuple[int, int],
        ct: Controller | None,
    ) -> list[tuple[Direction, tuple[int, int]]]:
        moves: list[tuple[Direction, tuple[int, int]]] = []
        current = Position(start_key[0], start_key[1])
        for direction in ALL_DIRECTIONS:
            nxt = current.add(direction)
            if not self.in_bounds(nxt):
                continue
            next_key = (nxt.x, nxt.y)
            if self._is_temporarily_blocked(ct, next_key, start_key):
                continue
            if math.isinf(self._movement_cost(start_key, next_key)):
                continue
            moves.append((direction, next_key))
        return moves

    def _remember_position(self, start_key: tuple[int, int]) -> None:
        if self._recent_positions and self._recent_positions[-1] == start_key:
            return
        self._recent_positions.append(start_key)
        if len(self._recent_positions) > 6:
            self._recent_positions.pop(0)

    def _previous_position(self) -> tuple[int, int] | None:
        if len(self._recent_positions) < 2:
            return None
        return self._recent_positions[-2]

    def _recent_backtrack_penalty(self, next_key: tuple[int, int]) -> int:
        previous = self._previous_position()
        if previous is None:
            return 0
        return 1 if next_key == previous else 0

    def _is_two_tile_loop(self, previous: tuple[int, int]) -> bool:
        if len(self._recent_positions) < 3:
            return False
        return (
            self._recent_positions[-1] == self._recent_positions[-3]
            and previous == self._recent_positions[-2]
        )

    def _flip_trace_side(self, start_key: tuple[int, int]) -> None:
        self._follow_right = not self._follow_right
        self._trace_state_visits.clear()
        self._trace_start = start_key
        self._trace_steps = 0
        if self._goal is not None:
            self._last_step_dir = self._direction_toward(start_key, self._goal)

    def _reset_trace(self) -> None:
        self._trace_mode = False
        self._follow_right = True
        self._last_step_dir = None
        self._trace_hit_distance = INF
        self._trace_best_distance = INF
        self._trace_start = None
        self._trace_steps = 0
        self._trace_state_visits.clear()

    def _set_known_cost(self, pos: Position, new_cost: float) -> bool:
        current = self._known_costs[pos.y][pos.x]
        if current == new_cost:
            return False
        self._known_costs[pos.y][pos.x] = new_cost
        self.costs[pos.y][pos.x] = new_cost
        return True

    def _visible_tile_cost(self, ct: Controller, pos: Position) -> float:
        env = ct.get_tile_env(pos)
        if env == Environment.WALL:
            return INF

        if ct.is_tile_passable(pos):
            return PASSABLE_COST

        building_id = ct.get_tile_building_id(pos)
        if building_id is not None:
            building_type = ct.get_entity_type(building_id)
            if building_type == EntityType.ROAD:
                return PASSABLE_COST
            return INF

        if env == Environment.EMPTY:
            return BUILDABLE_COST

        return INF

    def _is_temporarily_blocked(
        self,
        ct: Controller | None,
        node: tuple[int, int],
        start_key: tuple[int, int],
    ) -> bool:
        if ct is None:
            return False
        pos = Position(node[0], node[1])
        if not ct.is_in_vision(pos):
            return False
        bot_id = ct.get_tile_builder_bot_id(pos)
        if bot_id is None:
            return False
        return node != start_key

    def _movement_cost(
        self, from_node: tuple[int, int], to_node: tuple[int, int],
    ) -> float:
        cell_cost = self.costs[to_node[1]][to_node[0]]
        if math.isinf(cell_cost):
            return INF

        dx = abs(from_node[0] - to_node[0])
        dy = abs(from_node[1] - to_node[1])
        step_scale = math.sqrt(2.0) if dx == 1 and dy == 1 else 1.0
        return cell_cost * step_scale

    def _heuristic(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        diagonal = min(dx, dy)
        straight = max(dx, dy) - diagonal
        return diagonal * math.sqrt(2.0) + straight

    def _direction_toward(
        self,
        start_key: tuple[int, int],
        goal_key: tuple[int, int],
    ) -> Direction | None:
        start = Position(start_key[0], start_key[1])
        goal = Position(goal_key[0], goal_key[1])
        if start == goal:
            return None
        return start.direction_to(goal)

    def _turn_distance(self, a: Direction, b: Direction) -> int:
        if a == b:
            return 0

        steps = 0
        current = a
        while current != b and steps < 8:
            current = current.rotate_left()
            steps += 1

        other_steps = 0
        current = a
        while current != b and other_steps < 8:
            current = current.rotate_right()
            other_steps += 1

        return min(steps, other_steps)

    def _direction_bias(self, direction: Direction) -> int:
        if direction in (
            Direction.NORTH,
            Direction.EAST,
            Direction.SOUTH,
            Direction.WEST,
        ):
            return 0
        return 1

    def _to_key(self, pos: Position) -> tuple[int, int]:
        return (pos.x, pos.y)
from __future__ import annotations

import heapq

from cambc import Direction

INF = float("inf")
PASSABLE_COST = 1.0
BUILDABLE_COST = 2.0
UNKNOWN_COST = BUILDABLE_COST

ALL_DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class DStarLitePlanner:
    """Incremental path planner for builder bots on a 2D Battlecode map.

    The planner stores a persistent 2D cost grid where unseen tiles are treated
    optimistically as usable. Known walls and permanently blocked tiles are given
    infinite cost, while known passable or buildable tiles receive finite costs.

    This planner is designed for one builder bot instance. Call `observe()` each
    turn to update only the tiles that are currently visible, then call
    `next_step()` or `next_direction()` to retrieve the repaired path.
    """

    def __init__(self, width: int, height: int) -> None:
        """Create a planner for a rectangular map.

        Args:
            width: Map width in tiles.
            height: Map height in tiles.

        The planner starts with optimistic map knowledge: every in-bounds tile is
        assumed usable until vision proves otherwise.
        """

        self.width = width
        self.height = height
        self.costs = [[UNKNOWN_COST for _ in range(width)] for _ in range(height)]
        self.g = [[INF for _ in range(width)] for _ in range(height)]
        self.rhs = [[INF for _ in range(width)] for _ in range(height)]
        self._known_costs: list[list[float | None]] = [
            [None for _ in range(width)] for _ in range(height)
        ]
        self._queue: list[tuple[float, float, int, tuple[int, int]]] = []
        self._queue_counter = 0
        self._goal: tuple[int, int] | None = None
        self._last_start: tuple[int, int] | None = None
        self._k_m = 0.0

    def set_goal(self, goal: Position) -> None:
        """Set or replace the planner goal.

        Args:
            goal: The target tile the builder should move toward.

        Setting a new goal resets the D* Lite state while preserving the known
        map costs. The caller should set the goal once, then reuse the planner
        across turns as the builder moves.
        """

        goal_key = self._to_key(goal)
        if not self.in_bounds(goal):
            msg = "goal must be in bounds"
            raise ValueError(msg)

        self._goal = goal_key
        self._queue.clear()
        self._queue_counter = 0
        self._last_start = None
        self._k_m = 0.0

        for y in range(self.height):
            for x in range(self.width):
                self.g[y][x] = INF
                self.rhs[y][x] = INF

        self._set_rhs(goal_key, 0.0)
        self._push_queue(goal_key, self._calculate_key(goal_key, goal_key))

    def clear_goal(self) -> None:
        """Remove the current goal and clear the pending open set.

        After calling this method, `next_step()` and `next_direction()` will
        return `None` until a new goal is assigned with `set_goal()`.
        """

        self._goal = None
        self._queue.clear()
        self._queue_counter = 0
        self._last_start = None
        self._k_m = 0.0

    def has_goal(self) -> bool:
        """Return whether the planner currently has a goal."""

        return self._goal is not None

    def goal(self) -> Position | None:
        """Return the current goal position, if one is set."""

        if self._goal is None:
            return None
        return Position(self._goal[0], self._goal[1])

    def observe(self, ct: Controller) -> bool:
        """Update known tile costs from the bot's current vision.

        Args:
            ct: The live controller for the current builder bot.

        Returns:
            True if at least one visible tile changed known cost and the planner
            repaired its shortest path state, otherwise False.

        Only currently visible tiles are scanned. Unseen tiles remain optimistic
        so the planner can route through unexplored space. Temporary builder bot
        occupancy is not stored as a permanent obstacle in the map.
        """

        if self._goal is None:
            return False

        changed = False
        for pos in ct.get_nearby_tiles():
            new_cost = self._visible_tile_cost(ct, pos)
            if self._set_known_cost(pos, new_cost):
                changed = True
                key = self._to_key(pos)
                self._update_vertex(key)
                for neighbor in self._neighbors(key):
                    self._update_vertex(neighbor)

        if changed and self._last_start is not None:
            self._compute_shortest_path(self._last_start)
        return changed

    def next_step(
        self, start: Position, ct: Controller | None = None,
    ) -> Position | None:
        """Return the next tile on the repaired path from `start` to the goal.

        Args:
            start: The builder's current position.
            ct: Optional controller used to ignore temporary visible blockers when
                choosing the immediate next move.

        Returns:
            The adjacent tile the builder should head to next, or None if there is
            no goal, the goal has been reached, or no path is currently known.

        This method updates the D* Lite start state incrementally as the builder
        moves from turn to turn.
        """

        if self._goal is None:
            return None
        if not self.in_bounds(start):
            return None

        start_key = self._to_key(start)
        if start_key == self._goal:
            return None

        self._prepare_start(start_key)
        self._compute_shortest_path(start_key)

        best_neighbor = None
        best_score = INF
        for neighbor in self._neighbors(start_key):
            if self._is_temporarily_blocked(ct, neighbor, start_key):
                continue
            move_cost = self._movement_cost(start_key, neighbor)
            if math.isinf(move_cost):
                continue
            score = move_cost + self._get_g(neighbor)
            if score < best_score:
                best_score = score
                best_neighbor = neighbor

        if best_neighbor is None or math.isinf(best_score):
            return None
        return Position(best_neighbor[0], best_neighbor[1])

    def next_direction(
        self,
        start: Position,
        ct: Controller | None = None,
    ) -> Direction | None:
        """Return the direction for the next repaired step toward the goal.

        Args:
            start: The builder's current position.
            ct: Optional controller used to skip temporarily occupied neighbors.

        Returns:
            The direction from `start` to the next step, or None if no step is
            currently available.
        """

        step = self.next_step(start, ct)
        if step is None:
            return None
        return start.direction_to(step)

    def is_known_blocked(self, pos: Position) -> bool:
        """Return whether a tile is currently known to be permanently blocked."""

        if not self.in_bounds(pos):
            return True
        return math.isinf(self.costs[pos.y][pos.x])

    def debug_known_cost(self, pos: Position) -> float:
        """Return the planner's currently stored cost for a tile."""

        if not self.in_bounds(pos):
            return INF
        return self.costs[pos.y][pos.x]

    def in_bounds(self, pos: Position) -> bool:
        """Return whether a position lies inside the planner's map bounds."""

        return 0 <= pos.x < self.width and 0 <= pos.y < self.height

    def _prepare_start(self, start_key: tuple[int, int]) -> None:
        """Advance the incremental start state when the builder has moved."""

        if self._last_start is None:
            self._last_start = start_key
            return
        if self._last_start != start_key:
            self._k_m += self._heuristic(self._last_start, start_key)
            self._last_start = start_key

    def _set_known_cost(self, pos: Position, new_cost: float) -> bool:
        """Store a newly observed tile cost and report whether it changed."""

        current = self._known_costs[pos.y][pos.x]
        if current == new_cost:
            return False
        self._known_costs[pos.y][pos.x] = new_cost
        self.costs[pos.y][pos.x] = new_cost
        return True

    def _visible_tile_cost(self, ct: Controller, pos: Position) -> float:
        """Classify one visible tile into a persistent planner cost."""

        env = ct.get_tile_env(pos)
        if env == Environment.WALL:
            return INF

        if ct.is_tile_passable(pos):
            return PASSABLE_COST

        building_id = ct.get_tile_building_id(pos)
        if building_id is not None:
            building_type = ct.get_entity_type(building_id)
            if building_type == EntityType.ROAD:
                return PASSABLE_COST
            return INF

        if env == Environment.EMPTY:
            return BUILDABLE_COST

        return INF

    def _is_temporarily_blocked(
        self,
        ct: Controller | None,
        node: tuple[int, int],
        start_key: tuple[int, int],
    ) -> bool:
        """Check whether a visible builder bot blocks this step right now."""

        if ct is None:
            return False
        pos = Position(node[0], node[1])
        if not ct.is_in_vision(pos):
            return False
        bot_id = ct.get_tile_builder_bot_id(pos)
        if bot_id is None:
            return False
        return node != start_key

    def _compute_shortest_path(self, start_key: tuple[int, int]) -> None:
        """Repair shortest-path values until the current start becomes locally consistent."""

        while self._top_key(start_key) < self._calculate_key(start_key, start_key) or (
            self._get_rhs(start_key) != self._get_g(start_key)
        ):
            top_key, node = self._pop_valid_queue_item(start_key)
            if node is None:
                return

            node_key = self._calculate_key(node, start_key)
            if top_key < node_key:
                self._push_queue(node, node_key)
            elif self._get_g(node) > self._get_rhs(node):
                self._set_g(node, self._get_rhs(node))
                for predecessor in self._predecessors(node):
                    self._update_vertex(predecessor)
            else:
                self._set_g(node, INF)
                self._update_vertex(node)
                for predecessor in self._predecessors(node):
                    self._update_vertex(predecessor)

    def _update_vertex(self, node: tuple[int, int]) -> None:
        """Refresh one node's rhs value and enqueue it if inconsistent."""

        if self._goal is None:
            return

        if node != self._goal:
            best_rhs = INF
            for neighbor in self._neighbors(node):
                candidate = self._movement_cost(node, neighbor) + self._get_g(neighbor)
                best_rhs = min(best_rhs, candidate)
            self._set_rhs(node, best_rhs)

        if self._get_g(node) != self._get_rhs(node):
            start_key = self._last_start if self._last_start is not None else self._goal
            self._push_queue(node, self._calculate_key(node, start_key))

    def _calculate_key(
        self,
        node: tuple[int, int],
        start_key: tuple[int, int],
    ) -> tuple[float, float]:
        """Compute the D* Lite priority key for a node."""

        best = min(self._get_g(node), self._get_rhs(node))
        return (best + self._heuristic(start_key, node) + self._k_m, best)

    def _movement_cost(
        self, from_node: tuple[int, int], to_node: tuple[int, int],
    ) -> float:
        """Return the edge cost for stepping into a neighboring tile."""

        cell_cost = self.costs[to_node[1]][to_node[0]]
        if math.isinf(cell_cost):
            return INF

        dx = abs(from_node[0] - to_node[0])
        dy = abs(from_node[1] - to_node[1])
        step_scale = math.sqrt(2.0) if dx == 1 and dy == 1 else 1.0
        return cell_cost * step_scale

    def _heuristic(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        """Return an admissible octile heuristic for 8-neighbor movement."""

        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        diagonal = min(dx, dy)
        straight = max(dx, dy) - diagonal
        return diagonal * math.sqrt(2.0) + straight

    def _neighbors(self, node: tuple[int, int]) -> list[tuple[int, int]]:
        """Return all in-bounds 8-neighbor tiles for a node."""

        neighbors: list[tuple[int, int]] = []
        pos = Position(node[0], node[1])
        for direction in ALL_DIRECTIONS:
            nxt = pos.add(direction)
            if self.in_bounds(nxt):
                neighbors.append((nxt.x, nxt.y))
        return neighbors

    def _predecessors(self, node: tuple[int, int]) -> list[tuple[int, int]]:
        """Return predecessor nodes for D* Lite updates on an undirected grid."""

        return self._neighbors(node)

    def _push_queue(
        self,
        node: tuple[int, int],
        key: tuple[float, float],
    ) -> None:
        """Push a keyed node into the priority queue."""

        self._queue_counter += 1
        heapq.heappush(self._queue, (key[0], key[1], self._queue_counter, node))

    def _pop_valid_queue_item(
        self,
        start_key: tuple[int, int],
    ) -> tuple[tuple[float, float], tuple[int, int] | None]:
        """Pop the next non-stale inconsistent node from the queue."""

        while self._queue:
            k1, k2, _, node = heapq.heappop(self._queue)
            current_key = self._calculate_key(node, start_key)
            popped_key = (k1, k2)
            if popped_key > current_key:
                self._push_queue(node, current_key)
                continue
            if self._get_g(node) == self._get_rhs(node):
                continue
            return popped_key, node
        return (INF, INF), None

    def _top_key(self, start_key: tuple[int, int]) -> tuple[float, float]:
        """Peek the smallest valid queue key, discarding stale entries on demand."""

        while self._queue:
            k1, k2, _, node = self._queue[0]
            current_key = self._calculate_key(node, start_key)
            queued_key = (k1, k2)
            if queued_key > current_key or self._get_g(node) == self._get_rhs(node):
                heapq.heappop(self._queue)
                if queued_key > current_key:
                    self._push_queue(node, current_key)
                continue
            return queued_key
        return (INF, INF)

    def _get_g(self, node: tuple[int, int]) -> float:
        """Return the current g-value for a node."""

        return self.g[node[1]][node[0]]

    def _set_g(self, node: tuple[int, int], value: float) -> None:
        """Store a g-value for a node."""

        self.g[node[1]][node[0]] = value

    def _get_rhs(self, node: tuple[int, int]) -> float:
        """Return the current rhs-value for a node."""

        return self.rhs[node[1]][node[0]]

    def _set_rhs(self, node: tuple[int, int], value: float) -> None:
        """Store an rhs-value for a node."""

        self.rhs[node[1]][node[0]] = value

    def _to_key(self, pos: Position) -> tuple[int, int]:
        """Convert a Position into the planner's tuple node format."""

        return (pos.x, pos.y)
from __future__ import annotations

from collections import deque

from cambc import Direction
from role_memory import EconomyMemory

CARDINAL_DIRECTIONS = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
]

EIGHT_NEIGHBOR_STEPS = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


class BaseEconomyState:
    """Base class for economy-focused builder states."""

    name = "base"

    def enter(self, player, ct) -> None:
        pass

    def run(self, player, ct) -> None:
        raise NotImplementedError

    def exit(self, player, ct) -> None:
        pass

    def _memory(self, player) -> EconomyMemory:
        assert isinstance(player.memory, EconomyMemory)
        return player.memory

    def _set_move_goal(self, player, target: Position) -> None:
        memory = self._memory(player)
        assert player.planner is not None
        if memory.active_move_goal == target:
            return
        memory.active_move_goal = target
        player.planner.set_goal(target)

    def _advance_with_roads(self, player, ct: Controller, target: Position) -> bool:
        assert player.planner is not None
        self._set_move_goal(player, target)

        current = ct.get_position()
        next_pos = player.planner.next_step(current, ct)
        if next_pos is None:
            return False

        if ct.is_in_vision(next_pos):
            building_id = ct.get_tile_building_id(next_pos)
            if (
                ct.get_tile_env(next_pos) == Environment.EMPTY
                and building_id is None
                and ct.can_build_road(next_pos)
            ):
                ct.build_road(next_pos)

        move_dir = current.direction_to(next_pos)
        if ct.can_move(move_dir):
            ct.move(move_dir)
            return True
        return False

    def _clear_ore_job(self, player) -> None:
        memory = self._memory(player)
        memory.vein_ores = set()
        memory.harvested_vein_ores = set()
        memory.current_ore_target = None
        memory.ore_work_tile = None
        memory.conveyor_route = []
        memory.conveyor_index = 0
        memory.active_move_goal = None

    def _ore_tile_still_valid(
        self, player, ct: Controller, ore: Position | None,
    ) -> bool:
        if ore is None:
            return False
        assert player.planner is not None
        if not player.planner.in_bounds(ore):
            return False
        if not ct.is_in_vision(ore):
            return True
        if ct.get_tile_env(ore) != Environment.ORE_TITANIUM:
            return False
        building_id = ct.get_tile_building_id(ore)
        if building_id is None:
            return True
        return ct.get_entity_type(building_id) == EntityType.HARVESTER

    def _ore_target_still_valid(self, player, ct: Controller) -> bool:
        memory = self._memory(player)
        return self._ore_tile_still_valid(player, ct, memory.current_ore_target)

    def _ore_has_harvester(self, player, ct: Controller, ore: Position | None) -> bool:
        memory = self._memory(player)
        if ore in memory.harvested_vein_ores:
            return True
        if ore is None or not ct.is_in_vision(ore):
            return False
        building_id = ct.get_tile_building_id(ore)
        if building_id is None:
            return False
        has_harvester = ct.get_entity_type(building_id) == EntityType.HARVESTER
        if has_harvester:
            memory.harvested_vein_ores.add(ore)
        return has_harvester

    def _has_harvester_on_target(self, player, ct: Controller) -> bool:
        memory = self._memory(player)
        return self._ore_has_harvester(player, ct, memory.current_ore_target)

    def _pick_adjacent_work_tile(
        self, player, ct: Controller, ore_pos: Position,
    ) -> Position | None:
        current = ct.get_position()
        assert player.planner is not None
        candidates: list[tuple[int, int, Position]] = []
        for direction in CARDINAL_DIRECTIONS:
            pos = ore_pos.add(direction)
            if not player.planner.in_bounds(pos):
                continue
            if ct.is_in_vision(pos):
                if ct.get_tile_env(pos) != Environment.EMPTY:
                    continue
                building_id = ct.get_tile_building_id(pos)
                if building_id is not None:
                    building_type = ct.get_entity_type(building_id)
                    if building_type not in (EntityType.ROAD, EntityType.CONVEYOR):
                        continue
                bot_id = ct.get_tile_builder_bot_id(pos)
                if bot_id is not None and pos != current:
                    continue
            elif player.planner.is_known_blocked(pos):
                continue
            candidates.append((current.distance_squared(pos), pos.x + pos.y, pos))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _are_8_connected(self, a: Position, b: Position) -> bool:
        return max(abs(a.x - b.x), abs(a.y - b.y)) == 1

    def _expand_visible_vein(self, player, ct: Controller) -> None:
        memory = self._memory(player)
        if not memory.vein_ores:
            return

        visible_ores = {
            pos
            for pos in ct.get_nearby_tiles()
            if ct.get_tile_env(pos) == Environment.ORE_TITANIUM
        }
        expanded = set(memory.vein_ores)

        changed = True
        while changed:
            changed = False
            for ore in list(visible_ores):
                if ore in expanded:
                    visible_ores.remove(ore)
                    continue
                if any(self._are_8_connected(ore, known) for known in expanded):
                    expanded.add(ore)
                    visible_ores.remove(ore)
                    changed = True

        memory.vein_ores = expanded

    def _next_unharvested_vein_ore(self, player, ct: Controller) -> Position | None:
        memory = self._memory(player)
        self._expand_visible_vein(player, ct)

        invalid_ores = {
            ore
            for ore in memory.vein_ores
            if not self._ore_tile_still_valid(player, ct, ore)
        }
        if invalid_ores:
            memory.vein_ores.difference_update(invalid_ores)

        current = ct.get_position()
        candidates: list[tuple[int, int, Position, Position]] = []
        for ore in memory.vein_ores:
            if self._ore_has_harvester(player, ct, ore):
                continue
            work_tile = self._pick_adjacent_work_tile(player, ct, ore)
            if work_tile is None:
                continue
            candidates.append(
                (
                    current.distance_squared(ore),
                    current.distance_squared(work_tile),
                    ore,
                    work_tile,
                ),
            )

        if not candidates:
            return None

        candidates.sort()
        _, _, ore, work_tile = candidates[0]
        memory.current_ore_target = ore
        memory.ore_work_tile = work_tile
        return ore

    def _vein_complete(self, player, ct: Controller) -> bool:
        memory = self._memory(player)
        self._expand_visible_vein(player, ct)
        if not memory.vein_ores:
            return False
        for ore in memory.vein_ores:
            if not self._ore_tile_still_valid(player, ct, ore):
                continue
            if not self._ore_has_harvester(player, ct, ore):
                return False
        return True

    def _reconstruct_path(
        self,
        previous: dict[Position, Position | None],
        end: Position,
    ) -> list[Position]:
        path: list[Position] = []
        current = end
        while current is not None:
            path.append(current)
            current = previous[current]
        path.reverse()
        return path

    def _is_core_tile(self, player, pos: Position) -> bool:
        if player.core_pos is None:
            return False
        return (
            abs(pos.x - player.core_pos.x) <= 1 and abs(pos.y - player.core_pos.y) <= 1
        )

    def _core_sink_tiles(self, player) -> list[Position]:
        if player.core_pos is None:
            return []
        assert player.planner is not None

        sinks: list[Position] = []
        seen: set[tuple[int, int]] = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                core_tile = Position(player.core_pos.x + dx, player.core_pos.y + dy)
                for direction in CARDINAL_DIRECTIONS:
                    sink = core_tile.add(direction)
                    key = (sink.x, sink.y)
                    if key in seen:
                        continue
                    if not player.planner.in_bounds(sink):
                        continue
                    if self._is_core_tile(player, sink):
                        continue
                    seen.add(key)
                    sinks.append(sink)
        return sinks

    def _can_route_conveyor_through(
        self, player, pos: Position, sink_set: set[Position],
    ) -> bool:
        assert player.planner is not None
        if self._is_core_tile(player, pos):
            return False
        if pos in sink_set:
            return True
        return not player.planner.is_known_blocked(pos)

    def _plan_conveyor_route_to_core(
        self, player, start: Position,
    ) -> list[Position] | None:
        assert player.planner is not None
        sink_candidates = self._core_sink_tiles(player)
        if not sink_candidates:
            return None

        queue = deque([start])
        previous: dict[Position, Position | None] = {start: None}
        sink_set = set(sink_candidates)

        while queue:
            pos = queue.popleft()
            if pos in sink_set:
                return self._reconstruct_path(previous, pos)

            for direction in CARDINAL_DIRECTIONS:
                nxt = pos.add(direction)
                if nxt in previous:
                    continue
                if not player.planner.in_bounds(nxt):
                    continue
                if not self._can_route_conveyor_through(player, nxt, sink_set):
                    continue
                previous[nxt] = pos
                queue.append(nxt)

        return None

    def _refresh_conveyor_route(self, player, ct: Controller) -> None:
        memory = self._memory(player)
        if memory.ore_work_tile is None:
            memory.conveyor_route = []
            memory.conveyor_index = 0
            return
        route = self._plan_conveyor_route_to_core(player, memory.ore_work_tile)
        memory.conveyor_route = route or []
        memory.conveyor_index = 0

    def _core_input_target_for_sink(self, player, sink: Position) -> Position | None:
        if player.core_pos is None:
            return None
        for direction in CARDINAL_DIRECTIONS:
            neighbor = sink.add(direction)
            if self._is_core_tile(player, neighbor):
                return neighbor
        return None

    def _conveyor_output_target(self, player, index: int) -> Position | None:
        memory = self._memory(player)
        if index < 0 or index >= len(memory.conveyor_route):
            return None
        if index + 1 < len(memory.conveyor_route):
            return memory.conveyor_route[index + 1]
        return self._core_input_target_for_sink(player, memory.conveyor_route[index])

    def _has_enough_titanium_for_route(self, player, ct: Controller) -> bool:
        memory = self._memory(player)
        if not memory.conveyor_route:
            return False
        titanium, axionite = ct.get_global_resources()
        conveyor_ti, conveyor_ax = ct.get_conveyor_cost()
        needed = len(memory.conveyor_route)
        return titanium >= conveyor_ti * needed and axionite >= conveyor_ax * needed


class GoToEdgeState(BaseEconomyState):
    name = "go_to_edge"

    def _corner_goals(self, player, ct: Controller) -> list[Position]:
        width = ct.get_map_width()
        height = ct.get_map_height()
        return [
            Position(width - 1, height - 1),
            Position(width - 1, 0),
            Position(0, height - 1),
            Position(0, 0),
        ]

    def _ensure_explore_goal(self, player, ct: Controller) -> Position | None:
        memory = self._memory(player)
        if memory.explore_goal is None:
            memory.explore_goal = self._corner_goals(player, ct)[
                memory.explore_goal_index
            ]
        return memory.explore_goal

    def _advance_explore_goal(self, player, ct: Controller) -> Position:
        memory = self._memory(player)
        goals = self._corner_goals(player, ct)
        memory.explore_goal_index = (memory.explore_goal_index + 1) % len(goals)
        memory.explore_goal = goals[memory.explore_goal_index]
        return memory.explore_goal

    def _find_visible_titanium_seed(self, player, ct: Controller) -> Position | None:
        current = ct.get_position()
        best = None
        best_score = None
        for pos in ct.get_nearby_tiles():
            if ct.get_tile_env(pos) != Environment.ORE_TITANIUM:
                continue
            building_id = ct.get_tile_building_id(pos)
            if (
                building_id is not None
                and ct.get_entity_type(building_id) != EntityType.HARVESTER
            ):
                continue
            work_tile = self._pick_adjacent_work_tile(player, ct, pos)
            if work_tile is None:
                continue
            score = current.distance_squared(pos)
            if best_score is None or score < best_score:
                best = pos
                best_score = score
        return best

    def _collect_visible_titanium_cluster(
        self, player, ct: Controller, seed: Position,
    ) -> set[Position]:
        assert player.planner is not None

        cluster: set[Position] = set()
        queue = deque([seed])
        seen = {seed}

        while queue:
            pos = queue.popleft()
            if not player.planner.in_bounds(pos):
                continue
            if not ct.is_in_vision(pos):
                continue
            if ct.get_tile_env(pos) != Environment.ORE_TITANIUM:
                continue

            cluster.add(pos)
            for dx, dy in EIGHT_NEIGHBOR_STEPS:
                nxt = Position(pos.x + dx, pos.y + dy)
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append(nxt)

        return cluster

    def _acquire_visible_titanium(self, player, ct: Controller) -> bool:
        memory = self._memory(player)
        seed = self._find_visible_titanium_seed(player, ct)
        if seed is None:
            return False

        memory.vein_ores = self._collect_visible_titanium_cluster(player, ct, seed)
        memory.harvested_vein_ores = {
            ore for ore in memory.vein_ores if self._ore_has_harvester(player, ct, ore)
        }
        memory.current_ore_target = None
        memory.ore_work_tile = None
        memory.conveyor_route = []
        memory.conveyor_index = 0
        return self._next_unharvested_vein_ore(player, ct) is not None

    def enter(self, player, ct) -> None:
        self._ensure_explore_goal(player, ct)

    def run(self, player, ct) -> None:
        if self._acquire_visible_titanium(player, ct):
            player.transition(ct, "move_to_titanium", "found_titanium")
            return

        goal = self._ensure_explore_goal(player, ct)
        if goal is None:
            return
        if ct.get_position() == goal:
            goal = self._advance_explore_goal(player, ct)
        if goal is not None:
            self._advance_with_roads(player, ct, goal)


class MoveToTitaniumState(BaseEconomyState):
    name = "move_to_titanium"

    def enter(self, player, ct) -> None:
        self._next_unharvested_vein_ore(player, ct)

    def run(self, player, ct) -> None:
        memory = self._memory(player)
        ore = memory.current_ore_target
        if ore is None:
            ore = self._next_unharvested_vein_ore(player, ct)
        if ore is None:
            self._clear_ore_job(player)
            player.transition(ct, "go_to_edge", "missing_titanium_target")
            return
        if not self._ore_target_still_valid(player, ct):
            memory.vein_ores.discard(ore)
            memory.current_ore_target = None
            ore = self._next_unharvested_vein_ore(player, ct)
            if ore is None:
                self._clear_ore_job(player)
                player.transition(ct, "go_to_edge", "missing_titanium_target")
                return

        if memory.ore_work_tile is None:
            memory.ore_work_tile = self._pick_adjacent_work_tile(player, ct, ore)
            if memory.ore_work_tile is None:
                memory.vein_ores.discard(ore)
                memory.current_ore_target = None
                ore = self._next_unharvested_vein_ore(player, ct)
                if ore is None:
                    self._clear_ore_job(player)
                    player.transition(ct, "go_to_edge", "no_adjacent_work_tile")
                    return

        if ct.get_position() == memory.ore_work_tile:
            player.transition(ct, "build_harvester", "reached_titanium_support_tile")
            return

        if memory.ore_work_tile is None:
            return
        self._advance_with_roads(player, ct, memory.ore_work_tile)


class BuildHarvesterState(BaseEconomyState):
    name = "build_harvester"

    def run(self, player, ct) -> None:
        memory = self._memory(player)
        self._expand_visible_vein(player, ct)
        ore = memory.current_ore_target
        work_tile = memory.ore_work_tile
        if (
            ore is None
            or work_tile is None
            or not self._ore_target_still_valid(player, ct)
        ):
            if ore is not None:
                memory.vein_ores.discard(ore)
                memory.current_ore_target = None
            next_ore = self._next_unharvested_vein_ore(player, ct)
            if next_ore is not None:
                player.transition(ct, "move_to_titanium", "harvester_target_invalid")
            else:
                self._clear_ore_job(player)
                player.transition(ct, "go_to_edge", "harvester_target_invalid")
            return

        if self._has_harvester_on_target(player, ct):
            next_ore = self._next_unharvested_vein_ore(player, ct)
            if next_ore is not None:
                player.transition(ct, "move_to_titanium", "next_vein_ore_ready")
            else:
                player.transition(ct, "wait_for_titanium", "vein_harvested")
            return

        if ct.get_position() != work_tile:
            self._advance_with_roads(player, ct, work_tile)
            return

        if ct.can_build_harvester(ore):
            ct.build_harvester(ore)
            memory.harvested_vein_ores.add(ore)
            self._expand_visible_vein(player, ct)
            next_ore = self._next_unharvested_vein_ore(player, ct)
            if next_ore is not None:
                player.transition(
                    ct, "move_to_titanium", "built_harvester_continue_vein",
                )
            else:
                player.transition(ct, "wait_for_titanium", "built_final_harvester")


class WaitForTitaniumState(BaseEconomyState):
    name = "wait_for_titanium"

    def enter(self, player, ct) -> None:
        self._refresh_conveyor_route(player, ct)

    def run(self, player, ct) -> None:
        memory = self._memory(player)
        if not memory.vein_ores or memory.ore_work_tile is None:
            self._clear_ore_job(player)
            player.transition(ct, "go_to_edge", "wait_missing_ore_job")
            return

        if not self._vein_complete(player, ct):
            if self._next_unharvested_vein_ore(player, ct) is not None:
                player.transition(ct, "move_to_titanium", "vein_not_finished")
                return
            player.transition(ct, "build_harvester", "harvester_missing")
            return

        if not memory.conveyor_route:
            self._refresh_conveyor_route(player, ct)
        if not memory.conveyor_route:
            self._clear_ore_job(player)
            player.transition(ct, "go_to_edge", "no_conveyor_route")
            return

        if ct.get_position() != memory.conveyor_route[0]:
            self._advance_with_roads(player, ct, memory.conveyor_route[0])
            return

        if self._has_enough_titanium_for_route(player, ct):
            player.transition(ct, "connect_to_core", "enough_titanium_for_route")


class ConnectToCoreState(BaseEconomyState):
    name = "connect_to_core"

    def enter(self, player, ct) -> None:
        memory = self._memory(player)
        self._refresh_conveyor_route(player, ct)
        memory.conveyor_index = 0

    def run(self, player, ct) -> None:
        memory = self._memory(player)
        route = memory.conveyor_route
        if not route:
            self._clear_ore_job(player)
            player.transition(ct, "go_to_edge", "empty_conveyor_route")
            return

        if memory.conveyor_index >= len(route):
            self._clear_ore_job(player)
            player.transition(ct, "go_to_edge", "conveyor_route_complete")
            return

        target_tile = route[memory.conveyor_index]
        if ct.get_position() != target_tile:
            self._advance_with_roads(player, ct, target_tile)
            return

        next_target = self._conveyor_output_target(player, memory.conveyor_index)
        if next_target is None:
            self._clear_ore_job(player)
            player.transition(ct, "go_to_edge", "missing_conveyor_output_target")
            return

        building_id = ct.get_tile_building_id(target_tile)
        if building_id is not None:
            building_type = ct.get_entity_type(building_id)
            if building_type == EntityType.CONVEYOR:
                try:
                    direction = ct.get_direction(building_id)
                except Exception:
                    direction = None
                if direction == target_tile.direction_to(next_target):
                    memory.conveyor_index += 1
                    return
            if ct.can_destroy(target_tile):
                ct.destroy(target_tile)
            else:
                self._refresh_conveyor_route(player, ct)
                player.transition(ct, "wait_for_titanium", "blocked_conveyor_tile")
                return

        if ct.get_tile_env(target_tile) != Environment.EMPTY:
            self._refresh_conveyor_route(player, ct)
            player.transition(ct, "wait_for_titanium", "conveyor_tile_not_empty")
            return

        direction = target_tile.direction_to(next_target)
        if ct.can_build_conveyor(target_tile, direction):
            ct.build_conveyor(target_tile, direction)
            memory.conveyor_index += 1
            return

        if ct.get_global_resources()[0] < ct.get_conveyor_cost()[0]:
            player.transition(ct, "wait_for_titanium", "ran_out_of_titanium")


def find_friendly_core(player, ct: Controller) -> Position | None:
    """Return the visible allied core position for builder setup."""

    return _SETUP_HELPERS.find_friendly_core(player, ct)


def corner_goals(player, ct: Controller) -> list[Position]:
    """Return the fixed corner exploration goals used during builder setup."""

    return _SETUP_HELPERS.corner_goals(player, ct)


class _SetupHelpers(GoToEdgeState):
    def find_friendly_core(self, player, ct: Controller) -> Position | None:
        for building_id in ct.get_nearby_buildings():
            if ct.get_entity_type(building_id) != EntityType.CORE:
                continue
            if ct.get_team(building_id) != ct.get_team():
                continue
            return ct.get_position(building_id)
        return None

    def corner_goals(self, player, ct: Controller) -> list[Position]:
        return self._corner_goals(player, ct)


_SETUP_HELPERS = _SetupHelpers()
from __future__ import annotations

from bugnav import BugNavPlanner
from cambc import Direction
from economy_states import (
    BuildHarvesterState,
    ConnectToCoreState,
    GoToEdgeState,
    MoveToTitaniumState,
    WaitForTitaniumState,
    corner_goals,
    find_friendly_core,
)
from role_memory import BotRole, TurretPlacerMemory
from state_machine import StateMachine
from turret_placer_states import (
    AssaultTargetedConveyorState,
    EnemyCoreFoundState,
    SearchEnemyCoreState,
)

SPAWN_DIRECTIONS = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
]

MAX_ECONOMY_BUILDERS = 6
MAX_TURRET_PLACERS = 10
TURRET_PLACER_START_ROUND = 10


class Player:
    def __init__(self) -> None:
        self.spawned_economy_builders = 0
        self.spawned_turret_placers = 0

        self.planner: BugNavPlanner | None = None
        self.machine: StateMachine | None = None
        self.builder_ready = False

        self.core_pos = None
        self.role: BotRole | None = None
        self.memory: EconomyMemory | TurretPlacerMemory | None = None

    def run(self, ct: Controller) -> None:
        entity_type = ct.get_entity_type()
        try:
            if entity_type == EntityType.CORE:
                self.run_core(ct)
            elif entity_type == EntityType.BUILDER_BOT:
                self.run_builder(ct)
            elif entity_type == EntityType.GUNNER:
                self.run_gunner(ct)
        except Exception as e:
            print(f"Exception in run: {e}")
            return


    def run_core(self, ct: Controller) -> None:
        desired_role = self.next_spawn_role(ct)
        if desired_role is None:
            return

        center = ct.get_position()
        for direction in SPAWN_DIRECTIONS:
            spawn_pos = center.add(direction)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                if desired_role == BotRole.ECONOMY:
                    self.spawned_economy_builders += 1
                elif desired_role == BotRole.TURRET_PLACER:
                    self.spawned_turret_placers += 1
                return

    def run_builder(self, ct: Controller) -> None:
        self.ensure_builder_ready(ct)
        assert self.planner is not None
        assert self.machine is not None

        self.planner.observe(ct)
        self.machine.step(ct)

    def run_gunner(self, ct: Controller) -> None:
        target = ct.get_gunner_target()
        if target is None:
            return

        building_id = ct.get_tile_building_id(target)
        if building_id is None:
            return
        if ct.get_entity_type(building_id) != EntityType.CORE:
            return
        if ct.get_team(building_id) == ct.get_team():
            return
        if ct.can_fire(target):
            ct.fire(target)

    def ensure_builder_ready(self, ct: Controller) -> None:
        if self.builder_ready:
            return

        self.planner = BugNavPlanner(ct.get_map_width(), ct.get_map_height())
        self.core_pos = find_friendly_core(self, ct)
        self.role = self.choose_builder_role(ct)
        if self.role == BotRole.TURRET_PLACER:
            self.setup_turret_placer_machine(ct)
        else:
            self.setup_economy_machine(ct)

        assert self.machine is not None
        self.machine.enter_initial(ct)
        self.builder_ready = True

    def next_spawn_role(self, ct: Controller) -> BotRole | None:
        if ct.get_current_round() < TURRET_PLACER_START_ROUND:
            if self.spawned_economy_builders < MAX_ECONOMY_BUILDERS:
                return BotRole.ECONOMY
            return None
        if self.spawned_turret_placers < MAX_TURRET_PLACERS:
            return BotRole.TURRET_PLACER
        return None

    def choose_builder_role(self, ct: Controller) -> BotRole:
        if ct.get_current_round() >= TURRET_PLACER_START_ROUND:
            return BotRole.TURRET_PLACER
        return BotRole.ECONOMY

    def setup_economy_machine(self, ct: Controller) -> None:
        explore_goal_index = ct.get_id() % len(corner_goals(self, ct))
        self.memory = EconomyMemory(explore_goal_index=explore_goal_index)
        self.memory.explore_goal = corner_goals(self, ct)[explore_goal_index]

        self.machine = StateMachine(self, initial="go_to_edge")
        self.machine.add_state(GoToEdgeState())
        self.machine.add_state(MoveToTitaniumState())
        self.machine.add_state(BuildHarvesterState())
        self.machine.add_state(WaitForTitaniumState())
        self.machine.add_state(ConnectToCoreState())

        self.machine.connect("go_to_edge", "move_to_titanium")
        self.machine.connect("move_to_titanium", "build_harvester")
        self.machine.connect_many("move_to_titanium", ["go_to_edge"])
        self.machine.connect_many(
            "build_harvester", ["move_to_titanium", "wait_for_titanium", "go_to_edge"],
        )
        self.machine.connect_many(
            "wait_for_titanium",
            ["connect_to_core", "build_harvester", "go_to_edge"],
        )
        self.machine.connect_many(
            "connect_to_core", ["wait_for_titanium", "go_to_edge"],
        )

    def setup_turret_placer_machine(self, ct: Controller) -> None:
        search_goal_index = ct.get_id() % len(corner_goals(self, ct))
        self.memory = TurretPlacerMemory(search_goal_index=search_goal_index)

        self.machine = StateMachine(self, initial="search_enemy_core")
        self.machine.add_state(SearchEnemyCoreState())
        self.machine.add_state(EnemyCoreFoundState())
        self.machine.add_state(AssaultTargetedConveyorState())
        self.machine.connect("search_enemy_core", "enemy_core_found")
        self.machine.connect("enemy_core_found", "search_enemy_core")
        self.machine.connect("enemy_core_found", "assault_targeted_conveyor")
        self.machine.connect("assault_targeted_conveyor", "enemy_core_found")

    def transition(self, ct: Controller, new_state: str, reason: str = "") -> None:
        assert self.machine is not None
        old_state = self.machine.state
        self.machine.transition(new_state, ct, reason)
        if old_state != new_state:
            suffix = f" reason={reason}" if reason else ""
            print(
                f"[r={ct.get_current_round()} id={ct.get_id()}] state_change {old_state} -> {new_state}{suffix}",
            )
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BotRole(Enum):
    ECONOMY = "economy"
    TURRET_PLACER = "turret_placer"
    SCOUT = "scout"
    COMBAT = "combat"


@dataclass
class EconomyMemory:
    explore_goal_index: int = 0
    explore_goal: Position | None = None
    active_move_goal: Position | None = None
    vein_ores: set[Position] = field(default_factory=set)
    harvested_vein_ores: set[Position] = field(default_factory=set)
    current_ore_target: Position | None = None
    ore_work_tile: Position | None = None
    conveyor_route: list[Position] = field(default_factory=list)
    conveyor_index: int = 0


@dataclass
class TurretPlacerMemory:
    search_goal_index: int = 0
    search_goal: Position | None = None
    active_move_goal: Position | None = None
    enemy_core_pos: Position | None = None
    targeted_conveyors: set[Position] = field(default_factory=set)
    active_targeted_conveyor: Position | None = None
    gunner_site: Position | None = None
from __future__ import annotations

from typing import Any, Protocol


class StateProtocol(Protocol):
    """Protocol for object-based bot states."""

    name: str

    def enter(self, player: Any, ct: Any) -> None: ...

    def run(self, player: Any, ct: Any) -> None: ...

    def exit(self, player: Any, ct: Any) -> None: ...


class StateMachine:
    """Small explicit state machine for object-based bot states.

    Each registered state is an object with a unique ``name`` plus ``enter()``,
    ``run()``, and ``exit()`` methods. Transitions must be connected ahead of
    time, which makes state flow easy to inspect and hard to break accidentally.
    """

    def __init__(self, owner: Any, initial: str) -> None:
        """Create a state machine for one owner object.

        Args:
            owner: The object that owns the machine, usually a bot player.
            initial: Name of the initial registered state.
        """

        self.owner = owner
        self._initial = initial
        self._state = initial
        self._states: dict[str, StateProtocol] = {}
        self._transitions: dict[str, set[str]] = {}
        self._last_reason = ""

    @property
    def state(self) -> str:
        """Return the current state name."""

        return self._state

    @property
    def last_reason(self) -> str:
        """Return the reason attached to the most recent transition."""

        return self._last_reason

    def add_state(self, state: StateProtocol) -> None:
        """Register a state object with the machine."""

        self._states[state.name] = state
        self._transitions.setdefault(state.name, set())

    def connect(self, source: str, target: str) -> None:
        """Allow a transition from ``source`` to ``target``."""

        self._require_state(source)
        self._require_state(target)
        self._transitions[source].add(target)

    def connect_many(self, source: str, targets: list[str] | tuple[str, ...]) -> None:
        """Allow one state to transition to several targets."""

        for target in targets:
            self.connect(source, target)

    def can_transition(self, target: str) -> bool:
        """Return whether the current state may transition to ``target``."""

        if target == self._state:
            return True
        return target in self._transitions.get(self._state, set())

    def transition(self, target: str, ct: Any, reason: str = "") -> None:
        """Move to a connected state and run exit/enter hooks.

        Args:
            target: Name of the next state.
            ct: Controller-like object passed to state hooks.
            reason: Optional debug string for the transition.
        """

        self._require_state(target)
        old_state_name = self._state
        if target == old_state_name:
            self._last_reason = reason
            return
        if not self.can_transition(target):
            msg = f"illegal transition: {old_state_name} -> {target}"
            raise ValueError(msg)

        old_state = self._states[old_state_name]
        new_state = self._states[target]
        old_state.exit(self.owner, ct)
        self._state = target
        self._last_reason = reason
        new_state.enter(self.owner, ct)

    def reset(self, ct: Any | None = None) -> None:
        """Return the machine to its initial state.

        If ``ct`` is provided and both current and initial states are registered,
        exit/enter hooks are run as part of the reset.
        """

        if (
            ct is not None
            and self._state in self._states
            and self._initial in self._states
        ):
            self._states[self._state].exit(self.owner, ct)
            self._state = self._initial
            self._last_reason = ""
            self._states[self._state].enter(self.owner, ct)
            return
        self._state = self._initial
        self._last_reason = ""

    def enter_initial(self, ct: Any) -> None:
        """Run the initial state's enter hook once after setup."""

        self._require_state(self._state)
        self._states[self._state].enter(self.owner, ct)

    def step(self, ct: Any) -> None:
        """Run the current state's main logic."""

        self._require_state(self._state)
        self._states[self._state].run(self.owner, ct)

    def available_transitions(self, state: str | None = None) -> set[str]:
        """Return the allowed targets from a given state."""

        chosen_state = self._state if state is None else state
        self._require_state(chosen_state)
        return set(self._transitions[chosen_state])

    def _require_state(self, name: str) -> None:
        if name not in self._states:
            msg = f"unknown state: {name}"
            raise KeyError(msg)
from __future__ import annotations

from cambc import Direction
from role_memory import TurretPlacerMemory

SEARCH_DIRECTIONS = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
]


class BaseTurretPlacerState:
    name = "base"

    def enter(self, player, ct) -> None:
        pass

    def run(self, player, ct) -> None:
        raise NotImplementedError

    def exit(self, player, ct) -> None:
        pass

    def _memory(self, player) -> TurretPlacerMemory:
        assert isinstance(player.memory, TurretPlacerMemory)
        return player.memory

    def _set_move_goal(self, player, target: Position) -> None:
        memory = self._memory(player)
        assert player.planner is not None
        if memory.active_move_goal == target:
            return
        memory.active_move_goal = target
        player.planner.set_goal(target)

    def _advance_with_roads(self, player, ct: Controller, target: Position) -> bool:
        memory = self._memory(player)
        assert player.planner is not None
        self._set_move_goal(player, target)
        print(
            "current: ",
            ct.get_position(),
            " target: ",
            target,
            " active_move_goal: ",
            memory.active_move_goal,
        )

        current = ct.get_position()
        next_pos = player.planner.next_step(current, ct)
        if next_pos is None:
            visible = ct.is_in_vision(target)
            building_id = ct.get_tile_building_id(target) if visible else None
            building_type = (
                ct.get_entity_type(building_id) if building_id is not None else None
            )
            builder_id = ct.get_tile_builder_bot_id(target) if visible else None
            env = ct.get_tile_env(target) if visible else None
            passable = ct.is_tile_passable(target) if visible else None
            print(
                "no next step for target ",
                target,
                " current=",
                current,
                " target_blocked=",
                player.planner.is_known_blocked(target),
                " known_cost=",
                player.planner.debug_known_cost(target),
                " visible=",
                visible,
                " env=",
                env,
                " building_id=",
                building_id,
                " building_type=",
                building_type,
                " builder_id=",
                builder_id,
                " passable=",
                passable,
            )
            return False

        if ct.is_in_vision(next_pos):
            print("next step: ", next_pos)
            building_id = ct.get_tile_building_id(next_pos)
            if (
                ct.get_tile_env(next_pos) == Environment.EMPTY
                and building_id is None
                and ct.can_build_road(next_pos)
            ):
                print("building road to ", next_pos)
                ct.build_road(next_pos)
        print("moving towards ", next_pos)
        move_dir = current.direction_to(next_pos)
        if ct.can_move(move_dir):
            print("moving in direction ", move_dir)
            ct.move(move_dir)
            print("moved in direction ", move_dir)
            return True
        print("can't move in direction ", move_dir)
        memory.active_move_goal = None
        return False

    def _find_visible_enemy_core(self, player, ct: Controller) -> Position | None:
        for building_id in ct.get_nearby_buildings():
            if ct.get_entity_type(building_id) != EntityType.CORE:
                continue
            if ct.get_team(building_id) == ct.get_team():
                continue
            return ct.get_position(building_id)
        return None

    def _search_goals(self, player, ct: Controller) -> list[Position]:
        width = ct.get_map_width()
        height = ct.get_map_height()
        if player.core_pos is None:
            mirror = Position(width - 1, height - 1)
        else:
            mirror = Position(
                width - 1 - player.core_pos.x, height - 1 - player.core_pos.y,
            )

        goals = [
            mirror,
            Position(width - 1, height - 1),
            Position(width - 1, 0),
            Position(0, height - 1),
            Position(0, 0),
            Position(width // 2, height // 2),
        ]

        deduped: list[Position] = []
        seen: set[tuple[int, int]] = set()
        for goal in goals:
            key = (goal.x, goal.y)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(goal)
        return deduped

    def _core_touching_conveyor_tiles(self, player) -> list[Position]:
        memory = self._memory(player)
        if memory.enemy_core_pos is None:
            return []

        cx = memory.enemy_core_pos.x
        cy = memory.enemy_core_pos.y
        tiles = [
            Position(cx - 1, cy - 2),
            Position(cx, cy - 2),
            Position(cx + 1, cy - 2),
            Position(cx - 1, cy + 2),
            Position(cx, cy + 2),
            Position(cx + 1, cy + 2),
            Position(cx - 2, cy - 1),
            Position(cx - 2, cy),
            Position(cx - 2, cy + 1),
            Position(cx + 2, cy - 1),
            Position(cx + 2, cy),
            Position(cx + 2, cy + 1),
        ]

        if player.planner is None:
            return tiles
        return [tile for tile in tiles if player.planner.in_bounds(tile)]

    def _core_corner_tiles(self, player) -> list[Position]:
        memory = self._memory(player)
        if memory.enemy_core_pos is None:
            return []

        cx = memory.enemy_core_pos.x
        cy = memory.enemy_core_pos.y
        tiles = [
            Position(cx - 2, cy - 2),
            Position(cx - 2, cy + 2),
            Position(cx + 2, cy - 2),
            Position(cx + 2, cy + 2),
        ]

        if player.planner is None:
            return tiles
        return [tile for tile in tiles if player.planner.in_bounds(tile)]

    def _ensure_search_goal(self, player, ct: Controller) -> Position | None:
        memory = self._memory(player)
        if memory.search_goal is None:
            goals = self._search_goals(player, ct)
            memory.search_goal = goals[memory.search_goal_index % len(goals)]
        return memory.search_goal

    def _targeted_conveyor_building_id(
        self, ct: Controller, pos: Position,
    ) -> int | None:
        if not ct.is_in_vision(pos):
            return None
        building_id = ct.get_tile_building_id(pos)
        if building_id is None:
            return None
        building_type = ct.get_entity_type(building_id)
        if building_type not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
            return None
        return building_id

    def _draw_targeted_conveyors(self, player, ct: Controller) -> None:
        memory = self._memory(player)
        for pos in memory.targeted_conveyors:
            ct.draw_indicator_dot(pos, 255, 80, 80)
            if memory.enemy_core_pos is not None:
                ct.draw_indicator_line(pos, memory.enemy_core_pos, 255, 140, 80)


class SearchEnemyCoreState(BaseTurretPlacerState):
    name = "search_enemy_core"

    def _advance_search_goal(self, player, ct: Controller) -> Position:
        memory = self._memory(player)
        goals = self._search_goals(player, ct)
        memory.search_goal_index = (memory.search_goal_index + 1) % len(goals)
        memory.search_goal = goals[memory.search_goal_index]
        memory.active_move_goal = None
        return memory.search_goal

    def enter(self, player, ct) -> None:
        print("entering search enemy core state")
        self._ensure_search_goal(player, ct)

    def run(self, player, ct) -> None:
        print("running search enemy core state")
        memory = self._memory(player)
        enemy_core = self._find_visible_enemy_core(player, ct)
        if enemy_core is not None:
            memory.enemy_core_pos = enemy_core
            player.transition(ct, "enemy_core_found", "enemy_core_visible")
            return

        goal = self._ensure_search_goal(player, ct)
        if goal is None:
            return
        if ct.get_position() == goal:
            goal = self._advance_search_goal(player, ct)
        self._advance_with_roads(player, ct, goal)


class EnemyCoreFoundState(BaseTurretPlacerState):
    name = "enemy_core_found"

    def _has_other_friendly_builder_near(
        self, player, ct: Controller, target: Position,
    ) -> bool:
        my_id = ct.get_id()
        for unit_id in ct.get_nearby_units():
            if unit_id == my_id:
                print("skipping self in nearby units")
                continue
            if ct.get_team(unit_id) != ct.get_team():
                print("skipping enemy unit in nearby units")
                continue
            if ct.get_entity_type(unit_id) != EntityType.BUILDER_BOT:
                print("skipping non-builder unit in nearby units")
                continue
            if ct.get_position(unit_id).distance_squared(target) <= 20:
                print("found friendly builder near ", target)
                # check if they are ontop of the target conveyor
                if ct.get_position(unit_id) == target:
                    print(
                        "friendly builder is about to destroy target conveyor, we should help",
                    )
                    return True
                # check if they are on the corner tiles of the enemy core
                if player.planner is not None and ct.get_position(
                    unit_id,
                ) not in self._core_corner_tiles(player):
                    print(
                        "skipping builder at ",
                        ct.get_position(unit_id),
                        " because it's not on a core corner tile",
                    )
                    continue
                return True
            print(
                "friendly builder not near enough to ",
                target,
                " distance squared: ",
                ct.get_position(unit_id).distance_squared(target),
            )
        return False

    def _touching_tiles_visible_from(
        self,
        observer: Position,
        touching_tiles: list[Position],
        vision_radius_sq: int,
    ) -> int:
        visible = 0
        for tile in touching_tiles:
            if observer.distance_squared(tile) <= vision_radius_sq:
                visible += 1
        return visible

    def _is_enemy_core_tile(self, player, pos: Position) -> bool:
        memory = self._memory(player)
        if memory.enemy_core_pos is None:
            return False
        return (
            abs(pos.x - memory.enemy_core_pos.x) <= 1
            and abs(pos.y - memory.enemy_core_pos.y) <= 1
        )

    def _can_stage_on_tile(self, player, ct: Controller, pos: Position) -> bool:
        assert player.planner is not None
        if not player.planner.in_bounds(pos):
            return False
        if self._is_enemy_core_tile(player, pos):
            return False
        if ct.is_in_vision(pos):
            if ct.get_tile_builder_bot_id(pos) is not None and pos != ct.get_position():
                return False
            building_id = ct.get_tile_building_id(pos)
            if building_id is not None:
                building_type = ct.get_entity_type(building_id)
                if building_type not in (
                    EntityType.ROAD,
                    EntityType.CONVEYOR,
                    EntityType.ARMOURED_CONVEYOR,
                ):
                    return False
            env = ct.get_tile_env(pos)
            return env == Environment.EMPTY or ct.is_tile_passable(pos)
        return not player.planner.is_known_blocked(pos)

    def _nearest_supported_targeted_conveyor(
        self, player, ct: Controller,
    ) -> Position | None:
        memory = self._memory(player)
        current = ct.get_position()
        candidates: list[tuple[int, int, Position]] = []
        for pos in memory.targeted_conveyors:
            if not self._has_other_friendly_builder_near(player, ct, pos):
                print("no friendly builder near ", pos)
                continue
            building_id = self._targeted_conveyor_building_id(ct, pos)
            if building_id is None:
                print("target conveyor not visible for ", pos)
                continue
            candidates.append((current.distance_squared(pos), pos.x + pos.y, pos))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _best_core_observer_tile(self, player, ct: Controller) -> Position | None:
        memory = self._memory(player)
        if memory.enemy_core_pos is None:
            return None
        assert player.planner is not None

        current = ct.get_position()
        vision_radius_sq = ct.get_vision_radius_sq()
        touching_tiles = self._core_touching_conveyor_tiles(player)
        if not touching_tiles:
            return None

        best_pos = None
        best_score = (-1, float("inf"), float("inf"))
        center = memory.enemy_core_pos

        for dx in range(-5, 6):
            for dy in range(-5, 6):
                candidate = Position(center.x + dx, center.y + dy)
                if not self._can_stage_on_tile(player, ct, candidate):
                    continue
                if candidate in touching_tiles:
                    print(
                        "skipping candidate ",
                        candidate,
                        " because it's on a touching tile",
                    )
                    continue

                ct.draw_indicator_dot(candidate, 255, 80, 80)
                visible_count = self._touching_tiles_visible_from(
                    candidate, touching_tiles, vision_radius_sq,
                )
                if visible_count == 0:
                    continue
                score = (
                    visible_count,
                    -current.distance_squared(candidate),
                    -candidate.distance_squared(center),
                )
                if best_pos is None or score > best_score:
                    best_pos = candidate
                    best_score = score

        return best_pos

    def _scan_touching_conveyors(self, player, ct: Controller) -> None:
        memory = self._memory(player)
        for pos in self._core_touching_conveyor_tiles(player):
            if not ct.is_in_vision(pos):
                continue
            building_id = ct.get_tile_building_id(pos)
            if building_id is None:
                continue
            building_type = ct.get_entity_type(building_id)
            if building_type not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                continue
            stored_resource = ct.get_stored_resource(building_id)
            if stored_resource is None:
                continue
            if pos in memory.targeted_conveyors:
                continue
            memory.targeted_conveyors.add(pos)
            print(
                f"[r={ct.get_current_round()} id={ct.get_id()}] targeted_conveyor pos={pos.x},{pos.y} resource={stored_resource.value}",
            )

    def run(self, player, ct) -> None:
        print("running enemy core found state")
        memory = self._memory(player)
        enemy_core = self._find_visible_enemy_core(player, ct)
        if enemy_core is not None:
            memory.enemy_core_pos = enemy_core

        observer_tile = self._best_core_observer_tile(player, ct)
        if observer_tile is not None and ct.get_position() != observer_tile:
            self._advance_with_roads(player, ct, observer_tile)
            self._scan_touching_conveyors(player, ct)
            self._draw_targeted_conveyors(player, ct)
            return

        self._scan_touching_conveyors(player, ct)
        self._draw_targeted_conveyors(player, ct)

        target = self._nearest_supported_targeted_conveyor(player, ct)
        print("nearest supported targeted conveyor: ", target)
        if target is not None:
            memory.active_targeted_conveyor = target
            memory.gunner_site = None
            player.transition(
                ct, "assault_targeted_conveyor", "supported_targeted_conveyor",
            )
            return


class AssaultTargetedConveyorState(BaseTurretPlacerState):
    name = "assault_targeted_conveyor"

    def _pick_gunner_site(
        self, player, ct: Controller, target: Position,
    ) -> Position | None:
        assert player.planner is not None
        current = ct.get_position()
        candidates: list[tuple[int, int, Position]] = []
        print("searching gunner site near target ", target, " from ", current)
        for direction in SEARCH_DIRECTIONS:
            pos = target.add(direction)
            if not player.planner.in_bounds(pos):
                print("reject gunner site out of bounds ", pos)
                continue
            if ct.is_in_vision(pos):
                if ct.get_tile_env(pos) != Environment.EMPTY:
                    print(
                        "reject gunner site non-empty env ", pos, ct.get_tile_env(pos),
                    )
                    continue
                if player.planner.is_known_blocked(pos):
                    print(
                        "reject gunner site planner-blocked visible tile ",
                        pos,
                        " known_cost=",
                        player.planner.debug_known_cost(pos),
                        " building_id=",
                        ct.get_tile_building_id(pos),
                        " builder_id=",
                        ct.get_tile_builder_bot_id(pos),
                        " passable=",
                        ct.is_tile_passable(pos),
                    )
                    continue
                if ct.get_tile_builder_bot_id(pos) is not None and pos != current:
                    print("reject gunner site occupied by builder ", pos)
                    continue
            elif player.planner.is_known_blocked(pos):
                print("reject gunner site known blocked ", pos)
                continue
            print("accept gunner site candidate ", pos)
            candidates.append((current.distance_squared(pos), pos.x + pos.y, pos))

        if not candidates:
            print("no gunner site candidates found for target ", target)
            return None
        candidates.sort()
        print("chosen gunner site ", candidates[0][2])
        return candidates[0][2]

    def _build_gunner_if_possible(self, player, ct: Controller) -> bool:
        memory = self._memory(player)
        if memory.enemy_core_pos is None or memory.active_targeted_conveyor is None:
            return False

        if memory.gunner_site is None:
            memory.gunner_site = self._pick_gunner_site(
                player, ct, memory.active_targeted_conveyor,
            )

        if memory.gunner_site is None:
            return False

        print("loc for gunner: ", memory.gunner_site)

        if ct.get_position() != memory.gunner_site:
            print("moving to gunner site at ", memory.gunner_site)
            self._advance_with_roads(player, ct, memory.gunner_site)
            return False

        direction = memory.active_targeted_conveyor.direction_to(memory.enemy_core_pos)
        if ct.can_build_gunner(memory.active_targeted_conveyor, direction):
            ct.build_gunner(memory.active_targeted_conveyor, direction)
            return True
        return False

    def run(self, player, ct) -> None:
        print("running assault targeted conveyor state")
        memory = self._memory(player)
        target = memory.active_targeted_conveyor
        if target is None:
            player.transition(ct, "enemy_core_found", "missing_assault_target")
            return

        self._draw_targeted_conveyors(player, ct)

        building_id = self._targeted_conveyor_building_id(ct, target)
        if building_id is None:
            print("target conveyor no longer exists")
            print("loc for gunner: ", memory.gunner_site)
            if self._build_gunner_if_possible(player, ct):
                memory.targeted_conveyors.discard(target)
                memory.active_targeted_conveyor = None
                memory.gunner_site = None
                player.transition(
                    ct, "enemy_core_found", "built_gunner_after_target_lost",
                )
                return
            if memory.gunner_site is not None:
                return
            memory.targeted_conveyors.discard(target)
            memory.active_targeted_conveyor = None
            player.transition(ct, "enemy_core_found", "target_lost_no_gunner_site")
            return

        if ct.get_position() != target:
            self._advance_with_roads(player, ct, target)
            return

        ct.self_destruct()
