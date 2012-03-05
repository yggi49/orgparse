import re

from orgparse.date import OrgDate, OrgDateClock, parse_sdc


def lines_to_chunks(lines):
    chunk = []
    for l in lines:
        if RE_NODE_HEADER.search(l):
            yield chunk
            chunk = []
        chunk.append(l)
    yield chunk

RE_NODE_HEADER = re.compile(r"^\*+ ")


def parse_heading_level(heading):
    """
    Get star-stripped heading and its level

    >>> parse_heading_level('* Heading')
    ('Heading', 1)
    >>> parse_heading_level('******** Heading')
    ('Heading', 8)
    >>> parse_heading_level('not heading')  # None

    """
    match = RE_HEADING_STARS.search(heading)
    if match:
        return (match.group(2), len(match.group(1)))

RE_HEADING_STARS = re.compile('^(\*+)\s*(.*?)\s*$')


def parse_heading_tags(heading):
    """
    Get first tags and heading without tags

    >>> parse_heading_tags('HEADING')
    ('HEADING', [])
    >>> parse_heading_tags('HEADING :TAG1:TAG2:')
    ('HEADING', ['TAG1', 'TAG2'])
    >>> parse_heading_tags('HEADING: this is still heading :TAG1:TAG2:')
    ('HEADING: this is still heading', ['TAG1', 'TAG2'])

    """
    match = RE_HEADING_TAGS.search(heading)
    if match:
        heading = match.group(1)
        tagstr = match.group(2)
        tags = tagstr.split(':')
    else:
        tags = []
    return (heading, tags)

RE_HEADING_TAGS = re.compile(r'(.*?)\s*:([a-zA-Z0-9_:]+):\s*$')


def parse_heading_todos(heading, todo_candidates):
    """
    Get TODO keyword and heading without TODO keyword.

    >>> todos = ['TODO', 'DONE']
    >>> parse_heading_todos('Normal heading', todos)
    ('Normal heading', None)
    >>> parse_heading_todos('TODO Heading', todos)
    ('Heading', 'TODO')

    """
    for todo in todo_candidates:
        todows = '{0} '.format(todo)
        if heading.startswith(todows):
            return (heading[len(todows):], todo)
    return (heading, None)


def parse_heading_priority(heading):
    """
    Get priority and heading without priority field..

    >>> parse_heading_priority('HEADING')
    ('HEADING', None)
    >>> parse_heading_priority('[#A] HEADING')
    ('HEADING', 'A')
    >>> parse_heading_priority('[#0] HEADING')
    ('HEADING', '0')
    >>> parse_heading_priority('[#A]')
    ('', 'A')

    """
    match = RE_HEADING_PRIORITY.search(heading)
    if match:
        return (match.group(2), match.group(1))
    else:
        return (heading, None)

RE_HEADING_PRIORITY = re.compile(r'^\s*\[#([A-Z0-9])\] ?(.*)$')


def parse_property(line):
    """
    Get property from given string.

    >>> parse_property(':Some_property: some value')
    ('Some_property', 'some value')
    >>> parse_property(':Effort: 1:10')
    ('Effort', 70)

    """
    prop_key = None
    prop_val = None
    match = RE_PROP.search(line)
    if match:
        prop_key = match.group(1)
        prop_val = match.group(2)
        if prop_key == 'Effort':
            (h, m) = prop_val.split(":", 2)
            if h.isdigit() and m.isdigit():
                prop_val = int(h) * 60 + int(m)
    return (prop_key, prop_val)

RE_PROP = re.compile('^\s*:(.*?):\s*(.*?)\s*$')


def parse_comment(line):
    """
    Parse special comment such as ``#+SEQ_TODO``

    >>> parse_comment('#+SEQ_TODO: TODO | DONE')
    ('SEQ_TODO', 'TODO | DONE')
    >>> parse_comment('# not a special comment')  # None

    """
    if line.startswith('#+'):
        comment = line.lstrip('#+').split(':', 1)
        if len(comment) == 2:
            return (comment[0], comment[1].strip())


def parse_seq_todo(line):
    """
    Parse value part of SEQ_TODO comment

    >>> parse_seq_todo('TODO | DONE')
    (['TODO'], ['DONE'])
    >>> parse_seq_todo('Fred Sara Lucy Mike | DONE')
    (['Fred', 'Sara', 'Lucy', 'Mike'], ['DONE'])

    """
    todo_done = line.split('|', 1)
    if len(todo_done) == 2:
        (todos, dones) = todo_done
    else:
        (todos, dones) = (line, '')
    return (todos.split(), dones.split())


class OrgEnv(object):

    """
    Information global to a file.
    """

    def __init__(self, todos=['TODO'], dones=['DONE'],
                 source_path='<undefined>'):
        self._todos = list(todos)
        self._dones = list(dones)
        self._todo_not_specified_in_comment = True
        self._source_path = source_path

    def add_todo_keys(self, todos, dones):
        if self._todo_not_specified_in_comment:
            self._todos = []
            self._dones = []
            self._todo_not_specified_in_comment = False
        self._todos.extend(todos)
        self._dones.extend(dones)

    def get_todo_keys(self, todo=True, done=True):
        """
        Get TODO keywords defined for this document (file).

        :arg bool todo: Include TODO-type keywords if true.
        :arg bool done: Include DONE-type keywords if true.

        """
        if todo and done:
            return self._todos + self._dones
        elif todo:
            return self._todos
        elif done:
            return self._dones

    def get_source_path(self):
        """
        Return a path to the source file or similar information.

        If the org objects are not loaded from a file, this value
        will be a string of the form ``<SOME_TEXT>``.

        :rtype: str

        """
        return self._source_path

    # parser

    def from_chunks(self, chunks):
        yield OrgRootNode.from_chunk(self, next(chunks))
        for chunk in chunks:
            yield OrgNode.from_chunk(self, chunk)


class OrgBaseNode(object):

    """
    Base class for :class:`OrgRootNode` and :class:`OrgNode`

    .. attribute:: env

       An instance of :class:`OrgEnv`.
       All nodes in a same file shares same instance.

    """

    def __init__(self, env):
        """
        Create a :class:`OrgBaseNode` object.

        :type env: :class:`OrgEnv`
        :arg  env: This will be set to the :attr:`env` attribute.

        """
        self.env = env

        # tree structure
        self._next = None
        self._previous = None
        self._parent = None
        self._children = []

        # content
        self._lines = []

    def traverse(self, include_self=True):
        """Generate an iterator to traverse all descendant nodes."""
        if include_self:
            yield self
        for child in self.get_children():
            for grandchild in child.traverse():
                yield grandchild

    # tree structure

    def set_previous(self, previous):
        self._previous = previous
        previous._next = self   # FIXME: find a better way to do this

    def get_previous(self):
        """Return previous node if exists or None otherwise."""
        return self._previous

    def get_next(self):
        """Return next node if exists or None otherwise."""
        return self._next

    def set_parent(self, parent):
        self._parent = parent
        parent.add_children(self)

    def add_children(self, child):
        self._children.append(child)

    def get_parent(self, max_level=None):
        """
        Return a parent node.

        :arg int max_level:
            In the normally structured org file, it is a level
            of the ancestor node to return.  For example,
            ``get_parent(max_level=0)`` returns a root node.

            In general case, it specify a maximum level of the
            desired ancestor node.  If there is no ancestor node
            which level is equal to ``max_level``, this function
            try to find an ancestor node which level is smaller
            than ``max_level``.

        """
        if max_level is None:
            max_level = self.get_level() - 1
        parent = self._parent
        while parent.get_level() > max_level:
            parent = parent.get_parent()
        return parent

    def get_children(self):
        """Return a list of child nodes."""
        return self._children

    def get_root(self):
        """Return a root node."""
        root = self
        while True:
            parent = root.get_parent()
            if not parent:
                return root
            root = parent

    # parser

    @classmethod
    def from_chunk(cls, env, lines):
        self = cls(env)
        self._lines = lines
        self._parse_comments()
        return self

    def _parse_comments(self):
        special_comments = {}
        for line in self._lines:
            parsed = parse_comment(line)
            if parsed:
                (key, val) = parsed
                special_comments.setdefault(key, []).append(val)
        self._special_comments = special_comments
        # parse TODO keys and store in OrgEnv
        for todokey in ['TODO', 'SEQ_TODO', 'TYP_TODO']:
            for val in special_comments.get(todokey, []):
                self.env.add_todo_keys(*parse_seq_todo(val))

    # misc

    def get_level(self):
        """
        Return the level of this node

        :rtype: int

        """
        raise NotImplemented

    def get_tags(self, inher=False):
        """
        Return tags

        :arg bool inher:
            Mix with tags of all ancestor nodes if ``True``.

        :rtype: set

        """
        return set()

    def is_root(self):
        """Return ``True`` when it is a root node"""
        return False

    def __unicode__(self):
        return u"\n".join(self._lines)

    def __str__(self):
        return unicode(self).encode('utf-8')


class OrgRootNode(OrgBaseNode):

    """
    Node to represent a file

    See :class:`OrgBaseNode` for other available functions.

    """

    # getter

    def get_level(self):
        return 0

    # misc

    def is_root(self):
        return True


class OrgNode(OrgBaseNode):

    """
    Node to represent normal org node

    See :class:`OrgBaseNode` for other available functions.

    """

    def __init__(self, *args, **kwds):
        super(OrgNode, self).__init__(*args, **kwds)
        self._heading = None
        self._level = None
        self._tags = None
        self._todo = None
        self._priority = None
        self._properties = {}
        self._scheduled = OrgDate(None)
        self._deadline = OrgDate(None)
        self._closed = OrgDate(None)
        self._timestamps = []
        self._clocklist = []
        self._body_lines = []

    # parser

    def _parse_pre(self):
        """Call parsers which must be called before tree structuring"""
        self._parse_heading()
        # FIXME: make the following parsers "lazy"
        ilines = iter(self._lines)
        next(ilines)            # skip heading
        ilines = self._iparse_sdc(ilines)
        ilines = self._iparse_clock(ilines)
        ilines = self._iparse_properties(ilines)
        ilines = self._iparse_timestamps(ilines)
        self._body_lines = list(ilines)

    def _parse_heading(self):
        heading = self._lines[0]
        (heading, self._level) = parse_heading_level(heading)
        (heading, self._tags) = parse_heading_tags(heading)
        (heading, self._todo) = parse_heading_todos(
            heading, self.env.get_todo_keys())
        (heading, self._priority) = parse_heading_priority(heading)
        self._heading = heading

    def _iparse_sdc(self, ilines):
        """
        Parse SCHEDULED, DEADLINE and CLOSED time tamps.

        They are assumed be in the first line.

        """
        line = next(ilines)
        (self._scheduled, self._deadline, self._closed) = parse_sdc(line)

        if not (self._scheduled or
                self._deadline or
                self._closed):
            yield line  # when none of them were found

        for line in ilines:
            yield line

    def _iparse_clock(self, ilines):
        self._clocklist = clocklist = []
        for line in ilines:
            cl = OrgDateClock.from_str(line)
            if cl:
                clocklist.append(cl)
            else:
                yield line

    def _iparse_timestamps(self, ilines):
        self._timestamps = timestamps = []
        for l in ilines:
            timestamps.extend(OrgDate.list_from_str(l))
            yield l

    def _iparse_properties(self, ilines):
        self._properties = properties = {}
        in_property_field = False
        for line in ilines:
            if in_property_field:
                if line.find(":END:") >= 0:
                    break
                else:
                    (key, val) = parse_property(line)
                    if key:
                        properties.update({key: val})
            elif line.find(":PROPERTIES:") >= 0:
                in_property_field = True
            else:
                yield line
        for line in ilines:
            yield line

    # getter

    def get_body(self):
        """Return a string of body text"""
        if self._lines:
            return "\n".join(self._body_lines)

    def get_heading(self):
        """Return a string of head text without tags and TODO keywords"""
        return self._heading

    def get_level(self):
        return self._level

    def get_priority(self):
        """Return a string to indicate the priority or None if undefined."""
        return self._priority

    def get_tags(self, inher=False):
        tags = set(self._tags)
        if inher:
            parent = self.get_parent()
            if parent:
                return tags | parent.get_tags(inher=True)
        return tags

    def get_todo(self):
        """Return a TODO keyword if exists or None otherwise."""
        return self._todo

    def get_property(self, key, val=None):
        """
        Return property named ``key`` if exists or ``val`` otherwise.

        :arg str key:
            Key of property.

        :arg val:
            Default value to return.

        """
        return self._properties.get(key, val)

    def get_properties(self):
        """
        Return properties as a dictionary.
        """
        return self._properties

    def get_scheduled(self):
        """
        Return scheduled timestamp

        :rtype: a subclass of :class:`orgparse.date.OrgDate`

        """
        return self._scheduled

    def get_deadline(self):
        """
        Return deadline timestamp.

        :rtype: a subclass of :class:`orgparse.date.OrgDate`

        """
        return self._deadline

    def get_closed(self):
        """
        Return timestamp of closed time.

        :rtype: a subclass of :class:`orgparse.date.OrgDate`

        """
        return self._closed

    def get_clock(self):
        """
        Return a list of clocked timestamps

        :rtype: a list of a subclass of :class:`orgparse.date.OrgDate`

        """
        return self._clocklist

    def get_timestamps(self, active=True, inactive=True,
                       end=True, noend=True):
        """
        Return a list of timestamps in the body text.

        :type   active: bool
        :arg    active: Include active type timestamps.
        :type inactive: bool
        :arg  inactive: Include inactive type timestamps.
        :type      end: bool
        :arg       end: Include timestamps which has end date.
        :type    noend: bool
        :arg     noend: Include timestamps which has no end date.

        """
        return [
            ts for ts in self._timestamps if
            (((active and ts.is_active()) or
              (inactive and not ts.is_active())) and
             ((end and ts.has_end()) or
              (noend and not ts.has_end())))]

    def get_datelist(self):
        return self.get_timestamps(self, end=False)

    def get_rangelist(self):
        return self.get_timestamps(self, noend=False)

    def has_date(self):
        """
        Return ``True`` if it has any kind of timestamp
        """
        return (self.get_scheduled() or
                self.get_deadline() or
                self.get_datelist() or
                self.get_rangelist())

    def get_repeated_tasks(self):
        """
        Get repeated tasks marked DONE in a entry having repeater

        A repeater is something like ``+1m`` in a timestamp,
        such as::

            ** TODO Pay the rent
               DEADLINE: <2005-10-01 Sat +1m>
               - State "DONE"  from "TODO"  [2005-09-01 Thu 16:10]
               - State "DONE"  from "TODO"  [2005-08-01 Mon 19:44]
               - State "DONE"  from "TODO"  [2005-07-01 Fri 17:27]

        See: http://orgmode.org/manual/Repeated-tasks.html

        """
        raise NotImplementedError  # FIXME: implement!


def parse_lines(lines, source_path):
    env = OrgEnv(source_path=source_path)
    # parse into node of list (environment will be parsed)
    nodelist = list(env.from_chunks(lines_to_chunks(lines)))
    # parse headings (level, TODO, TAGs, and heading)
    for node in nodelist[1:]:   # nodes except root node
        node._parse_pre()
    # set the node tree structure
    for (n1, n2) in zip(nodelist[:-1], nodelist[1:]):
        level_n1 = n1.get_level()
        level_n2 = n2.get_level()
        if level_n1 == level_n2:
            n2.set_parent(n1.get_parent())
            n2.set_previous(n1)
        elif level_n1 < level_n2:
            n2.set_parent(n1)
        else:
            np = n1.get_parent(max_level=level_n2)
            if np.get_level() == level_n2:
                # * np    level=1
                # ** n1   level=2
                # * n2    level=1
                n2.set_parent(np.get_parent())
                n2.set_previous(np)
            else:  # np.get_level() < level_n2
                # * np    level=1
                # *** n1  level=3
                # ** n2   level=2
                n2.set_parent(np)
    return nodelist[0]  # root
