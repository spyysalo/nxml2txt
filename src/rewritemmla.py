#!/usr/bin/env python

# Moves the text content of MathML <annotation> elements into an
# attribute in XML files, thus removing the annotations from the file
# text content.

# This is a component in a pipeline to convert PMC NXML files into
# text and standoffs. The whole pipeline can be run as
#
#    python rewritetex.py FILE.xml -s | python rewritemmla.py -s | python rewriteu2a.py - -s | python respace.py - -s | python standoff.py - FILE.{txt,so}

from __future__ import with_statement

import sys
import os
import re
import codecs

from lxml import etree as ET

# XML tag to use for elements whose text content has been rewritten
# by this script.
REWRITTEN_TAG = 'n2t-mmla'

# XML attribute to use for storing the original text and tag of
# rewritten elements
ORIG_TAG_ATTRIBUTE  = 'orig-tag'
ORIG_TEXT_ATTRIBUTE = 'orig-text'

INPUT_ENCODING="UTF-8"
OUTPUT_ENCODING="UTF-8"

##########

def rewrite_element(e, s):
    """
    Given an XML tree element e and a string s, stores the original
    text content of the element in an attribute and replaces it with
    the string, further changing the tag to relect the change.
    """

    # check that the attributes that will be used don't clobber
    # anything
    for a in (ORIG_TAG_ATTRIBUTE, ORIG_TEXT_ATTRIBUTE):
        assert a not in e.attrib, "rewritemmla: error: attribute '%s' already defined!" % a

    # store original text content and tag as attributes
    e.attrib[ORIG_TEXT_ATTRIBUTE] = e.text if e.text is not None else ''
    e.attrib[ORIG_TAG_ATTRIBUTE] = e.tag

    # swap in the new ones
    e.text = s
    e.tag = REWRITTEN_TAG
    
    # that's all
    return True

def read_tree(filename):
    try:
        return ET.parse(filename)
    except ET.XMLSyntaxError:
        print >> sys.stderr, "Error parsing %s" % fn
        raise

def process_tree(tree, options=None):
    root = tree.getroot()

    namespaces = { 'mml': 'http://www.w3.org/1998/Math/MathML' }

    # find "annotation" elements in any the namespace
    # http://www.w3.org/1998/Math/MathML anywhere in the tree.
    for e in root.xpath("//mml:annotation", namespaces=namespaces):
        rewrite_element(e, '')

    return tree

def write_tree(tree, options=None):
    if options is not None and options.stdout:
        tree.write(sys.stdout, encoding=OUTPUT_ENCODING)
        return True

    if options is not None and options.directory is not None:
        output_dir = options.directory
    else:
        output_dir = ""

    output_fn = os.path.join(output_dir, os.path.basename(fn))

    # TODO: better checking of path identify to protect against
    # clobbering.
    if output_fn == fn and (not options or not options.overwrite):
        print >> sys.stderr, 'rewritemmla: skipping output for %s: file would overwrite input (consider -d and -o options)' % fn
    else:
        # OK to write output_fn
        try:
            with open(output_fn, 'w') as of:
                tree.write(of, encoding=OUTPUT_ENCODING)
        except IOError, ex:
            print >> sys.stderr, 'rewritemmla: failed write: %s' % ex
                
    return True

def process(fn, options=None):
    tree = read_tree(fn)
    process_tree(tree)
    write_tree(tree, options)

def argparser():
    import argparse
    ap=argparse.ArgumentParser(description='Mask MathML <annotation> element text content in XML files.')
    ap.add_argument('-d', '--directory', default=None, metavar='DIR', help='output directory')
    ap.add_argument('-o', '--overwrite', default=False, action='store_true', help='allow output to overwrite input files')
    ap.add_argument('-s', '--stdout', default=False, action='store_true', help='output to stdout')
    ap.add_argument('-v', '--verbose', default=False, action='store_true', help='verbose output')
    ap.add_argument('file', nargs='+', help='input XML file')
    return ap
    
def main(argv):
    options = argparser().parse_args(argv[1:])
    for fn in options.file:
        process(fn, options)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
