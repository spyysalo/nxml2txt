import cPickle as pickle
from optparse import OptionParser
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
    

def getInterestingSpans(soFileName):
    mainSection=None
    currentSection=None
    spans=[] #list of (element,beg,end,spanTxt)
    f=gzip.open(soFileName,"rb")
    ranges={} #key: latest seen element of the given type, value: (beg,end)
    for line in f:
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
                    
    f.close()
    return articleID,mainSection,spans

def printCleanTxt(out,spans,txtFileName,printAbstractless):
    actualSpanOffsets=[]
    f=gzip.open(txtFileName,"rb")
    txt=f.read()
    f.close()
    #print >> sys.stderr, u"#", txtFileName
    fileOffset=0
    for (element,charBeg,charEnd, spanControlTxt) in spans:
        if printAbstractless and element in (u"abstract",u"article-title"):
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

def getDocPairs(dirNameTXT,dirNameSO):
    print dirNameTXT, dirNameSO
    txtFiles=glob.glob(os.path.join(dirNameTXT,"*.txt.gz"))
    txtFiles.sort()
    soFiles=glob.glob(os.path.join(dirNameSO,"*.so.gz"))
    soFiles.sort()
    assert len(txtFiles)==len(soFiles)
    pairs=[]
    for txtFile,soFile in zip(txtFiles,soFiles):
        assert os.path.basename(txtFile.replace(".txt.gz",""))==os.path.basename(soFile.replace(".so.gz","")), (txtFile,soFile)
        pairs.append((txtFile,soFile))
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

def processPair(txtFile,soFile,outdirTXT,outdirSEC,abstractless):
    try:
        pmcID,mainSection,spans=getInterestingSpans(soFile)
        assert pmcID.isdigit()
        pmcID=int(pmcID)

        outFileNameTXT=os.path.join(outdirTXT,"pmc_"+str(pmcID)+".txt")
        outFile=codecs.open(outFileNameTXT,"w","utf-8")
        actualSpanOffsets,txt=printCleanTxt(outFile,spans,txtFile,pmcID in abstractless)
        outFile.close()

        outFileNameSEC=os.path.join(outdirSEC,"pmc_"+str(pmcID)+"_sections.xml")
        E=mainSection.elem(actualSpanOffsets,txt)
        indent(E)
        ET.ElementTree(E).write(outFileNameSEC,"utf-8")
    except:
        traceback.print_exc()
        print >> sys.stderr, "FAILURE / ERROR / SKIPPING"
        print >> sys.stderr, txtFile
        try:
            os.system("rm -f '%s'"%outFileNameTXT)
            os.system("rm -f '%s'"%outFileNameSEC)
        except:
            pass


def processDir(dirNameTXT,dirNameSO,abstractless,options):
    pairs=getDocPairs(dirNameTXT,dirNameSO)


    dirBase=os.path.basename("OUT")

    outdirTXT=os.path.join(options.outDirTXT_ROOT,dirBase)
    if not os.path.exists(outdirTXT):
        os.makedirs(outdirTXT)

    outdirSEC=os.path.join(options.outDirSEC_ROOT,dirBase)
    if not os.path.exists(outdirSEC):
        os.makedirs(outdirSEC)

    for txtFile,soFile in pairs:
        processPair(txtFile,soFile,outdirTXT,outdirSEC,abstractless)

if __name__=="__main__":
    parser = OptionParser(description="Give this script a list of directories containing .txt and .standoff files, it will write new directories with clean text and section data")
    parser.add_option("--abstractless",action="store",dest="abstractless",default=None, help="Pickled set of PMCIDs which should be processed without title & abstract")
    parser.add_option("--outDirTXT_ROOT",action="store",dest="outDirTXT_ROOT",default=None, help="Directory root to which the directories with clean .txts go", metavar="DIR")
    parser.add_option("--outDirSEC_ROOT",action="store",dest="outDirSEC_ROOT",default=None, help="Directory root to which the directories with section data XMLs go", metavar="DIR")
    (options, args) = parser.parse_args()
    
    #f=open(options.abstractless,"rb")
    abstractless=set()#pickle.load(f)
    #f.close()

    dirs2process=args
    dirs2process.sort()

    for dirName in dirs2process:
        print >> sys.stderr, dirName
        dirName=dirName.strip()
        processDir(dirName+"/TXT",dirName+"/SO",abstractless,options)
