"""
Start the server behind one reading with vim beside it.

The command that starts such a reading is a shell script, so the server runs as
a process of its own and has to say on its output where it landed: a reading
already up may hold the preferred port, and the shell script cannot know which
one was taken until it is told.

`bmv` needs none of this. It starts its own server in process and opens the
browser itself, so the port never has to leave the program.
"""

import sys
from pathlib import Path

from server import serve, start


def main(argv):
    """Serve the document named on the command line under the servername beside it."""
    document, servername = argv
    bound, reading, url = start(Path(document), servername=servername)
    print(url, flush=True)
    serve(bound, reading)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
