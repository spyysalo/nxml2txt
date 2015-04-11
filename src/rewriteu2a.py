#!/usr/bin/env python

# Replaces Unicode characters in input XML file text content with
# ASCII approximations based on file with mappings between the two.

# This is a component in a pipeline to convert PMC NXML files into
# text and standoffs. The whole pipeline can be run as
#
#    python rewritetex.py FILE.xml -s | python rewriteu2a.py - -s | python respace.py - -s | python standoff.py - FILE.{txt,so}

from __future__ import with_statement

import sys
import os
import re
import codecs

from lxml import etree as ET

# The name of the file from which to read the replacement. Each line
# should contain the hex code for the unicode character, TAB, and
# the replacement string.

MAPPING_FILE_NAME = os.path.join(os.path.dirname(__file__), 
                                 '../data/entities.dat')

# XML tag to use to mark text content rewritten by this script.
REWRITTEN_TAG = 'n2t-u2a'

# XML attribute to use for storing the original for rewritten text.
ORIG_TEXT_ATTRIBUTE = 'orig-text'

# File into which to append unicode codepoints missing from the
# mapping, if any
MISSING_MAPPING_FILE_NAME = 'missing-mappings.txt'

INPUT_ENCODING="UTF-8"
OUTPUT_ENCODING="UTF-8"

# command-line options
options = None

# all codepoints for which a mapping was needed but not found
missing_mappings = set()

def read_mapping(f, fn="mapping data"):
    """
    Reads in mapping from Unicode to ASCII from the given input stream
    and returns a dictionary keyed by Unicode characters with the
    corresponding ASCII characters as values. The expected mapping
    format defines a single mapping per line, each with the format
    CODE\tASC where CODE is the Unicode code point as a hex number and
    ASC is the replacement ASCII string ("\t" is the literal tab
    character). Any lines beginning with "#" are skipped as comments.
    """

    # read in the replacement data
    linere = re.compile(r'^([0-9A-Za-z]{4,})\t(.*)$')
    mapping = {}

    for i, l in enumerate(f):
        # ignore lines starting with "#" as comments
        if len(l) != 0 and l[0] == "#":
            continue

        m = linere.match(l)
        assert m, "Format error in %s line %s: '%s'" % (fn, i+1, l.replace("\n","").encode("utf-8"))
        c, r = m.groups()

        c = wide_unichr(int(c, 16))
        assert c not in mapping or mapping[c] == r, "ERROR: conflicting mappings for %.4X: '%s' and '%s'" % (wide_ord(c), mapping[c], r)

        # exception: literal '\n' maps to newline
        if r == '\\n':
            r = '\n'

        mapping[c] = r

    return mapping

def wide_ord(char):
    try:
        return ord(char)
    except TypeError:
        if len(char) == 2 and 0xD800 <= ord(char[0]) <= 0xDBFF and 0xDC00 <= ord(char[1]) <= 0xDFFF:
            return (ord(char[0]) - 0xD800) * 0x400 + (ord(char[1]) - 0xDC00) + 0x10000
        else:
            raise

def wide_unichr(i):
    try:
        return unichr(i)
    except ValueError:
        return (r'\U' + hex(i)[2:].zfill(8)).decode('unicode-escape')

def mapchar(c, mapping):
    if c in mapping:
        return mapping[c]
    else:
        # make a note of anything unmapped
        global missing_mappings, options
        missing_mappings.add("%.4X" % wide_ord(c))

        # remove missing by default, keep unicode or output codepoint
        # as hex as an option
        if not options.hex and not options.keep_missing:
            return ''
        elif options.keep_missing:
            return c
        else:
            return "<%.4X>" % wide_ord(c)

def replace_mapped_text(e, mapping):
    # TODO: inefficient, improve
    for i, c in enumerate(e.text):
        if wide_ord(c) >= 128:
            s = mapchar(c, mapping)

            # create new element for the replacement
            r = ET.Element(REWRITTEN_TAG)
            r.attrib[ORIG_TEXT_ATTRIBUTE] = c
            r.text = s

            # ... make it the first child of the current element
            e.insert(0, r)

            # ... and split the text between the two
            r.tail = e.text[i+1:]
            e.text = e.text[:i]

            # terminate search; the rest of the text is now
            # in a different element
            break

def parent_index(e, parent):
    for i, c in enumerate(parent):
        if c == e:
            return i
    return None

def replace_mapped_tail(e, mapping, parent):
    # TODO: inefficient, improve
    for i, c in enumerate(e.tail):
        if wide_ord(c) >= 128:
            s = mapchar(c, mapping)

            # create new element for the replacement
            r = ET.Element(REWRITTEN_TAG)
            r.attrib[ORIG_TEXT_ATTRIBUTE] = c
            r.text = s

            # ... make it the next child of the parent after the
            # current
            pidx = parent_index(e, parent)
            parent.insert(pidx+1, r)

            # ... and split the text between the two
            r.tail = e.tail[i+1:]
            e.tail = e.tail[:i]

            # process the rest in the new element
            replace_mapped_tail(r, mapping, parent)

            # terminate search; done in recursion.
            break

def replace_mapped(e, mapping, parent=None):
    # process text content
    if e.text is not None and e.text != "":
        replace_mapped_text(e, mapping)

    # process children recursively
    for c in e:
        replace_mapped(c, mapping, e)

    # process tail unless at root
    if parent is not None and e.tail is not None and e.tail != "":
        replace_mapped_tail(e, mapping, parent)

def process(fn, mapping):
    global options

    try:
        tree = ET.parse(fn)
    except ET.XMLSyntaxError:
        print >> sys.stderr, "Error parsing %s" % fn
        raise

    root = tree.getroot()

    replace_mapped(root, mapping)
    
    # processing done, output

    if options.stdout:
        tree.write(sys.stdout, encoding=OUTPUT_ENCODING)
        return True

    if options is not None and options.directory is not None:
        output_dir = options.directory
    else:
        output_dir = ""

    output_fn = os.path.join(output_dir, os.path.basename(fn))

    # TODO: better checking of path identify to protect against
    # clobbering.
    if output_fn == fn and not options.overwrite:
        print >> sys.stderr, 'rewriteu2a: skipping output for %s: file would overwrite input (consider -d and -o options)' % fn
    else:
        # OK to write output_fn
        try:
            with open(output_fn, 'w') as of:
                tree.write(of, encoding=OUTPUT_ENCODING)
        except IOError, ex:
            print >> sys.stderr, 'rewriteu2a: failed write: %s' % ex
                
    return True

def argparser():
    import argparse
    ap=argparse.ArgumentParser(description='Rewrite Unicode text content with approximately equivalent ASCII in PMC NXML files.')
    ap.add_argument('-d', '--directory', default=None, metavar='DIR',
                    help='output directory')
    ap.add_argument('-o', '--overwrite', default=False, action='store_true',
                    help='allow output to overwrite input files')
    ap.add_argument('-s', '--stdout', default=False, action='store_true',
                    help='output to stdout')
    ap.add_argument('-x', '--hex', default=False, action='store_true',
                    help='write hex sequence for missing mappings')
    ap.add_argument('-k', '--keep-missing', default=False, action='store_true',
                    help='keep unicode for missing mappings')
    ap.add_argument('file', nargs='+', help='input PubMed Central NXML file')
    return ap

def main(argv):
    global options

    options = argparser().parse_args(argv[1:])

    # read in mapping
    try:
        mapfn = MAPPING_FILE_NAME

        if not os.path.exists(mapfn):
            # fall back to trying in script dir
            mapfn = os.path.join(os.path.dirname(__file__), 
                                 os.path.basename(MAPPING_FILE_NAME))

        with codecs.open(mapfn, encoding="utf-8") as f:
            mapping = read_mapping(f, mapfn)
    except IOError, e:
        print >> sys.stderr, "Error reading mapping from %s: %s" % (MAPPING_FILE_NAME, e)
        return 1

    for fn in options.file:
        process(fn, mapping)

    # if there were any missing mappings and an output file name is
    # defined for these, try to append them in that file.
    if len(missing_mappings) > 0 and MISSING_MAPPING_FILE_NAME is not None:
        try:
            with open(MISSING_MAPPING_FILE_NAME, 'a+') as mmf:
                for mm in missing_mappings:
                    print >> mmf, "%s\t%s" % (fn, mm)
        except IOError, e:
            print >> sys.stderr, "Warning: failed to write missing mappings to %s: %s" % (MISSING_MAPPING_FILE_NAME, e)

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
