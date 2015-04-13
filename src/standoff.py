#!/usr/bin/env python

import sys
import re
import argparse

import lxml

# string to use to indicate elided text in output
ELIDED_TEXT_STRING = "[[[...]]]"

# maximum length of text sting to show without eliding (-1 for no limit)
#MAXIMUM_TEXT_DISPLAY_LENGTH = -1
MAXIMUM_TEXT_DISPLAY_LENGTH = 40

DESCRIPTION='XML to standoff conversion'
USAGE='%(prog)s [OPTIONS] IN-XML OUT-TEXT OUT-SO'

def argparser():
    ap = argparse.ArgumentParser(description=DESCRIPTION, usage=USAGE)

    ap.add_argument('in_xml', metavar='IN-XML',
                    help='input XML file')
    ap.add_argument('out_text', metavar='OUT-TEXT',
                    help='output text file')
    ap.add_argument('out_so', metavar='OUT-SO',
                    help='output standoff file')
    ap.add_argument('-f', '--filter', metavar='[TAG[,TAG[...]]]', default=None,
                    help='remove tags from output')
    ap.add_argument('-p', '--prefix', default=None,
                    help='prefix to add to IDs on output')

    return ap

# c-style string escaping for just newline, tab and backslash.
# (s.encode('string_escape') does too much for utf-8)
def c_escape(s):
    return s.replace('\\', '\\\\').replace('\t','\\t').replace('\n','\\n')

class Standoff:
    def __init__(self, sid, element, start, end, text):
        self.sid     = sid
        self.element = element
        self.start   = start
        self.end     = end
        self.text    = text
        self.prefix  = 'X'

    def tag(self):
        # remove namespace spec from output, if any
        if self.element.tag[0] == "{":
            tag = re.sub(r'\{.*?\}', '', self.element.tag)
        else:
            tag = self.element.tag
        return tag

    def set_prefix(self, prefix):
        self.prefix = prefix

    def compress_text(self, l):
        if l != -1 and len(self.text) >= l:
            el = len(ELIDED_TEXT_STRING)
            sl = (l-el)/2
            self.text = (self.text[:sl]+ELIDED_TEXT_STRING+self.text[-(l-sl-el):])
    def __str__(self):
        # remove namespace specs from attribute names, if any
        attrib = {}
        for a in self.element.attrib:
            if a[0] == "{":
                an = re.sub(r'\{.*?\}', '', a)
            else:
                an = a
            attrib[an] = self.element.attrib[a]

        return "%s%d\t%s %d %d\t%s\t%s" % (self.prefix, self.sid, self.tag(), self.start, self.end, c_escape(self.text.encode("utf-8")), " ".join(['%s="%s"' % (k.encode("utf-8"),c_escape(v).encode("utf-8")) for k,v in attrib.items()]))

def txt(s):
    return s if s is not None else ""

def is_standard_element(e):
    """Return whether given element is a normal element as opposed to a
    special like a comment, a processing instruction, or an entity."""
    try:
        return isinstance(e.tag, basestring)
    except:
        return False

next_free_so_id = 1

def text_and_standoffs(e, curroff=0, standoffs=None):
    global next_free_so_id

    if standoffs == None:
        standoffs = []
    startoff = curroff
    # to keep standoffs in element occurrence order, append
    # a placeholder before recursing
    so = Standoff(next_free_so_id, e, 0, 0, "")
    next_free_so_id += 1
    standoffs.append(so)
    setext, dummy = subelem_text_and_standoffs(e, curroff+len(txt(e.text)), standoffs)
    text = txt(e.text) + setext
    curroff += len(text)
    so.start = startoff
    so.end   = curroff
    so.text  = text
    return (text, standoffs)

def subelem_text_and_standoffs(e, curroff, standoffs):
    startoff = curroff
    text = ""
    for s in e:
        if is_standard_element(s):
            # the content of comments, processing instructions and
            # entities is ignored (except for the tail)
            stext, dummy = text_and_standoffs(s, curroff, standoffs)
            text += stext
        text += txt(s.tail)
        curroff = startoff + len(text)
    return (text, standoffs)

def read_tree(filename):
    # TODO: portable STDIN input
    if filename == "-":
        filename = "/dev/stdin"
    try:
        return ET.parse(filename)
    except Exception:
        print >> sys.stderr, "%s: Error parsing %s" % (argv[0], in_fn)
        raise

def convert_tree(tree, options=None):
    root = tree.getroot()

    text, standoffs = text_and_standoffs(root)

    # filter standoffs by tag
    if options is None or options.filter is None:
        filtered = set()
    else:
        filtered = set(options.filter.split(','))
    standoffs = [s for s in standoffs if s.tag() not in filtered]

    # set ID prefixes
    if options is not None and options.prefix is not None:
        for s in standoffs:
            s.set_prefix(options.prefix)

    # compress long reference texts
    for so in standoffs:
        so.compress_text(MAXIMUM_TEXT_DISPLAY_LENGTH)

    return text, standoffs

def write_text(text, filename):
    # TODO: be portable
    if filename == '-':
        filename = '/dev/stdout'
    with open(filename, 'wt') as out:
        out.write(text.encode('utf-8'))

def write_standoffs(standoffs, filename):
    # TODO: be portable
    if filename == '-':
        filename = '/dev/stdout'
    with open(filename, 'wt') as out:
        for so in standoffs:
            print >> out, so

def process(options):
    tree = read_tree(options.in_xml)
    text, standoffs = convert_tree(tree)
    write_text(text, options.out_text)
    write_standoffs(standoffs, options.out_so)

def main(argv=None):
    if argv is None:
        argv = sys.argv
    args = argparser().parse_args(argv[1:])

    process(args)

    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
