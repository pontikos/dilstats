DILStats Code Snippets
========

Code examples which should be useful for the rest of the dilstats team.

[select.py](https://github.com/pontikos/dilstats/blob/master/select.py):

This is a basic python script for selecting columns from text file given header name.
An extremely trivial piece of code on which you can build to
add conditions to only select certain lines etc.
Essentially this is not really doing anything that you can't already
do with awk/perl but it's just much easier (IMO) to build upon and
extend.
Here's an example of how you could use this script (let's call it
select.py) if you wanted to only select probe sequences on chr 19 from
the ImmunoChip support file:

`cat Immuno_BeadChip_11419691_B.csv | python select.py -f Chr,Name,AlleleA_ProbeSeq,AlleleB_ProbeSeq  | grep ^19,`

[submit.bash](https://github.com/pontikos/dilstats/blob/master/submit.bash):

Bash script example for submitting jobs to the queue, in the hope that some of you might benefit from this,
here's an example of a bash script which you can use to submit jobs  to the queue.
I think it's a good example of passing parameters to a bash script,  function calling and filename manipulation.
The general idea is to do all the directory creation and job submitting in bash and to how have the actual jobs
written as Rscripts which use the optparse library to parse command line arguments.

[splitby.py](https://github.com/pontikos/dilstats/blob/master/splitby.py)

Python script to split Illumina file by SNP or by Sample.  Will create a new file for each SNP or for each Sample.






