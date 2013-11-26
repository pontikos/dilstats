import os.path
import sys 
from optparse import OptionParser

parser = OptionParser()
parser.add_option("-d", "--dir", dest="dir", help="write output to DIR", metavar="DIR")
parser.add_option("--header", dest="header", action='store_true', help="whether file has a header", default=False)
(options, args) = parser.parse_args()

outdir=options.dir
if outdir.endswith('-sample'):
    def f(record, line) : file(os.path.join(outdir,record['Sample_ID']+'.csv'),'a+').write(line)
elif outdir.endswith('-snp'):
    def f(record, line): file(os.path.join(outdir,record['SNP_Name']+'.csv'),'a+').write(line)

#header=['SNP.Name','Sample.ID','GC.Score','Allele1.Forward','Allele2.Forward','Chr','Position','Theta','R','X','Y','B.Allele.Freq','Log.R.Ratio']
header=['Sample_ID','SNP_Name','Chr','Position','GC_Score','Genotype_Forward','Theta','R','X','Y','B_Allele_Freq','Log_R_Ratio','GT_Score']

if options.header: sys.stdin.readline()

line=sys.stdin.readline()
while line:
    record=dict(zip(header, line.strip().split('\t')))
    f(record, line)
    line=sys.stdin.readline()

