#!/usr/bin/env python

# Replaces the content of <tex-math> elements with approximately
# equivalent text strings in PMC NXML files. Requires catdvi.

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

# XML tag to use for elements whose text content has been rewritten
# by this script.
REWRITTEN_TAG = 'n2t-tex'

# XML attribute to use for storing the original text and tag of
# rewritten elements
ORIG_TAG_ATTRIBUTE  = 'orig-tag'
ORIG_TEXT_ATTRIBUTE = 'orig-text'

# command for invoking tex (-interaction=nonstopmode makes latex try
# to proceed on error without waiting for input.)
TEX_COMMAND = 'latex -interaction=nonstopmode'

# directory into which to instruct tex to place its output.
TEX_OUTPUTDIR = '/tmp'

# command for invokind catdvi (-e 0 specifies output encoding in UTF-8,
# and -s sets sequential mode, which turns off attempt to reproduce
# layout such as sub- and superscript positioning.)
CATDVI_COMMAND = 'catdvi -e 0 -s'

# path to on-disk cache of tex document -> text mappings
TEX2STR_CACHE_PATH = os.path.join(os.path.dirname(__file__), 
                                  '../data/tex2txt.cache')

INPUT_ENCODING="UTF-8"
OUTPUT_ENCODING="UTF-8"

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

def ordall(d):
    """
    Given a dict with string values, returns an equivalent dict where
    the strings have been transformed into arrays of integers. This is
    a data "wrapper" to avoid a weird issue with cPickle where
    undefined unicode chars were modified in the pickling/unpickling
    process.  (Try to pickle unichr(0x10FF0C) to see if this affects
    your setup)
    """
    from copy import deepcopy
    d = deepcopy(d)
    for k in d.keys():
        d[k] = [ord(c) for c in d[k]]
    return d

def unordall(d):
    """
    Given a dict with integer list values, returns an equivalent dict
    where the int lists have been transformed into unicode strings.
    This is a data "wrapper" to avoid a weird issue with cPickle where
    undefined unicode chars were modified in the pickling/unpickling
    process.  (Try to pickle unichr(0x10FF0C) to see if this affects
    your setup)
    """
    from copy import deepcopy
    d = deepcopy(d)
    for k in d.keys():
        d[k] = "".join([unichr(c) for c in d[k]])
    return d

def load_cache(fn):
    from cPickle import UnpicklingError
    from cPickle import load as pickle_load
    try:
        with open(fn, 'rb') as cache_file:
            data = pickle_load(cache_file)
            return data
    except UnpicklingError:
        print >> sys.stderr, "rewritetex: warning: failed to read cache file."
        raise
    except IOError:
        print >> sys.stderr, "rewritetex: note: cache file not found."
        raise
    except:
        print >> sys.stderr, "rewritetex: warning: unexpected error loading cache."
        raise

def save_cache(fn, data):
    from cPickle import UnpicklingError
    from cPickle import dump as pickle_dump
    try:
        with open(fn, 'wb') as cache_file:
            pickle_dump(data, cache_file)
            cache_file.close()
    except IOError:
        print >> sys.stderr, "rewritetex: warning: failed to write cache."        
    except:
        print >> sys.stderr, "rewritetex: warning: unexpected error writing cache."

def tex_compile(fn):
    """
    Invokes tex to compile the file with the given name.  
    Returns the name of the output file (.dvi), the empty string if
    the name could not be determined, or None if compilation fails.
    """

    from subprocess import PIPE, Popen

    cmd = TEX_COMMAND+' '+'-output-directory='+TEX_OUTPUTDIR+' '+fn

    try:
        # TODO: avoid shell with Popen
        tex = Popen(cmd, shell=True, stdin=None, stdout=PIPE, stderr=PIPE)
        tex.wait()
        tex_out, tex_err = tex.communicate()

        # check tex output to determine output file name or to see
        # if an error message indicating nothing was output is
        # included.
        dvifn, no_output = "", False
        for l in tex_out.split("\n"):
            m = re.match(r'Output written on (\S+)', l)
            if m:
                dvifn = m.group(1)
            if "No pages of output" in l:
                no_output = True

        if no_output and not dvifn:
            #print >> sys.stderr, "rewritetex: failed to compile tex"
            error_lines = [l for l in tex_out.split('\n') if 'Error' in l]
            if error_lines:
                print >> sys.stderr, '\n'.join(error_lines)
            return None

        return dvifn
    except IOError:
        #print >> sys.stderr, "rewritetex: error compiling tex document!"
        return None

def run_catdvi(fn):
    """
    Invokes catdvi to get the text content of the given .dvi file.
    Returns catdvi output or None if the invocation fails.
    """

    from subprocess import PIPE, Popen

    cmd = CATDVI_COMMAND+' '+fn

    try:
        # TODO: avoid shell with Popen
        catdvi = Popen(cmd, shell=True, stdin=None, stdout=PIPE, stderr=PIPE)
        catdvi.wait()
        catdvi_out, catdvi_err = catdvi.communicate()
        return catdvi_out
    except IOError, e:
        print >> sys.stderr, "rewritetex: failed to invoke catdvi:", e
        return None

def tex2str(tex):
    """
    Given a tex document as a string, returns a text string
    approximating the tex content. Performs conversion using the
    external tools tex and catdvi.
    """

    from tempfile import NamedTemporaryFile

    # perform some minor tweaks to the given tex document to get
    # around compilation problems that frequently arise with PMC
    # NXML embedded tex:

    # remove "\usepackage{pmc}". It's not clear what the contents
    # of this package are (I have not been able to find it), but
    # compilation more often succeeds without it than with it.
    tex = tex.replace('\\usepackage{pmc}', '')

    # replace "\documentclass{minimal}" with "\documentclass{slides}".
    # It's not clear why, but some font commands (e.g. "\tt") appear
    # to fail with the former.
    tex = re.sub(r'(\\documentclass(?:\[[^\[\]]*\])?\{)minimal(\})',
                 r'\1slides\2', tex)

    # now ready to try conversion.

    # create a temporary file for the tex content
    try:
        with NamedTemporaryFile('w', suffix='.tex') as tex_tmp:
            tex_tmp.write(tex.encode(OUTPUT_ENCODING))
            tex_tmp.flush()

            tex_out_fn = tex_compile(tex_tmp.name)

            if tex_out_fn is None:
                # failed to compile
                print >> sys.stderr, 'rewritetex: failed to compile tex document:\n"""\n%s\n"""' % tex.encode(OUTPUT_ENCODING)
                return None

            # if no output file name could be found in tex output
            # in the expected format, back off to an expected default
            if tex_out_fn == "":
                expected_out_fn = tex_tmp.name.replace(".tex", ".dvi")
                tex_out_fn = os.path.join(TEX_OUTPUTDIR,
                                            os.path.basename(expected_out_fn))

            dvistr = run_catdvi(tex_out_fn)

            try:
                dvistr = dvistr.decode(INPUT_ENCODING)
            except UnicodeDecodeError:
                print >> sys.stderr, 'rewritetex: error decoding catdvi output as %s (adjust INPUT_ENCODING?)' % INPUT_ENCODING

            if dvistr is None or dvistr == "":
                print >> sys.stderr, 'rewritetex: likely error invoking catdvi (empty output)'
                return None

            # perform minor whitespace cleanup
            dvistr = re.sub(r'\s+', ' ', dvistr)
            dvistr = re.sub(r'^\s+', '', dvistr)
            dvistr = re.sub(r'\s+$', '', dvistr)

            return dvistr
    except IOError:
        print >> sys.stderr, "rewritetex: failed to create temporary file"
        raise

def rewrite_tex_element(e, s):
    """
    Given an XML tree element e and a string s, stores the original
    text content of the element in an attribute and replaces it with
    the string, further changing the tag to relect the change.
    """

    # check that the attributes that will be used don't clobber
    # anything
    for a in (ORIG_TAG_ATTRIBUTE, ORIG_TEXT_ATTRIBUTE):
        assert a not in e.attrib, "rewritetex: error: attribute '%s' already defined!" % a

    # store original text content and tag as attributes
    e.attrib[ORIG_TEXT_ATTRIBUTE] = e.text
    e.attrib[ORIG_TAG_ATTRIBUTE] = e.tag

    # swap in the new ones
    e.text = s
    e.tag = REWRITTEN_TAG
    
    # that's all
    return True

class Stats(object):
    def __init__(self):
        self.rewrites = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.conversions_ok = 0
        self.conversions_err = 0

    def zero(self):
        return (self.rewrites == 0 and
                self.cache_hits == 0 and
                self.cache_misses == 0 and
                self.conversions_ok == 0 and
                self.conversions_err == 0)

    def __str__(self):
        return \
            '%d rewrites (%d cache hits, %d misses; converted %d, failed %d)' %\
            (self.rewrites, self.cache_hits, self.cache_misses,
             self.conversions_ok, self.conversions_err)

def process(fn, tex2str_map={}, stats=None, options=None):
    if stats is None:
        stats = Stats()

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

        if tex_norm in tex2str_map:
            mapped = tex2str_map[tex_norm]
            stats.cache_hits += 1
        else:
            stats.cache_misses += 1

            # no existing mapping to string; try to convert
            #print >> sys.stderr, "rewritetex: converting: '%s'" % tex_norm
            s = tex2str(tex)
            
            # only use results of successful conversions
            if s is None or s == "":
                mapped = None
                stats.conversions_err += 1
            else:
                stats.conversions_ok += 1
                mapped = s
                # store in cache 
                tex2str_map[tex_norm] = s

        if mapped is not None:
            # replace the <tex-math> element with the mapped text
            rewrite_tex_element(e, mapped)
            stats.rewrites += 1

    # processing done, output

    if options is not None and options.stdout:
        tree.write(sys.stdout, encoding=OUTPUT_ENCODING)
        return True

    if options is not None and options.directory is not None:
        output_dir = options.directory
    else:
        output_dir = ""

    output_fn = os.path.join(output_dir, os.path.basename(fn))

    # TODO: better checking to protect against clobbering.
    if output_fn == fn and not options.overwrite:
        print >> sys.stderr, 'rewritetex: skipping output for %s: file would overwrite input (consider -d and -o options)' % fn
    else:
        # OK to write output_fn
        try:
            with open(output_fn, 'w') as of:
                tree.write(of, encoding=OUTPUT_ENCODING)
        except IOError, ex:
            print >> sys.stderr, 'rewritetex: failed write: %s' % ex
                
    return True

def argparser():
    import argparse
    ap=argparse.ArgumentParser(description='Rewrite <tex-math> element content with approximately equivalent text strings in PMC NXML files.')
    ap.add_argument('-d', '--directory', default=None, metavar='DIR', help='output directory')
    ap.add_argument('-o', '--overwrite', default=False, action='store_true', help='allow output to overwrite input files')
    ap.add_argument('-s', '--stdout', default=False, action='store_true', help='output to stdout')
    ap.add_argument('-v', '--verbose', default=False, action='store_true', help='verbose output')
    ap.add_argument('file', nargs='+', help='input PubMed Central NXML file')
    return ap

def get_tex2str_map():
    try:
        # (see comment in unordall() for why this it's used here)
        return unordall(load_cache(TEX2STR_CACHE_PATH))
    except:
        return {}

def main(argv):
    options = argparser().parse_args(argv[1:])
    stats = Stats()

    # load cache
    tex2str_map = get_tex2str_map()

    # process each file
    for fn in options.file:
        process(fn, tex2str_map, stats, options)

    # save cache
    # (see comment in ordall() for why this it's used here)
    save_cache(TEX2STR_CACHE_PATH, ordall(tex2str_map))

    # output stats
    if options.verbose and not stats.zero():
        print >> sys.stderr, 'rewritetex: %s' % str(stats)

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
