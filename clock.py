#!/usr/bin/env python3

import curses
import time
from datetime import datetime, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

APP_NAME = "HYPRCLOCK"
VERSION = "1.0"

DEFAULT_TIMER_SECONDS = 5 * 60


# ─────────────────────────────────────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────────────────────────────────────

def format_duration(seconds: float, show_centiseconds: bool = True) -> str:
    """Format a duration as HH:MM:SS.cc or HH:MM:SS."""
    seconds = max(0.0, seconds)

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if show_centiseconds:
        centiseconds = int((seconds * 100) % 100)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_offset(offset_seconds: int) -> str:
    """Format timezone offset as UTC±HH:MM."""
    sign = "+" if offset_seconds >= 0 else "-"
    value = abs(offset_seconds)

    hours = value // 3600
    minutes = (value % 3600) // 60

    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def safe_addstr(window, y, x, text, attribute=0):
    """Draw text safely without crashing at terminal boundaries."""
    height, width = window.getmaxyx()

    if y < 0 or y >= height or x >= width:
        return

    text = str(text)

    if x < 0:
        text = text[-x:]
        x = 0

    available = width - x - 1

    if available <= 0:
        return

    try:
        window.addnstr(y, x, text, available, attribute)
    except curses.error:
        pass


def center_text(window, y, text, attribute=0):
    """Draw centered text."""
    _, width = window.getmaxyx()
    x = max(0, (width - len(text)) // 2)
    safe_addstr(window, y, x, text, attribute)


def draw_box(window, top, left, height, width, title="", attribute=0):
    """Draw a simple rounded-looking panel."""
    if height < 3 or width < 4:
        return

    try:
        window.attron(attribute)

        # Corners
        window.addch(top, left, "╭")
        window.addch(top, left + width - 1, "╮")
        window.addch(top + height - 1, left, "╰")
        window.addch(top + height - 1, left + width - 1, "╯")

        # Horizontal edges
        for x in range(left + 1, left + width - 1):
            window.addch(top, x, "─")
            window.addch(top + height - 1, x, "─")

        # Vertical edges
        for y in range(top + 1, top + height - 1):
            window.addch(y, left, "│")
            window.addch(y, left + width - 1, "│")

        if title:
            title_text = f" {title} "
            title_x = left + 2
            safe_addstr(window, top, title_x, title_text, attribute)

        window.attroff(attribute)
    except curses.error:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────────────

class HyprClock:
    def __init__(self, stdscr):
        self.stdscr = stdscr

        self.running = True
        self.active_view = "clock"

        # Manual clock adjustment.
        # This does not modify the operating system clock.
        self.clock_offset_seconds = 0

        # Additional timezone offset.
        self.timezone_offset_seconds = -23400

        # Stopwatch state.
        self.stopwatch_running = False
        self.stopwatch_started_at = 0.0
        self.stopwatch_accumulated = 0.0
        self.laps = []

        # Timer state.
        self.timer_duration = DEFAULT_TIMER_SECONDS
        self.timer_remaining = DEFAULT_TIMER_SECONDS
        self.timer_running = False
        self.timer_started_at = 0.0
        self.timer_last_update = time.monotonic()
        self.timer_finished = False

        self.setup_terminal()
        self.setup_colors()

    # ─────────────────────────────────────────────────────────────────────────
    # Setup
    # ─────────────────────────────────────────────────────────────────────────

    def setup_terminal(self):
        curses.curs_set(0)
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        self.stdscr.timeout(100)

    def setup_colors(self):
        curses.start_color()
        curses.use_default_colors()

        # Hyprland-inspired muted dark palette.
        curses.init_pair(1, curses.COLOR_CYAN, -1)     # Main accent
        curses.init_pair(2, curses.COLOR_MAGENTA, -1)  # Secondary accent
        curses.init_pair(3, curses.COLOR_GREEN, -1)    # Success
        curses.init_pair(4, curses.COLOR_YELLOW, -1)   # Warning
        curses.init_pair(5, curses.COLOR_RED, -1)      # Danger
        curses.init_pair(6, curses.COLOR_WHITE, -1)    # Main text
        curses.init_pair(7, curses.COLOR_BLUE, -1)     # Dim accent

        self.accent = curses.color_pair(1) | curses.A_BOLD
        self.secondary = curses.color_pair(2) | curses.A_BOLD
        self.success = curses.color_pair(3) | curses.A_BOLD
        self.warning = curses.color_pair(4) | curses.A_BOLD
        self.danger = curses.color_pair(5) | curses.A_BOLD
        self.text = curses.color_pair(6)
        self.dim = curses.color_pair(7)
        self.bold = curses.A_BOLD | self.text

    # ─────────────────────────────────────────────────────────────────────────
    # Time calculations
    # ─────────────────────────────────────────────────────────────────────────

    def now(self):
        """Return the displayed local time with manual adjustments."""
        return datetime.now() + timedelta(
            seconds=self.clock_offset_seconds + self.timezone_offset_seconds
        )

    def stopwatch_value(self):
        if self.stopwatch_running:
            return self.stopwatch_accumulated + (
                time.monotonic() - self.stopwatch_started_at
            )

        return self.stopwatch_accumulated

    def update_timer(self):
        if not self.timer_running:
            return

        current = time.monotonic()
        elapsed = current - self.timer_last_update
        self.timer_last_update = current
        self.timer_remaining -= elapsed

        if self.timer_remaining <= 0:
            self.timer_remaining = 0
            self.timer_running = False
            self.timer_finished = True

    # ─────────────────────────────────────────────────────────────────────────
    # Drawing
    # ─────────────────────────────────────────────────────────────────────────

    def draw(self):
        self.update_timer()
        self.stdscr.erase()

        height, width = self.stdscr.getmaxyx()

        if height < 20 or width < 65:
            center_text(
                self.stdscr,
                max(0, height // 2 - 1),
                "Terminal too small",
                self.danger,
            )
            center_text(
                self.stdscr,
                max(0, height // 2 + 1),
                "Resize to at least 65×20",
                self.text,
            )
            self.stdscr.refresh()
            return

        self.draw_header(width)
        self.draw_navigation(width)

        if self.active_view == "clock":
            self.draw_clock(height, width)
        elif self.active_view == "stopwatch":
            self.draw_stopwatch(height, width)
        elif self.active_view == "timer":
            self.draw_timer(height, width)

        self.draw_footer(height, width)

        self.stdscr.refresh()

    def draw_header(self, width):
        safe_addstr(self.stdscr, 1, 3, "◈", self.secondary)
        safe_addstr(self.stdscr, 1, 6, APP_NAME, self.accent)
        safe_addstr(self.stdscr, 1, width - 12, VERSION, self.dim)

        # Thin divider.
        safe_addstr(self.stdscr, 2, 2, "─" * max(1, width - 4), self.dim)

    def draw_navigation(self, width):
        tabs = [
            ("1", "CLOCK", "clock"),
            ("2", "STOPWATCH", "stopwatch"),
            ("3", "TIMER", "timer"),
        ]

        x = 4

        for key, label, view in tabs:
            selected = self.active_view == view
            attr = self.accent if selected else self.dim

            text = f"[{key}] {label}"

            if selected:
                text = f"  {text}  "

            safe_addstr(self.stdscr, 4, x, text, attr)
            x += len(text) + 3

    def draw_clock(self, height, width):
        panel_width = min(76, width - 8)
        panel_left = (width - panel_width) // 2
        panel_top = 7
        panel_height = 11

        draw_box(
            self.stdscr,
            panel_top,
            panel_left,
            panel_height,
            panel_width,
            " LOCAL TIME ",
            self.dim,
        )

        current = self.now()

        time_text = current.strftime("%H:%M:%S")
        date_text = current.strftime("%A  •  %d %B %Y")

        center_text(self.stdscr, panel_top + 3, time_text, self.accent)
        center_text(self.stdscr, panel_top + 5, date_text, self.text)

        timezone = format_offset(self.timezone_offset_seconds)
        manual = format_offset(self.clock_offset_seconds)

        status = f"{timezone}   •   manual shift {manual}"
        center_text(self.stdscr, panel_top + 7, status, self.dim)

        center_text(
            self.stdscr,
            panel_top + 9,
            "←/→ timezone    ↑/↓ clock    R reset",
            self.secondary,
        )

    def draw_stopwatch(self, height, width):
        panel_width = min(76, width - 8)
        panel_left = (width - panel_width) // 2
        panel_top = 7
        panel_height = 11

        draw_box(
            self.stdscr,
            panel_top,
            panel_left,
            panel_height,
            panel_width,
            " STOPWATCH ",
            self.dim,
        )

        elapsed = self.stopwatch_value()
        status = "RUNNING" if self.stopwatch_running else "PAUSED"

        center_text(
            self.stdscr,
            panel_top + 3,
            format_duration(elapsed),
            self.accent if self.stopwatch_running else self.text,
        )

        center_text(
            self.stdscr,
            panel_top + 5,
            f"● {status}",
            self.success if self.stopwatch_running else self.warning,
        )

        lap_text = f"LAPS  {len(self.laps):02d}"
        center_text(self.stdscr, panel_top + 7, lap_text, self.dim)

        center_text(
            self.stdscr,
            panel_top + 9,
            "Space start/pause    L lap    C clear",
            self.secondary,
        )

        # Show recent laps on the right/bottom when space permits.
        if self.laps:
            start_y = panel_top + panel_height + 1
            safe_addstr(self.stdscr, start_y, panel_left, "RECENT LAPS", self.dim)

            for index, lap in enumerate(self.laps[-3:], start=1):
                y = start_y + index
                safe_addstr(
                    self.stdscr,
                    y,
                    panel_left,
                    f"{len(self.laps) - len(self.laps[-3:]) + index:02d}   "
                    f"{format_duration(lap)}",
                    self.text,
                )

    def draw_timer(self, height, width):
        panel_width = min(76, width - 8)
        panel_left = (width - panel_width) // 2
        panel_top = 7
        panel_height = 13

        draw_box(
            self.stdscr,
            panel_top,
            panel_left,
            panel_height,
            panel_width,
            " COUNTDOWN TIMER ",
            self.dim,
        )

        if self.timer_finished:
            timer_attr = self.danger
            status = "TIME'S UP"
        elif self.timer_running:
            timer_attr = self.accent
            status = "RUNNING"
        else:
            timer_attr = self.text
            status = "PAUSED"

        center_text(
            self.stdscr,
            panel_top + 3,
            format_duration(self.timer_remaining, False),
            timer_attr,
        )

        center_text(
            self.stdscr,
            panel_top + 5,
            f"● {status}",
            self.danger if self.timer_finished else (
                self.success if self.timer_running else self.warning
            ),
        )

        center_text(
            self.stdscr,
            panel_top + 7,
            f"Preset  {format_duration(self.timer_duration, False)}",
            self.dim,
        )

        center_text(
            self.stdscr,
            panel_top + 9,
            "Space start/pause    +/- minute    R reset",
            self.secondary,
        )

        center_text(
            self.stdscr,
            panel_top + 10,
            "T set custom timer",
            self.secondary,
        )

    def draw_footer(self, height, width):
        safe_addstr(
            self.stdscr,
            height - 3,
            2,
            "─" * max(1, width - 4),
            self.dim,
        )

        help_text = "Q quit    1 clock    2 stopwatch    3 timer"
        center_text(self.stdscr, height - 2, help_text, self.dim)

    # ─────────────────────────────────────────────────────────────────────────
    # Input handling
    # ─────────────────────────────────────────────────────────────────────────

    def read_number(self, prompt):
        """Read a number using curses input."""
        curses.echo()
        curses.curs_set(1)

        height, width = self.stdscr.getmaxyx()
        self.stdscr.move(height - 2, 2)
        self.stdscr.clrtoeol()
        safe_addstr(self.stdscr, height - 2, 2, prompt, self.accent)
        self.stdscr.refresh()

        try:
            value = self.stdscr.getstr(height - 2, len(prompt) + 2, 20)
            value = value.decode("utf-8").strip()
        except Exception:
            value = ""

        curses.noecho()
        curses.curs_set(0)

        return value

    def handle_clock_input(self, key):
        if key == curses.KEY_LEFT:
            self.timezone_offset_seconds -= 3600
        elif key == curses.KEY_RIGHT:
            self.timezone_offset_seconds += 3600
        elif key == curses.KEY_UP:
            self.clock_offset_seconds += 60
        elif key == curses.KEY_DOWN:
            self.clock_offset_seconds -= 60
        elif key in (ord("r"), ord("R")):
            self.clock_offset_seconds = 0
            self.timezone_offset_seconds = 0

    def handle_stopwatch_input(self, key):
        if key == ord(" "):
            if self.stopwatch_running:
                self.stopwatch_accumulated += (
                    time.monotonic() - self.stopwatch_started_at
                )
                self.stopwatch_running = False
            else:
                self.stopwatch_started_at = time.monotonic()
                self.stopwatch_running = True

        elif key in (ord("l"), ord("L")):
            if self.stopwatch_running:
                self.laps.append(self.stopwatch_value())

        elif key in (ord("c"), ord("C")):
            self.stopwatch_running = False
            self.stopwatch_started_at = 0.0
            self.stopwatch_accumulated = 0.0
            self.laps.clear()

    def handle_timer_input(self, key):
        if key == ord(" "):
            if self.timer_finished:
                self.timer_remaining = self.timer_duration
                self.timer_finished = False

            self.timer_running = not self.timer_running
            self.timer_last_update = time.monotonic()

        elif key in (ord("+"), ord("=")):
            self.timer_remaining += 60
            self.timer_duration = self.timer_remaining
            self.timer_finished = False

        elif key in (ord("-"), ord("_")):
            self.timer_remaining = max(0, self.timer_remaining - 60)
            self.timer_duration = self.timer_remaining

        elif key in (ord("r"), ord("R")):
            self.timer_running = False
            self.timer_finished = False
            self.timer_remaining = self.timer_duration
            self.timer_last_update = time.monotonic()

        elif key in (ord("t"), ord("T")):
            value = self.read_number("Timer minutes: ")

            try:
                minutes = max(1, int(value))
                self.timer_duration = minutes * 60
                self.timer_remaining = self.timer_duration
                self.timer_running = False
                self.timer_finished = False
            except ValueError:
                pass

    def handle_input(self, key):
        if key == -1:
            return

        if key in (ord("q"), ord("Q"), 27):
            self.running = False
            return

        if key == ord("1"):
            self.active_view = "clock"
            return

        if key == ord("2"):
            self.active_view = "stopwatch"
            return

        if key == ord("3"):
            self.active_view = "timer"
            return

        if self.active_view == "clock":
            self.handle_clock_input(key)
        elif self.active_view == "stopwatch":
            self.handle_stopwatch_input(key)
        elif self.active_view == "timer":
            self.handle_timer_input(key)

    # ─────────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        while self.running:
            self.draw()
            key = self.stdscr.getch()
            self.handle_input(key)


def main():
    try:
        curses.wrapper(lambda stdscr: HyprClock(stdscr).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
