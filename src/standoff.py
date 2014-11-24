#!/usr/bin/env python

import sys
import re
import argparse

try:
    import cElementTree as ET
except:
    import xml.etree.cElementTree as ET

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

        return "%s%d\t%s %d %d\t%s\t%s" % (self.prefix, self.sid, self.tag(), self.start, self.end, c_escape(self.text.encode("utf-8")), " ".join(['%s="%s"' % (k.encode("utf-8"),v.encode("utf-8")) for k,v in attrib.items()]))

def txt(s):
    return s if s is not None else ""

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
        stext, dummy = text_and_standoffs(s, curroff, standoffs)
        text += stext
        text += txt(s.tail)
        curroff = startoff + len(text)
    return (text, standoffs)

def main(argv=None):
    if argv is None:
        argv = sys.argv

    args = argparser().parse_args(argv[1:])

    # Ugly hack for quick testing: allow "-" for standard in/out
    in_fn, out_txt_fn, out_so_fn = args.in_xml, args.out_text, args.out_so
    if in_fn == "-":
        in_fn = "/dev/stdin"
    if out_txt_fn == "-":
        out_txt_fn = "/dev/stdout"
    if out_so_fn == "-":
        out_so_fn = "/dev/stdout"

    try:
        tree = ET.parse(in_fn)
    except Exception:
        print >> sys.stderr, "%s: Error parsing %s" % (argv[0], in_fn)
        return 1

    root = tree.getroot()

    text, standoffs = text_and_standoffs(root)

    # filter standoffs by tag
    if args.filter is None:
        filtered = set()
    else:
        filtered = set(args.filter.split(','))
    standoffs = [s for s in standoffs if s.tag() not in filtered]

    # set ID prefixes
    if args.prefix is not None:
        for s in standoffs:
            s.set_prefix(args.prefix)

    # open output files 
    out_txt = open(out_txt_fn, "wt")
    out_so  = open(out_so_fn, "wt")

    out_txt.write(text.encode("utf-8"))
    for so in standoffs:
        so.compress_text(MAXIMUM_TEXT_DISPLAY_LENGTH)
        print >> out_so, so

    out_txt.close()
    out_so.close()

if __name__ == "__main__":
    sys.exit(main(sys.argv))
