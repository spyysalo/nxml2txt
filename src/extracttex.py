#!/usr/bin/env python

# Print unique <tex-math> elements from PMC NXML files.

# Helper for nxml2txt development.

import sys
import os
import re
import codecs

from lxml import etree as ET

# command-line options
options = None

# pre-compiled regular expressions

# key declarations in tex documents
texdecl_re = re.compile(r'(\\(?:documentclass|usepackage|setlength|pagestyle)(?:\[[^\[\]]*\])?(?:\{[^\{\}]*\})*)')
# document start or end
texdoc_re = re.compile(r'(\\(?:begin|end)(?:\[[^\[\]]*\])?\{document\})')
# includes for "standard" tex packages
texstdpack_re = re.compile(r'\\usepackage\{(?:amsbsy|amsfonts|amsmath|amssymb|mathrsfs|upgreek|wasysym)\}')
# consequtive space
space_re = re.compile(r'\s+')
# initial and terminal space.
docstartspace_re = re.compile(r'^\s*')
docendspace_re   = re.compile(r'\s*$')

##########

# for stats output
exttex_cache_hits = 0
exttex_cache_misses = 0

def normalize_tex(s):
    """
    Given the string content of a tex document, returns a normalized
    version of its content, abstracting away "standard" declarations
    and includes.
    """

    # Note: this could be made more effective by including synonymous
    # commands in tex and more removing content-neutral formatting
    # more aggressively.

    # remove "standard" package includes
    s = texstdpack_re.sub('', s)

    # remove header boilerplate declarations (superset of texstdpack_re)
    s = texdecl_re.sub(r'', s)

    # replace any amount of consequtive space by a single plain space
    s = space_re.sub(' ', s)

    # eliminate doc-initial and -terminal space.
    s = docstartspace_re.sub('', s)
    s = docendspace_re.sub('', s)

    return s

def compilable(tex):
    """Return tex-math content wrapped so that it can be compiled using tex."""

    # remove "\usepackage{pmc}". It's not clear what the contents
    # of this package are (I have not been able to find it), but
    # compilation more often succeeds without it than with it.
    tex = tex.replace('\\usepackage{pmc}', '')

    # replace "\documentclass{minimal}" with "\documentclass{slides}".
    # It's not clear why, but some font commands (e.g. "\tt") appear
    # to fail with the former.
    tex = re.sub(r'(\\documentclass(?:\[[^\[\]]*\])?\{)minimal(\})',
                 r'\1slides\2', tex)

    # replace any amount of consequtive space by a single plain space
    tex = space_re.sub(' ', tex)
    
    return tex
    
def process(fn, tex_set={}):
    global exttex_rewrites, exttex_cache_hits, exttex_cache_misses
    global options
    
    try:
        tree = ET.parse(fn)
    except ET.XMLSyntaxError:
        print >> sys.stderr, "Error parsing %s" % fn
        raise

    root = tree.getroot()

    # find "tex-math" elements in any namespace ("local-name")
    # anywhere in the tree.
    for e in root.xpath("//*[local-name()='tex-math']"):
        tex = e.text

        # normalize the tex document for cache lookup
        tex_norm = normalize_tex(tex)

        if tex_norm in tex_set:
            exttex_cache_hits += 1
        else:
            exttex_cache_misses += 1
            print compilable(tex)
            tex_set.add(tex_norm)
    return True

def argparser():
    import argparse
    ap=argparse.ArgumentParser(description='Extract <tex-math> element content from PMC NXML files.')
    ap.add_argument('-v', '--verbose', default=False, action='store_true', help='verbose output')
    ap.add_argument('file', nargs='+', help='input PubMed Central NXML file')
    return ap
    
def main(argv):
    global exttex_rewrites, exttex_cache_hits, exttex_cache_misses
    global options

    options = argparser().parse_args(argv[1:])

    tex_set = set()
    for fn in options.file:
        process(fn, tex_set)

    if options.verbose and any (value for value in (exttex_cache_hits, exttex_cache_misses) if value != 0):
        print >> sys.stderr, 'extracttex: %d dup, %d unique' % (exttex_cache_hits, exttex_cache_misses)

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
