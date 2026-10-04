"""
One reading to a document: the claim a reading holds on the file it opened.

A document opened while a reading of it is already up is not read a second
time. The command finds the reading that has it and brings that one forward
instead, so a document is never open in two windows at once, each with a
server of its own watching it and possibly a vim of its own writing it.

The claim is a socket bound under a name made from the document's full path,
in the namespace Linux keeps for sockets apart from the file system. Binding a
name is a step only one process can win, however close together two readings
start. A name there belongs to the process holding it and to nothing on the
disk, so it goes the moment that process does, however it went, and a reading
that crashed or was killed leaves nothing behind to be taken for one still up.

The path is hashed rather than used as it stands, since a name there is held
to a hundred and seven bytes and a path is not. The user is part of the name,
so two people on one machine each have readings of their own.

A second reading learns which process holds the name by connecting to it,
since the system says who is on the other end of such a connection. Nothing is
ever written or read over it.

Only the document a reading opened is claimed. A link followed inside a reading
leaves the claim where it was.
"""

import hashlib
import os
import socket
import struct

from server import NAME

CREDENTIALS = struct.Struct('3i')


def address(document):
    """Return the name a reading of one document holds its claim under.

    The path is resolved first, so the same file named relatively, absolutely
    or through a link is the same document.
    """
    path = os.fsencode(document.resolve())
    return f'\0{NAME}-{os.getuid()}-{hashlib.sha1(path).hexdigest()}'


def claim(document):
    """Claim a document for this reading, or return None where another has it.

    The claim lasts as long as what is returned is kept, which is the whole of
    the reading.
    """
    held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        held.bind(address(document))
    except OSError:
        held.close()
        return None
    held.listen()
    return held


def holder(document):
    """Return the process id of the reading that holds a document."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as asking:
        asking.connect(address(document))
        credentials = asking.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, CREDENTIALS.size
        )
    return CREDENTIALS.unpack(credentials)[0]
