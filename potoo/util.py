import collections
from contextlib import contextmanager
from datetime import datetime
import os
import pipes
import shutil
import sys
import time
import traceback


def or_else(x, f):
    try:
        return f()
    except:
        return x


# In pandas, 0 means use get_terminal_size(), ''/None means unlimited
get_term_size = lambda: shutil.get_terminal_size()  # ($COLUMNS else detect dynamically, $LINES else detect dynamically)  # noqa
get_rows = lambda: get_term_size().lines            # $LINES else detect dynamically                                      # noqa
get_cols = lambda: get_term_size().columns          # $COLUMNS else detect dynamically                                    # noqa


def puts(x):
    print(x)
    return x


def singleton(cls):
    return cls()


def attrs(**kwargs):
    [keys, values] = list(zip(*kwargs.items())) or [[], []]
    return collections.namedtuple('attrs', keys)(*values)


def shell(cmd):
    print >>sys.stderr, 'shell: cmd[%s]' % cmd
    status = os.system(cmd)
    if status != 0:
        raise Exception('Exit status[%s] from cmd[%s]' % (status, cmd))


def mkdir_p(dir):
    os.system("mkdir -p %s" % pipes.quote(dir))  # Don't error like os.makedirs


def timed_print(f, **kwargs):
    elapsed, x = timed_format(f, **kwargs)
    print(elapsed)
    return x


def timed_format(f, **kwargs):
    elapsed_s, x = timed(f, **kwargs)
    elapsed = '[%s]' % format_duration(elapsed_s)
    return elapsed, x


def timed(f, if_error_return='exception'):
    start_s = time.time()
    try:
        x = f()
    except Exception as e:
        traceback.print_exc()
        x = e if if_error_return == 'exception' else if_error_return
    elapsed_s = time.time() - start_s
    return elapsed_s, x


def format_duration(secs):
    """
    >>> format_duration(0)
    '00:00'
    >>> format_duration(1)
    '00:01'
    >>> format_duration(100)
    '01:40'
    >>> format_duration(10000)
    '02:46:40'
    >>> format_duration(1000000)
    '277:46:40'
    >>> format_duration(0.0)
    '00:00.000'
    >>> format_duration(0.5)
    '00:00.500'
    >>> format_duration(12345.6789)
    '03:25:45.679'
    >>> format_duration(-1)
    '-00:01'
    >>> format_duration(-10000)
    '-02:46:40'
    """
    if secs < 0:
        return '-' + format_duration(-secs)
    else:
        s = int(secs) % 60
        m = int(secs) // 60 % 60
        h = int(secs) // 60 // 60
        res = ':'.join('%02.0f' % x for x in (
            [m, s] if h == 0 else [h, m, s]
        ))
        if isinstance(secs, float):
            ms = round(secs % 1, 3)
            res += ('%.3f' % ms)[1:]
        return res


# Do everything manually to avoid weird behaviors in curses impl below
def watch(period_s, f):
    try:
        os.system('stty -echo -cbreak')
        while True:
            ncols, nrows = get_term_size()
            try:
                s = str(f())
            except Exception:
                s = traceback.format_exc()
            if not s.endswith('\n'):
                s += '\n'  # Ensure cursor is on next blank line
            lines = s.split('\n')
            lines = [
                datetime.now().isoformat()[:-3],  # Drop micros
                '',
            ] + lines
            os.system('tput cup 0 0')
            for row_i in range(nrows):
                if row_i < len(lines):
                    line = lines[row_i][:ncols]
                else:
                    line = ''
                trailing_space = ' ' * max(0, ncols - len(line))
                print(
                    line + trailing_space,
                    end='\n' if row_i < nrows - 1 else '',
                    flush=True,
                )
            os.system(f'tput cup {nrows - 1} {ncols - 1}')
            time.sleep(period_s)
    except KeyboardInterrupt:
        pass
    finally:
        os.system('stty sane 2>/dev/null')
        print()


# # FIXME stdscr.cbreak() barfs from within ipython, and omitting it soemtimes drops leading spaces
# def watch(period_s, f):
#     with use_curses() as (curses, stdscr):
#         try:
#             while True:
#                 curses.noecho()  # Don't echo key presses
#                 curses.cbreak()  # Don't buffer input until enter [also avoid addstr dropping leading spaces]
#                 max_y, max_x = stdscr.getmaxyx()
#                 stdscr.clear()
#                 stdscr.addnstr(0, 0, datetime.now().isoformat()[:-3], max_x)  # Drop micros
#                 try:
#                     s = str(f())
#                 except Exception:
#                     s = traceback.format_exc()
#                 if not s.endswith('\n'):
#                     s += '\n'  # Ensure cursor is on next blank line
#                 y = 2
#                 for line in s.split('\n'):
#                     # Don't addstr beyond max_y
#                     if y <= max_y - 2:
#                         # Don't addstr beyond max_x
#                         line = line[:max_x]
#                         try:
#                             # All chars must be within (max_y, max_x), else you'll get unhelpful "returned ERR" errors
#                             stdscr.addstr(y, 0, line)
#                         except:
#                             # Raise helpful error in case we use addstr wrong (it's very finicky with y/x)
#                             raise Exception('Failed to addstr(%r)' % line)
#                         y += 1
#                 stdscr.refresh()
#                 time.sleep(period_s)
#         except KeyboardInterrupt:
#             pass


@singleton
class use_curses:

    def __init__(self):
        self._stdscr = None

    @contextmanager
    def __call__(self):
        # Don't import until used, in case curses does weird things on some platform or in some environment
        import curses
        if self._stdscr is None:
            # Warning: if you call initscr twice you'll break curses for the rest of the current process
            #   - e.g. breaks under ipython %autoreload
            self._stdscr = curses.initscr()
        try:
            yield (curses, self._stdscr)
        finally:
            # Warning: if you call endwin you'll never be able to use curses again for the rest of the current process
            # curses.endwin()
            # Do `stty sane` instead
            os.system('stty sane 2>/dev/null')
            # Reset cursor to x=0
            print('')
