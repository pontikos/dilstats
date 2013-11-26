# *************************************************************
#
# $Source: /ebi/cvs/seqdb/sptrembl/src/python/tools/mapreduce.py,v $
# $Revision: 1.4 $                                                                 
# $State: Exp $                                                                     
# $Date: 2011/03/31 14:17:39 $                                                      
# $Author: pontikos $  
#
# $Log: mapreduce.py,v $
# Revision 1.4  2011/03/31 14:17:39  pontikos
# *** empty log message ***
#
# Revision 1.3  2011/03/31 13:37:41  pontikos
# *** empty log message ***
#
# Revision 1.2  2011/02/28 12:47:30  pontikos
# *** empty log message ***
#
# Revision 1.1  2011/02/25 10:02:20  pontikos
# *** empty log message ***
#
# Revision 1.5  2011/02/22 18:38:51  pontikos
# python tools to parse FF and distribute jobs on cluster
#
# Revision 1.4  2011/01/06 18:02:53  pontikos
# distribute-ff.py: fix lsf log file
#
# Revision 1.3  2011/01/06 16:56:11  pontikos
# use absolute paths to input and output files
#
#
# *************************************************************
import argparse
import os.path
import sys
from mmap import mmap
import time
from multiprocessing import Process
import subprocess

usage_example="""
For example in order to grep all AC lines in uniprot_trembl.dat one could do:

python mapreduce.py --infile uniprot_trembl.dat --outfile uniprot_trembl.ac_lines --map "grep ^AC" --reduce "cat" --slices 60

	"""

parser=argparse.ArgumentParser( formatter_class=argparse.RawDescriptionHelpFormatter, epilog=usage_example )
parser.add_argument('--infile', dest='infile', help="filename to read from.", required=True)
parser.add_argument('--outfile', dest='outfile', help="filename to write to.", required=True)
parser.add_argument('--map', dest='map', help="command to run on all subfiles.", required=True)
parser.add_argument('--reduce', dest='reduce', help="how to assemble all subfiles back into output file.", required=False, default="cat")
parser.add_argument('--separator', dest='separator', help="record sepator", default="//\n")
parser.add_argument('--slices', dest='slices', help="number of slices to distribute", type=int, default=5)
parser.add_argument('--noreadchunk', dest='readchunk', action='store_false', help="do not pipe output of readchunk but use --file_slice instead", default=True)
args=parser.parse_args()

outfilename_base,outfilename,= os.path.split(args.outfile)
if not outfilename_base:
	outfilename_base='.'
out_stem, out_ext,=os.path.splitext(outfilename)

print 'distribute', args.map, 'on', args.infile, 'into', args.slices, 'slices, sending output to', args.outfile

f=open(args.infile, 'r+b')
m=mmap(f.fileno(), 0)
s=len(m)
print args.infile, 'is', s, 'bytes', s*1e-9, 'gigabytes'

# uniprot entry separator is "//" in FF format
l=[m.find(args.separator,x)+len(args.separator) for x in [x*s/args.slices for x in range(1,args.slices)]]
print len(l), 'splits'
l2=[0]+l
l=l+[s]
slices=map(lambda x,y: (x,y), l2, l)
print len(slices), 'slices'

print time.time()


def f(logfile='', cmd=None, jobname='', blocking=True, big=False):
	if logfile:
		logfile='-o %s' % logfile
	else:
		logfile=''
	if jobname:
		jobname='-J"%s"' % jobname
	else:
		jobname=''
	if blocking:
		#if you use -K it will try to read from stdin
		blocking = '-I'
	else:
		blocking = ''
	if big:
		big='-M 16896 -R "rusage[mem=16896]"'
	else:
		big=''
	cmd='bsub {blocking} {log} -qproduction -Pprod {big} {jobname} "{cmd}"'.format(blocking=blocking, log=logfile, big=big, jobname=jobname, cmd=cmd)
	print cmd
	returncode=subprocess.call(cmd, shell=True)
	print returncode
	if returncode!=0:
		sys.exit(returncode)


workers=[]
slice_filenames=[]
#logfile='%sdistribute-ff_%d_%s_%s.log'%(outfilename_base, n, filename.split('/')[-1], outfilename,)
for (i, p) in enumerate(slices):
	i+=1
	slice_length=p[1]-p[0]
	slice_filename=os.path.sep.join([outfilename_base,'%s_%d_%d%s' % (out_stem, i, args.slices, out_ext)])
	slice_filenames.append(slice_filename)
	#reads a chunk of the infile line by line
	if args.readchunk:
		readchunk="python $CVS_RO/src/python/tools/readchunk.py -f {infile} -s {start} -e {end} | ".format(infile=args.infile,start=p[0],end=p[1])
		file_slice=''
	else:
		readchunk=''
		file_slice="--file_slice {infile}:{start}-{end}".format(infile=args.infile,start=p[0],end=p[1])
	w=Process(target=f, kwargs={'jobname':'MAP_%d'%i, 'cmd':'%s %s %s > %s'%(readchunk,args.map,file_slice,slice_filename,),'blocking':True})
	workers.append(w)
	w.start()
	#print workers
	#sleep not to overload submission queue
	time.sleep(1)

#time.sleep(5)

#blocking until all threads have returned
#this could be improved we could already start
#concatenating files while we wait for others threads
#to return

print 'joining'
for w in workers:
	w.join()
	print w
	if w.exitcode:
		sys.stderr.write(w)
		sys.stderr.write(w.exitcode)
		sys.exit(returncode)
		w.terminate()

#time.sleep(5)
print 'finished'
print [w.is_alive() for x in workers]

del workers
print time.time()

#reduce step
w=Process(target=f, kwargs={'cmd':'cat %s | %s > %s' % (' '.join(slice_filenames), args.reduce, args.outfile,), 'blocking':True, 'jobname':'REDUCE', 'big':True})
w.start()
w.join()

print time.time()

# final rm of all temp output files
w=Process(target=f,kwargs={'cmd':'rm %s' % ' '.join(slice_filenames), 'blocking':True, 'jobname':'FINAL_RM', 'big':True})
w.start()

print time.time()


