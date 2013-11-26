import sys
from optparse import OptionParser
parser = OptionParser()
parser.add_option('-f','--fields', dest='fields', default=None,
help="which fields to display (comma separated)")
parser.add_option('-s', '--separator', dest='sep', default=',',
help='separator to use')
(options, args) = parser.parse_args()
header=sys.stdin.readline().strip().split(options.sep)
fields=options.fields.split(',') if options.fields else header
print options.sep.join(fields)
line=sys.stdin.readline()
while line:
    record=dict(zip(header, line.strip().split(options.sep)))
    print options.sep.join([record[f] for f in fields])
    line=sys.stdin.readline()
