import cPickle as pickle
import argparse
import codecs
import glob
import sys
import os.path
import xml.etree.cElementTree as ET
import time
import traceback
import gzip

__author__ = 'Filip Ginter'

class Section:

    def __init__(self,title,charBeg,charEnd,titleCharBeg,titleCharEnd):
        self.title=title
        self.charBeg=charBeg
        self.charEnd=charEnd
        self.titleCharBeg=titleCharBeg
        self.titleCharEnd=titleCharEnd
        self.subsections=[]
        self.parent=None
        self.spans=[]

    def addsubsection(self,title,charBeg,charEnd,titleCharBeg,titleCharEnd):
        #Is this my own subsection?
        if charBeg>=self.charBeg and charEnd<=self.charEnd:
            #yup
            if self.subsections:
                assert charBeg>=self.subsections[-1].charEnd
            newS=Section(title,charBeg,charEnd,titleCharBeg,titleCharEnd)
            self.subsections.append(newS)
            newS.parent=self
            return newS
        #I guess this section should be following me
        assert charBeg>=self.charEnd
        return self.parent.addsubsection(title,charBeg,charEnd,titleCharBeg,titleCharEnd)

    def elem(self,actualSpanOffsets,inputTXT):
        E=ET.Element("section")
        if self.titleCharBeg==None and self.titleCharEnd==None:
            E.set("title",self.title)
        else:
            E.set("title",inputTXT[self.titleCharBeg:self.titleCharEnd])
        for spanID in self.spans:
            S=ET.SubElement(E,"span")
            cB,cE=actualSpanOffsets[spanID][0],actualSpanOffsets[spanID][1]
            if (cB,cE) == (None,None):
                S.set("charBeg",u"None")
                S.set("charEnd",u"None")
            else:
                S.set("charBeg",unicode(cB))
                S.set("charEnd",unicode(cE))
                
        for subS in self.subsections:
            E.append(subS.elem(actualSpanOffsets,inputTXT))
        return E

def is_zip_file(filename):
    return filename.endswith('.gz')

def read_lines(filename):
    if is_zip_file(filename):
        with gzip.open(filename, 'rb') as f:
            for line in f:
                yield line
    else:
        with open(filename, 'rt') as f:
            for line in f:
                yield line

def read_text(filename):
    return ''.join(read_lines(filename))

def getInterestingSpans(soFileName):
    mainSection=None
    currentSection=None
    spans=[] #list of (element,beg,end,spanTxt)
    ranges={} #key: latest seen element of the given type, value: (beg,end)
    for line in read_lines(soFileName):
        line=line.strip()
        if not line:
            continue
        line=unicode(line,"utf-8")
        line=line.split(u"\t")
        if len(line)==1:
            continue
        elif len(line)==2:
            spanId,spanOff=line[:2]
            spanTxt=u""
        elif len(line)>=3:
            spanId,spanOff,spanTxt=line[:3]
        element,charBeg,charEnd=spanOff.split()
        charBeg,charEnd=int(charBeg),int(charEnd)
        ranges[element]=(charBeg,charEnd)
        if element==u"body":
            currentSection=currentSection.addsubsection(element,charBeg,charEnd,None,None)
            continue
        if element==u"article" and charBeg==0:
            assert currentSection==None
            currentSection=Section(element,charBeg,charEnd,None,None)
            mainSection=currentSection
            continue
        if element==u"sec":
            #Do this only in the body
            if u"body" not in ranges:
                continue
            bodyB,bodyE=ranges[u"body"]
            if not (charBeg>=bodyB and charEnd<=bodyE):
                continue
            currentSection=currentSection.addsubsection(element,charBeg,charEnd,None,None)
            continue
        if element==u"title":
            #Does this belong to a section?
            if u"sec" not in ranges:
                continue #nope
            if currentSection.title==u"sec" and currentSection.titleCharBeg==None:
                currentSection.title=spanTxt.strip()
                currentSection.titleCharBeg=charBeg
                currentSection.titleCharEnd=charEnd
            #This doesn't really work with labels
            # secBeg,secEnd=ranges[u"sec"]
            # if secBeg!=charBeg:
            #     continue #nope
            #Any title past this point is a fresh section title
        if element==u"article-id":
            if len(line)!=4:
                continue
            if line[3]=="pub-id-type=\"pmc\"":
                articleID=line[2]
        if element in (u"article-title",u"abstract"):
            #These are only allowed before the body
            if u"body" in ranges:
                continue
            currentSection=currentSection.addsubsection(element,charBeg,charEnd,None,None) #making dummy sections for these
        elif element in (u"p",u"title"):
            #This is only allowed inside body
            if u"body" not in ranges:
                continue
            bodyB,bodyE=ranges[u"body"]
            if not (charBeg>=bodyB and charEnd<=bodyE):
                continue
        #The elements of interest here are permissible now
        if element in (u"p",u"title",u"article-title",u"abstract"):
            if spans:
                prev=spans[-1]
                if prev[1]<=charBeg and prev[2]>=charEnd: #
                    continue #Skip if the previous span crosses this one
            
            spans.append((element,charBeg,charEnd,spanTxt))
            currentSection.spans.append(len(spans)-1)
        if element in (u"inline-formula",u"math"):
            if spans:
                prev=spans[-1]
                if prev[1]==charBeg and prev[2]==charEnd: #
                    #math spanning whole paragraph
                    spans.pop(-1)
                    currentSection.spans.pop(-1)
                    
    return articleID,mainSection,spans

def printCleanTxt(out, spans, txtFileName, include_abstract=True):
    actualSpanOffsets=[]
    txt = read_text(txtFileName)
    fileOffset=0
    for (element,charBeg,charEnd, spanControlTxt) in spans:
        if element in (u"abstract",u"article-title") and not include_abstract:
            #print >> sys.stderr, "Skipping", element
            actualSpanOffsets.append((None,None))
            continue
        #print >> sys.stderr, u"#", element
        while charBeg<=charEnd and charBeg<len(txt) and txt[charBeg].isspace():
            charBeg+=1
        while charEnd>=charBeg and charEnd<=len(txt) and txt[charEnd-1].isspace():
            charEnd-=1
        spanText=txt[charBeg:charEnd]
        spanControlTxt=spanControlTxt.strip().replace(u"\\\\",u"xxxmymagicstringfilip1112xxx").replace(u"\\n",u"\n").replace(u"\\t",u"\t").replace(u"xxxmymagicstringfilip1112xxx",u"\\").strip()
        splitIdx=spanControlTxt.find(u"[[[...]]]")
        if splitIdx>=0:
            prefix=spanControlTxt[:splitIdx]
            suffix=spanControlTxt[splitIdx+len(u"[[[...]]]"):]
            assert spanText.startswith(prefix), (spanText,prefix)
            assert spanText.endswith(suffix), (spanText,suffix)
        else:
            assert spanText==spanControlTxt, (spanText,spanControlTxt)
        
        actualSpanOffsets.append((fileOffset,fileOffset+len(spanText)+2)) #+2 for the two newlines
        print >> out, spanText
        print >> out
        fileOffset+=len(spanText)+2
    return actualSpanOffsets,txt

def rootname(filename):
    """Return basename root without extensions."""
    name = os.path.basename(filename)
    root, ext = os.path.splitext(name)
    while ext:
        root, ext = os.path.splitext(root)
    return root

def getDocPairs(textdir, sodir, options=None):
    if options and options.zipped:
        txtglob = '*.txt.gz'
        soglob = '*.so.gz'
    else:
        txtglob = '*.txt'
        soglob = '*.so'
    textfiles=glob.glob(os.path.join(textdir, txtglob))
    textfiles.sort()
    sofiles=glob.glob(os.path.join(sodir, soglob))
    sofiles.sort()
    assert len(textfiles) == len(sofiles), \
        '.txt and .so counts differ in %s and %s' % (textdir, sodir)
    pairs=[]
    for textfile, sofile in zip(textfiles, sofiles):
        assert rootname(textfile) == rootname(sofile), (textfile, sofile)
        pairs.append((textfile, sofile))
    return pairs

def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def write_sections(secdir, docid, element):
    if secdir is None:
        # Silently skip output if no directory specified.
        return
    filename = os.path.join(secdir, 'pmc_%s_sections.xml' % docid)
    ET.ElementTree(element).write(filename, 'utf-8')

def processPair(txtFile, soFile, outdirTXT, outdirSEC):
    try:
        pmcID,mainSection,spans=getInterestingSpans(soFile)
        assert pmcID.isdigit()
        pmcID=int(pmcID)

        outFileNameTXT=os.path.join(outdirTXT,"pmc_"+str(pmcID)+".txt")
        outFile=codecs.open(outFileNameTXT,"w","utf-8")
        actualSpanOffsets,txt=printCleanTxt(outFile, spans, txtFile)
        outFile.close()

        E=mainSection.elem(actualSpanOffsets,txt)
        indent(E)
        write_sections(outdirSEC, pmcID, E)
    except:
        traceback.print_exc()
        print >> sys.stderr, "FAILURE / ERROR / SKIPPING"
        print >> sys.stderr, txtFile
        try:
            os.system("rm -f '%s'"%outFileNameTXT)
            os.system("rm -f '%s'"%outFileNameSEC)
        except:
            pass


def processDir(textdir, sodir, options):
    pairs = getDocPairs(textdir, sodir)

    textout = options.textout
    if not os.path.exists(textout):
        os.makedirs(textout)

    secout = options.secout
    if secout and not os.path.exists(secout):
        os.makedirs(secout)

    for txtfile, sofile in pairs:
        processPair(txtfile, sofile, textout, secout)

def main(argv):
    parser = argparse.ArgumentParser(description='Get clean text and section data from .txt and .so files.')
    parser.add_argument('-t', '--textout', metavar='DIR', required=True,
                        help='Directory to store clean .txt files to')
    parser.add_argument('-s', '--secout', metavar='DIR', default=None, 
                        help='Directory to store section data XML to')
    parser.add_argument('-z', '--zipped', default=False, action='store_true',
                        help='Process zipped (.gz) files')
    parser.add_argument('dirs', nargs='+',
                        help='Directories to process.')
    args = parser.parse_args(argv[1:])
    
    dirs2process=args.dirs
    dirs2process.sort()

    for dirName in dirs2process:
        print >> sys.stderr, dirName
        dirName=dirName.strip()
        processDir(dirName, dirName, args)

    return 0

if __name__=='__main__':
    sys.exit(main(sys.argv))
