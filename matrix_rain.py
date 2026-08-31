import curses
import random
import time


# Half-width Katakana characters occupy one terminal cell
CHARACTERS = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ01"


def setup_colors():
    curses.start_color()
    curses.use_default_colors()

    # Keep the terminal's existing background
    curses.init_pair(1, curses.COLOR_MAGENTA, -1)
    curses.init_pair(2, curses.COLOR_MAGENTA, -1)
    curses.init_pair(3, curses.COLOR_WHITE, -1)


def make_drop(height):
    return {
        "y": random.randint(-height, 0),
        "length": random.randint(7, max(10, height // 2)),
        "speed": random.uniform(0.08, 0.20), # Use to change rain value
        "last_move": time.monotonic(),
    }


def create_drops(width, height):
    drops = []

    for _ in range(width):
        if random.random() < 0.75:
            drops.append(make_drop(height))
        else:
            drops.append(None)

    return drops


def draw(stdscr):
    setup_colors()

    stdscr.nodelay(True)
    stdscr.timeout(0)

    try:
        curses.curs_set(0)
    except curses.error:
        pass

    height, width = stdscr.getmaxyx()
    drops = create_drops(width, height)

    while True:
        key = stdscr.getch()

        if key in (ord("q"), ord("Q"), 27):
            break

        new_height, new_width = stdscr.getmaxyx()

        if new_height != height or new_width != width:
            height, width = new_height, new_width
            drops = create_drops(width, height)

        now = time.monotonic()
        stdscr.erase()

        for x, drop in enumerate(drops):
            if drop is None:
                if random.random() < 0.025:
                    drops[x] = make_drop(height)
                continue

            if now - drop["last_move"] >= drop["speed"]:
                drop["y"] += 1
                drop["last_move"] = now

            for position in range(drop["length"]):
                y = drop["y"] - position

                if not 0 <= y < height:
                    continue

                character = random.choice(CHARACTERS)

                # White head, white first section, green fading trail
                if position == 0:
                    style = curses.color_pair(3) | curses.A_BOLD
                elif position <= 2:
                    style = curses.color_pair(3)
                elif position < drop["length"] // 2:
                    style = curses.color_pair(2) | curses.A_BOLD
                else:
                    style = curses.color_pair(1)

                try:
                    stdscr.addstr(y, x, character, style)
                except curses.error:
                    pass

            if drop["y"] - drop["length"] > height:
                drops[x] = make_drop(height)

        stdscr.refresh()
        time.sleep(0.016)


def main():
    curses.wrapper(draw)


if __name__ == "__main__":
    main()
